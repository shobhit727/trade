"""Shared harness for the breakout_momentum NSE validation.

Reuses nsealgo infrastructure only (loader, costs, engine, metrics, factors).
Does not modify anything under src/.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import (  # noqa: E402
    CleaningReport,
    load_symbol,
    load_universe,
)
from nsealgo.factors.core import build_composite_score  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data", "nse")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- THE SPLIT (non-negotiable, brief §4) ---------------------------------- #
TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
PORTFOLIO = PortfolioConfig()

#: Plausibility ceiling from brief §6.1. An unlevered long-only NIFTY-50 book
#: cannot beat this; anything above is a bug, not alpha.
PLAUSIBLE_CAGR_CEILING = 0.50


@dataclass
class Universe:
    """Aligned OHLC panels over exactly the symbols `load_universe` retains."""

    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    symbols: list[str]
    report: CleaningReport


def load_ohlc_universe(data_dir: str = DATA_DIR) -> Universe:
    """Close panel from `load_universe` (the mandatory path) + aligned high/low.

    `load_universe` only returns closes, but a Donchian channel needs highs and
    lows. Rather than re-implement the C1-C7 cleaning rules, each symbol is re-read
    through `load_symbol` -- the *same* cleaning function `load_universe` calls --
    and then restricted to the symbols `load_universe` actually retained, so the
    OHLC panels cannot disagree with the close panel about which rows survive.
    """
    panel, symbols, report = load_universe(data_dir)

    keep = set(symbols)
    high: dict[str, pd.Series] = {}
    low: dict[str, pd.Series] = {}
    for sym in sorted(keep):
        df = load_symbol(os.path.join(data_dir, f"{sym}_1d.csv"), sym)
        high[sym] = df["high"].rename(sym)
        low[sym] = df["low"].rename(sym)

    highs = pd.DataFrame(high).reindex(panel.index)
    lows = pd.DataFrame(low).reindex(panel.index)

    # A symbol listed later has NaN highs before its listing. That is a genuine
    # "not tradeable yet", not a data error -- it is left as NaN and excluded from
    # the tradable universe downstream, never forward-filled from the future.
    return Universe(panel, highs, lows, list(panel.columns), report)


#: Prices in the panel are vendor back-adjusted floats. A handful of bars carry
#: 1-ULP disagreements between the close and high/low columns (~1e-13 relative),
#: e.g. tcs 2009-10-13 close=198.68550109863280 vs low=198.68550109863284.
#: These are arithmetic noise, not inverted bars, so the OHLC range check compares
#: at this relative tolerance. Disclosed in the report.
OHLC_REL_TOL = 1e-9


def assert_ohlc_aligned(u: Universe) -> tuple[int, int]:
    """Fail loudly if the OHLC panels drifted from the close panel.

    Returns ``(n_bars, n_float_noise_bars)`` so the noise count can be reported.
    """
    assert list(u.close.columns) == list(u.high.columns) == list(u.low.columns)
    assert u.close.index.equals(u.high.index)
    assert u.close.index.equals(u.low.index)
    c, h, lo = u.close, u.high, u.low
    finite = c.notna() & h.notna() & lo.notna()
    tol = OHLC_REL_TOL * c.abs()
    bad_up = int(((c > h + tol) & finite).sum().sum())
    bad_dn = int(((c < lo - tol) & finite).sum().sum())
    noise = int((((c > h) & finite) | ((c < lo) & finite)).sum().sum())
    assert bad_up == 0, f"{bad_up} bars with close > high (beyond float tolerance)"
    assert bad_dn == 0, f"{bad_dn} bars with close < low (beyond float tolerance)"
    assert int(finite.sum().sum()) > 0, "no finite OHLC rows at all"
    return int(finite.sum().sum()), noise


# --------------------------------------------------------------------------- #
# Signal construction -- faithful port of the catalog strategy
# --------------------------------------------------------------------------- #
#
# catalog: BreakoutMomentumStrategy
#   hh = donchian_high(highs, period)      # max of highs[-period:]  -- INCLUDES today
#   m  = roc(closes, mom_period)           # close/close[-mom] - 1
#   long  if close[-1] >= hh and m > 0
#   short if close[-1] <= ll and m < 0
#
# Two things must be handled explicitly for NSE:
#   1. The short leg is dropped. A Zerodha delivery account cannot short.
#   2. `donchian_high` includes TODAY's bar, so `close >= hh` can only hold when
#      today is the window max AND today's close equals today's high. That is a
#      "closed exactly at the high of the day" condition, not a channel breakout.
#      Both readings are declared as variants below.


def donchian_high_incl(high: pd.DataFrame, period: int) -> pd.DataFrame:
    """Rolling max of highs over `period` bars, INCLUDING the current bar."""
    return high.rolling(period, min_periods=period).max()


def donchian_high_excl(high: pd.DataFrame, period: int) -> pd.DataFrame:
    """Rolling max of highs over `period` bars EXCLUDING the current bar.

    This is the textbook Donchian channel: today's close versus the prior
    `period` bars' highs. `.shift(1)` moves the window strictly into the past, so
    it cannot import information from the decision bar.
    """
    return high.rolling(period, min_periods=period).max().shift(1)


def roc_panel(close: pd.DataFrame, period: int) -> pd.DataFrame:
    """Rate of change over `period` bars: close / close.shift(period) - 1."""
    return close / close.shift(period) - 1.0


def signal_long(
    u: Universe,
    period: int,
    mom_period: int,
    channel: str = "incl",
    mom_floor: float = 0.0,
) -> pd.DataFrame:
    """Boolean panel: True on bars where the long leg fires.

    All inputs are trailing (today's bar included, never a future bar), so a
    decision on day t uses data up to and including t -- which is what
    `run_backtest`'s one-bar weight lag then converts into a t+1 fill.

    channel:
        "incl" -- faithful to the catalog (`highs[-period:]`, today's bar included)
        "excl" -- prior-`period` channel, the standard Donchian reading
    mom_period:
        ROC lookback in bars. ``0`` means **no ROC filter at all** (the catalog's
        `m > 0` conjunct is dropped), which is how variant 3 tests whether the
        momentum filter earns its place.
    mom_floor:
        minimum ROC required, strict, per the catalog (`m > mom_floor`).
    """
    ch = donchian_high_incl if channel == "incl" else donchian_high_excl
    chmax = ch(u.high, period)
    breakout = (u.close >= chmax) & chmax.notna()
    if mom_period <= 0:
        return breakout
    roc = roc_panel(u.close, mom_period)
    return breakout & (roc > mom_floor) & roc.notna()


def signal_pct_long(sig: pd.DataFrame) -> float:
    """Fraction of *finite* symbol-bars where the strategy wants to be long."""
    return float(sig.to_numpy(dtype=float).mean())


def score_from_signal(
    u: Universe,
    sig: pd.DataFrame,
    rank_lookback: int = 126,
) -> pd.DataFrame:
    """Cross-sectional score: trailing momentum percentile rank among flagged names.

    A Donchian flag says "something is breaking out here"; it says nothing about
    which of the flags is best. Ranking the flagged names by trailing momentum
    turns a per-symbol binary into the cross-sectional ordering a long-only
    22-name book can actually hold. Unflagged names get NaN, which
    `build_rebalance_weights` treats as untradable -- no imputation, no leak.
    """
    mom = u.close / u.close.shift(rank_lookback) - 1.0
    return mom.where(sig).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame) -> pd.Series:
    """Equal-weight buy-and-hold daily return series -- the brief §4 rule 5 bar.

    Costs are applied identically to a monthly-rebalanced strategy: one full
    rotation in and out (turnover 1.0) at the start, charged at the same
    all-in round-trip bps the engine uses.
    """
    rets = panel.pct_change(fill_method=None).fillna(0.0)
    rate = float(COST_MODEL.all_in_round_trip_bps(100_000)) / 10_000.0
    daily = rets.mean(axis=1)
    # Entry cost charged on day 1 of the window; everything else is frictionless
    # carry. Same statutory stack, same notional convention as run_backtest.
    daily.iloc[0] -= rate
    return daily


def random_signal(
    u: Universe,
    target_pct_long: float,
    seed: int,
) -> pd.DataFrame:
    """Negative control: same bar-level long rate, random names, no information.

    Bernoulli(p) per finite symbol-bar with a fixed seed, then the *same*
    momentum ranking applied, so the only difference from the strategy is which
    names are flagged. Isolates "is the Donchian flag informative" from "does a
    momentum tilt work at all".
    """
    rng = np.random.default_rng(seed)
    a = u.close.to_numpy(dtype=float)
    finite = np.isfinite(a)
    draw = rng.random(a.shape) < target_pct_long
    return pd.DataFrame(draw & finite, index=u.close.index, columns=u.close.columns)


# --------------------------------------------------------------------------- #
# Backtest plumbing
# --------------------------------------------------------------------------- #


def run(
    u: Universe,
    score: pd.DataFrame,
    start,
    end,
    config: PortfolioConfig = PORTFOLIO,
    rebalance: str = "M",
) -> dict:
    """Run the engine on a window and flatten the result for reporting."""
    sl = (slice(start, end),)
    pnl = u.close.loc[sl[0]]
    sc = score.loc[sl[0]]
    res = run_backtest(pnl, sc, COST_MODEL, config=config, rebalance=rebalance)
    m = res.metrics
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "max_dd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "total_return": m.total_return,
        "annual_turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "trades_per_year": m.trades_per_year,
        "avg_names": res.diag["avg_names"],
        "avg_top_weight": res.diag["avg_top_weight"],
        "n_rebalances": res.diag["n_rebalances"],
        "win_rate": m.win_rate,
        "round_trip_bps": res.diag["round_trip_bps"],
        "_returns": res.returns,
        "_equity": res.equity,
        "_weights": res.weights,
        "_metrics": m,
    }


def bench_run(u: Universe, start, end) -> dict:
    """Buy-and-hold over the identical window, net of the identical cost stack."""
    daily = buy_and_hold(u.close.loc[start:end])
    eq = (1.0 + daily).cumprod()
    years = max(len(eq) / 244.0, 1e-9)
    rate = float(COST_MODEL.all_in_round_trip_bps(100_000)) / 10_000.0
    m = compute_metrics(daily, eq, cost_drag_annual=rate / years, annual_turnover=1.0 / years)
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "max_dd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "total_return": m.total_return,
        "win_rate": m.win_rate,
        "annual_turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "_returns": daily,
        "_equity": eq,
    }


def composite_run(u: Universe, start, end) -> dict:
    """The nsealgo production composite on the same panel and window."""
    sc = build_composite_score(u.close.loc[start:end])
    return run(u, sc, start, end)


def yearly(returns: pd.Series) -> pd.Series:
    return yearly_returns(returns)


def fmt_row(label: str, r: dict) -> str:
    return (
        f"{label:<26} CAGR {r['cagr'] * 100:>7.2f}%  Sharpe {r['sharpe']:>6.2f}  "
        f"MaxDD {r['max_dd'] * 100:>7.2f}%  Calmar {r['calmar']:>6.2f}  "
        f"Turn {r['annual_turnover']:>5.2f}x/y  Cost {r['cost_drag'] * 100:>5.2f}%/y  "
        f"Names {r.get('avg_names', float('nan')):>5.1f}"
    )
