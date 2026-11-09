"""Shared harness for the cointegration-strategy agent run.

Faithful port of ``cryptobot.strategies.catalog.cointegration_strategy``:

    z_t = (close_t - mean(W)) / std(W)          # trailing window W, population std
    +1 (long) when z < -entry,  -1 (short) when z > +entry,  0 otherwise

Judgement calls, recorded once here so every variant uses them identically:

* **Window is explicit.** The catalog computes ``zscore(closes)`` over its whole
  ``maxlen=300`` rolling buffer and uses ``config.period`` only for warmup, so the
  configured ``period`` never actually windows the statistic. That is a latent bug.
  For a cross-sectional NSE book the lookback *is* the parameter, so this port takes
  it explicitly (``W``) and reproduces the catalog's z-score formula exactly
  (mean and **population** std, i.e. ``ddof=0``, matching ``indicators.zscore``).
* **Long leg only.** The catalog shorts the over-extended side. An Indian delivery
  account cannot, so the short leg is dropped. The signal is unchanged for the long
  side: oversold -> buy.
* **Cross-sectional score.** The book is long-only cross-sectional, so a +1/0/-1
  time-series flag becomes "eligible universe". Score construction is a declared
  variant dimension, not an afterthought.
* **No lookahead.** ``z`` on date *t* uses closes up to and including *t* only. The
  engine holds weights from *t+1* onward, so there is exactly one bar of lag.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import Metrics, compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

DATA_DIR = "data/nse"

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

BASE_COSTS = CostModel(segment="delivery", slippage_bps=5)
PF_CFG = PortfolioConfig(n_positions=22)


class DoubledCosts(CostModel):
    """Research-side cost correction. ``src/nsealgo`` is NOT modified.

    ``run_backtest`` charges ``one_way_turnover * all_in_round_trip_bps``
    (engine.py:432), but ``all_in_round_trip_bps`` is defined in bps of **total**
    turnover (costs.py:198-201) while the engine's turnover is **one-way**
    (engine.py:415-419). The two cancel to a factor of 2: the engine bills
    10.96 bps of total turnover instead of 21.92. See REPORT.md Bug-3, proved in
    ``bug3_engine_trace.py``.

    Returning ``2x`` from this method makes the engine's charge land on the
    *intended* 21.92 bps of total turnover, so a corrected run is net of the full
    Indian delivery stack.
    """

    def all_in_round_trip_bps(self, notional):  # type: ignore[override]
        return super().all_in_round_trip_bps(notional) * 2


CORRECTED_COSTS = DoubledCosts(segment="delivery", slippage_bps=5)

_PANEL: pd.DataFrame | None = None


def panel() -> pd.DataFrame:
    """Cached cleaned daily close panel."""
    global _PANEL
    if _PANEL is None:
        p, _syms, _rep = load_universe(DATA_DIR)
        _PANEL = p
    return _PANEL


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def zscore_panel(px: pd.DataFrame, window: int) -> pd.DataFrame:
    """Trailing z-score of price vs its own trailing mean. Population std (ddof=0).

    Mirrors ``cryptobot.strategies.indicators.zscore``: mean and std over the whole
    supplied window, last value standardised.
    """
    mu = px.rolling(window, min_periods=window).mean()
    sd = px.rolling(window, min_periods=window).std(ddof=0)
    return (px - mu) / sd.replace(0.0, np.nan)


def cointegration_signal(px: pd.DataFrame, window: int, entry: float) -> pd.DataFrame:
    """Long-side flag: +1 where price is more than ``entry`` sigma below the mean."""
    z = zscore_panel(px, window)
    return (z < -float(entry)).astype(float)


def build_score(
    px: pd.DataFrame,
    window: int,
    entry: float,
    rule: str = "depth",
    momentum_lb: int = 126,
    history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cross-sectional score panel from the cointegration flag.

    ``rule="depth"``
        Deeper oversold ranks higher (the signal's own conviction). NaN off-signal.
    ``rule="momentum"``
        Brief's suggested construction: among flagged names, rank by trailing
        momentum. ``NaN`` off-signal.

    ``history`` is the panel the indicator is warmed up on, when the scored window is
    a *slice* of it. Every z-score on day *t* inside the slice still sees only data up
    to *t* — ``rolling`` is backward-looking — so this adds no lookahead; it only
    stops the window from starting blind for ``window`` bars. Omit it and the slice
    is scored from scratch, which silently deletes the first ~6 months of any window.
    """
    src = px if history is None else history
    z = zscore_panel(src, window).loc[px.index]
    flag = z < -float(entry)
    score = pd.DataFrame(np.nan, index=px.index, columns=px.columns, dtype=float)
    if rule == "depth":
        score = score.mask(flag, -z)
    elif rule == "momentum":
        mom = (src / src.shift(momentum_lb) - 1.0).loc[px.index]
        score = score.mask(flag, mom)
    else:
        raise ValueError(f"unknown rule {rule!r}")
    return score


