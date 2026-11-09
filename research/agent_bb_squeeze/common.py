"""Shared plumbing for the bollinger_band_squeeze NSE evaluation.

Faithful vectorised port of
``src/cryptobot/strategies/catalog/bollinger_band_squeeze.py``.

Catalog logic, per symbol, at bar *t*:
    m    = sma(closes, period)            # mean of last `period` closes
    std  = np.std(closes[-period:]) / m   # POPULATION stdev of the last `period`
                                           # closes, divided by that mean
                                           # -> coefficient of variation (CV)
    r    = roc(closes, 3)                 # (c[t] - c[t-3]) / c[t-3]
    sig  = +1 if std < threshold and r > 0
    sig  = -1 if std < threshold and r < 0
    sig  =  0 otherwise

So the signal is a **volatility-compression gate** (realised CV below threshold)
ANDed with a **3-bar short-term continuation** direction. The `-1` branch is
unusable in a long-only Indian delivery account; only `+1` is traded.

Everything here is point-in-time: a signal on bar *t* uses closes up to and
including *t*. `run_backtest` holds the resulting weights from *t+1*, so there
is no look-ahead.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "nse"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    run_backtest,
    sector_of,
)
from nsealgo.backtest.metrics import Metrics, compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

# Re-exported so scratch scripts have one import site. Referenced here so ruff
# does not strip them as unused.
__all__ = [
    "BASE",
    "DATA",
    "MOM_LOOKBACK",
    "TEST",
    "TRAIN",
    "CostModel",
    "Metrics",
    "PortfolioConfig",
    "Variant",
    "WARMUP_BARS",
    "build_composite_score",
    "build_score",
    "buy_and_hold",
    "composite_returns",
    "compute_metrics",
    "cv_panel",
    "hr",
    "liveness",
    "load_universe",
    "metrics_for",
    "momentum_score",
    "roc_panel",
    "roc_score",
    "row",
    "run_backtest",
    "run_variant",
    "sector_exposure",
    "squeeze_signal",
    "table",
    "yearly_returns",
]

#: Full Indian delivery stack + 5 bps adverse slippage per side.
BASE = CostModel(segment="delivery", slippage_bps=Decimal("5"))

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

MOM_LOOKBACK = 126  # brief §5: rank flagged names by trailing 6-month momentum


# --------------------------------------------------------------------------- #
# Signal construction
# --------------------------------------------------------------------------- #


def cv_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Coefficient of variation over a trailing ``period``-bar window.

    Mirrors the catalog exactly: population stdev (``ddof=0``) of the last
    ``period`` closes, divided by the SMA of the same window. Requires a full
    window of real prices, so ``min_periods=period`` reproduces the catalog's
    ``len(closes) < period -> 0`` guard instead of silently using a short one.
    """
    win = panel.rolling(period, min_periods=period)
    mean = win.mean()
    std = win.std(ddof=0)
    return std / mean.replace(0.0, np.nan)


