"""Shared harness for the flag_pattern agent run.

Reuses nsealgo infrastructure only; nothing under src/ is modified.

Signals (all point-in-time, no lookahead): every panel is computed from data up to and
including day t, and ``run_backtest`` earns from t+1 only (it shifts held weights by one
bar). The one deliberate exception is V0, which reproduces the shipped code EXACTLY --
including its use of today's own close to form today's signal. That is the same
convention the shipped backtester would use (signal on bar t, fill on bar t+1), so it
is not lookahead.

The -1 (short) branch is mapped to "not long" everywhere: ``PortfolioConfig`` and
``run_backtest`` are long-only and an Indian delivery account cannot short.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import Metrics, compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import CleaningReport, load_symbol, load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score, rank_cross_sectional  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = ROOT / "data" / "nse"

__all__ = [
    "CONTROL_SEEDS",
    "TEST_END",
    "TEST_START",
    "TRAIN_END",
    "TRAIN_START",
    "VARIANTS",
    "build_composite_score",
    "ZeroCostModel",
    "backtest",
    "build_score",
    "cost_model",
    "equal_weight_bh",
    "flag_signal",
    "liveness",
    "literal_signal",
    "load_all",
    "metrics_table",
    "portfolio_config",
    "random_signal_like",
    "run_signal",
    "slice_panel",
]

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

#: Ranking lookback, held FIXED at 126d (6-month) momentum for every variant so the
#: whole parameter budget is spent on the signal, not on the ranking.
RANK_LB = 126

CONTROL_SEEDS = (0, 1, 2, 3, 4)

#: The declared budget, in code, so a run cannot silently exceed it.
VARIANTS = {
    "V0_LITERAL": dict(kind="run", n=2),
    "V1_RUN3": dict(kind="run", n=3),
    "V2_RUN5": dict(kind="run", n=5),
    "V3_FLAG5": dict(kind="flag", pole=20, pole_thr=0.10, consol=5, band=0.03),
    "V4_FLAG10": dict(kind="flag", pole=20, pole_thr=0.10, consol=10, band=0.05),
}


# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #


def cost_model() -> CostModel:
    return CostModel(segment="delivery", slippage_bps=5)


class ZeroCostModel:
    """Research-only: a perfectly frictionless model, for the gross/net split only.

    ``run_backtest`` touches the cost model through exactly one method,
    ``all_in_round_trip_bps``. Returning 0 makes the equity curve gross. The
    zero-cost number is NEVER reported as a result.
    """

    def all_in_round_trip_bps(self, notional) -> float:  # noqa: ARG002
        return 0.0


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str], str]:
    """(close, high, low, symbols, cleaning_report) on one shared index."""
    panel, symbols, report = load_universe(str(DATA))
    highs, lows, closes = {}, {}, {}
    for sym in symbols:
        df = load_symbol(str(DATA / f"{sym}_1d.csv"), sym, CleaningReport())
        closes[sym] = df["close"].rename(sym)
        highs[sym] = df["high"].rename(sym)
        lows[sym] = df["low"].rename(sym)
    close = pd.DataFrame(closes).sort_index().dropna(how="all")
    high = pd.DataFrame(highs).reindex(index=close.index, columns=close.columns)
    low = pd.DataFrame(lows).reindex(index=close.index, columns=close.columns)
    assert close.equals(panel), "OHLC rebuild diverged from the load_universe panel"
    return panel, high, low, symbols, report.describe()


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #


def literal_signal(close: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """The shipped signal: ``n`` consecutive higher closes (n=2 is V0, verbatim).

    Returns +1 long / -1 short / 0 flat. The short branch is retained so the shipped
    semantics are measurable; downstream, only ``> 0`` is ever used.
    """
    # n consecutive rises means every ADJACENT pair in the run rose:
    #   close.shift(k) > close.shift(k+1)  for k = 0 .. n-1
    # which is exactly the shipped chain c_t > c_{t-1} > ... > c_{t-n+1} when n=2.
    # Chaining matters: (c_t > c_{t-1} and c_t > c_{t-2}) is a DIFFERENT and much
    # looser condition -- it fires on 10, 9, 11, which the shipped code rejects.
    run_up = pd.DataFrame(
        True, index=close.index, columns=close.columns,
    )
    run_dn = pd.DataFrame(
        True, index=close.index, columns=close.columns,
    )
    for k in range(n):
        run_up &= close.shift(k) > close.shift(k + 1)
        run_dn &= close.shift(k) < close.shift(k + 1)
    sig = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    sig = sig.mask(run_up, 1.0)
    sig = sig.mask(run_dn, -1.0)
    sig[close.isna()] = np.nan
    return sig


def flag_signal(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                pole: int, pole_thr: float, consol: int, band: float) -> pd.DataFrame:
    """Textbook flag: pole, then consolidation, then breakout. Long-only side.

    * pole    : the ``pole`` bars ending ``consol`` bars ago gained >= ``pole_thr``
    * flag    : the ``consol`` bars immediately before today had a high-low range
                <= ``band`` of the low (tight sideways drift)
    * trigger : today's close breaks above the highest high of those ``consol`` bars

    All three windows are shifted so they exclude today's bar except the trigger
    itself, which necessarily uses today's close. No lookahead.
    """
    base = close.shift(consol)
    pole_ret = base / base.shift(pole) - 1.0
    has_pole = pole_ret >= pole_thr

    ph = high.rolling(consol, min_periods=consol).max().shift(1)
    pl = low.rolling(consol, min_periods=consol).min().shift(1)
    tight = ((ph - pl) / pl) <= band

    trig = close > ph
    sig = (has_pole & tight & trig).astype(float)
    sig[ph.isna()] = 0.0
    sig[close.isna()] = np.nan
    return sig


def run_signal(close, high, low, spec: dict) -> pd.DataFrame:
    if spec["kind"] == "run":
        return literal_signal(close, spec["n"])
    return flag_signal(close, high, low, spec["pole"], spec["pole_thr"],
                       spec["consol"], spec["band"])


#: Backwards-compatible alias used by the runner scripts.
flag_signal_entry = run_signal


def build_score(signal: pd.DataFrame, panel: pd.DataFrame,
                rank_lb: int = RANK_LB) -> pd.DataFrame:
    """Cross-sectional score: percentile rank of 126d momentum AMONG flagged names.

    Unflagged names become NaN, which ``build_rebalance_weights`` treats as
    uninvestable, so no short is expressible.
    """
    mom = panel / panel.shift(rank_lb) - 1.0
    return rank_cross_sectional(mom.where(signal > 0))


# --------------------------------------------------------------------------- #
# Benchmarks / controls
# --------------------------------------------------------------------------- #


def equal_weight_bh(panel: pd.DataFrame) -> tuple[pd.Series, Metrics, float]:
    """Buy-and-hold: equal weight all names, ONE entry+exit round trip charged on day 1.

    A buy-and-hold book pays a single round trip, not the strategy's monthly turnover,
    so charging it the strategy's drag would be unfair to the benchmark. This is the
    generous reading.
    """
    rets = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rate = float(cost_model().all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    eq, costs, out = 1.0, 0.0, pd.Series(0.0, index=panel.index)
    for i, dt in enumerate(panel.index):
        prev = eq
        if i == 0:
            eq *= 1.0 - rate
            costs += rate
        else:
            eq *= 1.0 + float(rets.loc[dt])
        out.loc[dt] = eq / prev - 1.0
    equity = (1.0 + out).cumprod()
    return out, compute_metrics(out, equity), costs


def random_signal_like(signal: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: random names, identical long-fraction per day."""
    rng = np.random.default_rng(seed)
    valid = signal.notna().sum(axis=1).clip(lower=1)
    frac = ((signal > 0).sum(axis=1) / valid).to_numpy()[:, None]
    draws = rng.random((len(signal), signal.shape[1]))
    out = pd.DataFrame(
        np.where(signal.notna().to_numpy(), np.where(draws < frac, 1.0, 0.0), np.nan),
        index=signal.index, columns=signal.columns,
    )
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def portfolio_config() -> PortfolioConfig:
    return PortfolioConfig()  # 22 names / 12% / 25% / 10% cash / 35% turnover


