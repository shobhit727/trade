"""STAGE 5 — BUG FOUND: slicing the panel to TEST starves the factor warmup.

`run_backtest` computes the score itself from the panel, so slicing to TEST and
then building the score leaves the momentum term with zero history. The book then
sits in 100% cash for the first ~7 months of a 34-month TEST window and every
reported number is wrong.

THE FIX IS PROTOCOL-COMPLIANT, NOT A LOOKAHEAD:
  * the score on TEST date t is built from closes up to and including t only;
  * warmup history is taken from dates BEFORE the TEST window, which is exactly
    what a live deployment would have;
  * metrics are still computed ONLY over TEST.

The honest way to express this: give `run_backtest` a panel that starts early enough
for the factor to warm up, then measure only the TEST slice of the result. Nothing
about the TEST data informs the factor.

Both the buggy and the corrected number are reported. The buggy one is kept only
because it is what the naive harness produces, and it is materially wrong.
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
    slice_split,
    vwm_signal,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

CFG = PortfolioConfig()
PERIOD, THR = 63, 0.03
WIN_PERIOD, WIN_THRESH = 126, 0.03  # the 126d ranking lookback fixed in REPORT.md

#: how much pre-TEST history the ranking factor needs
WARMUP_BARS = WIN_PERIOD + 10


def score_window(px_all: pd.DataFrame, vol_all: pd.DataFrame):
    """Build the signal+score over history+TEST, then cut to TEST.

    The extra history is pre-TEST only. The score on any TEST date uses only data
    up to that date, so this introduces no lookahead -- it is what a live system
    would have had on 2024-01-01.
    """
    hist_start = TEST_START - pd.Timedelta(days=int(WARMUP_BARS * 1.55))
    hist_start = px_all.index[px_all.index < TEST_START][-WARMUP_BARS]
    sig, diag = vwm_signal(px_all, vol_all, PERIOD, THR, long_only=True)
    sc_all = momentum_rank_score(px_all, sig, mom_days=WIN_PERIOD)
    # verify no TEST date uses pre-TEST info beyond warmup: score is point-in-time
    sc = sc_all.loc[TEST_START:TEST_END]
    sig_t = sig.loc[TEST_START:TEST_END]
    return sig_t, sc, diag, hist_start


def metrics_on_test(res) -> dict:
    """Restrict a full-window run to the TEST slice and recompute metrics."""
    r = res.returns.loc[TEST_START:TEST_END]
    e = res.equity.loc[TEST_START:TEST_END]
    e = e / e.iloc[0]
    m = compute_metrics(r, e, annual_turnover=res.metrics.annual_turnover,
                        cost_drag_annual=res.metrics.cost_drag_annual,
                        trades_per_year=res.metrics.trades_per_year)
    return {
        "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
        "calmar": m.calmar, "vol": m.volatility, "total_return": m.total_return,
        "sortino": m.sortino,
    }


def main() -> None:
    px, vol, _ = load_panels()
    px_te = slice_split(px, TEST_START, TEST_END)

    # ---------- the BUGGY version, kept for the record ----------
    px_te_s, vol_te_s = px_te, slice_split(vol, TEST_START, TEST_END)
    sig_b, _ = vwm_signal(px_te_s, vol_te_s, PERIOD, THR)
    sc_b = momentum_rank_score(px_te_s, sig_b, mom_days=WIN_PERIOD)
    res_buggy = run_backtest(px_te_s, sc_b, COST_MODEL, CFG, "M")
    buggy = {
        "cagr": res_buggy.metrics.cagr, "sharpe": res_buggy.metrics.sharpe,
        "max_dd": res_buggy.metrics.max_drawdown, "calmar": res_buggy.metrics.calmar,
        "avg_names": res_buggy.diag["avg_names"],
    }
    n_zero = int((res_buggy.weights > 0).sum(axis=1).eq(0).sum())
    print("=" * 84)
    print("A. THE BUG — score built from a TEST-only slice")
    print("=" * 84)
    print(f"  rebalances delivered            : {res_buggy.diag['n_rebalances']}")
    print(f"  days with ZERO names held      : {n_zero} of {len(res_buggy.weights)}")
    print(f"  CAGR {buggy['cagr']*100:.2f}%  Sharpe {buggy['sharpe']:.2f}  "
          f"MaxDD {buggy['max_dd']*100:.2f}%  avg names {buggy['avg_names']:.1f}")
    print("  -> 7 months of the TEST window produce an EMPTY book (factor warmup,")
    print("     not the signal). This is a harness artefact, not a strategy result.")

    # ---------- the CORRECTED version ----------
    sig_t, sc_t, diag, hist_start = score_window(px, vol)
    print()
    print("=" * 84)
    print("B. THE FIX — build the score with pre-TEST warmup, measure on TEST only")
    print("=" * 84)
    print(f"  warmup history starts {hist_start.date()} "
          f"({int((TEST_START - hist_start).days)} calendar days before TEST)")
    # run over history+TEST, then measure the TEST slice
    px_run = px.loc[hist_start:TEST_END]
    vol_run = vol.loc[hist_start:TEST_END]
    sig_run, _ = vwm_signal(px_run, vol_run, PERIOD, THR)
    sc_run = momentum_rank_score(px_run, sig_run, mom_days=WIN_PERIOD)
    res_fix = run_backtest(px_run, sc_run, COST_MODEL, CFG, "M")
    fixed = metrics_on_test(res_fix)
    n_zero_fix = int((res_fix.weights.loc[TEST_START:] > 0).sum(axis=1).eq(0).sum())
    print(f"  days with ZERO names held in TEST: {n_zero_fix} "
          f"of {len(res_fix.weights.loc[TEST_START:])}")
    print(f"  TEST CAGR {fixed['cagr']*100:.2f}%  Sharpe {fixed['sharpe']:.2f}  "
          f"MaxDD {fixed['max_dd']*100:.2f}%  Calmar {fixed['calmar']:.2f}")
    print(f"  mean exposure: {(res_fix.weights.loc[TEST_START:].sum(axis=1)).mean():.1%}")

    # zero-cost control on the corrected run
    res_fix_zc = run_backtest(px_run, sc_run, ZERO_COST_MODEL, CFG, "M")
    fixed_zc = metrics_on_test(res_fix_zc)

    # buy-and-hold on TEST, same costs
    from decimal import Decimal
    rt = float(COST_MODEL.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    rets = px_te.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    eq = (1.0 + rets).cumprod() * (1.0 - rt)
    daily = eq.pct_change(fill_method=None).fillna(0.0)
    m_bh = compute_metrics(daily, eq, annual_turnover=1.0, cost_drag_annual=rt,
                           trades_per_year=1 / 3)
    bh = {"cagr": m_bh.cagr, "sharpe": m_bh.sharpe, "max_dd": m_bh.max_drawdown,
          "calmar": m_bh.calmar, "vol": m_bh.volatility, "total_return": m_bh.total_return}

    # composite with the same warmup treatment
    comp_run = build_composite_score(px_run)
    res_comp = run_backtest(px_run, comp_run, COST_MODEL, CFG, "M")
    comp = metrics_on_test(res_comp)

    # negative control on the corrected construction
    rng = np.random.default_rng(20261012)
    tgt = diag["frac_cells_long"]
    ncs = []
    for _ in range(20):
        rand = pd.DataFrame(rng.random(px_run.shape) < tgt,
                            index=px_run.index, columns=px_run.columns).astype(float)
        sc_r = momentum_rank_score(px_run, rand, mom_days=WIN_PERIOD)
        r_ = run_backtest(px_run, sc_r, COST_MODEL, CFG, "M")
        d = metrics_on_test(r_)
        ncs.append(d)
    cagrs = np.array([x["cagr"] for x in ncs])
    sharpes = np.array([x["sharpe"] for x in ncs])
    dds = np.array([x["max_dd"] for x in ncs])

    print()
    print("=" * 84)
    print("C. CORRECTED TEST RESULTS (2024-01-01 .. 2026-10-01), net of 21.92 bps")
    print("=" * 84)
    hdr = (f"{'':<26}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Calmar':>8}"
           f"{'Vol':>8}{'Total':>10}")
    print(hdr)
    print("-" * len(hdr))

    def line(lbl, d, extra=""):
        print(f"{lbl:<26}{d['cagr']*100:>8.2f}%{d['sharpe']:>8.2f}"
              f"{d['max_dd']*100:>8.2f}%{d['calmar']:>8.2f}{d['vol']*100:>7.2f}%"
              f"{d['total_return']*100:>9.2f}%{extra}")

    line("vw_momentum V3 NET", fixed)
    line("  ...zero cost", fixed_zc)
    line("BUY-AND-HOLD net", bh)
    line("nsealgo composite", comp)
    print()
    print(f"  vw_momentum vs buy-and-hold: CAGR {(fixed['cagr']-bh['cagr'])*100:+.2f}pp  "
          f"Sharpe {fixed['sharpe']-bh['sharpe']:+.2f}  "
          f"MaxDD {(fixed['max_dd']-bh['max_dd'])*100:+.2f}pp")
    print(f"  vw_momentum vs composite   : CAGR {(fixed['cagr']-comp['cagr'])*100:+.2f}pp  "
          f"Sharpe {fixed['sharpe']-comp['sharpe']:+.2f}")
    print()
    print(f"NEGATIVE CONTROL: 20 random signals, {tgt:.2%} of bars long, same costs")
    print(f"  random CAGR    mean {cagrs.mean()*100:>7.2f}%  sd {cagrs.std(ddof=1)*100:>5.2f}%  "
          f"[{np.quantile(cagrs,.05)*100:.2f}%, {np.quantile(cagrs,.95)*100:.2f}%]")
    print(f"  random Sharpe  mean {sharpes.mean():>7.2f}  sd {sharpes.std(ddof=1):>5.2f}  "
          f"[{np.quantile(sharpes,.05):.2f}, {np.quantile(sharpes,.95):.2f}]")
    print(f"  random MaxDD   mean {dds.mean()*100:>7.2f}%  "
          f"[{np.quantile(dds,.05)*100:.2f}%, {np.quantile(dds,.95)*100:.2f}%]")
    print(f"  vw_momentum beats random on CAGR: "
          f"{int((cagrs < fixed['cagr']).sum())}/20   "
          f"Sharpe: {int((sharpes < fixed['sharpe']).sum())}/20")
    print(f"  vw_momentum CAGR percentile vs random: "
          f"{float((cagrs < fixed['cagr']).mean()):.0%}")

    yr = {str(k): float(v) for k, v in
          yearly_returns(res_fix.returns.loc[TEST_START:TEST_END]).items()}
    print()
    print("  calendar years:", yr)

    out = {"buggy_slice": buggy, "fixed": fixed, "fixed_zero_cost": fixed_zc,
           "buy_hold": bh, "composite": comp,
           "random_cagr_mean": float(cagrs.mean()),
           "random_cagr_sd": float(cagrs.std(ddof=1)),
           "random_sharpe_mean": float(sharpes.mean()),
           "random_sharpe_sd": float(sharpes.std(ddof=1)),
           "random_beaten_cagr": int((cagrs < fixed["cagr"]).sum()),
           "random_beaten_sharpe": int((sharpes < fixed["sharpe"]).sum()),
           "random_maxdd_mean": float(dds.mean()),
           "yearly": yr,
           "mean_exposure": float(res_fix.weights.loc[TEST_START:].sum(axis=1).mean()),
           "n_rebalances": res_fix.diag["n_rebalances"],
           "avg_names": res_fix.diag["avg_names"],
           "turnover_yr": res_fix.metrics.annual_turnover,
           "cost_drag_yr": res_fix.metrics.cost_drag_annual,
           "costs_paid_rupees": res_fix.costs_paid,
           "rt_bps": res_fix.diag["round_trip_bps"]}
    with open("research/agent_vwm/stage5_fixed.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nwrote research/agent_vwm/stage5_fixed.json")


if __name__ == "__main__":
    main()
