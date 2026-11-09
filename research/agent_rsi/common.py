"""Shared harness for the RSI (mean-reversion) strategy on NSE NIFTY-50.

Reuses `nsealgo` infrastructure end to end: same loader, same `CostModel`, same
`run_backtest` / `build_rebalance_weights`, same metrics, same composite. Nothing in
`src/` is modified.

The only thing implemented locally is a *vectorised* RSI, because the catalog indicator
`cryptobot.strategies.indicators.rsi` is a streaming function over a window while the
panel needs one value per bar. `validate_rsi_matches_catalog` proves the vectorised
version is numerically identical to the catalog original over random probes.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import (  # noqa: E402
    Metrics,
    compute_metrics,
    yearly_returns,
)
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import (  # noqa: E402
    CleaningReport,
    DataIntegrityError,
    load_universe,
)
from nsealgo.factors.core import (  # noqa: E402
    build_composite_score,
    equal_weight_market,
)

__all__ = [
    "CONFIG",
    "COST",
    "DATA_DIR",
    "Panels",
    "Run",
    "Metrics",
    "PortfolioConfig",
    "CostModel",
    "CleaningReport",
    "DataIntegrityError",
    "build_composite_score",
    "compute_metrics",
    "equal_weight_market",
    "load_universe",
    "yearly_returns",
]

DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "nse")
)

#: Protocol windows from research/AGENT_BRIEF.md section 4.
TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

COST = CostModel(segment="delivery", slippage_bps=5)
CONFIG = PortfolioConfig()

#: Per-position notional the engine prices costs at (`engine.REF_POSITION_NOTIONAL`).
REF_NOTIONAL = Decimal("100000")


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


@dataclass
class Panels:
    close: pd.DataFrame
    symbols: list[str]
    report: CleaningReport


_CACHE: dict[str, Panels] = {}


def load_panels(data_dir: str = DATA_DIR) -> Panels:
    """Cleaned daily close panel via the mandated `load_universe` entry point."""
    if data_dir in _CACHE:
        return _CACHE[data_dir]
    panel, symbols, report = load_universe(data_dir)
    _CACHE[data_dir] = Panels(close=panel, symbols=list(symbols), report=report)
    return _CACHE[data_dir]


# --------------------------------------------------------------------------- #
# Vectorised RSI — identical maths to cryptobot.strategies.indicators.rsi
# --------------------------------------------------------------------------- #


def rsi_panel(close: pd.DataFrame, period: int) -> pd.DataFrame:
    """Cutler's simple RSI, one value per bar, NaN until the window is full.

    Catalog original (streaming, over the last ``period + 1`` closes)::

        d       = diff(closes[-(period + 1):])      # exactly `period` differences
        gains   = sum(d[d > 0]) / period
        losses  = -sum(d[d < 0]) / period
        if losses == 0: return 100.0
        return 100 - 100 / (1 + gains / losses)

    This is the **rolling simple-average** RSI, not Wilder's smoothed version, and it is
    what the catalog strategy actually trades. Vectorising it as
    ``diff -> clip -> rolling(sum)`` reproduces it exactly: the rolling window at bar t
    spans the same ``period`` differences as the catalog's slice. No lookahead — the
    window ends at t.
    """
    d = close.diff()
    gains = d.clip(lower=0.0).rolling(period, min_periods=period).sum()
    losses = (-d.clip(upper=0.0)).rolling(period, min_periods=period).sum()

    r = gains / losses.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + r)
    # `losses == 0` -> catalog returns exactly 100.0 (an unbroken advance window).
    out = out.mask(losses == 0.0, 100.0)
    # An all-flat window gives gains == 0 and losses == 0, which the mask above already
    # sends to 100.0, matching the catalog's `losses == 0` early return.
    return out


def validate_rsi_matches_catalog(
    close: pd.DataFrame, period: int = 14, n_probe: int = 200
) -> dict:
    """Prove the vectorised RSI equals the catalog's streaming `rsi()`.

    This is the check that matters: if the two disagree, every downstream number
    describes a different indicator than the one the catalog strategy trades.
    """
    from cryptobot.strategies.indicators import rsi as catalog_rsi

    vec = rsi_panel(close, period)
    cols = list(close.columns)
    rng = np.random.default_rng(0)

    probes: list[tuple[str, int]] = []
    for _ in range(n_probe):
        sym = cols[int(rng.integers(len(cols)))]
        t = int(rng.integers(period, len(close)))
        probes.append((sym, t))

    max_abs_err = 0.0
    n_checked = 0
    n_nan_skipped = 0
    for sym, t in probes:
        hist = close[sym].iloc[: t + 1].dropna().tolist()
        got = catalog_rsi(hist, period)
        exp = float(vec[sym].iloc[t])
        if np.isnan(got):
            n_nan_skipped += 1
            continue
        n_checked += 1
        max_abs_err = max(max_abs_err, abs(got - exp))

    return {
        "period": period,
        "n_checked": n_checked,
        "n_nan_skipped": n_nan_skipped,
        "max_abs_error": max_abs_err,
        "identical": bool(max_abs_err < 1e-9),
    }


# --------------------------------------------------------------------------- #
# Signal -> cross-sectional score
# --------------------------------------------------------------------------- #


def signal_panel(rsi: pd.DataFrame, lower: float, upper: float = 70.0) -> pd.DataFrame:
    """The catalog signal, verbatim: +1 if RSI < lower, -1 if RSI > upper, else 0.

    Long-only book: the -1 (overbought) branch is not tradable, so it collapses into
    "not long". The panel keeps the raw sign for reporting; book eligibility is `> 0`.
    """
    sig = np.zeros(rsi.shape, dtype=float)
    r = rsi.to_numpy(dtype=float)
    sig[:] = np.where(
        np.isnan(r), 0.0, np.where(r > upper, -1.0, np.where(r < lower, 1.0, 0.0))
    )
    return pd.DataFrame(sig, index=rsi.index, columns=rsi.columns)


def build_score(
    close: pd.DataFrame,
    rsi: pd.DataFrame,
    lower: float,
    rank_by: str = "deepest",
    lookback: int = 126,
) -> pd.DataFrame:
    """Turn the per-symbol time-series signal into a cross-sectional score.

    `rank_by="deepest"` is the strategy-faithful construction: among flagged (oversold)
    names, buy the most oversold (lowest RSI). `rank_by="mom126"` is the brief section 5
    construction: among flagged names, buy the strongest trailing performer. Unflagged
    names are NaN, hence ineligible — the engine only ever buys flagged names.
    """
    sig = signal_panel(rsi, lower)
    eligible = sig > 0

    if rank_by == "deepest":
        raw = -rsi
    elif rank_by.startswith("mom"):
        n = int(rank_by[3:])
        raw = close / close.shift(n) - 1.0
    else:
        raise ValueError(f"unknown rank_by: {rank_by}")

    return raw.where(eligible)


def eligible_counts(score: pd.DataFrame, rebalance: str = "M") -> dict:
    """How many names are eligible per rebalance date.

    Reported because it decides what the book actually is: while the eligible count is
    below `n_positions`, the engine buys *every* flagged name and the ranking convention
    is cosmetic. Only once the count exceeds 22 does ranking bind.
    """
    from nsealgo.backtest.engine import _rebalance_dates

    rb = _rebalance_dates(score.index, rebalance)
    rb = [d for d in rb if d in score.index]
    counts = np.array([int(score.loc[d].notna().sum()) for d in rb])
    return {
        "n_rebalances": int(len(counts)),
        "min": int(counts.min()) if len(counts) else 0,
        "median": float(np.median(counts)) if len(counts) else float("nan"),
        "mean": float(counts.mean()) if len(counts) else float("nan"),
        "max": int(counts.max()) if len(counts) else 0,
        "frac_at_or_above_cap": float((counts >= CONFIG.n_positions).mean())
        if len(counts)
        else float("nan"),
    }


def bar_long_fraction(
    rsi: pd.DataFrame, lower: float, start, end
) -> float:
    """Fraction of (bar, symbol) cells that are tradably long, over a window."""
    r = rsi.loc[start:end]
    n = int(r.notna().to_numpy().sum())
    if n == 0:
        return float("nan")
    return float((r < lower).to_numpy().sum()) / n


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


@dataclass
class Run:
    name: str
    metrics: Metrics
    diag: dict
    equity: pd.Series
    returns: pd.Series
    avg_names: float
    long_frac: float = float("nan")


def run_variant(
    name: str,
    panel: pd.DataFrame,
    score: pd.DataFrame,
    rebalance: str = "M",
) -> Run:
    res = run_backtest(panel, score, COST, CONFIG, rebalance=rebalance)
    return Run(
        name=name,
        metrics=res.metrics,
        diag=res.diag,
        equity=res.equity,
        returns=res.returns,
        avg_names=float(res.diag["avg_names"]),
    )


def equal_weight_score(panel: pd.DataFrame) -> pd.DataFrame:
    """A deliberately untilted book through the *same* engine and cost model.

    Same 22-name cap, same 10% cash, same monthly rebalance, same costs — so any gap
    against the strategy is attributable to the signal rather than to the harness.
    """
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns)


def buy_and_hold(panel: pd.DataFrame) -> Run:
    """`panel.pct_change().mean(axis=1)` — the brief's literal market proxy, net.

    Costs: a buy-and-hold book pays one round trip at entry and nothing thereafter.
    Charged on day 1 so the comparison is net, not gross. The return series is rebuilt
    from the equity curve so the entry cost is visible in Sharpe / MaxDD too.
    """
    r = equal_weight_market(panel).fillna(0.0)
    rate = float(COST.all_in_round_trip_bps(REF_NOTIONAL)) / 10_000.0
    eq, out = 1.0, []
    for i, x in enumerate(r.to_numpy()):
        eq *= 1.0 + float(x)
        if i == 0:
            eq *= 1.0 - rate
        out.append(eq)
    eqs = pd.Series(out, index=r.index)
    daily = eqs.pct_change().fillna(0.0)
    m = compute_metrics(daily, eqs)
    return Run(
        "buy_and_hold_EW",
        m,
        {"avg_names": len(panel.columns)},
        eqs,
        daily,
        float(len(panel.columns)),
        1.0,
    )


def random_control(
    close: pd.DataFrame,
    long_frac: float,
    rebalance: str = "M",
    n_seeds: int = 50,
    base_seed: int = 1000,
    window: tuple | None = None,
) -> dict:
    """Random signal with the *same* long fraction — the minimum bar to clear.

    On each seed an iid Bernoulli(long_frac) mask picks which names are eligible, then
    the book is ranked by 126d momentum among them. Everything downstream (ranking,
    inverse-vol scaling, caps, cash, turnover budget, costs) is identical to the
    strategy run, so the only difference is *which* names were picked.

    `window` is an optional (start, end) slice applied to the score so the control can be
    run on the same sub-period as the strategy it is compared against.
    """
    mom = close / close.shift(126) - 1.0
    cagrs, sharpes, mdds, names = [], [], [], []
    for seed in range(n_seeds):
        rng = np.random.default_rng(base_seed + seed)
        mask = rng.random(close.shape) < long_frac
        score = mom.where(pd.DataFrame(mask, index=close.index, columns=close.columns))
        if window is not None:
            score = score.loc[window[0] : window[1]]
        r = run_variant(f"rand{seed}", close, score, rebalance=rebalance)
        cagrs.append(r.metrics.cagr)
        sharpes.append(r.metrics.sharpe)
        mdds.append(r.metrics.max_drawdown)
        names.append(r.avg_names)
    return {
        "n_seeds": n_seeds,
        "long_frac": long_frac,
        "cagr_mean": float(np.mean(cagrs)),
        "cagr_median": float(np.median(cagrs)),
        "cagr_p05": float(np.percentile(cagrs, 5)),
        "cagr_p95": float(np.percentile(cagrs, 95)),
        "sharpe_mean": float(np.mean(sharpes)),
        "sharpe_p05": float(np.percentile(sharpes, 5)),
        "sharpe_p95": float(np.percentile(sharpes, 95)),
        "maxdd_mean": float(np.mean(mdds)),
        "avg_names_mean": float(np.mean(names)),
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def row(label: str, run: Run) -> str:
    m = run.metrics
    return (
        f"{label:<26} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x  Cost {m.cost_drag_annual * 100:>5.2f}%  "
        f"Names {run.avg_names:>5.1f}"
    )


def header(title: str) -> str:
    return f"\n{'=' * 100}\n{title}\n{'=' * 100}"
