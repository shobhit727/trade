"""Shared harness for the `momentum_volatility` NSE validation.

Nothing here modifies src/. All paths are read-only.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

DATA_DIR = "data/nse"

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

#: Ranking key for the cross-sectional score: 126d trailing return (the brief's
#: recommended construction). Fixed across all variants — not a tuned parameter.
RANK_LB = 126

COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
PORT_CONFIG = PortfolioConfig()

_PANEL: pd.DataFrame | None = None
_SYMBOLS: list[str] | None = None


def get_panel() -> tuple[pd.DataFrame, list[str]]:
    """Load once and cache — `load_universe` re-reads 48 CSVs each call."""
    global _PANEL, _SYMBOLS
    if _PANEL is None:
        _PANEL, _SYMBOLS, _ = load_universe(DATA_DIR)
    return _PANEL, _SYMBOLS


# --------------------------------------------------------------------------- #
# Signal construction
# --------------------------------------------------------------------------- #


def roc_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised equivalent of `cryptobot.strategies.indicators.roc`.

    `roc(closes, period)` on a trailing window of length >= period+1 returns
    `(close[-1] - close[-period-1]) / close[-period-1]`, and NaN when
    `len(closes) <= period`. On a panel that is exactly `pct_change(period)`.
    """
    return panel.pct_change(period, fill_method=None)


def signal_panel(panel: pd.DataFrame, momperiod: int, threshold: float) -> pd.DataFrame:
    """Long branch only. 1.0 where ROC > threshold, NaN elsewhere.

    NaN (not 0.0) outside the flagged set is deliberate: `build_rebalance_weights`
    requires a finite score, and masking with NaN makes unflagged names
    *unselectable* rather than merely low-scored.
    """
    return roc_panel(panel, momperiod).where(
        roc_panel(panel, momperiod) > threshold
    )


def score_from_signal(panel: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Rank trailing 126d return among the names the signal flagged."""
    mom = panel / panel.shift(RANK_LB) - 1.0
    return mom.where(sig.notna()).rank(axis=1, pct=True)


def build_score(panel: pd.DataFrame, momperiod: int, threshold: float) -> pd.DataFrame:
    return score_from_signal(panel, signal_panel(panel, momperiod, threshold))


# --------------------------------------------------------------------------- #
# ATR-predicate equivalence guard
# --------------------------------------------------------------------------- #

_ATR_LB = 14  # MomentumVolConfig.period default
_ATR_MASK_CACHE: dict[str, pd.DataFrame] | None = None


def atr_zero_mask() -> pd.DataFrame:
    """Boolean panel: True where the strategy's `atr(...) > 0` predicate would FAIL.

    `src_atr` returns the mean of the last 14 true ranges, so `atr <= 0` iff every one
    of those 14 TRs is 0 (TR >= 0 always). Vectorised as a 14-bar rolling sum.
    Requires `len(closes) >= period + 1`, so the mask starts at the 15th row.
    """
    global _ATR_MASK_CACHE
    if _ATR_MASK_CACHE is not None:
        return _ATR_MASK_CACHE

    h = hi_panel()
    low = lo_panel()
    c = close_panel()
    prev = c.shift(1)
    tr = pd.concat([h - low, (h - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    mask = (tr <= 0).rolling(_ATR_LB, min_periods=_ATR_LB).sum() == _ATR_LB
    _ATR_MASK_CACHE = mask.fillna(False)
    return _ATR_MASK_CACHE


_OHLC_CACHE: dict[str, pd.DataFrame] | None = None


def _load_ohlc() -> dict[str, pd.DataFrame]:
    global _OHLC_CACHE
    if _OHLC_CACHE is None:
        from nsealgo.data.loader import load_symbol

        panel_cols = get_panel()[0].columns
        store: dict[str, pd.DataFrame] = {}
        for s in panel_cols:
            d = load_symbol(os.path.join(DATA_DIR, f"{s}_1d.csv"), s)
            store[s] = d[["high", "low", "close"]]
        _OHLC_CACHE = store
    return _OHLC_CACHE


def hi_panel() -> pd.DataFrame:
    return pd.DataFrame({s: d["high"] for s, d in _load_ohlc().items()})


def lo_panel() -> pd.DataFrame:
    return pd.DataFrame({s: d["low"] for s, d in _load_ohlc().items()})


def close_panel() -> pd.DataFrame:
    return pd.DataFrame({s: d["close"] for s, d in _load_ohlc().items()})


def assert_atr_tautology(start, end, tag: str) -> int:
    """Fail loudly if the ATR predicate could gate anything inside [start, end].

    The score is built ROC-only. That is a *simplification* of the source strategy, and
    it is only legitimate while `atr > 0` holds on every bar of the window. Rather than
    trust the prose in REPORT.md, this re-checks it on every run — if a future data
    refresh introduces a frozen series inside TEST, the run aborts instead of silently
    reporting a number for a strategy that is no longer the one being tested.
    """
    m = atr_zero_mask()
    idx = (m.index >= start) & (m.index <= end)
    n = int(m.loc[idx].to_numpy().sum())
    if n:
        offenders = m.loc[idx].sum()
        offenders = offenders[offenders > 0]
        raise AssertionError(
            f"[{tag}] atr<=0 on {n} bar-endpoints inside the window -- the ROC-only "
            f"score is NOT equivalent to the source signal. Offenders: "
            f"{offenders.to_dict()}"
        )
    return n


# --------------------------------------------------------------------------- #
# Windowing
# --------------------------------------------------------------------------- #


def slice_window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    return df.loc[(df.index >= start) & (df.index <= end)]


def train_parts(panel: pd.DataFrame, momperiod: int, threshold: float):
    """Features on the FULL panel, then sliced — so TRAIN starts warm.

    Trailing features at 2016-01-01 only ever read 2015 bars, so this introduces
    no lookahead; it just avoids a spurious NaN gap at the window boundary.
    """
    sc = build_score(panel, momperiod, threshold)
    p = slice_window(panel, TRAIN_START, TRAIN_END)
    return p, slice_window(sc, TRAIN_START, TRAIN_END)


def test_parts(panel: pd.DataFrame, momperiod: int, threshold: float):
    sc = build_score(panel, momperiod, threshold)
    p = slice_window(panel, TEST_START, TEST_END)
    return p, slice_window(sc, TEST_START, TEST_END)


# --------------------------------------------------------------------------- #
# Benchmark scores (fixed construction, never tuned)
# --------------------------------------------------------------------------- #


def buy_hold_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Same 22-name / 12% / 25%-sector / 10%-cash book, chosen once, then held.

    Apples-to-apples with the strategy: identical constraints and identical costs,
    so any difference is attributable to the *signal*, not to the risk wrapper.
    """
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns)