def backtest(panel: pd.DataFrame, score: pd.DataFrame, rebalance: str = "M",
             gross: bool = False):
    cm = ZeroCostModel() if gross else cost_model()
    return run_backtest(panel, score, cm, portfolio_config(), rebalance=rebalance)


def slice_panel(panel: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    return panel.loc[lo:hi]


def liveness(signal: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> tuple:
    """(frac long, frac short, mean names flagged) over [lo, hi]."""
    s = signal.loc[lo:hi]
    valid = s.notna().sum(axis=1).clip(lower=1)
    return (
        float((s > 0).sum(axis=1).div(valid).mean()),
        float((s < 0).sum(axis=1).div(valid).mean()),
        float((s > 0).sum(axis=1).mean()),
    )


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_HEAD = (
    f"  {'Label':<22}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}"
    f"{'Calmar':>8}{'Turn':>8}{'Drag':>8}{'N':>7}"
)


def metrics_table(rows: list[dict]) -> str:
    """rows: [{'label', 'metrics', 'avg_names'}, ...]"""
    out = [_HEAD, "  " + "-" * (len(_HEAD) - 2)]
    for r in rows:
        m: Metrics = r["metrics"]
        out.append(
            f"  {r['label']:<22}{m.cagr * 100:>8.2f}%{m.sharpe:>9.2f}"
            f"{m.max_drawdown * 100:>8.2f}%{m.calmar:>8.2f}"
            f"{m.annual_turnover:>7.2f}x{m.cost_drag_annual * 100:>7.2f}%"
            f"{r.get('avg_names', float('nan')):>7.1f}"
        )
    return "\n".join(out)
