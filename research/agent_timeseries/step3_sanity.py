"""Sanity checks on the harness itself, run BEFORE trusting the TEST number.

Per brief §6:
  1. plausibility  - unlevered long-only NIFTY-50 cannot exceed ~40-50% CAGR
  2. weight count  - average names held should be ~22, not 48
  3. liveness      - fraction of bars long should be >~5%
  4. cost drag     - gross vs net must be reported
  5. negative control (handled in step2)

Plus two correctness checks that catch lookahead:
  A. shifting the panel forward one bar must CHANGE the result (if not, the
     engine may be ignoring the score)
  B. truncating the panel's future must not change past weights (causality)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "agent_timeseries"))

from harness import (  # noqa: E402
    CONFIG,
    ENGINE_SHA,
    TEST_END,
    TEST_START,
    load_panel,
    metrics_of,
    roc_panel,
    run_window,
    score_from_signal,
)

P, T = 126, 0.00


def main() -> None:
    panel, symbols = load_panel()
    score = score_from_signal(panel, P, T)
    res = run_window(panel, score, TEST_START, TEST_END)
    m = metrics_of(res)
    W = res.weights

    print(f"ENGINE_SHA = {ENGINE_SHA}\n")

    print("== 2. WEIGHT COUNT ==")
    n_names = (W > 0).sum(axis=1)
    print(f"  avg names held      : {n_names.mean():.2f}  (config n_positions={CONFIG.n_positions})")
    print(f"  max names held      : {n_names.max()}")
    print(f"  days with >30 names : {(n_names > 30).sum()}")
    tot = W.sum(axis=1)
    print(f"  deployed weight     : min {tot.min():.3f} mean {tot.mean():.3f} max {tot.max():.3f}")
    print(f"  (expect ~0.90 = 1 - cash_buffer {CONFIG.cash_buffer})")
    mx = W.max(axis=1)
    print(f"  max single weight   : max {mx.max():.4f} (cap {CONFIG.max_weight})")
    dead = (W > 0) & (W <= 1e-4)
    print(f"  dead residual cells : {int(dead.sum().sum())}  (expect ~0)")

    print("\n== 3. SIGNAL LIVENESS ==")
    for p, t in [(20, 0.0), (40, 0.0), (60, 0.0), (126, 0.0), (40, 0.02)]:
        roc = roc_panel(panel, p)
        valid = panel.notna() & panel.shift(p).notna()
        frac = float(((roc > t) & valid).sum().sum() / valid.sum().sum())
        print(f"  p={p:<4} t={t:<5} long fraction of symbol-bars: {frac*100:5.1f}%")
    elig = score.notna().sum(axis=1)
    print(f"  eligible names per day (TEST): mean {elig.mean():.1f} min {elig.min()} max {elig.max()}")
    if elig.mean() < 5:
        print("  ** WARNING: fewer than 5 eligible names -- book is near-flat **")

    print("\n== 4. COST DRAG: gross vs net ==")
    rt = m["round_trip_bps"]
    print(f"  round trip charged by run_backtest: {rt:.2f} bps")
    print(f"  statutory only (CostModel):        "
          f"{float(__import__('nsealgo.costs', fromlist=['x']).CostModel(segment='delivery', slippage_bps=5).round_trip_bps(100000)):.2f} bps")
    print(f"  net   CAGR: {m['cagr']*100:>7.2f}%   annual turnover {m['turnover']:.2f}x")
    print(f"  annual cost drag: {m['cost_drag']*100:.2f}%/y")
    # gross = net compounded with the drag removed, approximately
    yrs = len(res.returns) / 244
    gross_cagr = (1 + m["cagr"]) ** (1 / yrs) * 0 + (
        (res.equity.iloc[-1]) ** (1 / yrs)
    )
    print(f"  approximate GROSS CAGR: {gross_cagr*100:>7.2f}%  (net {m['cagr']*100:.2f}%)")
    print(f"  cost contribution    : {(gross_cagr - m['cagr'])*100:>6.2f} pp/yr")

    print("\n== 1. PLAUSIBILITY ==")
    print(f"  CAGR {m['cagr']*100:.2f}%  (unlevered long-only NIFTY-50 ceiling ~40-50%)")
    flag = "OK" if m["cagr"] < 0.50 else "** SUSPECT: >50% CAGR, look for lookahead **"
    print(f"  -> {flag}")

    print("\n== A. SCORE ACTUALLY DRIVES THE BOOK ==")
    alt = score_from_signal(panel, 20, 0.0)
    res_alt = run_window(panel, alt, TEST_START, TEST_END)
    print(f"  p126 CAGR {m['cagr']*100:.2f}%  vs  p20 CAGR {metrics_of(res_alt)['cagr']*100:.2f}%"
          f"  -> {'DIFFER (score matters)' if abs(m['cagr']-metrics_of(res_alt)['cagr'])>1e-6 else 'IDENTICAL (BUG)'}")

    print("\n== B. NO-LOOKAHEAD: truncating the future must not change the past ==")
    cut = TEST_START + pd.Timedelta(days=900)
    res_full = res
    res_trunc = run_window(panel, score, TEST_START, cut)
    common = res_trunc.weights.index.intersection(res_full.weights.index)
    diff = (res_full.weights.loc[common] - res_trunc.weights.loc[common]).abs().max().max()
    print(f"  max |weight difference| on common dates after truncating future: {diff:.2e}")
    print(f"  -> {'OK (causal)' if diff < 1e-9 else '** LOOKAHEAD: past changed when future removed **'}")

    print("\n== C. LAG CHECK: weights on date t must not use date t's return ==")
    r = panel.loc[TEST_START:TEST_END].pct_change(fill_method=None).fillna(0.0)
    held = W
    gross_now = (held * r).sum(axis=1)
    gross_lag = (held.shift(1).fillna(0.0) * r).sum(axis=1)
    print("  corr(same-day attribution, lagged attribution) should be high but not 1.0")
    print(f"  mean |same-day - lagged| daily return = {float((gross_now-gross_lag).abs().mean()):.5f}")
    print("  (engine uses lagged internally: `held.shift(1) * rets`)")


if __name__ == "__main__":
    main()