def random_score(panel: pd.DataFrame, long_frac: float, seed: int) -> pd.DataFrame:
    """Negative control: a coin flip with the same fraction of names long."""
    rng = np.random.default_rng(seed)
    mask = rng.random(panel.shape) < long_frac
    sig = pd.DataFrame(np.where(mask, 1.0, np.nan), index=panel.index,
                       columns=panel.columns)
    return score_from_signal(panel, sig)


def composite_score(panel: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(panel)


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


@dataclass
class Run:
    name: str
    metrics: object
    result: object
    long_frac: float
    panel: pd.DataFrame

    def gross_cagr(self) -> float:
        """CAGR of the same weight stream with costs removed.

        Reconstructed from `result.weights` rather than by re-running with
        slippage=0, so it is exactly the gross the engine charged against.
        """
        rets = self.panel.pct_change(fill_method=None).fillna(0.0)
        gross = (self.result.weights.shift(1).fillna(0.0) * rets).sum(axis=1)
        eq = (1.0 + gross).cumprod()
        years = len(eq) / 244
        return float(eq.iloc[-1] ** (1.0 / years) - 1.0)

    def row(self) -> dict:
        m = self.metrics
        return {
            "name": self.name,
            "cagr": m.cagr,
            "sharpe": m.sharpe,
            "maxdd": m.max_drawdown,
            "calmar": m.calmar,
            "vol": m.volatility,
            "turnover": m.annual_turnover,
            "cost_drag": m.cost_drag_annual,
            "avg_names": self.result.diag["avg_names"],
            "max_weight": self.result.diag["avg_top_weight"],
            "trades": m.trades_per_year,
            "gross_cagr": self.gross_cagr(),
            "long_frac": self.long_frac,
            "n_rebal": self.result.diag["n_rebalances"],
            "total_return": m.total_return,
        }


def run(panel: pd.DataFrame, score: pd.DataFrame, name: str,
        long_frac: float = float("nan")) -> Run:
    res = run_backtest(panel, score, COST_MODEL, PORT_CONFIG, rebalance="M")
    return Run(name=name, metrics=res.metrics, result=res,
               long_frac=long_frac, panel=panel)


def metrics_from_returns(daily: pd.Series, name: str) -> dict:
    eq = (1.0 + daily).cumprod()
    m = compute_metrics(daily, eq)
    years = len(eq) / 244
    return {
        "name": name,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "total_return": m.total_return,
        "years": years,
    }


def out(name: str, obj) -> str:
    os.makedirs("research/agent_momvol", exist_ok=True)
    path = f"research/agent_momvol/{name}"
    if isinstance(obj, (pd.DataFrame, pd.Series)):
        obj.to_csv(path)
    else:
        import json

        with open(path, "w") as fh:
            json.dump(obj, fh, indent=2, default=str)
    return path
