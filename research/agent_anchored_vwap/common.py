"""Shared plumbing for the `anchored_vwap` NSE experiment.

The catalog strategy (`src/cryptobot/strategies/catalog/anchored_vwap.py`) is:

    v   = volume-weighted mean of `closes` over the trailing `period` buffer
    dev = (close[-1] - v) / v
    signal = -1 if dev > +threshold else (+1 if dev < -threshold else 0)

i.e. a **mean-reversion** trigger: buy when price sits more than `threshold` below
its trailing volume-weighted average price; short when symmetrically above.

Translation to this book (long-only, cross-sectional, NIFTY-50):
  * the `-1` branch is unusable (no shorting in a delivery account) -> becomes "avoid"
  * the `+1` branch becomes the **eligibility filter**
  * among eligible names we need a *cross-sectional* score, because `run_backtest`
    picks the top `n_positions` by score, not by signal sign.

Two score constructions are compared (V5 vs V1-V4):
  * "mom"  — trailing 126d momentum rank among eligible names (the brief §5 recipe).
    In a trending market the least-extended eligible name is the safer long.
  * "deep" — deepest discount to VWAP first. The purest reading of the strategy:
    the further below VWAP, the stronger the mean-reversion claim.

No lookahead anywhere: `dev[t]` uses closes/volumes up to and including `t`;
`run_backtest` decides weights from close `t` and earns returns from `t+1`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    REF_POSITION_NOTIONAL,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import Metrics, compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import CleaningReport, load_symbol  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

DATA_DIR = str(ROOT / "data" / "nse")

IST = "Asia/Kolkata"
TRAIN = (pd.Timestamp("2016-01-01", tz=IST), pd.Timestamp("2023-12-31", tz=IST))
TEST = (pd.Timestamp("2024-01-01", tz=IST), pd.Timestamp("2026-10-01", tz=IST))

CFG = PortfolioConfig(n_positions=22)


# --------------------------------------------------------------------------- #
# Declared parameter budget — 5 variants, fixed before any run.
# Selection rule: highest TRAIN Sharpe, tie-broken by lower TRAIN cost drag.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Variant:
    name: str
    period: int      # VWAP lookback, in daily bars
    threshold: float # |deviation| band that triggers the long leg
    score_kind: str  # "mom" | "deep"


VARIANTS: list[Variant] = [
    Variant("V1_p50_t2.0_mom",   50,  0.02, "mom"),
    Variant("V2_p50_t5.0_mom",   50,  0.05, "mom"),
    Variant("V3_p200_t5.0_mom", 200,  0.05, "mom"),
    Variant("V4_p20_t3.0_mom",   20,  0.03, "mom"),
    Variant("V5_p50_t5.0_deep",  50,  0.05, "deep"),
]


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


@dataclass
class Universe:
    close: pd.DataFrame
    volume: pd.DataFrame
    symbols: list[str]
    report: CleaningReport


_UNIVERSE: Universe | None = None


def load() -> Universe:
    """Load closes *and* share volumes through the audited `load_symbol` path.

    `load_universe` only returns closes, but VWAP is volume-weighted, so we re-use
    the same loader per symbol to get the volume column under the same cleaning
    rules (C1-C7). Cached: it re-reads ~50 CSVs otherwise.
    """
    global _UNIVERSE
    if _UNIVERSE is not None:
        return _UNIVERSE

    import os

    closes: dict[str, pd.Series] = {}
    vols: dict[str, pd.Series] = {}
    rep = CleaningReport()
    dropped: list[str] = []

    from nsealgo.data.loader import EXCLUDE_SYMBOLS

    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith("_1d.csv"):
            continue
        sym = fname[: -len("_1d.csv")]
        if sym in EXCLUDE_SYMBOLS:
            dropped.append(sym)
            continue
        local = CleaningReport()
        try:
            df = load_symbol(os.path.join(DATA_DIR, fname), sym, local)
        except Exception:
            dropped.append(sym)
            continue
        if len(df) < 1000:
            dropped.append(sym)
            continue
        rep.merge(local)
        closes[sym] = df["close"].rename(sym)
        vols[sym] = df["vol"].rename(sym)

    rep.excluded_symbols.extend(dropped)
    close = pd.DataFrame(closes).sort_index()
    volume = pd.DataFrame(vols).reindex_like(close)
    _UNIVERSE = Universe(close, volume, list(close.columns), rep)
    return _UNIVERSE


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def vwap_panel(close: pd.DataFrame, volume: pd.DataFrame, period: int) -> pd.DataFrame:
    """Trailing volume-weighted mean close, computed with data up to and including t.

    Rolling VWAP is *not* the same as `cumsum(px*vol)/cumsum(vol)` — the latter would
    be anchored at the start of history and never decay. Here the window is exactly
    the last `period` bars, matching the catalog's rolling buffer.
    """
    pv = (close * volume).rolling(period, min_periods=period).sum()
    vv = volume.rolling(period, min_periods=period).sum()
    out = pv / vv.replace(0.0, np.nan)
    return out.where(vv > 0)


def deviation(close: pd.DataFrame, period: int) -> pd.DataFrame:
    """(close - vwap) / vwap, trailing, point-in-time."""
    v = vwap_panel(close, load().volume, period)
    return (close - v) / v


def eligible(dev: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Long leg of the catalog signal: dev < -threshold. 1 = flagged, else 0/NaN."""
    return (dev < -threshold).astype(float)


