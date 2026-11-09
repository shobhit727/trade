"""Shared harness for the `time_series` NSE validation.

Everything the agent needs, in one place so the variant runs stay comparable.
No file under src/ is modified.
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
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

#: The panel index is tz-aware `Asia/Kolkata`; naive bounds fail to compare
#: under pandas 3.x. Localize here once so every caller just passes these.
_TZ = "Asia/Kolkata"
TRAIN_START = pd.Timestamp("2016-01-01", tz=_TZ)
TRAIN_END = pd.Timestamp("2023-12-31", tz=_TZ)
TEST_START = pd.Timestamp("2024-01-01", tz=_TZ)
TEST_END = pd.Timestamp("2026-10-01", tz=_TZ)

COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
CONFIG = PortfolioConfig()


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_panel() -> tuple[pd.DataFrame, list[str]]:
    panel, symbols, report = load_universe(str(ROOT / "data" / "nse"))
    assert report is not None
    return panel, symbols


# --------------------------------------------------------------------------- #
# The strategy, translated
# --------------------------------------------------------------------------- #


def roc_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised equivalent of `cryptobot.strategies.indicators.roc`.

    `roc(closes, p) = (closes[-1] - closes[-p-1]) / closes[-p-1]`, i.e. the return
    from `period` bars ago to the current bar. The rolling-window `maxlen`
    in `SignalStrategy.feed` is 300 bars, comfortably above every period here
    (max 126), so no truncation issue arises.
    """
    return panel / panel.shift(period) - 1.0


def signal_panel(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """The strategy's own +1/-1, as a boolean 'is flagged long' panel.

    Faithful to `TimeSeriesStrategy.signal`: it returns 0 only while `roc` is NaN
    (warmup) and +1/-1 otherwise. In a long-only book the -1 leg means "do not
    hold", so a boolean long-flag is the complete and lossless translation.
    """
    return roc_panel(panel, period) > threshold


def score_from_signal(
    panel: pd.DataFrame, period: int, threshold: float
) -> pd.DataFrame:
    """Cross-sectional score: rank eligible names by the strategy's own ROC.

    Rank is taken AFTER masking so an ineligible name never consumes a rank slot
    or a slot in `n_positions`. `build_rebalance_weights` treats non-finite
    scores as invalid and takes the top `n_positions` of what is valid.
    """
    roc = roc_panel(panel, period)
    eligible = roc > threshold
    return roc.where(eligible).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Benchmark score panels
# --------------------------------------------------------------------------- #


def buy_hold_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Constant score so every name is 'eligible'; the engine's inverse-vol
    scaling + caps produce a fully invested, broadly-held book.

    With a constant score the stable argsort ties-breaks on column order, so this
    would always buy the same 22 names and never rebalance. Instead we rank a
    constant by universe size, which is still constant-per-day and produces a
    genuinely rotating book. Simpler and honest: use the nsealgo composite-free
    approach below.
    """
    raise NotImplementedError


def equal_weight_market_score(panel: pd.DataFrame) -> pd.DataFrame:
    """A score that rotates the book but carries no directional view.

    Used only as a *control* (does a constant-beta book do as well?), not as the
    buy-and-hold benchmark, which is defined in the brief as
    `panel.pct_change().mean(axis=1)`.
    """
    n = panel.shape[1]
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns) + \
        pd.DataFrame(
            np.arange(n) / n, index=panel.index, columns=panel.columns
        ) * 1e-6


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


def slice_window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    return df.loc[(df.index >= start) & (df.index <= end)]


def run_window(
    panel: pd.DataFrame,
    score: pd.DataFrame,
    start,
    end,
    config: PortfolioConfig | None = None,
    rebalance: str = "M",
) -> object:
    """Backtest restricted to a window, then report metrics on that window only.

    Important: the *weights* are built from the score inside the window, exactly as
    a live system restarted at the window boundary would have to. Indicators use
    only data at or before the decision date, so slicing the panel does not leak:
    the first rebalance of the window has `period` bars of real history behind it.
    """
    p = slice_window(panel, start, end)
    s = slice_window(score, start, end)
    return run_backtest(p, s, COST_MODEL, config or CONFIG, rebalance=rebalance)


def metrics_of(result) -> dict:
    m = result.metrics
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "max_dd": m.max_drawdown,
        "calmar": m.calmar,
        "sortino": m.sortino,
        "vol": m.volatility,
        "total_return": m.total_return,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "trades_per_year": m.trades_per_year,
        "avg_names": result.diag["avg_names"],
        "avg_top_weight": result.diag["avg_top_weight"],
        "round_trip_bps": result.diag["round_trip_bps"],
    }


def fmt_row(name: str, d: dict) -> str:
    return (
        f"{name:<26} CAGR {d['cagr'] * 100:>7.2f}%  Sharpe {d['sharpe']:>6.2f}  "
        f"MaxDD {d['max_dd'] * 100:>7.2f}%  Calmar {d['calmar']:>6.2f}  "
        f"TO {d['turnover']:>5.2f}x  Drag {d['cost_drag'] * 100:>5.2f}%/y  "
        f"Names {d['avg_names']:>5.1f}"
    )


def buy_and_hold(panel: pd.DataFrame, start, end) -> dict:
    """The brief's definition: equal-weight universe return, net of the same costs.

    `panel.pct_change().mean(axis=1)` is the raw daily return. A buy-and-hold book
    pays one entry (and one eventual exit) of the full round-trip stack; the
    honest annualisation is to charge the 21.92 bps round trip once at entry,
    scaled by the window length, so the drag is comparable to the strategy's own.
    """
    p = slice_window(panel, start, end)
    rets = p.pct_change(fill_method=None).fillna(0.0)
    daily = rets.mean(axis=1)
    rt = COST_MODEL.all_in_round_trip_bps(100_000)
    rate = float(rt) / 10_000.0
    daily.iloc[0] -= rate
    eq = (1.0 + daily).cumprod()
    m = compute_metrics(daily, eq)
    years = len(daily) / 244
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "max_dd": m.max_drawdown,
        "calmar": m.calmar,
        "sortino": m.sortino,
        "vol": m.volatility,
        "total_return": m.total_return,
        "turnover": 0.0,
        "cost_drag": rate / years,
        "trades_per_year": 0.0,
        "avg_names": float(p.notna().sum(axis=1).mean()),
        "avg_top_weight": 0.0,
        "round_trip_bps": rt,
    }


def yearly_table(returns: pd.Series) -> str:
    yr = yearly_returns(returns)
    return "  ".join(f"{y}:{v * 100:+.1f}%" for y, v in yr.items())
