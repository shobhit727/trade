"""Shared harness for the donchian_channel agent run.

Reuses nsealgo infrastructure only. Nothing in src/ is modified.

Two facts about the catalog strategy drive this module (see REPORT.md):

1. ``cryptobot.strategies.indicators.donchian_high(highs, p)`` returns
   ``max(highs[-p:])`` -- the window INCLUDES today. Since ``close <= high``
   always, ``close >= max(highs[-p:])`` can only hold when
   ``close == high_today == max(window)``: the close must sit exactly on the
   window high. The as-shipped signal is therefore near-dead, not merely rare.
2. It needs highs/lows, but ``load_universe`` only returns closes. So the OHLC
   panels are rebuilt with ``load_symbol`` (the same C1-C6 cleaning rules) and
   then *checked* against the ``load_universe`` close panel for exact equality.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import Metrics, compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import (  # noqa: E402
    CleaningReport,
    load_symbol,
    load_universe,
)
from nsealgo.factors.core import (  # noqa: E402
    build_composite_score,
    rank_cross_sectional,
)

#: Re-exported for the runner scripts. ``build_composite_score`` is not used
#: inside this module, so without an explicit __all__ a `ruff --fix` treats the
#: import as dead and strips it -- which silently breaks run_train/run_test.
__all__ = [
    "CONTROL_SEEDS",
    "TEST_END",
    "TEST_START",
    "TRAIN_END",
    "TRAIN_START",
    "ZeroCostModel",
    "backtest",
    "breakout_signal",
    "build_composite_score",
    "build_score",
    "cost_model",
    "equal_weight_bh",
    "liveness",
    "literal_signal",
    "load_all",
    "metrics_table",
    "portfolio_config",
    "random_signal_like",
    "slice_panel",
]

DATA_DIR = str(ROOT / "data" / "nse")

TRAIN_START = pd.Timestamp("2016-01-01")
TRAIN_END = pd.Timestamp("2023-12-31")
TEST_START = pd.Timestamp("2024-01-01")
TEST_END = pd.Timestamp("2026-10-01")

#: Ranking lookback. NOT tuned -- held fixed at the brief's recommended 126d
#: (6-month) momentum for every one of the five declared variants, so the whole
#: parameter budget is spent on the channel period (the strategy's own knob).
RANK_LB = 126


def cost_model() -> CostModel:
    return CostModel(segment="delivery", slippage_bps=5)


class ZeroCostModel:
    """Research-only stub: a *perfectly* frictionless cost model.

    ``run_backtest`` touches the cost model through exactly one method,
    ``all_in_round_trip_bps``. Returning 0 makes the equity curve gross. This
    exists only to answer brief §6.4 ("if gross is positive but net is negative,
    the strategy is unviable") -- the zero-cost number is NEVER reported as a
    result, only as the numerator of the gross/net decomposition. Note that
    ``nsealgo.costs.STRESS_MODELS["zero_cost"]`` is *not* zero cost: it zeroes
    slippage but leaves the ~1.9bps statutory round trip in place.
    """

    def all_in_round_trip_bps(self, notional) -> float:  # noqa: ARG002
        return 0.0


CONTROL_SEEDS = (0, 1, 2, 3, 4)


def portfolio_config() -> PortfolioConfig:
    return PortfolioConfig()  # 22 names, 12% / 25% / 10% cash, 35% turnover budget


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str], str]:
    """Return (close, high, low, symbols, cleaning_report) on one shared index."""
    panel, symbols, report = load_universe(DATA_DIR)

    highs: dict[str, pd.Series] = {}
    lows: dict[str, pd.Series] = {}
    closes: dict[str, pd.Series] = {}
    for sym in symbols:
        df = load_symbol(os.path.join(DATA_DIR, f"{sym}_1d.csv"), sym, CleaningReport())
        closes[sym] = df["close"].rename(sym)
        highs[sym] = df["high"].rename(sym)
        lows[sym] = df["low"].rename(sym)

    close = pd.DataFrame(closes).sort_index().dropna(how="all")
    high = pd.DataFrame(highs).reindex(index=close.index, columns=close.columns)
    low = pd.DataFrame(lows).reindex(index=close.index, columns=close.columns)

    # Audit: our rebuilt close panel must equal the mandated loader's panel exactly.
    assert close.equals(panel), "OHLC rebuild diverged from load_universe close panel"

    return panel, high, low, symbols, report.describe()


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def literal_signal(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                   period: int) -> pd.DataFrame:
    """The catalog signal EXACTLY as shipped: channel window includes today.

    Long fires only when close == high == max(high over window including today).
    Returns a panel of +1 (long) / -1 (short) / 0 (flat), no lookahead: today's
    own bar is used at today's close, and the engine only earns from t+1.
    """
    inc_high = high.rolling(period, min_periods=period).max()
    inc_low = low.rolling(period, min_periods=period).min()
    c = close
    sig = pd.DataFrame(0.0, index=c.index, columns=c.columns)
    sig = sig.mask(c >= inc_high, 1.0)
    sig = sig.mask(c <= inc_low, -1.0)
    sig[inc_high.isna()] = 0.0
    return sig


def breakout_signal(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                    period: int) -> pd.DataFrame:
    """Classic Donchian breakout: channel is the PRIOR ``period`` bars, today excluded.

    Long when today's close breaks above the highest high of the previous
    ``period`` sessions. This is the textbook definition the catalog code was
    reaching for; excluding today is the only change to the signal semantics
    and it is disclosed as such.
    """
    prior_high = high.rolling(period, min_periods=period).max().shift(1)
    prior_low = low.rolling(period, min_periods=period).min().shift(1)
    c = close
    sig = pd.DataFrame(0.0, index=c.index, columns=c.columns)
    sig = sig.mask(c > prior_high, 1.0)
    sig = sig.mask(c < prior_low, -1.0)
    sig[prior_high.isna()] = 0.0
    return sig


def build_score(signal: pd.DataFrame, panel: pd.DataFrame,
                rank_lb: int = RANK_LB) -> pd.DataFrame:
    """Cross-sectional score: rank trailing momentum among the flagged names only.

    Long-only: anything the signal does not flag becomes NaN, which the engine
    treats as uninvestable, so no short is ever expressible.
    """
    mom = panel / panel.shift(rank_lb) - 1.0
    masked = mom.where(signal > 0)
    return rank_cross_sectional(masked)


# --------------------------------------------------------------------------- #
# Controls / benchmarks
# --------------------------------------------------------------------------- #


def equal_weight_bh(
    panel: pd.DataFrame,
) -> tuple[pd.Series, Metrics, float]:
    """Buy-and-hold: equal-weight all names, net of one entry+exit round trip.

    The brief asks for buy-and-hold net of the *same* costs. A buy-and-hold book
    pays a single round trip, not the monthly turnover the strategy pays, so the
    cost is charged once on day 1. That is the *generous* reading for the
    benchmark -- it flatters buy-and-hold, which is the honest way to run a
    comparison that could go either way.
    """
    rets = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    cm = cost_model()
    from decimal import Decimal

    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    eq, costs = 1.0, 0.0
    out = pd.Series(0.0, index=panel.index)
    for i, dt in enumerate(panel.index):
        prev = eq
        if i == 0:
            eq *= 1.0 - rate
            costs += rate
        else:
            eq *= 1.0 + float(rets.loc[dt])
        out.loc[dt] = eq / prev - 1.0
    equity = (1.0 + out).cumprod()
    m = compute_metrics(out, equity)
    return out, m, costs


def random_signal_like(signal: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: random names, identical long-fraction per day."""
    rng = np.random.default_rng(seed)
    frac = (signal > 0).sum(axis=1) / signal.notna().sum(axis=1).clip(lower=1)
    n = signal.shape[1]
    draws = rng.random((len(signal), n))
    thresh = frac.to_numpy()[:, None]
    out = pd.DataFrame(
        np.where(draws < thresh, 1.0, 0.0), index=signal.index, columns=signal.columns
    )
    return out


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_COLS = ["label", "CAGR", "Sharpe", "MaxDD", "Calmar", "Turn", "Drag", "N"]

_HEAD = (
    f"  {'Label':<20}{'CAGR':>10}{'Sharpe':>9}{'MaxDD':>10}"
    f"{'Calmar':>8}{'Turn':>8}{'Drag':>8}{'N':>8}"
)


def metrics_table(rows: list[dict]) -> str:
    """rows: [{'label': str, 'metrics': Metrics, 'avg_names': float}, ...]"""
    out = [_HEAD, "  " + "-" * (len(_HEAD) - 2)]
    for r in rows:
        m: Metrics = r["metrics"]
        cells = (
            f"  {r['label']:<20}{m.cagr * 100:>9.2f}%{m.sharpe:>9.2f}"
            f"{m.max_drawdown * 100:>9.2f}%{m.calmar:>8.2f}"
            f"{m.annual_turnover:>7.2f}x{m.cost_drag_annual * 100:>7.2f}%"
            f"{r.get('avg_names', float('nan')):>8.1f}"
        )
        out.append(cells)
    return "\n".join(out)


def liveness(signal: pd.DataFrame, lo: str, hi: str) -> tuple[float, float, float]:
    """(frac long, frac short, frac flat) over [lo, hi] inclusive."""
    s = signal.loc[lo:hi]
    valid = s.notna().sum(axis=1).clip(lower=1)
    return (
        float((s > 0).sum(axis=1).div(valid).mean()),
        float((s < 0).sum(axis=1).div(valid).mean()),
        float((s == 0).sum(axis=1).div(valid).mean()),
    )


def backtest(panel: pd.DataFrame, score: pd.DataFrame, rebalance: str = "M",
             gross: bool = False):
    cm = ZeroCostModel() if gross else cost_model()
    return run_backtest(panel, score, cm, portfolio_config(), rebalance=rebalance)


def slice_panel(panel: pd.DataFrame, lo: str, hi: str) -> pd.DataFrame:
    return panel.loc[lo:hi]
