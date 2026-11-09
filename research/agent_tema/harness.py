"""Harness for the `tema` NSE validation.

What the source strategy is
---------------------------
`TemaStrategy.signal` = `+1 if close[-1] > TEMA(close, period) else -1`, i.e. a
price-vs-triple-EMA trend filter. `TemaConfig.period` is the only live parameter.
Verified numerically equal to `cryptobot.strategies.indicators.tema` in step0.

Construction into the NSE book
-----------------------------
Long-only delivery account: `-1` becomes **do not hold**, `+1` becomes **eligible**.
Eligible names are then ranked cross-sectionally by a trailing trend factor (the
brief's §5 construction). Without ranking, every signalled name ties at +1 and the
choice among them is arbitrary — the top-22 pick would then be alphabetical, i.e.
a silent survivorship/inception artifact.

No lookahead: TEMA at bar *t* uses closes ≤ *t*; ranking factors are trailing;
`run_backtest` holds weights decided at *t* from *t+1*.

Streaming-buffer fidelity
-------------------------
`SignalStrategy` feeds a `deque(maxlen=300)`, so the source EMA is re-seeded at the
oldest bar of a rolling 300-bar window every bar, rather than on full history. That is
a real (if small) semantic difference. `fidelity_check()` measures it instead of
assuming it away.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.costs import CostModel
from nsealgo.data.loader import load_universe
from nsealgo.factors.core import (
    build_composite_score,
    momentum_6m,
    momentum_12_1,
    trend_strength_200d,
)

#: Repo root, derived from this file's location, so every script works from any cwd.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data", "nse")
HERE = os.path.dirname(os.path.abspath(__file__))

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

REF_NOTIONAL = Decimal("100000")
COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
RT_BPS = float(COST_MODEL.all_in_round_trip_bps(REF_NOTIONAL))
ZERO_COST = CostModel(segment="delivery", slippage_bps=0.0)
ZERO_RT_BPS = float(ZERO_COST.all_in_round_trip_bps(REF_NOTIONAL))

PORTFOLIO = PortfolioConfig()

#: The source strategy's rolling buffer length (SignalStrategy maxlen default).
SOURCE_MAXLEN = 300

# --------------------------------------------------------------------------- #
# Declared variants (see REPORT.md §3 -- fixed before any run)
# --------------------------------------------------------------------------- #

RANKERS = {
    "mom6m": momentum_6m,
    "mom12_1": momentum_12_1,
    "trend200": trend_strength_200d,
}

VARIANTS: dict[str, dict] = {
    "V1": {"period": 20, "rank": "mom6m"},
    "V2": {"period": 50, "rank": "mom6m"},
    "V3": {"period": 100, "rank": "mom6m"},
    "V4": {"period": 20, "rank": "mom12_1"},
    "V5": {"period": 50, "rank": "trend200"},
}

_panel: pd.DataFrame | None = None


def load_panel() -> pd.DataFrame:
    global _panel
    if _panel is None:
        _panel, _syms, _ = load_universe(DATA_DIR)
    return _panel


# --------------------------------------------------------------------------- #
# Indicator + signal
# --------------------------------------------------------------------------- #


def _ema(a: np.ndarray, k: float) -> np.ndarray:
    out = np.empty(len(a), dtype=float)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1.0 - k) * out[i - 1]
    return out


def tema_column(values: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1.0)
    e1 = _ema(values, k)
    e2 = _ema(e1, k)
    e3 = _ema(e2, k)
    return 3.0 * e1 - 3.0 * e2 + e3


def tema_panel(panel: pd.DataFrame, period: int, maxlen: int | None = None) -> pd.DataFrame:
    """TEMA for every symbol, on the bars that symbol actually has.

    ``maxlen=None``  -> full-history recursion (standard EMA).
    ``maxlen=300``   -> faithful to `SignalStrategy`'s rolling buffer: at every bar the
                        EMA chain is re-seeded at the oldest bar of the trailing window.

    Both are computed per symbol on its *observed* bars (NaN rows dropped), because
    that is exactly the sequence a streaming `feed()` would receive. Rows where the
    symbol has no price are left NaN, not forward-filled.
    """
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns, dtype=float)
    for s in panel.columns:
        vals = panel[s].dropna().to_numpy(dtype=float)
        if len(vals) < period + 1:
            continue
        if maxlen is None or len(vals) <= maxlen:
            series = tema_column(vals, period)
        else:
            w = min(maxlen, len(vals))
            series = np.empty(len(vals), dtype=float)
            k = 2.0 / (period + 1.0)
            # Rolling-window re-seed. Computed with an explicit python loop because the
            # recursion is inherently sequential; cost is O(n * maxlen) per symbol and
            # only run in `fidelity_check`.
            for i in range(len(vals)):
                win = vals[max(0, i - w + 1) : i + 1]
                e1 = _ema(win, k)
                e2 = _ema(e1, k)
                e3 = _ema(e2, k)
                series[i] = 3.0 * e1[-1] - 3.0 * e2[-1] + e3[-1]
        out.loc[panel[s].dropna().index, s] = series
    return out


def signal_panel(panel: pd.DataFrame, period: int, maxlen: int | None = None) -> pd.DataFrame:
    """`+1` where close > TEMA, `-1` otherwise, `NaN` during warmup.

    Warmup is faithful to `TemaStrategy.warmup` = `period`: a symbol emits no signal
    until it has at least `period` observed bars.
    """
    t = tema_panel(panel, period, maxlen=maxlen)
    sig = np.sign(panel - t)
    warm = panel.notna().cumsum(axis=0) < period
    sig = sig.mask(warm)
    return sig


def build_score(panel: pd.DataFrame, period: int, ranker: str) -> pd.DataFrame:
    """Cross-sectional score: rank the TEMA-long names by trailing trend."""
    sig = signal_panel(panel, period)
    mom = RANKERS[ranker](panel)
    score = mom.where(sig > 0).rank(axis=1, pct=True)
    return score


def liveness(panel: pd.DataFrame, period: int) -> dict:
    sig = signal_panel(panel, period)
    valid = sig.notna()
    return {
        "frac_bars_long": float((sig > 0).sum().sum() / valid.sum().sum()),
        "frac_bars_short": float((sig < 0).sum().sum() / valid.sum().sum()),
        "mean_eligible_names": float((sig > 0).sum(axis=1).mean()),
        "median_eligible_names": float((sig > 0).sum(axis=1).median()),
        "min_eligible_names": float((sig > 0).sum(axis=1).min()),
    }


def fidelity_check(panel: pd.DataFrame, period: int = 20, n_sym: int = 3) -> dict:
    """Full-history TEMA vs the source's rolling-300-bar buffer."""
    syms = list(panel.columns)[:n_sym]
    res = {}
    for s in syms:
        full = tema_panel(panel[[s]], period).iloc[:, 0]
        roll = tema_panel(panel[[s]], period, maxlen=SOURCE_MAXLEN).iloc[:, 0]
        d = (full - roll).abs()
        rel = d / full.abs().clip(lower=1e-9)
        s_full = signal_panel(panel[[s]], period).iloc[:, 0]
        s_roll = signal_panel(panel[[s]], period, maxlen=SOURCE_MAXLEN).iloc[:, 0]
        res[s] = {
            "max_abs": float(d.max()),
            "max_rel": float(rel.max()),
            "p99_rel": float(rel.quantile(0.99)),
            "signal_disagreements": int((s_full != s_roll).sum()),
            "n_bars": int(full.notna().sum()),
        }
    return res


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


