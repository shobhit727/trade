"""Shared harness for the `regime_switch` NSE agent run.

Signal definition comes verbatim from the catalog strategy
`src/cryptobot/strategies/catalog/regime_switch_strategy.py`:

    t = sma(closes, period)
    b = atr(highs, lows, closes, adx_p)      # <-- dead code, NaN guard only
    up = closes[-1] > t
    if up     and closes[-1] >  closes[-2]: return  1
    if not up and closes[-1] <  closes[-2]: return -1
    return 0

Two facts about the host engine that fix the translation:

* `cryptobot.strategies.signal_base.SignalStrategy.feed` treats `0` as **go flat**
  (it emits a reduce-only close), not as "hold". So the state is instantaneous, and
  the faithful NSE reading is: sample the state on the rebalance date; names that are
  not in state `+1` on that date are simply not held. The `-1` leg maps to cash.
* `atr(...)` never enters the decision -- it is only a NaN guard, and `adx_p` is
  therefore not a real parameter. The only live tunable is `period`.

No lookahead: the SMA on day *t* uses closes through *t*, and `run_backtest` applies
weights decided at *t* from *t+1* onward.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    _rebalance_dates,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN_START = pd.Timestamp("2016-01-01")
TRAIN_END = pd.Timestamp("2023-12-31")
TEST_START = pd.Timestamp("2024-01-01")
TEST_END = pd.Timestamp("2026-10-01")

DATA_DIR = "data/nse"
SLIPPAGE_BPS = 5
N_POSITIONS = 22
REF_NOTIONAL = Decimal("100000")


def _ts(t: pd.Timestamp, like: pd.DatetimeIndex) -> pd.Timestamp:
    """Align a window bound to the panel's timezone (the panel is tz-aware IST)."""
    return t.tz_localize(like.tz) if like.tz is not None and t.tz is None else t


def cost_model(slippage_bps: int = SLIPPAGE_BPS) -> CostModel:
    return CostModel(segment="delivery", slippage_bps=Decimal(str(slippage_bps)))


def portfolio_config() -> PortfolioConfig:
    return PortfolioConfig(n_positions=N_POSITIONS)


def window(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    start = _ts(start, panel.index)
    end = _ts(end, panel.index)
    idx = panel.index
    return panel.iloc[idx.searchsorted(start):idx.searchsorted(end, side="right")]


def load():
    return load_universe(DATA_DIR)


# --------------------------------------------------------------------------- #
# The strategy
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Variant:
    name: str
    period: int


#: DECLARED PARAMETER BUDGET -- 5 variants, fixed in REPORT.md section 2 before
#: any run. `adx_p` is dead code in the catalog strategy, so `period` is the only
#: live parameter and the whole budget goes to it.
VARIANTS: tuple[Variant, ...] = (
    Variant("V1_p20_catalog", 20),
    Variant("V2_p10_fast", 10),
    Variant("V3_p50_mid", 50),
    Variant("V4_p100_slow", 100),
    Variant("V5_p200_verySlow", 200),
)


def tradable_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Panel forward-filled **from the past only** (brief §4: never from the future).

    Audit: the panel's NaNs are 3,406 leading (names that listed after a window start,
    e.g. the Tata Motors demerger) against exactly **1 interior hole** in TEST and
    **0** in TRAIN. So this ffill is a "name has not started yet" fix, not a way to
    invent prices. The single interior hole becomes a stale-price bar where both
    `rising` and `falling` are False -> state 0 -> not held: the book never trades on
    a stale print.
    """
    return panel.ffill()


def sma_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """`cryptobot.strategies.indicators.sma` == rolling mean of the last `period` closes."""
    return tradable_panel(panel).rolling(period).mean()


#: Catalog default `adx_p`. It is *not* a signal input -- ATR never enters the
#: decision -- but it IS a warmup gate: `atr()` returns NaN while
#: `len(closes) < adx_p + 1`, and the `t != t or b != b` guard turns that into 0.
#: So the effective warmup is `max(period, ADX_P + 1)`. Found by verify_translation.py,
#: which showed the vector mislabelling bars SHORT for `period < 15` without this.
ADX_P = 14


def state_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """+1 / -1 / 0 exactly as the catalog strategy returns them.

    The NaN guard is load-bearing twice over:
      * it kills the SMA warmup region, where `~(NaN > NaN) & (price < prev)` would
        otherwise be True and mislabel every such bar SHORT;
      * `atr` extends that region to `max(period, ADX_P + 1)`.
    """
    px = tradable_panel(panel)
    warm = px.notna() & px.rolling(period).mean().notna()
    warm &= px.notna().cumsum() >= max(period, ADX_P + 1)
    up = px > px.rolling(period).mean()
    rising = px > px.shift(1)
    falling = px < px.shift(1)
    return pd.DataFrame(
        np.select(
            [warm & up & rising, warm & ~up & falling], [1.0, -1.0], default=0.0
        ),
        index=panel.index,
        columns=panel.columns,
    )


def long_flag(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """The investable set: names in state +1 on this bar."""
    return (state_panel(panel, period) > 0).astype(float).where(
        tradable_panel(panel).notna()
    )


def distance_above_sma(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """close / SMA - 1 -- the strategy's own quantity, used to rank its own picks."""
    px = tradable_panel(panel)
    return px / px.rolling(period).mean() - 1.0


