"""Shared harness for the gaussian_strategy NSE port.

Port of `GaussianStrategy.signal` to a vectorised, strictly-trailing panel form:

    z_t = (C_t - rolling_mean(C, period)_t) / rolling_std(C, period)_t   # ddof=0

which is exactly `zscore(closes[-period:])` — the *intent* of `GaussianConfig.period`
(see BUG-1 in REPORT.md) rather than the shipped 300-bar buffer behaviour.

Long-only port: `z <= -entry` -> LONG. The `z >= entry` SHORT leg is dropped; an
Indian delivery account cannot short, so those bars are simply "not signalled".

Score construction inside the signalled set (brief §5):
    momentum : rank signalled names by trailing 126d momentum
    equalw   : flat score -> the engine's own inverse-vol scaling is the only tilt
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.costs import CostModel  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

VARIANTS = [
    # (id, period, entry, construction) — the DECLARED budget of 5, nothing else.
    ("V1", 30, 0.8, "momentum"),
    ("V2", 30, 1.2, "momentum"),
    ("V3", 126, 0.8, "momentum"),
    ("V4", 10, 0.8, "momentum"),
    ("V5", 30, 0.8, "equalw"),
]


def rolling_zscore(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Trailing `period`-bar z of close. Population stdev, matches np.std."""
    win = panel.rolling(period, min_periods=period)
    mu = win.mean()
    sd = win.std(ddof=0).replace(0.0, np.nan)
    return (panel - mu) / sd


def signal_panel(panel: pd.DataFrame, period: int, entry: float) -> pd.DataFrame:
    """True where the long-only gaussian signal fires."""
    return rolling_zscore(panel, period) <= -entry


def build_score(
    panel: pd.DataFrame,
    period: int,
    entry: float,
    construction: str = "momentum",
) -> pd.DataFrame:
    """Cross-sectional score; NaN where the strategy does not signal.

    NaN is load-bearing: `build_rebalance_weights` treats non-finite scores as
    ineligible, so an un-signalled name can never be selected.
    """
    sig = signal_panel(panel, period, entry)
    if construction == "momentum":
        score = (panel / panel.shift(126) - 1.0).where(sig)
    elif construction == "equalw":
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns).where(sig)
    else:
        raise ValueError(f"unknown construction {construction!r}")
    return score


def cost_model() -> CostModel:
    """Full Indian delivery stack + 5bps slippage, as the brief mandates."""
    return CostModel(segment="delivery", slippage_bps=5)


def run_window(panel: pd.DataFrame, score_full: pd.DataFrame, window, config=None):
    """Run one window.

    The score is computed on the FULL panel (so `period`-bar warmup and the 126d
    momentum lookback are genuinely seeded at the first bar of the window) and then
    sliced. `run_backtest` intersects on the score's index, so passing the full panel
    plus a windowed score restricts the simulation to the window with no forward-fill
    anywhere.
    """
    from nsealgo.backtest.engine import PortfolioConfig, run_backtest

    cfg = config or PortfolioConfig()
    score_w = score_full.loc[window[0]:window[1]]
    return run_backtest(panel, score_w, cost_model(), cfg, rebalance="M")


def row(result, label: str) -> dict:
    """Flatten a BacktestResult into a reporting row."""
    m = result.metrics
    return {
        "id": label,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "trades": m.trades_per_year,
        "names": result.diag["avg_names"],
        "tot_ret": m.total_return,
    }


HDR = (
    f"{'id':<4} {'CAGR':>8} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8} "
    f"{'Calmar':>7} {'Vol':>7} {'Turn':>6} {'Cost':>7} {'Names':>6}"
)


def fmt_rows(rows: list[dict]) -> str:
    out = [HDR]
    for r in rows:
        out.append(
            f"{r['id']:<4} {r['cagr'] * 100:>7.2f}% {r['sharpe']:>7.2f} "
            f"{r['sortino']:>8.2f} {r['maxdd'] * 100:>7.2f}% {r['calmar']:>7.2f} "
            f"{r['vol'] * 100:>6.2f}% {r['turnover']:>5.2f}x {r['cost_drag'] * 100:>6.2f}% "
            f"{r['names']:>6.1f}"
        )
    return "\n".join(out)


def buy_and_hold(panel: pd.DataFrame, window, cost_model_: CostModel | None = None):
    """Equal-weight-universe benchmark over `window`, net of the same costs.

    The brief specifies `panel.pct_change().mean(axis=1)` as the benchmark series; note
    that is a **daily-rebalanced** equal-weight return, which is what is computed here.

    Costs are charged as ONE round trip: half of `all_in_round_trip_bps` on the entry
    bar and half on the exit bar. An earlier version of this function multiplied every
    single bar by `(1 - rt)`, i.e. charged the round trip 685 times over the TEST window
    — a 78% equity haircut that turned a +7.9% benchmark into −36.6%. See BUG-2 in
    REPORT.md. The charge now happens exactly twice.
    """
    from nsealgo.backtest.metrics import compute_metrics

    cm = cost_model_ or cost_model()
    px = panel.loc[window[0] : window[1]]
    r = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)

    rt = float(cm.all_in_round_trip_bps(100_000)) / 10_000.0
    half = rt / 2.0
    net = (1.0 + r).copy()
    net.iloc[0] *= 1.0 - half          # buy side: half the round trip
    net.iloc[-1] *= 1.0 - half         # sell side: the other half
    equity = net.cumprod()
    years = len(net) / 244.0
    m = compute_metrics(
        net - 1.0,
        equity,
        annual_turnover=1.0,
        cost_drag_annual=rt / years,    # one-off charge, spread over the window
        trades_per_year=1.0,
    )
    return m, equity


def held_basket(panel: pd.DataFrame, window) -> float:
    """True buy-and-hold: equal capital in each name on day 1, never rebalanced.

    Reported alongside the brief's series because the two differ: the brief's
    `pct_change().mean(axis=1)` rebalances daily, which is a different (and easier)
    thing to earn than holding 48 names for 2.75 years.
    """
    px = panel.loc[window[0] : window[1]]
    per_name = (px.iloc[-1] / px.iloc[0]).fillna(0.0) / px.shape[1]
    total = float(per_name.sum())
    years = len(px) / 244.0
    return float(total ** (1.0 / years) - 1.0)
