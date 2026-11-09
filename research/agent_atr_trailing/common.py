"""Shared helpers for the atr_trailing_stop NSE validation run.

Strategy under test (verbatim logic from
`src/cryptobot/strategies/catalog/atr_trailing_stop.py`):

    b = ATR(high, low, close, period)            # mean of last `period` true ranges
    m = SMA(close, period)
    signal = +1 if close > m + mult*b else (-1 if close < m - mult*b else 0)

The catalog name says "trailing stop"; the implementation is a volatility-normalised
*breakout band* around an SMA. The code is the contract, so the code is what is
ported here. Shorts (-1) are untradeable in an Indian delivery account, so the book
is long-only and `-1` simply means "not eligible today".

Everything is vectorised over a wide panel. ATR/SMA use strictly trailing windows, so
the value on day t uses only bars <= t: no look-ahead.
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
from nsealgo.factors.core import build_composite_score, trailing_return  # noqa: E402

DATA = str(ROOT / "data" / "nse")

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

CACHE = Path(__file__).resolve().parent / "_ohlc.pkl"

#: Score construction is FIXED across all parameter variants so that the only thing
#: that varies between runs is the strategy's own (period, multiplier).
MOM_DAYS = 126


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_ohlc():
    """Return (close, high, low) panels sharing `load_universe`'s symbol set.

    The close panel comes from the mandatory `load_universe` call (auditable
    cleaning). High/low come from the same per-symbol `load_symbol` cleaning path
    restricted to exactly those symbols, so ATR is built on clean data.
    """
    if CACHE.exists():
        cached = pd.read_pickle(CACHE)
        return cached["close"], cached["high"], cached["low"]

    panel, symbols, report = load_universe(DATA)
    print(report.describe())
    print(f"Universe: {len(symbols)} symbols | {panel.index[0].date()} -> "
          f"{panel.index[-1].date()} | {len(panel)} bars")

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


def true_range(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    prev = close.shift(1)
    a = (high - low).to_numpy()
    b = (high - prev).abs().to_numpy()
    c = (low - prev).abs().to_numpy()
    out = np.maximum(np.maximum(a, b), c)
    return pd.DataFrame(out, index=close.index, columns=close.columns)


def atr_trailing_signal(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    period: int,
    multiplier: float,
) -> pd.DataFrame:
    """Vectorised port of `AtrTrailingStrategy.signal`. Returns +1 / 0 / -1 panel."""
    b = true_range(close, high, low).rolling(period, min_periods=period).mean()
    m = close.rolling(period, min_periods=period).mean()
    band = multiplier * b
    sig = pd.DataFrame(
        np.where(close > m + band, 1.0, np.where(close < m - band, -1.0, 0.0)),
        index=close.index,
        columns=close.columns,
    )
    # Warmup / no-data bars are not a signal of "flat with conviction".
    valid = m.notna() & b.notna()
    return sig.where(valid, np.nan)


def momentum_score(close: pd.DataFrame, signal: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank of 6-month momentum, restricted to names the
    strategy flags +1 today. Non-flagged names are NaN -> excluded from the book."""
    mom = trailing_return(close, MOM_DAYS)
    return mom.where(signal > 0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #


def base_costs() -> CostModel:
    return CostModel(segment="delivery", slippage_bps=5)


def cfg() -> PortfolioConfig:
    return PortfolioConfig(n_positions=22)


def window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    return df.loc[(df.index >= start) & (df.index <= end)]


def run(close, score, start, end, cm=None, config=None, rebalance="M") -> BacktestResult:
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
        "vol": m.volatility,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "gross_cagr": gm.cagr,
        "avg_names": float(live.sum(axis=1).mean()),
        "max_names": int(live.sum(axis=1).max()),
        "avg_invested": float(held.sum(axis=1).mean()),
        "n_rebalances": result.diag["n_rebalances"],
    }


def buy_and_hold(close: pd.DataFrame, start, end, cm=None, config=None):
    """Equal-weight buy & hold of the whole universe, charged one full round trip.

    Charge model: the book is entered once (full round-trip bps) and then held, so
    the only turnover is at entry and exit. This is the honest benchmark — the
    strategy pays its round trip on every rebalance.
    """
    cm = cm or base_costs()
    p = window(close, start, end)
    rets = p.pct_change(fill_method=None).fillna(0.0)
    daily = rets.mean(axis=1)
    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    eq = 1.0
    out = []
    for i in range(len(p.index)):
        prev = eq
        if i == 0:
            eq *= 1.0 - rate  # entry: the book is bought once and held
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
        "vol": m.volatility,
        "turnover": 2.0,
        "cost_drag": rate / years,
        "gross_cagr": gross_factor ** (1.0 / years) - 1.0,
        "avg_names": float(p.notna().sum(axis=1).mean()),
        "max_names": int(p.notna().sum(axis=1).max()),
        "avg_invested": 1.0,
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
    """Random-signal control with the SAME number of names long on every rebalance.

    Uniform random names, random scores, otherwise identical pipeline (same weight
    builder, same turnover budget, same costs) — so turnover and cost drag match and
    the only difference is whether the selection carries information.
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
        # Built as a numpy block: `.loc` row/col assignment with integer keys
        # silently *appends* columns on this pandas version.
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
        row = summarise(res, close, f"random_seed_{s_i}")
        out.append(row)
    return out


def fmt_row(row: dict) -> str:
    return (
        f"{row['label']:<28} CAGR {row['cagr'] * 100:>7.2f}%  Sharpe {row['sharpe']:>6.2f}  "
        f"MaxDD {row['max_drawdown'] * 100:>7.2f}%  Calmar {row['calmar']:>6.2f}  "
        f"Turn {row['turnover']:>5.2f}x  Drag {row['cost_drag'] * 100:>5.2f}%  "
        f"Names {row['avg_names']:>4.1f}  grossCAGR {row['gross_cagr'] * 100:>7.2f}%"
    )


def composite(close: pd.DataFrame):
    return build_composite_score(close)


def year_table(result: BacktestResult, bench_returns: pd.Series) -> pd.DataFrame:
    y = pd.concat(
        [yearly_returns(result.returns).rename("strategy"),
         yearly_returns(bench_returns).rename("equal_weight")],
        axis=1,
    )
    y["alpha"] = y["strategy"] - y["equal_weight"]
    return y