def slice_window(df: pd.DataFrame, start, end) -> pd.DataFrame:
    """Slice, but keep the history before `start` as *lookback only*.

    Indicators are computed on the full panel and then sliced -- never sliced first.
    A TEMA at 2016-01-04 must be allowed to see 2015 bars.
    """
    return df.loc[:end].loc[start:]


def run(panel, score, cost_model=COST_MODEL, config=PORTFOLIO, rebalance="M"):
    return run_backtest(panel, score, cost_model, config, rebalance)


def summarise(res, label: str) -> dict:
    m = res.metrics
    return {
        "label": label,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "calmar": m.calmar,
        "max_drawdown": m.max_drawdown,
        "vol": m.volatility,
        "total_return": m.total_return,
        "annual_turnover": m.annual_turnover,
        "cost_drag_annual": m.cost_drag_annual,
        "trades_per_year": m.trades_per_year,
        "avg_names": res.diag.get("avg_names", float("nan")),
        "rt_bps": res.diag.get("round_trip_bps", float("nan")),
        "final_equity": float(res.equity.iloc[-1]),
    }


def buy_and_hold(panel: pd.DataFrame, cost_model=COST_MODEL) -> dict:
    """Equal-weight buy-and-hold of the same universe, over the same window.

    Charged ONE round trip (entry + eventual exit) at the engine's own bps, which is
    the honest comparison for a strategy that also holds through the end of the window.
    Also reports the zero-cost version so cost drag is visible as a separate number.
    """
    px = panel.dropna(how="all")
    px = px.ffill()
    rets = px.pct_change(fill_method=None).fillna(0.0)
    eqw = rets.mean(axis=1)
    rate = float(cost_model.all_in_round_trip_bps(REF_NOTIONAL)) / 10_000.0
    # one entry cost, charged once on day 0, and one exit at the end
    net = (1.0 - rate) * (1.0 + eqw).cumprod() * (1.0 - rate)
    m = compute_metrics(net.pct_change(fill_method=None).fillna(0.0), net)
    gross = (1.0 + eqw).cumprod()
    m0 = compute_metrics(eqw, gross)
    return {
        "label": "buy_and_hold",
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "calmar": m.calmar,
        "max_drawdown": m.max_drawdown,
        "vol": m.volatility,
        "total_return": m.total_return,
        "cagr_gross": m0.cagr,
        "max_drawdown_gross": m0.max_drawdown,
        "cost_drag_annual": m0.cagr - m.cagr,
        "final_equity": float(net.iloc[-1]),
        "equity_net": net,
        "equity_gross": gross,
    }


