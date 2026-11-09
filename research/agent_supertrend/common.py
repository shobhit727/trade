"""Shared helpers for the `supertrend` NSE validation run.

Strategy under test
-------------------
Two readings of `src/cryptobot/strategies/catalog/supertrend_strategy.py`, both ported
here. See REPORT.md §0.2 for why the file as shipped is not Supertrend.

**V0 `as_shipped`** — the literal shipped signal, verbatim::

    b = atr(high, low, close, period)
    if b != b and len(closes) < period + 1:
        return 0
    return 1 if closes[-1] > closes[-2] else -1

`period` and `multiplier` are dead in this expression (see REPORT.md §0.2), so V0 is
zero-parameter. On the daily panel it reduces to `sign(close[t] - close[t-1])`.

**V1-V4 `supertrend`** — a correct ATR-banded trend filter using the class's own two
config knobs (`period`, `multiplier`). Recursion is causal: band and direction at bar
`t` depend only on bars <= t. No look-ahead.

ATR follows the repo's own `cryptobot.strategies.indicators.atr`: the plain mean of the
last `period` true ranges (SMA of TR, *not* Wilder's RMA). Matching the crypto reference
keeps the port honest rather than silently "improving" it.

Long-only: a `-1` signal means "not eligible today" (Indian delivery account cannot
short). The book is cross-sectional: rank trailing momentum among flagged names.

Everything vectorised over wide panels with strictly trailing windows.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    BacktestResult,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402
from nsealgo.factors.core import (  # noqa: E402
    equal_weight_market,
    trailing_return,
)

DATA = str(ROOT / "data" / "nse")

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

CACHE = Path(__file__).resolve().parent / "_ohlc_supertrend.pkl"

#: Score construction is FIXED across every parameter variant (REPORT.md §0.5), so the
#: only thing that varies between runs is the strategy's own (period, multiplier).
MOM_DAYS = 126

#: True-range series; identical definition to `cryptobot.strategies.indicators.atr`'s
#: internal `max(hi-lo, |hi-pc|, |lo-pc|)`.
def true_range(close, high, low):
    prev = close.shift(1)
    a = (high - low).to_numpy()
    b = (high - prev).abs().to_numpy()
    c = (low - prev).abs().to_numpy()
    out = np.maximum(np.maximum(a, b), c)
    return pd.DataFrame(out, index=close.index, columns=close.columns)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_ohlc():
    """Return (close, high, low) panels over `load_universe`'s symbol set.

    The close panel comes from the mandatory `load_universe` call (auditable cleaning
    rules C1-C8). High/low come from the same per-symbol `load_symbol` cleaning path
    restricted to exactly those symbols, so ATR is built on clean data.
    """
    if CACHE.exists():
        cached = pd.read_pickle(CACHE)
        return cached["close"], cached["high"], cached["low"]

    panel, symbols, report = load_universe(DATA)
    print(report.describe())
    print(
        f"UNIVERSE: {len(symbols)} symbols | {panel.index[0].date()} -> "
        f"{panel.index[-1].date()} | {len(panel)} bars"
    )

    hi, lo = {}, {}
    for sym in symbols:
        df = load_symbol(os.path.join(DATA, f"{sym}_1d.csv"), sym)
        hi[sym] = df["high"].rename(sym)
        lo[sym] = df["low"].rename(sym)
    high = pd.DataFrame(hi).reindex(panel.index)
    low = pd.DataFrame(lo).reindex(panel.index)

    out = {"close": panel, "high": high, "low": low}
    pd.to_pickle(out, CACHE)
    return panel, high, low


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def as_shipped_signal(close: pd.DataFrame) -> pd.DataFrame:
    """V0 — the literal catalog signal: sign of the one-day return.

    `+1` when close rose today, `-1` when it fell. Nothing else.
    """
    up = (close > close.shift(1)).to_numpy(dtype=float)
    dn = (close < close.shift(1)).to_numpy(dtype=float)
    sig = np.where(up, 1.0, np.where(dn, -1.0, 0.0))
    sig[0, :] = np.nan  # no prior close to compare
    return pd.DataFrame(sig, index=close.index, columns=close.columns)


def supertrend_signal(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    period: int,
    multiplier: float,
) -> pd.DataFrame:
    """Correct Supertrend: `+1` while in an uptrend, `-1` while in a downtrend.

    Per symbol, causal recursion (bar t uses only bars <= t):

        hl2  = (high + low) / 2
        bu   = hl2 + multiplier * ATR(period)
        bl   = hl2 - multiplier * ATR(period)
        fu[t] = bu[t] if (bu[t] < fu[t-1] or close[t-1] > fu[t-1]) else fu[t-1]
        fl[t] = bl[t] if (bl[t] > fl[t-1] or close[t-1] < fl[t-1]) else fl[t-1]
        up   flips false when close[t] <= fl[t], true when close[t] >= fu[t]

    The ATR is the plain mean of the last `period` true ranges, matching
    `cryptobot.strategies.indicators.atr` (this repo's own reference implementation).

    Bars before the ATR is defined (and the very first ATR bar, which has no previous
    band to compare against) return NaN = "no signal", not a confident flat.
    """
    c = close.to_numpy(dtype=float)
    h = high.to_numpy(dtype=float)
    lo_ = low.to_numpy(dtype=float)
    tr = true_range(close, high, low).to_numpy(dtype=float)

    out = np.full_like(c, np.nan)
    n, m = c.shape

    for j in range(m):
        cj, hj, lj, tj = c[:, j], h[:, j], lo_[:, j], tr[:, j]
        fu = np.full(n, np.nan)
        fl = np.full(n, np.nan)
        up = False
        for i in range(period, n):
            atr = np.mean(tj[i - period + 1: i + 1])
            if not np.isfinite(atr):
                continue
            hl2 = 0.5 * (hj[i] + lj[i])
            bu = hl2 + multiplier * atr
            bl = hl2 - multiplier * atr
            if i == period:
                fu[i], fl[i] = bu, bl
                # No prior band to compare, but the direction on the first defined bar
                # is still well defined by the raw bands.
                up = bool(cj[i] >= fu[i])
            else:
                fu[i] = bu if (bu < fu[i - 1] or cj[i - 1] > fu[i - 1]) else fu[i - 1]
                fl[i] = bl if (bl > fl[i - 1] or cj[i - 1] < fl[i - 1]) else fl[i - 1]
                if up:
                    if cj[i] <= fl[i]:
                        up = False
                else:
                    if cj[i] >= fu[i]:
                        up = True
            out[i, j] = 1.0 if up else -1.0

    return pd.DataFrame(out, index=close.index, columns=close.columns)


def momentum_score(close: pd.DataFrame, signal: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank of 126-day momentum, restricted to names the
    strategy flags `+1` today. Non-flagged names are NaN -> excluded from the book."""
    mom = trailing_return(close, MOM_DAYS)
    return mom.where(signal > 0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #


def base_costs() -> CostModel:
    """Delivery, 5 bps slippage. `run_backtest` charges all_in_round_trip_bps = 21.92."""
    return CostModel(segment="delivery", slippage_bps=5)


def cfg() -> PortfolioConfig:
    return PortfolioConfig(n_positions=22)


def window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    return df.loc[(df.index >= start) & (df.index <= end)]


def run(close, score, start, end, cm=None, config=None, rebalance="M") -> BacktestResult:
    """Backtest over [start, end].

    The score panel is computed over the FULL history and only then sliced, so a window
    that starts mid-history is not blinded by a synthetic warm-up hole (a 126-day
    momentum computed from scratch at 2016-01-01 would leave the first ~6 months of
    TRAIN uninvested). The engine drops the first rebalance date anyway.
    """
    p = window(close, start, end)
    s = window(score, start, end)
    return run_backtest(p, s, cm or base_costs(), config or cfg(), rebalance=rebalance)


def gross_returns(result: BacktestResult, close: pd.DataFrame) -> pd.Series:
    """Pre-cost return series implied by the engine's own held weights.

    Same expression the engine uses internally (`held.shift(1) * rets`), so the gap
    against the net series is exactly the cost drag — no re-implementation risk.
    """
    px = close.reindex(result.weights.index)
    rets = px.pct_change(fill_method=None).fillna(0.0)
    return (result.weights.shift(1).fillna(0.0) * rets).sum(axis=1)


def summarise(result: BacktestResult, close: pd.DataFrame, label: str) -> dict:
    g = gross_returns(result, close)
    gm = compute_metrics(g)
    m = result.metrics
    held = result.weights
    live = held > 0
    return {
        "label": label,
        "n_periods": m.n_periods,
        "total_return": m.total_return,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "calmar": m.calmar,
        "max_drawdown": m.max_drawdown,
        "max_drawdown_days": m.max_drawdown_days,
        "vol": m.volatility,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "gross_cagr": gm.cagr,
        "gross_sharpe": gm.sharpe,
        "avg_names": float(live.sum(axis=1).mean()),
        "max_names": int(live.sum(axis=1).max()),
        "avg_invested": float(held.sum(axis=1).mean()),
        "avg_top_weight": result.diag["avg_top_weight"],
        "n_rebalances": result.diag["n_rebalances"],
        "round_trip_bps": result.diag["round_trip_bps"],
    }


def buy_and_hold(close: pd.DataFrame, start, end, cm=None):
    """Equal-weight buy & hold of the whole universe, charged one full round trip.

    The book is entered once and held, so the only turnover is at entry and exit —
    the honest benchmark, because the strategy pays a round trip on every rebalance.
    Uses `equal_weight_market` (i.e. `panel.pct_change().mean(axis=1)`) exactly as
    brief §4.5 prescribes.
    """
    cm = cm or base_costs()
    p = window(close, start, end)
    daily = equal_weight_market(p).fillna(0.0)
    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    eq = 1.0
    out = []
    for i in range(len(p.index)):
        prev = eq
        if i == 0:
            eq *= 1.0 - rate  # entry: bought once and held
        eq *= 1.0 + float(daily.iloc[i])
        out.append(eq / prev - 1.0)
    r = pd.Series(out, index=p.index)
    equity = (1.0 + r).cumprod()
    m = compute_metrics(r, equity)
    years = max(len(r) / 244, 1e-9)
    gross_factor = (1.0 + rate) * (1.0 + m.total_return)
    return {
        "label": "buy_and_hold_equal_weight",
        "n_periods": m.n_periods,
        "total_return": m.total_return,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "calmar": m.calmar,
        "max_drawdown": m.max_drawdown,
        "max_drawdown_days": m.max_drawdown_days,
        "vol": m.volatility,
        "turnover": 2.0,
        "cost_drag": rate / years,
        "gross_cagr": gross_factor ** (1.0 / years) - 1.0,
        "gross_sharpe": compute_metrics(
            equal_weight_market(p).fillna(0.0)
        ).sharpe,
        "avg_names": float(p.notna().sum(axis=1).mean()),
        "max_names": int(p.notna().sum(axis=1).max()),
        "avg_invested": 1.0,
        "avg_top_weight": float(1.0 / max(p.notna().sum(axis=1).max(), 1)),
        "n_rebalances": 1,
        "returns": r,
    }


def random_control(
    close: pd.DataFrame,
    n_eligible: pd.Series,
    start,
    end,
    seeds: int = 30,
    seed0: int = 12345,
) -> list[dict]:
    """Random-signal control with the SAME number of names eligible on every rebalance.

    Uniformly random names, uniformly random scores, otherwise an identical pipeline
    (same weight builder, same turnover budget, same costs) — so turnover and cost drag
    match the strategy's and the only difference is whether the selection carries
    information.
    """
    p = window(close, start, end)
    rng_master = np.random.default_rng(seed0)
    rb_idx = p.index.to_series().groupby(
        p.index.tz_localize(None).to_period("M")
    ).apply(lambda g: g.index[0])
    dates = pd.DatetimeIndex(rb_idx.to_numpy())
    out = []
    for s_i in range(seeds):
        rng = np.random.default_rng(rng_master.integers(0, 2**32))
        block = np.full((len(dates), p.shape[1]), np.nan)
        for i, d in enumerate(dates):
            k = int(n_eligible.get(d, 0))
            if k <= 0:
                continue
            cols = rng.choice(p.shape[1], size=min(k, p.shape[1]), replace=False)
            block[i, cols] = rng.random(len(cols))
        score = pd.DataFrame(block, index=dates, columns=p.columns).reindex(p.index)
        assert len(score) == len(p), "score index must span the whole panel"
        res = run_backtest(p, score, base_costs(), cfg(), rebalance="M")
        out.append(summarise(res, close, f"random_seed_{s_i}"))
    return out


def fmt_row(row: dict) -> str:
    return (
        f"{row['label']:<28} CAGR {row['cagr'] * 100:>7.2f}%  Sharpe {row['sharpe']:>6.2f}  "
        f"MaxDD {row['max_drawdown'] * 100:>7.2f}%  Calmar {row['calmar']:>6.2f}  "
        f"Turn {row['turnover']:>5.2f}x  Drag {row['cost_drag'] * 100:>5.2f}%  "
        f"Names {row['avg_names']:>4.1f}  grossCAGR {row['gross_cagr'] * 100:>7.2f}%"
    )


def year_table(strategy_returns, bench_returns) -> pd.DataFrame:
    y = pd.concat(
        [
            yearly_returns(strategy_returns).rename("strategy"),
            yearly_returns(bench_returns).rename("equal_weight"),
        ],
        axis=1,
    )
    y["alpha"] = y["strategy"] - y["equal_weight"]
    return y
