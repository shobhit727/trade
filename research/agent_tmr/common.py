"""Shared harness for agent_tmr. Nothing here is strategy-specific tuning.

Design rules enforced by this module:
  * One panel load, cached to disk, so every script sees identical data.
  * TRAIN and TEST slices are explicit and non-overlapping.
  * The signal reproduces the catalog indicator EXACTLY, including its quirks
    (z-score over the trailing 300-bar buffer, ddof=0, and the dead `period`).
  * Results always carry `engine_sha` so a concurrent engine edit cannot silently
    change the numbers between scripts.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    ENGINE_SHA,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

CACHE = Path(__file__).resolve().parent / "panel.pkl"
SYMS = Path(__file__).resolve().parent / "symbols.txt"

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

COSTS = CostModel(segment="delivery", slippage_bps=5)
#: Statutory-only stack: no slippage. Used as the zero-cost control (brief context).
COSTS_ZERO = CostModel(segment="delivery", slippage_bps=0.0)
CFG = PortfolioConfig()

NOTIONAL = 100_000

#: `SignalStrategy` builds its buffers as ``deque(maxlen=300)``. That -- not
#: ``TrendMrConfig.period`` (which is never referenced) -- is what fixes the
#: catalog z-score window. See REPORT.md F1/F2.
Z_WINDOW = 300

#: `panel` is sliced to TEST_START at the earliest; the 300-bar z window must be
#: built from history BEFORE that slice or the first ~300 TEST bars are wrong.
#: We therefore always compute signals on the full panel and slice afterwards.


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_panel() -> tuple[pd.DataFrame, list[str], str]:
    """Daily close panel + symbols + cleaning report text. Cached."""
    if CACHE.exists():
        with CACHE.open("rb") as fh:
            panel, symbols, txt = pickle.load(fh)
        return panel, symbols, txt
    panel, symbols, rep = load_universe(str(ROOT / "data" / "nse"))
    txt = rep.describe()
    with CACHE.open("wb") as fh:
        pickle.dump((panel, symbols, txt), fh)
    SYMS.write_text("\n".join(symbols))
    return panel, symbols, txt


def full_panel() -> pd.DataFrame:
    panel, _, _ = load_panel()
    return panel


def train_slice(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[(df.index >= TRAIN_START) & (df.index <= TRAIN_END)]


def test_slice(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[(df.index >= TEST_START) & (df.index <= TEST_END)]


# --------------------------------------------------------------------------- #
# The strategy's signal -- faithful reproduction
# --------------------------------------------------------------------------- #


def z300(panel: pd.DataFrame, window: int = Z_WINDOW) -> pd.DataFrame:
    """Catalog z-score per symbol over its own trailing `window` closes.

    Reproduces ``cryptobot.strategies.indicators.zscore``:
        z = (last - mean(window)) / stdev(window)
    Population stdev (ddof=0) -- that is what ``np.std()`` returns in the catalog,
    and what the indicator calls.

    ``min_periods=2`` matches the indicator's ``if len(a) < 2: return nan``, but the
    strategy's own ``warmup()`` only demands ``slow`` bars (40), so between 40 and 300
    bars the buffer is still growing and the z uses however many closes exist. That is
    genuine catalog behaviour, so it is reproduced rather than smoothed away -- the
    TRAIN slice starts 8 years into the panel, so by 2016 every buffer is saturated.
    """
    win = panel.rolling(window, min_periods=2)
    mu = win.mean()
    sd = win.std(ddof=0)
    return (panel - mu) / sd.replace(0.0, np.nan)


def sma(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Catalog ``sma``: plain mean of the trailing ``period`` closes."""
    return panel.rolling(period, min_periods=period).mean()


def long_flag(
    panel: pd.DataFrame, slow: int, entry: float, zwin: int = Z_WINDOW
) -> pd.DataFrame:
    """The strategy's LONG branch: ``z > entry and close > sma(slow)``.

    The SHORT branch (z < -entry and close < sma) is discarded -- the NSE delivery book
    is long-only (REPORT.md F4).
    """
    z = z300(panel, zwin)
    t = sma(panel, slow)
    return (z > entry) & (panel > t)


def tmr_score(
    panel: pd.DataFrame, slow: int, entry: float, mom_days: int = 126
) -> pd.DataFrame:
    """Signal -> cross-sectional score, per brief section 5.

    Rank the signalled names by trailing ``mom_days`` momentum; higher score = more
    preferred. Only flagged names receive a score (everything else stays NaN, which the
    engine treats as "not holdable").

    Both inputs are strictly backward-looking:
      * ``z300`` / ``sma`` are trailing rolling windows ending at t;
      * ``pct_change(mom_days)`` uses closes at t and t-126.
    """
    flag = long_flag(panel, slow, entry)
    mom = panel / panel.shift(mom_days) - 1.0
    return mom.where(flag).rank(axis=1, pct=True, na_option="keep")