def momentum_6m(close: pd.DataFrame) -> pd.DataFrame:
    return close / close.shift(126) - 1.0


def build_score(
    close: pd.DataFrame, dev: pd.DataFrame, threshold: float, kind: str
) -> pd.DataFrame:
    """Cross-sectional score panel: higher = more attractive. NaN = not eligible.

    NaN (not 0) matters: `build_rebalance_weights` masks non-finite to -inf, so an
    ineligible name can never be selected no matter how the rest of the book sorts.
    """
    mask = eligible(dev, threshold)
    if kind == "mom":
        raw = momentum_6m(close)
    elif kind == "deep":
        raw = -dev
    else:
        raise ValueError(f"unknown score kind {kind!r}")
    return raw.where(mask > 0).rank(axis=1, pct=True, na_option="keep")


# --------------------------------------------------------------------------- #
# Cost shim for a true gross-of-everything run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ZeroCostModel:
    """Charges nothing. Used only to measure the gross-vs-net cost drag.

    `run_backtest` touches exactly one method on the cost model, so this is a
    complete substitute — and it lets us report *true* gross, not merely
    "statutory charges without slippage".
    """

    def all_in_round_trip_bps(self, notional: Decimal) -> Decimal:  # noqa: ARG002
        return Decimal("0")


BASE_COSTS = CostModel(segment="delivery", slippage_bps=5)
ONE_WAY_RATE = float(BASE_COSTS.all_in_round_trip_bps(Decimal(int(REF_POSITION_NOTIONAL)))) / 2 / 1e4
ROUND_TRIP_BPS = float(BASE_COSTS.all_in_round_trip_bps(Decimal(int(REF_POSITION_NOTIONAL))))


# --------------------------------------------------------------------------- #
# Metrics over a window
# --------------------------------------------------------------------------- #


@dataclass
class WindowResult:
    label: str
    metrics: Metrics
    avg_names: float
    gross_cagr: float
    gross_total: float
    avg_eligible: float
    cost_drag_annual: float
    annual_turnover: float


def _slice_metrics(
    label: str,
    returns: pd.Series,
    weights: pd.DataFrame,
    gross_returns: pd.Series,
    elig: pd.DataFrame,
    window: tuple[pd.Timestamp, pd.Timestamp],
) -> WindowResult:
    """Recompute metrics on `window` only, from a full-history backtest.

    The book is run over the whole history so factors are warm and the portfolio
    enters TEST already invested (a live book, not a cold start). Only the reported
    window is sliced. Parameters are never refit at the boundary.
    """
    lo, hi = window
    in_win = (returns.index >= lo) & (returns.index <= hi)
    r = returns.loc[in_win]
    g = gross_returns.loc[in_win]
    w = weights.loc[in_win]
    if r.empty:
        raise ValueError(f"empty window {label}")

    n = len(r)
    years = n / 244.0

    net_eq = float((1.0 + r).cumprod().iloc[-1])
    gross_eq = float((1.0 + g).cumprod().iloc[-1])

    # Turnover MUST be differenced on the *full* weight history and only then sliced.
    # Differencing after slicing makes the first in-window row NaN, which silently drops
    # one whole rebalance (a third of a monthly book-turn) from the reported turnover.
    turn_by_date = 0.5 * weights.diff().abs().sum(axis=1).fillna(0.0)
    turn = float(turn_by_date.loc[in_win].sum()) / years
    # Cost actually paid over the window, in normalised equity units, annualised the
    # same way the engine annualises it (total / years).
    drag = (gross_eq / net_eq - 1.0) / years if years > 0 else 0.0

    m = compute_metrics(
        r,
        annual_turnover=turn,
        cost_drag_annual=drag,
        trades_per_year=12.0 if years > 0 else 0.0,
    )

    return WindowResult(
        label=label,
        metrics=m,
        avg_names=float((w > 0).sum(axis=1).mean()),
        gross_cagr=gross_eq ** (1.0 / years) - 1.0 if years > 0 else 0.0,
        gross_total=gross_eq - 1.0,
        avg_eligible=float((elig.loc[r.index] > 0).sum(axis=1).mean()),
        cost_drag_annual=drag,
        annual_turnover=turn,
    )