def random_control(
    panel_full: pd.DataFrame,
    period: int,
    ranker: str,
    target_frac: float,
    seed: int,
    cost_model=COST_MODEL,
    long_frac: float | None = None,
    start=None,
    end=None,
) -> dict:
    """Random gate with the *same* per-symbol long-fraction as the real signal.

    This is the minimum bar in the brief §6.5: a coin flip that is long the same
    fraction of the time, ranked by the same factor, must be beaten.

    ``panel_full`` is the FULL panel: the ranking factor must be computed with its full
    lookback history and only *then* sliced to [start, end]. Computing it on an already
    sliced panel makes `momentum_12_1` NaN for the first 252 bars, which starves the
    control of candidates -- a bug that once cost this control 8 names of position.
    """
    rng = np.random.default_rng(seed)
    if long_frac is None:
        sig = signal_panel(panel_full, period)
        long_frac = (sig > 0).sum() / max(sig.notna().sum().sum(), 1)
    target = long_frac * target_frac
    mom = RANKERS[ranker](panel_full)          # full history
    if start is not None:
        mom = mom.loc[:end].loc[start:]
    gate = rng.random(mom.shape) < target
    score = mom.where(gate).rank(axis=1, pct=True)
    panel = panel_full.loc[:end].loc[start:] if start is not None else panel_full
    res = run_backtest(panel, score, cost_model, PORTFOLIO)
    out = summarise(res, f"random_seed{seed}")
    out["gate_target_frac"] = float(target)
    out["real_long_frac"] = float(long_frac)
    return out


def composite(panel_full: pd.DataFrame, cost_model=COST_MODEL, start=None, end=None) -> dict:
    """nsealgo composite. Factor history computed on the FULL panel, then sliced."""
    sc = build_composite_score(panel_full)
    if start is not None:
        sc = sc.loc[:end].loc[start:]
        panel = panel_full.loc[:end].loc[start:]
    else:
        panel = panel_full
    res = run_backtest(panel, sc, cost_model, PORTFOLIO)
    out = summarise(res, "nsealgo_composite")
    out["equity"] = res.equity
    out["returns"] = res.returns
    return out


def fmt(d: dict) -> str:
    return (
        f"{d['label']:<22} CAGR {d['cagr'] * 100:>7.2f}%  Sharpe {d['sharpe']:>6.2f}  "
        f"MaxDD {d['max_drawdown'] * 100:>7.2f}%  Calmar {d['calmar']:>6.2f}  "
        f"TO {d.get('annual_turnover', float('nan')):>5.2f}x  "
        f"Drag {d.get('cost_drag_annual', float('nan')) * 100:>5.2f}%/y  "
        f"names {d.get('avg_names', float('nan')):>5.1f}"
    )


def dump(obj, path: str) -> None:
    def default(o):
        if isinstance(o, (pd.Series, pd.DataFrame)):
            return None
        return str(o)

    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=default)
