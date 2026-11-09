"""Shared harness for the `absolute_momentum` NSE agent run.

Signal definition comes verbatim from the catalog strategy
`src/cryptobot/strategies/catalog/absolute_momentum.py`:

    m = roc(closes, period)
    return 1 if m > threshold else (-1 if m < -threshold else 0)

Shorting is unavailable in an Indian delivery account, so the `-1` branch maps to
"not held". The book is long-only and cross-sectional, so the signal is turned into
a cross-sectional score by ranking the *signalled* names by the same trailing
return that produced the signal (brief section 5).

No lookahead: `roc` on day t uses closes through t only, and `run_backtest` applies
weights decided at t from t+1 onward.
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


def _ts(t: pd.Timestamp, like: pd.DatetimeIndex) -> pd.Timestamp:
    """Align a window bound to the panel's timezone (the panel is tz-aware IST)."""
    return t.tz_localize(like.tz) if like.tz is not None and t.tz is None else t

DATA_DIR = "data/nse"
SLIPPAGE_BPS = 5
N_POSITIONS = 22


def cost_model(slippage_bps: int = SLIPPAGE_BPS) -> CostModel:
    return CostModel(segment="delivery", slippage_bps=Decimal(str(slippage_bps)))


def portfolio_config() -> PortfolioConfig:
    return PortfolioConfig(n_positions=N_POSITIONS)


def window(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    start = _ts(start, panel.index)
    end = _ts(end, panel.index)
    idx = panel.index
    lo = idx.searchsorted(start)
    hi = idx.searchsorted(end, side="right")
    return panel.iloc[lo:hi]


# --------------------------------------------------------------------------- #
# The strategy
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Variant:
    name: str
    period: int
    threshold: float


#: DECLARED PARAMETER BUDGET — 5 variants, fixed before any run.
#: Chosen to span the lookback from the catalog's crypto default (30d) to a full
#: trading year, plus one threshold variant to test whether a magnitude hurdle
#: (rather than a sign filter) reduces whipsaw churn.
VARIANTS: tuple[Variant, ...] = (
    Variant("V1_p30_t0.00", 30, 0.00),
    Variant("V2_p63_t0.00", 63, 0.00),
    Variant("V3_p126_t0.00", 126, 0.00),
    Variant("V4_p252_t0.00", 252, 0.00),
    Variant("V5_p126_t0.05", 126, 0.05),
)


def roc_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """`cryptobot.strategies.indicators.roc` == close/close.shift(period) - 1."""
    return panel / panel.shift(period) - 1.0


def signal_panel(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """+1 where ROC > threshold, NaN elsewhere (the -1 branch == not held)."""
    m = roc_panel(panel, period)
    return m.where(m > threshold)


def strategy_score(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """Cross-sectional percentile rank of trailing return, gated by the signal."""
    m = signal_panel(panel, period, threshold)
    return m.rank(axis=1, pct=True)


def liveness(panel: pd.DataFrame, period: int, threshold: float,
             start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    """How often the strategy wants to hold, and how many names it has to choose from."""
    sig = signal_panel(panel, period, threshold)
    sig = sig.loc[_ts(start, sig.index):_ts(end, sig.index)]
    n_flagged = sig.notna().sum(axis=1)
    return {
        "long_frac": float(sig.notna().to_numpy().mean()),
        "avg_flagged_names": float(n_flagged.mean()),
        "days_with_fewer_than_n_positions": float((n_flagged < N_POSITIONS).mean()),
    }


# --------------------------------------------------------------------------- #
# Benchmarks & controls
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, cost_model_: CostModel,
                 start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Equal-weight buy-and-hold over the window, net of the same cost stack.

    Mirrors `run_backtest`'s accounting exactly: cost is charged on the *compounding*
    normalised equity, and a full round trip (100% in at the start, 100% out at the
    end) is one-way turnover of 1.0 total.
    """
    px = window(panel, start, end)
    daily_gross = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(cost_model_.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0

    daily = pd.Series(0.0, index=px.index)
    eq, costs = 1.0, 0.0
    for i, dt in enumerate(px.index):
        prev = eq
        eq *= 1.0 + float(daily_gross.loc[dt])
        if i == 0 or i == len(px.index) - 1:
            cost = 0.5 * eq * rate  # 50% of book traded on each leg
            eq -= cost
            costs += cost
        daily.loc[dt] = eq / prev - 1.0
    equity = (1.0 + daily).cumprod()
    years = len(equity) / 244
    m = compute_metrics(
        daily, equity,
        annual_turnover=1.0 / years,
        cost_drag_annual=costs / years,
    )
    return {"returns": daily, "equity": equity, "metrics": m, "costs_paid": costs * 2_100_000}


def random_control_score(panel: pd.DataFrame, period: int, threshold: float,
                         seed: int) -> tuple[pd.DataFrame, float]:
    """Random names, random order, matched to the strategy's long fraction per day.

    This is the minimum bar from brief section 6.5: same number of names eligible on
    each day, but neither the trend filter nor the momentum ranking. The long
    fraction is copied from the real signal's own daily count so the two books face
    identical capacity limits.
    """
    sig = signal_panel(panel, period, threshold)
    n_flagged = sig.notna().sum(axis=1)
    rng = np.random.default_rng(seed)
    noise = pd.DataFrame(
        rng.random(sig.shape), index=sig.index, columns=sig.columns
    )
    # rank within a random subset of exactly the right size per day
    order = noise.rank(axis=1, ascending=False)
    keep = order.le(n_flagged, axis=0)
    score = (1.0 - noise).where(keep)
    long_frac = float(sig.notna().to_numpy().mean())
    return score, long_frac


def unfiltered_composite(panel: pd.DataFrame) -> pd.DataFrame:
    """nsealgo composite with the absolute-momentum gate removed (all names eligible).

    Isolates how much the *filter* contributes versus the cross-sectional ranking.
    """
    return build_composite_score(panel)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def row(label: str, r, extra: str = "") -> str:
    m = r.metrics if hasattr(r, "metrics") else r
    return (
        f"{label:<26} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x/y  Cost {m.cost_drag_annual * 100:>5.2f}%/y  "
        f"{extra}"
    )


def cost_drag_split(panel: pd.DataFrame, score: pd.DataFrame,
                    start: pd.Timestamp, end: pd.Timestamp) -> tuple:
    """Same book at zero cost vs base cost, over the window. Isolates viability."""
    px = window(panel, start, end)
    sc = score.reindex(px.index)
    cfg = portfolio_config()
    net = run_backtest(px, sc, cost_model(), cfg, rebalance="M")
    zero = CostModel(segment="delivery", slippage_bps=Decimal("0"))
    gross = run_backtest(px, sc, zero, cfg, rebalance="M")
    return net, gross


def load():
    return load_universe(DATA_DIR)


__all__ = [
    "Variant", "VARIANTS", "TRAIN_START", "TRAIN_END", "TEST_START", "TEST_END",
    "build_composite_score", "cost_drag_split", "cost_model", "load", "liveness",
    "portfolio_config", "random_control_score", "roc_panel", "row", "run_backtest",
    "signal_panel", "strategy_score", "unfiltered_composite", "window",
    "yearly_returns", "buy_and_hold", "_rebalance_dates",
]