def build_score_window(
    window: tuple[pd.Timestamp, pd.Timestamp],
    lookback: int,
    entry: float,
    rule: str = "depth",
    momentum_lb: int = 126,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(panel, score)`` restricted to ``window``, indicators warmed up on history.

    The window must be scored with the ``need`` bars that precede it, otherwise the
    first ``window`` scored bars are blind and silently deleted. Those warm-up bars
    are all dated at or before the first scored bar, so nothing after the window
    opens can influence its opening decisions.

    Implementation note: the warm-up bars are **concatenated onto the window** rather
    than scored separately, because the rolling z-score at the first scored bar needs
    the preceding bars present in the same frame. ``zscore_panel`` is strictly
    backward-looking, so this introduces no lookahead (``audit_lookahead.py`` proves
    it).
    """
    full = panel()
    lo, hi = window
    px = full.loc[(full.index >= lo) & (full.index <= hi)]
    if px.empty:
        raise ValueError(f"empty window {lo} .. {hi}")
    need = max(lookback, momentum_lb) + 2
    first = px.index[0]
    warm = full.loc[:first][-(need + 1):]
    warm = warm.loc[warm.index < first]
    src = pd.concat([warm, px])
    return px, build_score(px, lookback, entry, rule, momentum_lb, history=src)


# --------------------------------------------------------------------------- #
# Controls
# --------------------------------------------------------------------------- #


def random_score_like(score: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Random signal with the same % of (date, symbol) cells live as ``score``.

    Uniform over the same support: this is the minimum bar — beating a coin flip.
    Live cells get a uniform draw in [0, 1); everything else stays NaN.
    """
    rng = np.random.default_rng(seed)
    live = score.notna()
    vals = pd.DataFrame(
        rng.random(score.shape), index=score.index, columns=score.columns
    )
    out = vals.where(live)
    assert out.notna().to_numpy().mean() == live.to_numpy().mean()
    return out


def buy_and_hold(px: pd.DataFrame, cost_model: CostModel = BASE_COSTS) -> Metrics:
    """Equal-weight buy-and-hold over the given panel, net of the same costs.

    Uses the **stock** ``CostModel`` deliberately, not ``DoubledCosts``: each of the
    two legs is itself a complete one-way rotation of the book, so each carries total
    turnover of 1x the book and each is charged ``all_in_round_trip_bps`` (21.92 bps).
    Together that is 43.84 bps of book value for one round trip — which is exactly
    what ``run_backtest`` charges for a complete rotation once ``DoubledCosts``
    corrects the engine's one-way/total mismatch (Bug-3). The two bases agree.

    Checked: 1 round trip = 2 x book traded, x 21.92 bps = 43.84 bps of book.
    Engine with DoubledCosts = one_way 1.0 x 43.84 bps = 43.84 bps of book. Match.
    """
    from nsealgo.backtest.engine import REF_POSITION_NOTIONAL, _d

    rets = px.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rets = rets.iloc[1:]
    rate = float(cost_model.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL))) / 10_000.0

    daily = rets.copy()
    daily.iloc[0] = daily.iloc[0] - rate  # build the book (total turnover 1x)
    daily.iloc[-1] = daily.iloc[-1] - rate  # liquidate at the end (total turnover 1x)

    equity = (1.0 + daily).cumprod()
    years = max(len(equity) / 244, 1e-9)
    return compute_metrics(
        daily,
        equity,
        annual_turnover=2.0 / years,
        cost_drag_annual=2.0 * rate / years,
    )


# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Run:
    label: str
    metrics: Metrics
    diag: dict
    liveness: float
    equity: pd.Series
    returns: pd.Series
    costs_paid: float = 0.0


def evaluate(
    label: str,
    px: pd.DataFrame,
    score: pd.DataFrame,
    rebalance: str = "M",
    cost_model: CostModel = CORRECTED_COSTS,
    config: PortfolioConfig = PF_CFG,
) -> Run:
    """Run the engine on one window and package the diagnostics the brief demands."""
    live = float(score.notna().to_numpy().mean())
    res = run_backtest(px, score, cost_model, config, rebalance=rebalance)
    diag = dict(res.diag)
    # Gross exposure matters: a thin signal leaves the book in cash, so raw CAGR is
    # not comparable with a fully-invested composite.
    diag["avg_exposure"] = float(res.weights.sum(axis=1).mean())
    return Run(
        label=label,
        metrics=res.metrics,
        diag=diag,
        liveness=live,
        equity=res.equity,
        returns=res.returns,
        costs_paid=res.costs_paid,
    )


def fmt(m: Metrics) -> str:
    return (
        f"CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x/y  Drag {m.cost_drag_annual * 100:>5.2f}%/y  "
        f"Ret {m.total_return * 100:>8.1f}%"
    )


def composite_score(px: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(px)
