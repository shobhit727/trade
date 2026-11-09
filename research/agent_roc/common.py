"""Shared harness for the rate_of_change (ROC) NSE validation run.

Everything is built on the FULL panel and sliced afterwards — trailing indicators are
unaffected by slicing after the fact, while slice-then-compute injects artificial
dead time at the start of every window (a bug found in agent_cci's harness).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import ENGINE_SHA, PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

# Re-exported for the step scripts. Listed in __all__ so ruff keeps them.
__all__ = [
    "COST",
    "CFG",
    "ENGINE_SHA",
    "HEADER",
    "TEST_END",
    "TEST_START",
    "TRAIN_END",
    "TRAIN_START",
    "build_composite_score",
    "build_score",
    "buy_and_hold",
    "coin_book",
    "compute_metrics",
    "fmt_yearly",
    "load",
    "random_book",
    "roc_panel",
    "roc_signal",
    "row",
    "run_backtest",
    "yearly_returns",
]

#: The panel index is tz-aware (Asia/Kolkata), so every window bound must be too.
TZ = "Asia/Kolkata"
TRAIN_START = pd.Timestamp("2016-01-01", tz=TZ)
TRAIN_END = pd.Timestamp("2023-12-31", tz=TZ)
TEST_START = pd.Timestamp("2024-01-01", tz=TZ)
TEST_END = pd.Timestamp("2026-10-01", tz=TZ)

COST = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()


def load():
    from nsealgo.data.loader import load_universe

    panel, symbols, report = load_universe(str(ROOT / "data" / "nse"))
    return panel, symbols, report


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def roc_panel(close: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised twin of `cryptobot.strategies.indicators.roc`.

    roc(c, n) = (c[-1] - c[-n-1]) / c[-n-1]  ==  c / c.shift(n) - 1
    """
    return close / close.shift(period) - 1.0


def roc_signal(close: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """+1 where the ROC gate fires, 0 elsewhere (long-only adaptation).

    The catalog returns -1 for a negative ROC; that branch is not tradable in an
    Indian delivery account and becomes "not long", which is 0.
    """
    r = roc_panel(close, period)
    return (r > threshold).astype(float)


def build_score(close: pd.DataFrame, signal: pd.DataFrame, rank_by: str) -> pd.DataFrame:
    """Cross-sectional score, higher = more attractive.

    `mom126`  : brief §5 construction — trailing 6m return among the flagged names.
    `roc10`   : rank by the strategy's own raw ROC magnitude (no momentum overlay).
    """
    if rank_by == "mom126":
        base = close / close.shift(126) - 1.0
    elif rank_by == "roc10":
        base = roc_panel(close, 10)
    else:
        raise ValueError(f"unknown rank_by {rank_by!r}")
    score = base.where(signal > 0)
    return score.rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Comparators
# --------------------------------------------------------------------------- #


def buy_and_hold(close: pd.DataFrame) -> pd.Series:
    """Equal-weight buy-and-hold over the slice, net of ONE entry+exit round trip."""
    rets = close.pct_change(fill_method=None).fillna(0.0)
    eq = (1.0 + rets.mean(axis=1)).cumprod()
    from nsealgo.backtest.engine import REF_POSITION_NOTIONAL, _d

    rt = float(COST.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL))) / 10_000.0
    eq.iloc[0] *= 1.0 - rt  # entry, and the eventual exit, charged once
    return eq / eq.iloc[0]


def random_book(close: pd.DataFrame, seed: int, frac_long: float | None = None):
    """Null: random eligibility + the same ranking the strategy uses."""
    rng = np.random.default_rng(seed)
    r = roc_panel(close, 10)
    mask = rng.random(r.shape) < (frac_long if frac_long is not None else r.gt(0).mean())
    sc = build_score(close, mask.astype(float), "mom126")
    return run_backtest(close, sc, COST, CFG)


def coin_book(close: pd.DataFrame, seed: int, frac_long: float):
    """Null: purely random scores on a random eligible subset at a matched long fraction."""
    rng = np.random.default_rng(seed)
    elig = rng.random(close.shape) < frac_long
    sc = pd.DataFrame(
        np.where(elig, rng.random(close.shape), np.nan),
        index=close.index,
        columns=close.columns,
    )
    return run_backtest(close, sc, COST, CFG)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def row(label: str, m, extra: dict | None = None) -> str:
    parts = [
        f"| {label} | {m.cagr * 100:.2f}% | {m.sharpe:.2f} | {m.max_drawdown * 100:.2f}% "
        f"| {m.calmar:.2f} | {m.annual_turnover:.2f}x | {m.cost_drag_annual * 100:.2f}% "
        f"| {m.trades_per_year:.1f} |"
    ]
    if extra:
        parts.append(" " + " | ".join(f"{k}={v}" for k, v in extra.items()) + " |")
    return "".join(parts)


HEADER = (
    "| book | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Trades/y |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


def fmt_yearly(r: pd.Series) -> str:
    return ", ".join(f"{y} {v * 100:+.2f}%" for y, v in yearly_returns(r).items())