def roc_panel(panel: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """Rate of change over ``lookback`` bars: ``c[t]/c[t-lookback] - 1``."""
    return panel / panel.shift(lookback) - 1.0


def squeeze_signal(
    panel: pd.DataFrame, period: int, threshold: float, roc_lookback: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return ``(long_panel, short_panel, squeeze_panel)``.

    ``long_panel`` is 1.0 where the catalog would return +1, ``short_panel`` is
    1.0 where it would return -1, ``squeeze_panel`` is 1.0 wherever the squeeze
    gate alone fires (regardless of direction) — that third one exists only to
    measure how much of the +1/-1 split is direction versus gate.
    """
    cv = cv_panel(panel, period)
    r = roc_panel(panel, roc_lookback)
    gate = cv < threshold
    return (
        (gate & (r > 0)).astype(float),
        (gate & (r < 0)).astype(float),
        gate.astype(float),
    )


# --------------------------------------------------------------------------- #
# Score construction
# --------------------------------------------------------------------------- #


def momentum_score(panel: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """Brief §5 construction: 6-month trailing momentum, percentile-ranked
    *within the flagged names only*. Unflagged names are NaN so the engine's
    top-k selection cannot buy them.

    The percentile rank is computed on the masked momentum only, so the ranks of
    the flagged names span (0, 1] regardless of how many are flagged.
    """
    mom = panel / panel.shift(MOM_LOOKBACK) - 1.0
    mom = mom.where(mask > 0)
    return mom.rank(axis=1, pct=True)


def roc_score(panel: pd.DataFrame, mask: pd.DataFrame, roc_lookback: int = 3) -> pd.DataFrame:
    """Strategy-native scoring: rank the flagged names by the *strategy's own*
    3-bar ROC instead of by 6-month momentum. A more faithful reading of the
    catalog, which gives no ranking rule at all."""
    r = roc_panel(panel, roc_lookback)
    return r.where(mask > 0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Buy-and-hold benchmark, net of the same costs
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, cost_model: CostModel = BASE) -> pd.Series:
    """Equal-weight buy-and-hold daily returns, charged the engine's own cost
    convention: one-way turnover 0.90 at entry and 0.90 at exit (10% cash
    buffer, matching `PortfolioConfig`), each charged
    ``all_in_round_trip_bps`` — exactly how `run_backtest` charges a rebalance.
    """
    r = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rate = float(cost_model.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    r = r.copy()
    r.iloc[0] -= 0.90 * rate
    r.iloc[-1] -= 0.90 * rate
    return r


# --------------------------------------------------------------------------- #
# Variant spec
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Variant:
    name: str
    period: int
    threshold: float
    scorer: str = "momentum"  # "momentum" | "roc"
    roc_lookback: int = 3
    note: str = ""


def build_score(panel: pd.DataFrame, v: Variant) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(score_panel, long_mask)`` for a variant."""
    lng, _, _ = squeeze_signal(panel, v.period, v.threshold, v.roc_lookback)
    if v.scorer == "momentum":
        score = momentum_score(panel, lng)
    else:
        score = roc_score(panel, lng, v.roc_lookback)
    return score, lng


#: Factor warmup needed before a window's first bar can carry a valid score.
#: The longest lookback in play is 126 (momentum) and the engine's inverse-vol
#: window is 60, so 190 bars is comfortably sufficient.
WARMUP_BARS = 260


def _tz(stamp: str, like: pd.DataFrame) -> pd.Timestamp:
    """Localise a window bound to the panel's timezone (the panel is tz-aware)."""
    ts = pd.Timestamp(stamp)
    return ts.tz_localize(like.index.tz) if ts.tzinfo is None and like.index.tz else ts


def run_variant(
    panel: pd.DataFrame,
    v: Variant,
    window: tuple[str, str],
    config: PortfolioConfig | None = None,
    cost_model: CostModel = BASE,
    rebalance: str = "M",
) -> tuple[pd.Series, pd.DataFrame, Metrics, dict]:
    """Backtest one variant on one window. Returns (daily_returns, weights,
    metrics, diagnostics), all restricted to ``window``.

    The panel is fed to the engine starting ``WARMUP_BARS`` *before* the window
    so the 126-bar momentum and 60-bar inverse-vol rolling windows are already
    populated on the window's first bar. Only returns/weights inside ``window``
    are kept; the warmup stretch is discarded.

    This is not lookahead: every factor at bar *t* still uses closes up to *t*,
    and the warmup stretch only supplies trailing history. Slicing the panel to
    the window *before* computing the score is the bug this avoids — it silently
    deletes the first ~6 months of the window (2024Q1+Q2 held nothing at all),
    which shortens the evaluation and biases it toward late-window regimes.
    """
    cfg = config or PortfolioConfig()
    lo, hi = _tz(window[0], panel), _tz(window[1], panel)
    start_pos = max(int(panel.index.searchsorted(lo)) - WARMUP_BARS, 0)
    px = panel.iloc[start_pos:][lambda d: d.index <= hi]

    score, _ = build_score(px, v)
    res = run_backtest(px, score, cost_model, cfg, rebalance)

    r = res.returns.loc[lo:hi]
    w = res.weights.loc[lo:hi]
    yrs = max(len(r) / 244.0, 1e-9)

    # Turnover, in the engine's own convention (one-way = 0.5 * sum |change| in
    # held weights), counted only at the first bar of each rebalance period.
    changes = w.diff().abs().sum(axis=1) / 2.0
    changes.iloc[0] = float(w.iloc[0].abs().sum())
    period = w.index.tz_localize(None).to_period("M" if rebalance.upper() == "M" else "W")
    is_rebalance = pd.Series(w.index, index=w.index).groupby(period).transform(
        "first"
    ).eq(w.index)
    n_rb = int(is_rebalance.sum())
    turn = float(changes[is_rebalance].sum())
    rate = float(cost_model.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0

    metrics = compute_metrics(
        r,
        (1.0 + r).cumprod(),
        annual_turnover=turn / yrs,
        cost_drag_annual=(turn / yrs) * rate,
        trades_per_year=n_rb / yrs,
    )
    diag = dict(res.diag)
    diag["avg_names"] = float((w > 0).sum(axis=1).mean())
    diag["avg_invested"] = float(w.sum(axis=1).mean())
    diag["n_rebalances"] = n_rb
    return r, w, metrics, diag


# --------------------------------------------------------------------------- #
# Metrics for an arbitrary daily return series (benchmark / composite)
# --------------------------------------------------------------------------- #


def metrics_for(
    returns: pd.Series, window: tuple[str, str], turnover: float = 0.0
) -> Metrics:
    r = returns.loc[window[0] : window[1]]
    eq = (1.0 + r).cumprod()
    years = len(r) / 244.0
    # Turnover for a buy-and-hold book: 0.90 out at entry + 0.90 in at exit,
    # spread over the window, on the compounding equity (engine convention).
    return compute_metrics(
        r,
        eq,
        annual_turnover=turnover / years,
        cost_drag_annual=0.0,
        trades_per_year=1.0 / years,
    )


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #


def row(label: str, m: Metrics, extra: dict | None = None) -> str:
    e = extra or {}
    s = (
        f"{label:<22} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"turn {m.annual_turnover:>5.2f}x/y  drag {m.cost_drag_annual * 100:>5.2f}%/y"
    )
    if "names" in e:
        s += f"  names {e['names']:>5.1f}"
    if "longbar" in e:
        s += f"  long {e['longbar'] * 100:>5.1f}%"
    return s


def hr(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def table(rows: list[str], header: str) -> None:
    print("\n" + header)
    print("-" * 100)
    for r in rows:
        print(r)


def composite_returns(panel: pd.DataFrame, window: tuple[str, str]) -> pd.Series:
    """nsealgo's own composite over the given window — the thing to beat."""
    px = panel.loc[window[0] : window[1]]
    res = run_backtest(px, build_composite_score(px), BASE, PortfolioConfig(), "M")
    return res.returns


def liveness(px: pd.DataFrame, mask: pd.DataFrame) -> dict:
    """How often the signal is actually on.

    ``bar_frac``  — of all (name, day) pairs in the window, fraction signalled.
    ``day_frac``  — average cross-sectional breadth per day.
    ``days_any``  — fraction of days with at least one signalled name.
    """
    m = mask.loc[px.index]
    per_name = m.mean(axis=1)
    return {
        "bar_frac": float(m.to_numpy().mean()),
        "day_frac": float(m.mean(axis=1).mean()),
        "days_any": float((m.sum(axis=1) > 0).mean()),
        "names_median": float(per_name.median()),
    }


def sector_exposure(weights: pd.DataFrame) -> dict:
    """Average per-sector share of *invested* capital across the window.

    Both numerator and denominator are averaged over days first, so a
    sector summed across 685 days is never compared against a single-day mean
    total.
    """
    tot = weights.sum(axis=1).replace(0.0, np.nan)
    share = weights.div(tot, axis=0)
    out: dict[str, float] = {}
    for c in weights.columns:
        out.setdefault(sector_of(c), 0.0)
        out[sector_of(c)] += float(share[c].fillna(0.0).mean())
    return out
