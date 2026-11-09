"""Shared helpers for the `trend_volume_strategy` NSE study.

Signal is a faithful vectorised port of
`src/cryptobot/strategies/catalog/trend_volume_strategy.py`:

    sma_c = indicators.sma(closes, period)          -> rolling mean, trailing `period`
    avg_v = mean(volumes[-period:])                  -> rolling mean of VOLUME
    +1  if close > sma_c and volume > vol_ratio * avg_v
    -1  if close < sma_c and volume > vol_ratio * avg_v
     0  otherwise

Note the source's `avg` window *includes today's volume*. That is what the catalog code
does; it is ported faithfully rather than "fixed", because a study of this strategy must
test the strategy that exists. (It makes the volume leg slightly self-referential: the
threshold is inflated by 1/period of the quantity it is thresholding. Recorded as an
observation, not a change.)

The -1 branch has no meaning in an Indian delivery account (brief section 5: long-only,
never short), so the NSE adaptation is the LONG leg only:

    "hold a name on any day where close > SMA(period) AND volume > vol_ratio * SMA(volume, period)."

Construction (declared in REPORT.md section 3, brief section 5 recipe):
    score = (panel / panel.shift(126) - 1).where(signal > 0).rank(axis=1, pct=True)

`run_backtest` picks weights from the close of day t and holds from t+1, so the one-bar
lag that removes look-ahead is the engine's. No forward-fill from the future anywhere.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics, yearly_returns
from nsealgo.costs import CostModel
from nsealgo.provenance import provenance

SCRATCH = "research/agent_trendvol"

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

#: Brief section 3 mandate: full Indian delivery cost stack, 5 bps slippage.
#: run_backtest charges all_in_round_trip_bps(REF_POSITION_NOTIONAL) = 21.92 bps.
COST = CostModel(segment="delivery", slippage_bps=5)

#: Zero-cost control. CostModel now accepts float slippage, so this is exactly
#: round_trip_bps only (11.92 bps statutory), no slippage. Used to separate
#: "no edge" from "edge eaten by costs" -- never as the headline number.
COST_ZERO_SLIP = CostModel(segment="delivery", slippage_bps=0.0)

#: Brief section 5 / GOAL.md section 3.2 defaults. Never bypassed.
PORT = PortfolioConfig()

#: The DECLARED variant budget (REPORT.md section 2). Closed list, fixed before any run.
VARIANTS: dict[str, dict] = {
    "tv_p20_r12":  {"period": 20,  "vol_ratio": 1.2},
    "tv_p60_r12":  {"period": 60,  "vol_ratio": 1.2},
    "tv_p120_r12": {"period": 120, "vol_ratio": 1.2},
    "tv_p20_r10":  {"period": 20,  "vol_ratio": 1.0},
    "tv_p60_r10":  {"period": 60,  "vol_ratio": 1.0},
}

MOM_LOOKBACK = 126


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def load_panel() -> pd.DataFrame:
    return pd.read_pickle(f"{SCRATCH}/panel.pkl")


def load_vol() -> pd.DataFrame:
    return pd.read_pickle(f"{SCRATCH}/vol.pkl")


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #
def trend_volume_signal(
    close: pd.DataFrame, vol: pd.DataFrame, period: int, vol_ratio: float
) -> pd.DataFrame:
    """Vectorised port of TrendVolumeStrategy.signal(). Returns +1 / 0 / -1.

    NaN in either input propagates to 0, which matches the source: `if t != t`
    (the NaN guard on the SMA) returns 0, and so does any missing bar.
    """
    sma_c = close.rolling(period, min_periods=period).mean()
    avg_v = vol.rolling(period, min_periods=period).mean()
    hot = vol > avg_v * vol_ratio
    up = close > sma_c
    dn = close < sma_c
    sig = pd.DataFrame(0, index=close.index, columns=close.columns, dtype=int)
    sig[up & hot] = 1
    sig[dn & hot] = -1
    sig[close.isna()] = 0
    return sig


def signal_liveness(sig: pd.DataFrame, window: tuple[str, str]) -> dict[str, float]:
    """Section 6.3: what fraction of symbol-days is long, and how many names/day."""
    m = (sig.index >= window[0]) & (sig.index <= window[1])
    sub = sig.loc[m]
    per_day = (sub > 0).sum(axis=1)
    return {
        "sym_day_long_frac": float((sub > 0).to_numpy().mean()),
        "sym_day_short_frac": float((sub < 0).to_numpy().mean()),
        "sym_day_flat_frac": float((sub == 0).to_numpy().mean()),
        "avg_names_signalled_per_day": float(per_day.mean()),
        "median_names_signalled_per_day": float(per_day.median()),
        "pct_days_with_zero_signals": float((per_day == 0).mean()),
        "pct_days_under_5_signals": float((per_day < 5).mean()),
    }


# --------------------------------------------------------------------------- #
# Score construction
# --------------------------------------------------------------------------- #
def gated_momentum_score(
    panel: pd.DataFrame, sig: pd.DataFrame, lookback: int = MOM_LOOKBACK
) -> pd.DataFrame:
    """Brief section 5 recipe. Gate on signal > 0, rank survivors by 126d momentum."""
    mom = panel / panel.shift(lookback) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def soft_gate_score(
    panel: pd.DataFrame, sig: pd.DataFrame, lookback: int = MOM_LOOKBACK
) -> pd.DataFrame:
    """DECLARED DIAGNOSTIC ONLY (REPORT.md section 3).

    Momentum rank with signalled names boosted, instead of a hard gate. Used only to
    explain a negative result. Never reported as this strategy's performance.
    """
    mom = panel / panel.shift(lookback) - 1.0
    base = mom.rank(axis=1, pct=True)
    return base + 1.0 * (sig > 0).astype(float)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def slice_window(df: pd.DataFrame, window: tuple[str, str]) -> pd.DataFrame:
    return df.loc[(df.index >= window[0]) & (df.index <= window[1])]


def metrics_row(result, label: str) -> dict[str, float | str]:
    m = result.metrics
    return {
        "label": label,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "max_dd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "total_return": m.total_return,
        "annual_turnover": m.annual_turnover,
        "cost_drag_annual": m.cost_drag_annual,
        "trades_per_year": m.trades_per_year,
        "avg_names": result.diag.get("avg_names", float("nan")),
        "avg_top_weight": result.diag.get("avg_top_weight", float("nan")),
        "n_rebalances": result.diag.get("n_rebalances", 0),
        "round_trip_bps": result.diag.get("round_trip_bps", float("nan")),
        "costs_paid": result.costs_paid,
    }


def fmt_table(rows: list[dict], keys: list[str]) -> str:
    head = f"{'variant':<22}" + "".join(f"{k:>14}" for k in keys)
    lines = [head, "-" * len(head)]
    for r in rows:
        line = f"{str(r['label']):<22}"
        for k in keys:
            v = r.get(k, float("nan"))
            line += f"{v:>14.3f}" if isinstance(v, (int, float)) else f"{str(v):>14}"
        lines.append(line)
    return "\n".join(lines)


def buy_and_hold(panel: pd.DataFrame, window: tuple[str, str], cost: CostModel) -> dict:
    """Equal-weight buy-and-hold over the panel, net of the same cost stack.

    Charged once, on entry, as a full rotation (sum|dW| = 2.0) plus one monthly
    rebalance's worth of nothing -- the book never changes, so turnover is 2.0 total.
    The engine's convention is `cost = 2 * one_way_turnover * rate` where one-way
    turnover = sum|dW|/2; a single full rotation is one_way 1.0 -> cost = 2 * rate.
    """
    px = slice_window(panel, window)
    rets = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rt_bps = float(cost.all_in_round_trip_bps(100_000))
    rate = rt_bps / 10_000.0
    # One full entry: sell 0 -> buy 100% of the book, i.e. total turnover 2.0.
    total_turnover = 2.0
    cost_amt = total_turnover * rate
    eq = 1.0 - cost_amt
    equity, daily = [], []
    for r in rets.to_numpy():
        prev = eq
        eq *= 1.0 + float(r)
        daily.append(eq / prev - 1.0)
        equity.append(eq)
    equity = pd.Series(equity, index=px.index)
    daily = pd.Series(daily, index=px.index)
    years = max(len(equity) / 252.0, 1e-9)
    m = compute_metrics(daily, equity, annual_turnover=1.0 / years,
                        cost_drag_annual=cost_amt / years, trades_per_year=1.0 / years)
    return {
        "label": "buy_and_hold",
        "cagr": m.cagr, "sharpe": m.sharpe, "sortino": m.sortino,
        "max_dd": m.max_drawdown, "calmar": m.calmar, "vol": m.volatility,
        "total_return": m.total_return, "annual_turnover": 1.0 / years,
        "cost_drag_annual": cost_amt / years, "trades_per_year": 1.0 / years,
        "avg_names": float(px.notna().sum(axis=1).mean()),
        "round_trip_bps": rt_bps,
    }


def yearly_str(returns: pd.Series) -> str:
    yr = yearly_returns(returns)
    return "  ".join(f"{int(y)}:{v * 100:+.1f}%" for y, v in yr.items())


def save_json(obj, path: str) -> None:
    import json

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=float)


__all__ = [
    "SCRATCH", "TRAIN", "TEST", "COST", "COST_ZERO_SLIP", "PORT", "VARIANTS",
    "load_panel", "load_vol", "trend_volume_signal", "signal_liveness",
    "gated_momentum_score", "soft_gate_score", "slice_window", "metrics_row",
    "fmt_table", "buy_and_hold", "yearly_str", "save_json", "provenance",
    "run_backtest", "compute_metrics", "yearly_returns", "np", "pd",
]