def evaluate(
    close: pd.DataFrame,
    score: pd.DataFrame,
    dev: pd.DataFrame,
    threshold: float,
    window: tuple[pd.Timestamp, pd.Timestamp],
    label: str,
) -> WindowResult:
    """Run the net and gross backtests over full history, then slice to `window`."""
    res = run_backtest(close, score, BASE_COSTS, CFG, rebalance="M")
    gross = run_backtest(close, score, ZeroCostModel(), CFG, rebalance="M")
    return _slice_metrics(
        label, res.returns, res.weights, gross.returns, eligible(dev, threshold), window
    )


def full_backtest(close: pd.DataFrame, score: pd.DataFrame):
    """Raw net backtest over the full history (used for equity curves)."""
    return run_backtest(close, score, BASE_COSTS, CFG, rebalance="M")


# --------------------------------------------------------------------------- #
# Buy & hold, net of the same costs
# --------------------------------------------------------------------------- #


def buy_and_hold(close: pd.DataFrame, window: tuple[pd.Timestamp, pd.Timestamp]) -> pd.Series:
    """Equal-weight hold of the universe over `window`, net of entry cost.

    Mirrors the strategy's structure so the comparison is like-for-like: 90% deployed
    (same `cash_buffer`), equal weight across all names, one-way cost charged once on
    entry at the same `ONE_WAY_RATE` the engine charges per side. Nothing is sold
    inside the window, so one-way (not round-trip) is the exact charge.

    `panel.pct_change().mean(axis=1)` is the brief's mandated benchmark series.
    """
    lo, hi = window
    sub = close.loc[lo:hi]
    ew = sub.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    deployed = 1.0 - CFG.cash_buffer
    out = (deployed * ew).copy()
    out.iloc[0] -= deployed * ONE_WAY_RATE
    return out


# --------------------------------------------------------------------------- #
# Random-signal negative control
# --------------------------------------------------------------------------- #


def random_score(
    close: pd.DataFrame,
    rng: np.random.Generator,
    elig_counts: dict,
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Random eligibility mask matching our per-date eligible counts, then the same score.

    Only the *selection* is randomised — the score construction, the portfolio
    constraints, the rebalance dates and the costs are all identical. So any
    difference in outcome is attributable to the VWAP signal itself.
    """
    raw = momentum_6m(close)
    mask = pd.DataFrame(0.0, index=index, columns=raw.columns)
    for dt in index:
        k = elig_counts.get(dt, 0)
        if k <= 0:
            continue
        k = min(k, len(raw.columns))
        picks = rng.choice(len(raw.columns), size=k, replace=False)
        mask.loc[dt, raw.columns[picks]] = 1.0
    return raw.where(mask > 0).rank(axis=1, pct=True, na_option="keep")


def rebalance_dates(index: pd.DatetimeIndex, freq: str = "M") -> list[pd.Timestamp]:
    """First available trading day of each period — mirrors the engine's own choice."""
    keys = index.tz_localize(None).to_period(freq)
    s = pd.Series(index, index=index)
    return [g.index[0] for _, g in s.groupby(keys)]


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def row(w: WindowResult, name: str) -> str:
    m = w.metrics
    return (
        f"| {name:<26} | {m.cagr * 100:>7.2f}% | {m.sharpe:>6.2f} | "
        f"{m.max_drawdown * 100:>7.2f}% | {m.calmar:>6.2f} | "
        f"{w.annual_turnover:>5.2f}x | {w.cost_drag_annual * 100:>5.2f}% | "
        f"{w.avg_names:>5.1f} | {w.gross_cagr * 100:>7.2f}% |"
    )


HEADER = (
    "| variant                      |    CAGR | Sharpe |  MaxDD | Calmar | Turn |  Drag | names |  gross |"
)
SEP = "|" + "-" * (len(HEADER) - 2) + "|"


def composite_score(close: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(close)
