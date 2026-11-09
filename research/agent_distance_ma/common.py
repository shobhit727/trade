"""Shared harness for the `distance_moving_average` agent study.

Everything the brief mandates is imported from `nsealgo` — no reimplementation of
costs, portfolio construction or metrics. This module only does three things:

1. load the cleaned daily panel once,
2. build the strategy's cross-sectional score from a *point-in-time* deviation panel,
3. run the standard backtest plus the controls the brief requires.

No look-ahead: every factor on row *t* uses closes up to and including *t*, and
`run_backtest` holds the weights decided on *t* from *t+1* onward.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    build_rebalance_weights,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import STRESS_MODELS, CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

# --------------------------------------------------------------------------- #
# Non-negotiable split (brief §4)
# --------------------------------------------------------------------------- #
TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

COST = CostModel(segment="delivery", slippage_bps=5)

#: `PortfolioConfig` defaults (`GOAL.md` §3.2) — used unmodified everywhere.
PORTFOLIO = PortfolioConfig()


def load_panel() -> tuple[pd.DataFrame, list[str], object]:
    from nsealgo.data.loader import load_universe

    panel, symbols, report = load_universe(str(ROOT / "data" / "nse"))
    return panel, symbols, report


# --------------------------------------------------------------------------- #
# Strategy -> cross-sectional score
# --------------------------------------------------------------------------- #


def deviation_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """dev = (close - SMA_period(close)) / SMA_period(close).

    Vectorised equivalent of `DistanceMaStrategy.signal`; the rolling mean uses only
    trailing bars, so no row can see the future.
    """
    ma = panel.rolling(period, min_periods=period).mean()
    return (panel - ma) / ma


def score_dev_depth(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """Construction A — buy the *deepest* mean-reversion candidates.

    `DistanceMaStrategy` returns +1 when dev < -threshold (price far below its MA).
    Only the long leg is tradable in an Indian delivery account, so the short leg
    (dev > +threshold) is discarded rather than inverted.

    Among the signalled names, score = how far below the MA the name sits, so the
    book buys the most stretched names. Non-signalled names get NaN and are never
    eligible.
    """
    dev = deviation_panel(panel, period)
    long_leg = dev < -abs(threshold)
    score = (-dev).where(long_leg)
    return score.replace([np.inf, -np.inf], np.nan)


def score_momentum_ranked(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """Construction B — the brief's recommended pattern.

    Gate on the strategy's own long signal, then rank the survivors by 126-day
    trailing momentum (percentile, higher = better) rather than by deviation depth.
    """
    dev = deviation_panel(panel, period)
    long_leg = dev < -abs(threshold)
    mom = (panel / panel.shift(126) - 1.0).where(long_leg)
    return mom.rank(axis=1, pct=True, na_option="keep").where(long_leg)


BUILDERS = {
    "dev_depth": score_dev_depth,
    "mom_ranked": score_momentum_ranked,
}


# --------------------------------------------------------------------------- #
# Controls
# --------------------------------------------------------------------------- #


def buy_and_hold_result(
    panel: pd.DataFrame, cols: list[str] | None = None, label: str | None = None
) -> dict:
    """Equal-weight buy-and-hold, net of the same delivery stack.

    The brief specifies ``panel.pct_change().mean(axis=1)`` — the cross-sectional mean
    daily return — as the benchmark. Held as a fixed equal-weight book with the same
    10% cash buffer `PortfolioConfig` mandates, entered once and exited once, so the
    only costs are the two halves of one round trip. The strategy books churn ~2-4x
    per year and pay ~1%/yr in drag; buy-and-hold pays two halves of one round trip
    and nothing after. That is the correct, favourable comparison for the benchmark.
    """
    from decimal import Decimal

    px = panel[cols] if cols is not None else panel
    k = len(px.columns)
    rets = px.pct_change(fill_method=None).mean(axis=1).fillna(0.0)

    # `rets` is already the cross-sectional MEAN, i.e. an equal-weight book return.
    # Scale once, by the deployed fraction only -- not by 1/k.
    deployed = 1.0 - PORTFOLIO.cash_buffer
    rt = COST.all_in_round_trip_bps(Decimal("100000"))
    half = float(rt) / 2 / 10_000.0
    entry = deployed * half  # cost is charged on deployed notional, both legs

    daily = rets * deployed
    daily.iloc[0] -= entry
    daily.iloc[-1] -= entry
    equity = (1.0 + daily).cumprod()

    m = compute_metrics(daily, equity)
    return {
        "name": label or f"buy_and_hold({k} EW)",
        "metrics": m,
        "yearly": yearly_returns(daily),
        "daily": daily,
        "equity": equity,
    }


def random_signal_result(
    panel: pd.DataFrame, liveness: float, seeds: tuple[int, ...] = (1, 2, 3)
) -> dict:
    """Negative control: a coin flip long the same fraction of name-days.

    `liveness` is the real strategy's fraction of name-days long. Each control flips
    that fraction of names independently every bar. Structure, cost model, rebalance
    frequency and portfolio constraints are identical, so the only difference between
    the strategy and this control is the information in the signal.
    """
    out = {}
    for s in seeds:
        rng = np.random.default_rng(s)
        shape = panel.shape
        score = pd.DataFrame(rng.random(shape), index=panel.index, columns=panel.columns)
        score = score.where(rng.random(shape) < liveness)
        r = run_backtest(panel, score, COST, PORTFOLIO, rebalance="M")
        out[s] = r
    return out


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #

ROW = [
    ("CAGR", "cagr", "pct"),
    ("Sharpe", "sharpe", "raw"),
    ("MaxDD", "max_drawdown", "pct"),
    ("Calmar", "calmar", "raw"),
    ("Turnover/y", "annual_turnover", "raw"),
    ("CostDrag/y", "cost_drag_annual", "pct"),
    ("Trades/y", "trades_per_year", "raw"),
]


def fmt_metrics(m) -> str:
    return m.fmt().replace("\n", "  |  ")


def table(rows: list[tuple[str, object]]) -> str:
    """rows = [(label, Metrics)] -> aligned metric table."""
    head = f"{'variant':<34}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Calmar':>8}{'Turn/y':>8}{'Drag/y':>8}{'Trd/y':>7}"
    out = [head, "-" * len(head)]
    for label, m in rows:
        out.append(
            f"{label:<34}{m.cagr * 100:>8.2f}%{m.sharpe:>8.2f}"
            f"{m.max_drawdown * 100:>8.2f}%{m.calmar:>8.2f}"
            f"{m.annual_turnover:>8.2f}{m.cost_drag_annual * 100:>7.2f}%"
            f"{m.trades_per_year:>7.1f}"
        )
    return "\n".join(out)


__all__ = [
    "PORTFOLIO",
    "COST",
    "STRESS_MODELS",
    "PortfolioConfig",
    "TRAIN_START",
    "TRAIN_END",
    "TEST_START",
    "TEST_END",
    "load_panel",
    "deviation_panel",
    "BUILDERS",
    "buy_and_hold_result",
    "random_signal_result",
    "run_backtest",
    "compute_metrics",
    "yearly_returns",
    "build_rebalance_weights",
    "build_composite_score",
    "table",
]
