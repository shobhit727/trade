"""Shared harness for the `volatility_scaling` NSE validation.

What the source strategy actually does
--------------------------------------
`cryptobot.strategies.catalog.volatility_scaling.VolScalingStrategy.signal` returns

    +1  if ATR(period)/close > min_vol  AND  close[t] > close[t-1]
    -1  if ATR(period)/close > min_vol  AND  close[t] < close[t-1]
     0  otherwise

with `period=14`, `min_vol=0.001` by default. So it is a **high-volatility gate** plus a
**1-bar direction test** -- a volatility filter, not a volatility scaler. `verify_source_signal`
asserts this mechanically against the real class on synthetic bars.

Construction into the NSE book
-----------------------------
Long-only: `-1` and `0` both become "not held". The engine needs a ranking, so a
cross-sectional ranking is chosen per variant (see VARIANTS in the report).

No lookahead: every input to the score on day t uses data up to and including t.
`run_backtest` shifts held weights by one bar internally.

NATR is built with a rolling mean of true ranges, which matches
`cryptobot.strategies.indicators.atr` exactly: that helper is `np.mean(trs)` over the
last `period` true ranges, i.e. an SMA, **not** Wilder's smoothing.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import ENGINE_SHA, PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402

#: Repo root, so the scripts work from their own directory as well as the root.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

DATA_DIR = os.path.join(_ROOT, "data", "nse")

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

REF_NOTIONAL = Decimal("100000")
COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
#: What `run_backtest` actually charges per unit of total turnover.
RT_BPS = float(COST_MODEL.all_in_round_trip_bps(REF_NOTIONAL))

PORTFOLIO = PortfolioConfig()

#: Warmup for every factor we build, in bars. 200d trend needs the longest.
#: Must carry the same UTC offset as the panel index or pandas refuses the slice.
WARMUP = pd.Timestamp("2015-01-01", tz="Asia/Kolkata")

_panel: pd.DataFrame | None = None
_symbols: list[str] | None = None
_hl: tuple[pd.DataFrame, pd.DataFrame] | None = None


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def get_panel():
    global _panel, _symbols
    if _panel is None:
        _panel, _symbols, _rep = load_universe(DATA_DIR)
    return _panel, _symbols


def get_hl():
    """High and low panels aligned to the close panel.

    `load_universe` returns closes only, but the ATR needs H/L, so each symbol's own
    file is re-read through the same cleaning path and then reindexed onto the panel's
    index. The panel drops a handful of stray vendor rows (C8), so this reindex is
    what keeps the H/L and close calendars identical -- a silent mismatch here would
    shift every true range by one bar.
    """
    global _hl
    if _hl is None:
        panel, symbols = get_panel()
        hi, lo = [], []
        for s in symbols:
            df = load_symbol(os.path.join(DATA_DIR, f"{s}_1d.csv"), s, None)
            hi.append(df["high"].rename(s))
            lo.append(df["low"].rename(s))
        H = pd.concat(hi, axis=1).reindex(panel.index)
        L = pd.concat(lo, axis=1).reindex(panel.index)
        _hl = (H, L)
    return _hl


def true_range() -> pd.DataFrame:
    """True range per (date, symbol).

    The three candidate ranges are stacked to long form before `max(axis=1)` on
    purpose. Concatting them as three wide frames and reducing with `max(axis=1)`
    silently collapses on the duplicated symbol labels and returns a Series indexed
    by *date* -- which then broadcasts into a nonsense-shaped frame instead of
    raising. Stacking first gives each row a unique (date, symbol) key, so the
    reduction is well defined.
    """
    panel, _ = get_panel()
    H, L = get_hl()
    prev = panel.shift(1)
    tr = pd.concat(
        [
            (H - L).stack(future_stack=True),
            (H - prev).abs().stack(future_stack=True),
            (L - prev).abs().stack(future_stack=True),
        ],
        axis=1,
    ).max(axis=1).unstack()
    return tr.reindex(index=panel.index, columns=panel.columns)


def natr(period: int = 14) -> pd.DataFrame:
    """ATR(period)/close -- an SMA of trailing true ranges, matching `atr()`."""
    panel, _ = get_panel()
    return true_range().rolling(period, min_periods=period).mean() / panel


def vol_score(window: int = 60) -> pd.DataFrame:
    panel, _ = get_panel()
    v = panel.pct_change(fill_method=None).rolling(window, min_periods=40).std()
    return -v  # higher = lower vol = more attractive


def mom_score(window: int = 126) -> pd.DataFrame:
    panel, _ = get_panel()
    return panel / panel.shift(window) - 1.0


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def flag_panel(
    min_vol: float,
    period: int = 14,
    use_direction: bool = True,
) -> pd.DataFrame:
    """The strategy's own +1/0 flag, vectorised. Long-only: -1 collapses to 0."""
    panel, _ = get_panel()
    gate = natr(period) > min_vol
    if not use_direction:
        return gate.astype(float)
    up = panel > panel.shift(1)
    return (gate & up).astype(float)


