"""Shared harness for the CCI (mean-reversion) strategy on NSE NIFTY-50.

Everything here reuses `nsealgo` infrastructure: the same loader, the same cost
model, the same portfolio engine, the same metrics. Nothing in `src/` is modified.

The only thing implemented locally is a *vectorised* CCI, because the catalog
indicator `cryptobot.strategies.indicators.cci` is a streaming function over a
window and the panel needs one value per bar. `validate_cci_matches_catalog`
proves the vectorised version is numerically identical to the catalog original.
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
    build_rebalance_weights,
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
    load_symbol,
    load_universe,
)
from nsealgo.factors.core import (  # noqa: E402
    build_composite_score,
    equal_weight_market,
    rank_cross_sectional,
    zscore_cross_sectional,
)

# Re-exported for the scratch scripts, which import them from here rather than from
# `nsealgo` directly. Ruff's unused-import autofix stripped these once; do not let it
# strip them again — keep the __all__ below as the contract.
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
    "build_rebalance_weights",
    "compute_metrics",
    "equal_weight_market",
    "load_symbol",
    "load_universe",
    "rank_cross_sectional",
    "yearly_returns",
    "zscore_cross_sectional",
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

#: Same exclusions/min-bars as `load_universe`, so the symbol set matches exactly.
MIN_BARS = 1000
EXCLUDE = frozenset({"adanient"})


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


@dataclass
class Panels:
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    symbols: list[str]
    report: CleaningReport


_CACHE: dict[str, Panels] = {}


def load_panels(data_dir: str = DATA_DIR) -> Panels:
    """OHLC panels built with the loader's own binding cleaning rules (C1-C6).

    `load_universe` returns closes only, but CCI needs typical price = (H+L+C)/3,
    so we call `load_symbol` per file — the identical cleaning path — and keep H/L.
    """
    if data_dir in _CACHE:
        return _CACHE[data_dir]

    report = CleaningReport()
    o, h, lo, c = {}, {}, {}, {}
    dropped: list[str] = []

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith("_1d.csv"):
            continue
        sym = fname[: -len("_1d.csv")]
        if sym in EXCLUDE:
            dropped.append(sym)
            continue
        local = CleaningReport()
        try:
            df = load_symbol(os.path.join(data_dir, fname), sym, local)
        except DataIntegrityError:
            dropped.append(sym)
            continue
        if len(df) < MIN_BARS:
            dropped.append(sym)
            continue
        report.merge(local)
        o[sym] = df["open"]
        h[sym] = df["high"]
        lo[sym] = df["low"]
        c[sym] = df["close"]

    report.excluded_symbols.extend(dropped)
    panels = Panels(
        open=pd.DataFrame(o).sort_index(),
        high=pd.DataFrame(h).sort_index(),
        low=pd.DataFrame(lo).sort_index(),
        close=pd.DataFrame(c).sort_index().dropna(how="all"),
        symbols=sorted(c),
        report=report,
    )
    _CACHE[data_dir] = panels
    return panels


def typical_price(p: Panels) -> pd.DataFrame:
    """(high + low + close) / 3 — the CCI input."""
    return (p.high + p.low + p.close) / 3.0


# --------------------------------------------------------------------------- #
# Vectorised CCI — identical maths to cryptobot.strategies.indicators.cci
# --------------------------------------------------------------------------- #


def cci_panel(tp: pd.DataFrame, period: int) -> pd.DataFrame:
    """CCI with mean-absolute-deviation denominator, one value per bar.

    Catalog original (streaming, window = last ``period`` bars *including* the
    current one)::

        tp    = [(h+l+c)/3 for the last `period` bars]
        mean  = mean(tp)
        md    = mean(|tp - mean|)
        cci   = 0.0 if md == 0 else (tp[-1] - mean) / (0.015 * md)

    The mean-absolute-deviation term is *not* a plain rolling mean of |tp - its own
    rolling mean|, so the window is materialised explicitly via sliding_window_view.
    No lookahead: the window for bar t ends at t.
    """
    out = pd.DataFrame(np.nan, index=tp.index, columns=tp.columns)

    for col in tp.columns:
        a = tp[col].to_numpy(dtype=float)
        n = len(a)
        if n < period:
            continue
        win = np.lib.stride_tricks.sliding_window_view(a, period)  # (n-p+1, p)
        mean = win.mean(axis=1)
        md = np.abs(win - mean[:, None]).mean(axis=1)
        # md == 0 -> CCI is 0.0 (catalog behaviour). Computed via np.divide(where=)
        # rather than np.where so the zero denominator is never actually divided by.
        vals = np.zeros_like(md)
        np.divide(a[period - 1 :] - mean, 0.015 * md, out=vals, where=md != 0.0)
        out.iloc[period - 1 :, tp.columns.get_loc(col)] = vals

    return out


def validate_cci_matches_catalog(p: Panels, period: int = 20, n_probe: int = 60) -> dict:
    """Prove the vectorised CCI equals the catalog's streaming `cci()`.

    This is the check that matters: if the two disagree, every downstream number is
    about a different indicator than the one the catalog strategy trades.
    """
    from cryptobot.strategies.indicators import cci as catalog_cci

    tp = typical_price(p)
    vec = cci_panel(tp, period)

    rng = np.random.default_rng(0)
    hi = p.high
    lo = p.low
    cl = p.close
    cols = list(p.close.columns)
    probes: list[tuple[str, int]] = []
    for _ in range(n_probe):
        sym = cols[int(rng.integers(len(cols)))]
        t = int(rng.integers(period + 5, len(cl)))
        probes.append((sym, t))

    max_abs_err = 0.0
    n_checked = 0
    for sym, t in probes:
        s = slice(t - period, t + 1)
        got = float(
            catalog_cci(hi[sym].iloc[s].tolist(), lo[sym].iloc[s].tolist(),
                        cl[sym].iloc[s].tolist(), period)
        )
        exp = float(vec[sym].iloc[t])
        n_checked += 1
        if np.isnan(got) and np.isnan(exp):
            continue
        max_abs_err = max(max_abs_err, abs(got - exp))

    return {
        "period": period,
        "n_checked": n_checked,
        "max_abs_error": max_abs_err,
        "identical": bool(max_abs_err < 1e-9),
    }


# --------------------------------------------------------------------------- #
# Signal -> cross-sectional score
# --------------------------------------------------------------------------- #


def signal_panel(cci: pd.DataFrame, entry: float) -> pd.DataFrame:
    """The catalog signal, verbatim: +1 when CCI < -entry, -1 when CCI > +entry.

    Long-only book: the -1 (overbought, would-short) branch is not tradable, so it
    collapses into "not long". `signal_panel` keeps the raw sign for reporting;
    eligibility for the book is `> 0`.
    """
    sig = np.zeros(cci.shape, dtype=float)
    c = cci.to_numpy(dtype=float)
    sig[:] = np.where(
        np.isnan(c), 0.0, np.where(c > entry, -1.0, np.where(c < -entry, 1.0, 0.0))
    )
    return pd.DataFrame(sig, index=cci.index, columns=cci.columns)


def build_score(
    close: pd.DataFrame,
    cci: pd.DataFrame,
    entry: float,
    rank_by: str = "mom126",
    lookback: int = 126,
) -> pd.DataFrame:
    """Turn the per-symbol CCI signal into a cross-sectional score.

    Following research/AGENT_BRIEF.md section 5: among the names the strategy
    flags, rank by trailing momentum. Unflagged names are NaN, which makes them
    ineligible — the engine therefore only ever buys flagged names.

    `rank_by="deepest"` is the strategy-faithful alternative: among flagged names,
    buy the most oversold (lowest CCI) rather than the strongest recent performer.
    """
    sig = signal_panel(cci, entry)
    eligible = sig > 0

    if rank_by == "deepest":
        raw = -cci
    elif rank_by.startswith("mom"):
        n = int(rank_by[3:])
        raw = close / close.shift(n) - 1.0
    else:
        raise ValueError(f"unknown rank_by: {rank_by}")

    return raw.where(eligible)


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
    long_frac: float


def run_variant(
    name: str,
    panel: pd.DataFrame,
    score: pd.DataFrame,
    rebalance: str = "M",
    long_frac: float | None = None,
) -> Run:
    res = run_backtest(panel, score, COST, CONFIG, rebalance=rebalance)
    return Run(
        name=name,
        metrics=res.metrics,
        diag=res.diag,
        equity=res.equity,
        returns=res.returns,
        avg_names=float(res.diag["avg_names"]),
        long_frac=float("nan") if long_frac is None else long_frac,
    )


def equal_weight_score(panel: pd.DataFrame) -> pd.DataFrame:
    """A deliberately untilted book through the *same* engine and cost model.

    This is the honest market comparator: same 22-name cap, same 10% cash, same
    monthly rebalance, same costs. Comparing against an unconstrained index return
    would flatter the strategy by construction.
    """
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns)


def buy_and_hold(panel: pd.DataFrame) -> Run:
    """`panel.pct_change().mean(axis=1)` — the brief's literal market proxy.

    Costs: a buy-and-hold book pays one round trip at entry (11.92 bps at the
    engine's Rs 1,00,000 reference notional) and nothing thereafter. Charged here
    on day 1 so the comparison is net, not gross.
    """
    r = equal_weight_market(panel).fillna(0.0)
    rate = float(COST.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    eq, out = 1.0, []
    for i, x in enumerate(r.to_numpy()):
        eq *= 1.0 + float(x)
        if i == 0:
            eq *= 1.0 - rate
        out.append(eq)
    eqs = pd.Series(out, index=r.index)
    # Returns are rebuilt from the equity curve so the entry cost is visible in the
    # daily series (and therefore in Sharpe / MaxDD), not silently dropped.
    daily = eqs.pct_change().fillna(0.0)
    m = compute_metrics(daily, eqs)
    return Run("buy_and_hold_EW", m, {"avg_names": len(panel.columns)},
               eqs, daily, float(len(panel.columns)), 1.0)


def random_control(
    panel: pd.DataFrame,
    cci: pd.DataFrame,
    entry: float,
    long_frac: float,
    rebalance: str,
    n_seeds: int = 20,
) -> dict:
    """Random signal with the *same* long fraction. The minimum bar to clear.

    On each seed, an iid Bernoulli(long_frac) mask selects which names are eligible
    on the strategy's rebalance dates; everything downstream (ranking by momentum,
    inverse-vol scaling, caps, cash, turnover budget, costs) is identical.
    """
    sig = signal_panel(cci, entry)
    assert bool((sig > 0).to_numpy().any()), "strategy never long — liveness check"
    cagrs, sharpes, mdds = [], [], []
    for seed in range(n_seeds):
        rng = np.random.default_rng(1000 + seed)
        score = pd.DataFrame(
            rng.random(panel.shape) < long_frac, index=panel.index, columns=panel.columns
        )
        score = (panel / panel.shift(126) - 1.0).where(score)
        r = run_variant(f"rand{seed}", panel, score, rebalance=rebalance)
        cagrs.append(r.metrics.cagr)
        sharpes.append(r.metrics.sharpe)
        mdds.append(r.metrics.max_drawdown)
    return {
        "n_seeds": n_seeds,
        "long_frac": long_frac,
        "cagr_mean": float(np.mean(cagrs)),
        "cagr_median": float(np.median(cagrs)),
        "cagr_p05": float(np.percentile(cagrs, 5)),
        "cagr_p95": float(np.percentile(cagrs, 95)),
        "sharpe_mean": float(np.mean(sharpes)),
        "maxdd_mean": float(np.mean(mdds)),
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
