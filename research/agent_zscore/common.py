"""Shared harness for agent_zscore. Nothing here is strategy-specific tuning.

Design rules enforced by this module:
  * One panel load, cached to disk, so every script sees identical data.
  * TRAIN and TEST slices are explicit and non-overlapping.
  * The z-score reproduces the catalog indicator exactly (population stdev, ddof=0).
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
CFG = PortfolioConfig()

NOTIONAL = 100_000


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


def train_panel() -> pd.DataFrame:
    panel, _, _ = load_panel()
    return panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]


def test_panel() -> pd.DataFrame:
    panel, _, _ = load_panel()
    return panel.loc[(panel.index >= TEST_START) & (panel.index <= TEST_END)]


# --------------------------------------------------------------------------- #
# The strategy's signal
# --------------------------------------------------------------------------- #


def ts_zscore(panel: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Catalog z-score, per symbol, over its own trailing `lookback` closes.

    Reproduces `cryptobot.strategies.indicators.zscore`:
        z = (last - mean(window)) / stdev(window)
    evaluated at every point of a rolling window. Population stdev (ddof=0), which is
    what `np.std()` returns in the catalog. Window uses only the current and prior
    closes, so there is no look-ahead.
    """
    win = panel.rolling(lookback, min_periods=lookback)
    mu = win.mean()
    sd = win.std(ddof=0)
    return (panel - mu) / sd.replace(0.0, np.nan)


def zscore_score(panel: pd.DataFrame, lookback: int, entry: float) -> pd.DataFrame:
    """Signal -> cross-sectional score, per brief: only flagged names may be bought.

    `score = percentile_rank(-z)` restricted to `z <= -entry`. Higher = more oversold.
    The `-entry` side is the strategy's long branch; the `z >= +entry` short branch is
    discarded because an Indian delivery book cannot short.
    """
    z = ts_zscore(panel, lookback)
    oversold = z <= -entry
    score = (-z).where(oversold)
    return score.rank(axis=1, pct=True, na_option="keep")


def liveness(panel: pd.DataFrame, lookback: int, entry: float) -> float:
    """Fraction of (symbol, bar) cells flagged long, over the panel given."""
    z = ts_zscore(panel, lookback)
    valid = z.notna()
    flagged = (z <= -entry) & valid
    denom = int(valid.to_numpy().sum())
    return float(flagged.to_numpy().sum()) / denom if denom else 0.0


def mean_names_flagged(panel: pd.DataFrame, lookback: int, entry: float) -> float:
    z = ts_zscore(panel, lookback)
    return float((z <= -entry).sum(axis=1).mean())


# --------------------------------------------------------------------------- #
# Run + report
# --------------------------------------------------------------------------- #


def run(panel: pd.DataFrame, score: pd.DataFrame, cfg: PortfolioConfig | None = None):
    """Run the engine, and assert the panel/score alignment is sane before trusting it."""
    cfg = cfg or CFG
    res = run_backtest(panel, score, COSTS, config=cfg, rebalance="M")
    assert res.engine_sha == ENGINE_SHA, (
        f"engine changed mid-run: result {res.engine_sha} != current {ENGINE_SHA}"
    )
    return res


def buy_and_hold(panel: pd.DataFrame, label: str = "buy_and_hold") -> dict:
    """Equal-weight whole-universe hold, net of one full round trip of cost.

    Brief §4 rule 5 specifies `panel.pct_change().mean(axis=1)`. That is the daily
    equal-weight return of every name. Entering and exiting once costs one round trip
    (21.92 bps each way), which is charged here as a flat deduction on the compounding
    path so buy-and-hold is measured on the same net footing as the strategy.

    Names missing a bar are simply not in that day's average (pandas `mean` skips NaN);
    `nan_frac` is reported so this is visible rather than silent.
    """
    rets = panel.pct_change(fill_method=None)
    daily = rets.mean(axis=1).dropna()
    rt = float(COSTS.all_in_round_trip_bps(__import__("decimal").Decimal(str(NOTIONAL))))
    rate = rt / 10_000.0

    eq = 1.0
    curve = []
    first = True
    for v in daily.to_numpy():
        eq *= (1.0 + float(v))
        if first:
            eq *= (1.0 - rate)  # entry
            first = False
        curve.append(eq)
    equity = pd.Series(curve, index=daily.index)
    net = equity / equity.iloc[0]
    net.iloc[0] = 1.0 - rate
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