def strategy_score(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Cross-sectional percentile rank of distance-above-SMA among flagged names.

    Deliberately NOT a 126d momentum rank: importing one would smuggle in the
    nsealgo composite's edge and make attribution meaningless.
    """
    d = distance_above_sma(panel, period)
    return d.where(long_flag(panel, period) > 0).rank(axis=1, pct=True)


def momentum_ranked_score(panel: pd.DataFrame, period: int, mom: int = 126):
    """Robustness ablation only: same gate, but ranked by 126d momentum."""
    m = panel / panel.shift(mom) - 1.0
    return m.where(long_flag(panel, period) > 0).rank(axis=1, pct=True)


def gate_only_score(panel: pd.DataFrame, period: int, seed: int) -> pd.DataFrame:
    """Ablation: same gate, random order among the flagged names."""
    flag = long_flag(panel, period)
    rng = np.random.default_rng(seed)
    noise = pd.DataFrame(rng.random(flag.shape), index=flag.index, columns=flag.columns)
    return noise.where(flag > 0)


def rank_only_score(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Ablation: same ranking, no gate at all (every name eligible)."""
    return distance_above_sma(panel, period).rank(axis=1, pct=True)


def liveness(panel: pd.DataFrame, period: int,
             start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    st = state_panel(panel, period).loc[
        _ts(start, panel.index):_ts(end, panel.index)
    ]
    n_long = (st > 0).sum(axis=1)
    n_short = (st < 0).sum(axis=1)
    return {
        "long_frac_cells": float((st > 0).to_numpy().mean()),
        "short_frac_cells": float((st < 0).to_numpy().mean()),
        "flat_frac_cells": float((st == 0).to_numpy().mean()),
        "avg_long_names": float(n_long.mean()),
        "avg_short_names": float(n_short.mean()),
        "days_below_n_positions": float((n_long < N_POSITIONS).mean()),
        "days_zero_long": float((n_long == 0).mean()),
    }


# --------------------------------------------------------------------------- #
# Benchmarks & controls
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, cm: CostModel,
                 start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Equal-weight buy-and-hold over the window, net of the same cost stack.

    Mirrors `run_backtest`'s accounting: cost is charged on the *compounding*
    normalised equity; a full round trip is one-way turnover of 1.0 total.
    """
    px = window(panel, start, end)
    daily_gross = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(cm.all_in_round_trip_bps(REF_NOTIONAL)) / 10_000.0

    daily = pd.Series(0.0, index=px.index)
    eq, costs = 1.0, 0.0
    for i, dt in enumerate(px.index):
        prev = eq
        eq *= 1.0 + float(daily_gross.loc[dt])
        if i == 0 or i == len(px.index) - 1:
            eq -= 0.5 * eq * rate
            costs += 0.5 * eq * rate
        daily.loc[dt] = eq / prev - 1.0
    equity = (1.0 + daily).cumprod()
    years = len(equity) / 244
    m = compute_metrics(
        daily, equity, annual_turnover=1.0 / years, cost_drag_annual=costs / years
    )
    return {"returns": daily, "equity": equity, "metrics": m,
            "costs_paid": costs * 2_100_000}


def random_control_score(panel: pd.DataFrame, period: int, seed: int) -> pd.DataFrame:
    """Random names, random order, matched day-by-day to the strategy's long count.

    The minimum bar from brief section 6.5: same number of names eligible each day,
    but neither the trend filter nor the ranking.
    """
    flag = long_flag(panel, period)
    n_flagged = flag.sum(axis=1)
    rng = np.random.default_rng(seed)
    noise = pd.DataFrame(rng.random(flag.shape), index=flag.index, columns=flag.columns)
    order = noise.rank(axis=1, ascending=False)
    keep = order.le(n_flagged, axis=0)
    return (1.0 - noise).where(keep)


def market_series(panel: pd.DataFrame) -> pd.Series:
    return panel.pct_change(fill_method=None).fillna(0.0).mean(axis=1)


def beta_alpha(returns: pd.Series, panel: pd.DataFrame,
               start: pd.Timestamp, end: pd.Timestamp) -> tuple[float, float, float]:
    """(beta, annualised alpha, correlation) vs the equal-weight market."""
    mkt = market_series(panel).loc[returns.index]
    j = pd.concat([returns.rename("r"), mkt.rename("m")], axis=1).dropna()
    if len(j) < 30:
        return float("nan"), float("nan"), float("nan")
    beta = float(j["r"].cov(j["m"]) / j["m"].var())
    corr = float(j["r"].corr(j["m"]))
    alpha = float((j["r"].mean() - beta * j["m"].mean()) * 244)
    return beta, alpha, corr


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def row(label: str, m, extra: str = "") -> str:
    return (
        f"{label:<28} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x/y  Cost {m.cost_drag_annual * 100:>5.2f}%/y"
        + (f"  {extra}" if extra else "")
    )


def cost_drag_split(panel, score, start, end):
    """Same book at zero cost vs base cost over the window. Isolates viability."""
    px = window(panel, start, end)
    sc = score.reindex(px.index)
    net = run_backtest(px, sc, cost_model(), portfolio_config(), rebalance="M")
    gross = run_backtest(
        px, sc, CostModel(segment="delivery", slippage_bps=Decimal("0")),
        portfolio_config(), rebalance="M",
    )
    return net, gross


__all__ = [
    "VARIANTS", "Variant", "TRAIN_START", "TRAIN_END", "TEST_START", "TEST_END",
    "beta_alpha", "build_composite_score", "buy_and_hold", "cost_drag_split",
    "cost_model", "distance_above_sma", "gate_only_score", "liveness", "load",
    "long_flag", "market_series", "momentum_ranked_score", "portfolio_config",
    "random_control_score", "rank_only_score", "row", "run_backtest",
    "sma_panel", "state_panel", "strategy_score", "window", "yearly_returns",
    "_rebalance_dates", "compute_metrics",
]