def liveness(panel: pd.DataFrame, slow: int, entry: float) -> float:
    """Fraction of (symbol, bar) cells flagged long over the panel given."""
    flag = long_flag(panel, slow, entry)
    valid = z300(panel).notna()
    denom = int(valid.to_numpy().sum())
    return float(flag.to_numpy().sum()) / denom if denom else 0.0


def mean_names_flagged(panel: pd.DataFrame, slow: int, entry: float) -> float:
    return float(long_flag(panel, slow, entry).sum(axis=1).mean())


# --------------------------------------------------------------------------- #
# Run + report
# --------------------------------------------------------------------------- #


def run(
    panel: pd.DataFrame,
    score: pd.DataFrame,
    cfg: PortfolioConfig | None = None,
    costs: CostModel | None = None,
    label: str = "run",
):
    """Run the engine, asserting panel/score alignment before trusting any number."""
    cfg = cfg or CFG
    costs = costs or COSTS
    res = run_backtest(panel, score, costs, config=cfg, rebalance="M")
    assert res.engine_sha == ENGINE_SHA, (
        f"engine changed mid-run: {res.engine_sha} != {ENGINE_SHA}"
    )
    assert score.index.equals(panel.index), "score/panel index misaligned"
    assert list(score.columns) == list(panel.columns), "score/panel columns misaligned"
    res.diag = dict(res.diag or {})
    res.diag["label"] = label
    return res


def buy_and_hold(
    panel: pd.DataFrame, label: str = "buy_and_hold", costs: CostModel | None = None
) -> dict:
    """Equal-weight whole-universe hold, net of one full round trip of cost.

    Brief section 4 rule 5 specifies ``panel.pct_change().mean(axis=1)``. Entering and
    exiting once costs one round trip, charged here as a flat deduction on the
    compounding path so buy-and-hold sits on the same net footing as the strategy.
    """
    costs = costs or COSTS
    rets = panel.pct_change(fill_method=None)
    daily = rets.mean(axis=1).dropna()
    from decimal import Decimal

    rt = float(costs.all_in_round_trip_bps(Decimal(str(NOTIONAL))))
    rate = rt / 10_000.0

    eq = 1.0
    curve = []
    first = True
    for v in daily.to_numpy():
        eq *= 1.0 + float(v)
        if first:
            eq *= 1.0 - rate
            first = False
        curve.append(eq)
    equity = pd.Series(curve, index=daily.index)
    net = equity / equity.iloc[0]
    r = net.pct_change(fill_method=None).fillna(0.0)

    nan_frac = float(rets.isna().sum().sum()) / float(rets.size)
    m = compute_metrics(r, (1.0 + r).cumprod())
    return {
        "label": label,
        "engine_sha": ENGINE_SHA,
        "metrics": m,
        "equity": net,
        "returns": r,
        "round_trip_bps": rt,
        "nan_frac": nan_frac,
        "yearly": yearly_returns(r),
    }


def row(name: str, m, extra: str = "") -> str:
    return (
        f"| {name} | {m.cagr * 100:.2f}% | {m.sharpe:.2f} | {m.calmar:.2f} | "
        f"{m.max_drawdown * 100:.2f}% | {m.volatility * 100:.2f}% | "
        f"{m.total_return * 100:.1f}% | {m.annual_turnover:.2f}x/y | "
        f"{m.cost_drag_annual * 100:.2f}%/y | {extra} |"
    )


HDR = (
    "| run | CAGR | Sharpe | Calmar | MaxDD | Vol | Total | Turnover | CostDrag | notes |\n"
    "|---|---|---|---|---|---|---|---|---|---|"
)


def fmt_yearly(yr: pd.Series) -> str:
    return "  ".join(f"{y}:{v * 100:+.1f}%" for y, v in yr.items())


def avg_names(res) -> float:
    """Average number of names held, from the engine's weight frame."""
    return float((res.weights.abs() > 1e-9).sum(axis=1).mean())


def invested_frac(res) -> float:
    """Average fraction of the book actually deployed (not sitting in the 10% cash)."""
    return float(res.weights.abs().sum(axis=1).mean())


__all__ = [
    "COSTS",
    "COSTS_ZERO",
    "CFG",
    "TRAIN_END",
    "TRAIN_START",
    "TEST_END",
    "TEST_START",
    "Z_WINDOW",
    "avg_names",
    "buy_and_hold",
    "fmt_yearly",
    "full_panel",
    "invested_frac",
    "liveness",
    "long_flag",
    "mean_names_flagged",
    "row",
    "run",
    "sma",
    "test_slice",
    "train_slice",
    "z300",
    "tmr_score",
    "np",
    "pd",
]
