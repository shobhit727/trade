"""STAGE 2 — the single, one-shot TEST evaluation.

TEST = 2024-01-01 .. 2026-10-01. Winner = V3 (period=63, threshold=0.03), chosen
purely on TRAIN Sharpe before TEST was ever loaded.

This script also runs, on the identical window and identical costs:
  * buy-and-hold (panel.pct_change().mean(axis=1)), net of the same 21.92 bps
  * the nsealgo composite
  * a zero-cost control (CostModel now coerces float slippage, so this works)
  * negative controls: random signals at matched % of bars long

Nothing here is used to re-pick the variant.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    COST_MODEL,
    TEST_END,
    TEST_START,
    ZERO_COST_MODEL,
    load_panels,
    momentum_rank_score,
    roc_panel,
    slice_split,
    vwm_signal,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

WINNER = ("V3", 63, 0.03)
CFG = PortfolioConfig()
OUT = "research/agent_vwm/stage2_test.json"
SEED = 20261012


def row(res) -> dict:
    m = res.metrics
    return {
        "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
        "calmar": m.calmar, "sortino": m.sortino, "vol": m.volatility,
        "total_return": m.total_return, "turnover_yr": m.annual_turnover,
        "cost_drag_yr": m.cost_drag_annual, "trades_yr": m.trades_per_year,
        "avg_names": res.diag["avg_names"], "avg_top_weight": res.diag["avg_top_weight"],
        "rt_bps": res.diag["round_trip_bps"],
        "costs_paid_rupees": res.costs_paid,
    }


def bh_backtest(px: pd.DataFrame, cost_model) -> dict:
    """Buy-and-hold equal weight, net of ONE entry+exit round trip.

    `run_backtest` cannot express this (it always holds a ranked book and pays on
    every rebalance), so we charge the same 21.92 bps once, at entry, which is what
    a buy-and-hold actually incurs. rf handling is identical to `compute_metrics`.
    """
    from decimal import Decimal

    rt = float(cost_model.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    rets = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    eq = (1.0 + rets).cumprod() * (1.0 - rt)
    daily = eq.pct_change(fill_method=None).fillna(0.0)
    m = compute_metrics(
        daily, eq, annual_turnover=1.0, cost_drag_annual=rt, trades_per_year=1 / 3
    )
    return {
        "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
        "calmar": m.calmar, "total_return": m.total_return, "vol": m.volatility,
        "sortino": m.sortino, "turnover_yr": 1.0, "cost_drag_yr": rt,
        "rt_bps": rt * 10_000, "avg_names": float(px.shape[1]),
    }


def main() -> None:
    px, vol, symbols = load_panels()
    px_te = slice_split(px, TEST_START, TEST_END)
    vol_te = slice_split(vol, TEST_START, TEST_END)
    vid, period, thr = WINNER

    print("=" * 96)
    print(f"TEST — one shot.  {px_te.index[0].date()} -> {px_te.index[-1].date()} "
          f"({len(px_te)} bars, {px_te.shape[1]} symbols)")
    print(f"Variant {vid} chosen on TRAIN alone (max TRAIN Sharpe). Not re-picked.")
    print("=" * 96)

    sig, diag = vwm_signal(px_te, vol_te, period, thr, long_only=True)
    score = momentum_rank_score(px_te, sig, mom_days=126)

    res = run_backtest(px_te, score, COST_MODEL, CFG, rebalance="M")
    r = row(res)

    res_free = run_backtest(px_te, score, ZERO_COST_MODEL, CFG, rebalance="M")
    r_free = row(res_free)

    # volume-free signal, full cost -- proves the volume term is inert on TEST too
    m = roc_panel(px_te, period)
    sig_free = pd.DataFrame(0.0, index=px_te.index, columns=px_te.columns)
    sig_free[m > thr] = 1.0
    sig_free[m.isna()] = 0.0
    res_nv = run_backtest(px_te, momentum_rank_score(px_te, sig_free, 126),
                          COST_MODEL, CFG, rebalance="M")
    r_nv = row(res_nv)

    bh = bh_backtest(px_te, COST_MODEL)
    bh_free = bh_backtest(px_te, ZERO_COST_MODEL)

    comp = run_backtest(px_te, build_composite_score(px_te), COST_MODEL, CFG, rebalance="M")
    r_comp = row(comp)

    # ---- negative controls: random signals, matched % of bars long.
    rng = np.random.default_rng(SEED)
    target_frac = diag["frac_cells_long"]
    nc = []
    for _trial in range(20):
        rand = pd.DataFrame(
            rng.random(px_te.shape) < target_frac, index=px_te.index, columns=px_te.columns
        ).astype(float)
        # match the real signal's own long-only gating discipline
        rand = rand.where(rand > 0, 0.0)
        sc = momentum_rank_score(px_te, rand, mom_days=126)
        rr = run_backtest(px_te, sc, COST_MODEL, CFG, rebalance="M")
        nc.append(row(rr))

    def agg(key):
        v = np.array([x[key] for x in nc])
        return {"mean": float(v.mean()), "std": float(v.std(ddof=1)),
                "p05": float(np.quantile(v, 0.05)), "p95": float(np.quantile(v, 0.95)),
                "max": float(v.max()), "min": float(v.min()),
                "n_beaten_by_vwm": int((v < r[key]).sum()), "n_trials": len(v)}

    ctrl = {k: agg(k) for k in ("cagr", "sharpe", "max_dd", "calmar")}

    out = {
        "winner": {"id": vid, "period": period, "threshold": thr},
        "window": [str(px_te.index[0].date()), str(px_te.index[-1].date())],
        "n_bars": len(px_te), "n_symbols": px_te.shape[1],
        "vwm": r, "vwm_zero_cost": r_free, "vwm_no_volume_term": r_nv,
        "buy_hold": bh, "buy_hold_zero_cost": bh_free,
        "composite": r_comp,
        "random_control": ctrl,
        "diag": diag,
        "yearly": {str(k): float(v) for k, v in yearly_returns(res.returns).items()},
        "seed": SEED, "provenance": provenance(),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    # ---- print
    hdr = (f"{'':<22}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Calmar':>8}"
           f"{'Turn/y':>8}{'Cost/y':>8}{'Names':>7}")
    print()
    print(hdr)
    print("-" * len(hdr))

    def line(label, d):
        print(f"{label:<22}{d['cagr']*100:>8.2f}%{d['sharpe']:>8.2f}"
              f"{d['max_dd']*100:>8.2f}%{d['calmar']:>8.2f}"
              f"{d.get('turnover_yr',0):>8.2f}{d.get('cost_drag_yr',0)*100:>7.2f}%"
              f"{d.get('avg_names',0):>7.1f}")

    line(f"vw_momentum {vid} NET", r)
    line("  ...zero cost", r_free)
    line("  ...volume term deleted", r_nv)
    line("BUY-AND-HOLD net", bh)
    line("  ...zero cost", bh_free)
    line("nsealgo composite", r_comp)

    print()
    print("NEGATIVE CONTROL — 20 random signals, same % of bars long "
          f"({target_frac:.2%}), same costs:")
    print(f"  random CAGR   mean {ctrl['cagr']['mean']*100:>7.2f}%  "
          f"sd {ctrl['cagr']['std']*100:>5.2f}%  "
          f"[{ctrl['cagr']['p05']*100:.2f}%, {ctrl['cagr']['p95']*100:.2f}%]  "
          f"vw_momentum beat {ctrl['cagr']['n_beaten_by_vwm']}/{ctrl['cagr']['n_trials']}")
    print(f"  random Sharpe mean {ctrl['sharpe']['mean']:>7.2f}  "
          f"sd {ctrl['sharpe']['std']:>5.2f}  "
          f"[{ctrl['sharpe']['p05']:.2f}, {ctrl['sharpe']['p95']:.2f}]  "
          f"vw_momentum beat {ctrl['sharpe']['n_beaten_by_vwm']}/{ctrl['sharpe']['n_trials']}")
    print(f"  random MaxDD  mean {ctrl['max_dd']['mean']*100:>7.2f}%  "
          f"[{ctrl['max_dd']['p05']*100:.2f}%, {ctrl['max_dd']['p95']*100:.2f}%]")

    print()
    print("Calendar years:", out["yearly"])
    print("Signal liveness:", {k: (round(v, 4) if isinstance(v, float) else v)
                               for k, v in diag.items()})
    print(f"\nCosts paid over TEST (₹21L book): ₹{r['costs_paid_rupees']:,.0f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