def build_score(
    min_vol: float,
    ranking: str,
    period: int = 14,
    use_direction: bool = True,
) -> pd.DataFrame:
    """Cross-sectional score: rank the flagged names, everything else NaN."""
    flag = flag_panel(min_vol, period, use_direction)
    if ranking == "mom126":
        base = mom_score(126)
    elif ranking == "lowvol":
        base = vol_score(60)
    elif ranking == "natr":  # rank by the gate's own quantity: voltilest first
        base = natr(period)
    else:
        raise ValueError(f"unknown ranking {ranking!r}")
    return base.where(flag > 0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Verification against the real source class
# --------------------------------------------------------------------------- #


def verify_source_signal(
    n_bars: int = 300, period: int = 14, min_vol: float = 0.001, seed: int = 7
) -> tuple[int, int]:
    """Run the real `VolScalingStrategy` on synthetic bars; compare to the vector.

    This is the check that the vectorised flag is the same function as the shipped
    class. Returns (matches, total).
    """
    from cryptobot.strategies.catalog.volatility_scaling import (
        VolScalingConfig,
        VolScalingStrategy,
    )

    rng = np.random.default_rng(seed)
    strat = VolScalingStrategy(
        VolScalingConfig(period=period, min_vol=min_vol, quantity=Decimal("1"))
    )
    n = 40
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n_bars)))
    highs = closes * (1 + rng.uniform(0.0, 0.03, n_bars))
    lows = closes * (1 - rng.uniform(0.0, 0.03, n_bars))
    vols = rng.uniform(1e5, 1e6, n_bars)

    # Vectorised reference on the same synthetic bars.
    c = pd.Series(closes)
    h = pd.Series(highs)
    lo = pd.Series(lows)
    tr = pd.concat([(h - lo), (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1)
    vatr = tr.max(axis=1).rolling(period, min_periods=period).mean()
    vnatr = vatr / c
    ref = pd.Series(0.0, index=c.index)
    ok = (vnatr > min_vol).fillna(False)
    ref[ok & (c > c.shift(1))] = 1.0
    ref[ok & (c < c.shift(1))] = -1.0

    matches = 0
    total = 0
    for i in range(n, n_bars):
        got = strat.signal(closes[: i + 1], highs[: i + 1], lows[: i + 1], vols[: i + 1])
        want = ref.iloc[i]
        total += 1
        if got == want:
            matches += 1
    return matches, total


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #


@dataclass
class Run:
    label: str
    set_name: str
    cagr: float
    sharpe: float
    maxdd: float
    calmar: float
    turnover: float
    cost_drag: float
    avg_names: float
    total: float
    pct_years_pos: float
    engine_sha: str
    diag: dict
    returns: pd.Series
    equity: pd.Series

    def line(self) -> str:
        return (
            f"{self.label:<24}{self.set_name:<7}{self.cagr * 100:7.2f}"
            f"{self.sharpe:8.2f}{self.maxdd * 100:9.2f}{self.calmar:8.2f}"
            f"{self.turnover:8.2f}{self.cost_drag * 100:9.2f}"
            f"{self.avg_names:7.1f}{self.total * 100:9.1f}{self.pct_years_pos * 100:6.0f}%"
        )


HEADER = (
    f"{'label':<24}{'set':<7}{'CAGR%':>7}{'Sharpe':>8}{'MaxDD%':>9}"
    f"{'Calmar':>8}{'Turn/y':>8}{'Cost/y%':>9}{'Names':>7}{'Total%':>9}{'Yr+':>6}"
)


def to_run(label: str, set_name: str, m, diag: dict, returns, equity) -> Run:
    return Run(
        label=label,
        set_name=set_name,
        cagr=m.cagr,
        sharpe=m.sharpe,
        maxdd=m.max_drawdown,
        calmar=m.calmar,
        turnover=m.annual_turnover,
        cost_drag=m.cost_drag_annual,
        avg_names=diag.get("avg_names", float("nan")),
        total=m.total_return,
        pct_years_pos=float((yearly_returns(returns) > 0).mean()),
        engine_sha=diag.get("engine_sha", ""),
        diag=diag,
        returns=returns,
        equity=equity,
    )


def run_on(
    label: str,
    set_name: str,
    score: pd.DataFrame,
    start,
    end,
    config: PortfolioConfig | None = None,
    cost_model: CostModel | None = None,
    cost_detail: bool = True,
) -> Run:
    """Evaluate over [start, end], but *build* the book over [WARMUP, end].

    Two separate windows, deliberately:

    * The engine must see warmup bars, or the first ~200 bars have no 126d momentum
      and the book is effectively empty while it warms up. Slicing the panel to
      [start, end] before the run (which is what the prior agent's harness did)
      throws that away and measures a book that starts part-cash for no reason.
    * The metrics must be computed over [start, end] only. Annualising a curve that
      begins at WARMUP reports a CAGR for the whole warmup+eval span, so a "TEST"
      number would silently include 2015-2023 in-sample data. The drawdown is the
      give-away: slicing only at the end makes TRAIN and TEST MaxDD identical,
      because the deepest trough lies before TEST and is still inside the curve.

    Costs and turnover are re-derived on the same basis by differencing a second run
    that stops just before `start`, so they describe the eval window and not the
    build window.
    """
    cfg = config or PORTFOLIO
    cm = cost_model or COST_MODEL
    panel, _ = get_panel()
    px = panel.loc[WARMUP:end]
    sc = score.loc[WARMUP:end]
    res = run_backtest(px, sc, cm, config=cfg, rebalance="M")

    # Per-date turnover reconstructed from held weights. `held` is the target frame
    # forward-filled, so its changes land exactly on rebalance dates and equal the
    # engine's `sum|dW| / 2`. Validated against the engine's own annual figure below.
    held = res.weights
    turn = held.diff().abs().sum(axis=1) / 2.0
    turn.iloc[0] = float(held.iloc[0].abs().sum()) / 2.0
    span_turn = float(turn.sum())
    span_years = len(res.returns) / 244
    engine_turn = res.metrics.annual_turnover
    recon_ok = abs(span_turn / span_years - engine_turn) < 1e-6

    # Eval-window slice.
    r_win = res.returns.loc[start:end]
    eq_win = (1.0 + r_win).cumprod()
    years = max(len(r_win) / 244, 1e-9)

    # Costs inside the window: differencing against a run that stops before `start`.
    prior_end = start - pd.Timedelta(days=1)
    costs_in_window = 0.0
    if cost_detail and prior_end > WARMUP:
        prior = run_backtest(
            panel.loc[WARMUP:prior_end], sc.loc[WARMUP:prior_end], cm,
            config=cfg, rebalance="M",
        )
        costs_in_window = float(res.costs_paid - prior.costs_paid)

    m = compute_metrics(
        r_win,
        eq_win,
        annual_turnover=float(turn.loc[start:end].sum()) / years,
        cost_drag_annual=costs_in_window / 21_000_000.0 / years,
        trades_per_year=float(turn.loc[start:end].gt(0).sum()) / years,
    )

    diag = dict(res.diag)
    diag["engine_sha"] = res.engine_sha
    diag["turnover_reconciles_with_engine"] = recon_ok
    diag["engine_annual_turnover_full_span"] = engine_turn
    diag["recon_annual_turnover_full_span"] = span_turn / span_years
    return to_run(label, set_name, m, diag, r_win, eq_win)


# --------------------------------------------------------------------------- #
# Buy and hold
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, start, end, cash: float = 0.0) -> dict:
    """True buy-and-hold equal-weight basket over [start, end].

    Equal weight at the first bar, shares then held (weights drift). One round trip
    charged at entry against compounding equity, exactly as the engine does. No
    rebalancing, hence no rebalance drag -- the strongest form of the benchmark.
    """
    px = panel.loc[start:end]
    rets = px.pct_change(fill_method=None).fillna(0.0)
    w = pd.Series(0.0, index=px.columns)
    w[px.columns] = (1.0 - cash) / len(px.columns)
    gross = w * rets
    rate = RT_BPS / 10_000.0
    eq, daily = 1.0, []
    for dt in px.index:
        eq *= 1.0 + float(gross.loc[dt].sum())
        daily.append(eq)
    turn = float(w.sum())
    eq -= turn * eq * rate
    costs = turn * eq * rate
    daily[-1] = eq
    daily = pd.Series(daily, index=px.index)
    m = compute_metrics(daily.pct_change(fill_method=None).fillna(0.0), daily)
    return dict(
        metrics=m,
        equity=daily,
        annual_turnover=turn / max(len(px) / 244, 1e-9),
        cost_drag=costs / max(len(px) / 244, 1e-9),
    )


def bh_row(label: str, set_name: str, start, end) -> Run:
    panel, _ = get_panel()
    b = buy_and_hold(panel, start, end)
    rets = b["equity"].pct_change(fill_method=None).fillna(0.0)
    n = panel.loc[start:end].notna().sum(axis=1).mean()
    diag = {
        "avg_names": float(n),
        "engine_sha": ENGINE_SHA,
    }
    r = to_run(label, set_name, b["metrics"], diag, rets, b["equity"])
    r.turnover = b["annual_turnover"]
    r.cost_drag = b["cost_drag"]
    return r


def print_table(rows: list[Run]) -> None:
    print(HEADER)
    for r in rows:
        print(r.line())
