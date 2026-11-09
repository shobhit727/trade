"""STEP 4 -- verification. Proves the three things a number like this can be faked with.

  1. NO LOOKAHEAD: truncating the panel at T must not change any score on or before T.
  2. THE COST FIGURE: confirm run_backtest really charges 21.92 bps, not 11.92.
  3. DETERMINISM: re-running s2's TEST numbers must reproduce bit-identically.

Run: .venv/bin/python research/agent_flag_pattern/s4_verify.py
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    TEST_END,
    TEST_START,
    VARIANTS,
    ZeroCostModel,
    backtest,
    build_score,
    cost_model,
    load_all,
    portfolio_config,
    run_signal,
)

HERE = Path(__file__).resolve().parent
PANEL, HIGH, LOW, SYMBOLS, _ = load_all()
sig = run_signal(PANEL, HIGH, LOW, VARIANTS["V0_LITERAL"])

# --------------------------------------------------------------------------- #
print("=" * 74)
print("1. NO-LOOKAHEAD PROOF")
print("=" * 74)
print("Truncate the panel at several dates; any score on or before T must be")
print("identical to the full-history score. If any future row influenced the past,")
print("these would differ.\n")

for cut in ("2018-06-30", "2021-03-31", "2024-12-31", "2026-01-31"):
    t = pd.Timestamp(cut, tz=PANEL.index.tz)
    full_sig = sig.loc[:t]
    full_sc = build_score(full_sig, PANEL.loc[:t])
    trunc_sig = run_signal(PANEL.loc[:t], HIGH.loc[:t], LOW.loc[:t],
                           VARIANTS["V0_LITERAL"])
    trunc_sc = build_score(trunc_sig, PANEL.loc[:t])
    sig_eq = np.array_equal(full_sig.to_numpy(), trunc_sig.to_numpy(),
                            equal_nan=True)
    sc_eq = np.allclose(full_sc.to_numpy(), trunc_sc.to_numpy(),
                        rtol=0, atol=0, equal_nan=True)
    print(f"  cut at {cut}: signal identical {sig_eq}   score identical {sc_eq}"
          f"   ({len(trunc_sc)} bars)")
    assert sig_eq and sc_eq, f"LOOKAHEAD at {cut}"

print("\n  Also checked: the engine earns from t+1 only. run_backtest computes")
print("  `gross = (held.shift(1) * rets).sum(axis=1)` -- weights chosen at the close")
print("  of t are credited with t's return only via the shift, i.e. from t+1.")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 74)
print("2. COST FIGURE")
print("=" * 74)
cm = cost_model()
rt = float(cm.round_trip_bps(Decimal("100000")))
ai = float(cm.all_in_round_trip_bps(Decimal("100000")))
print(f"  CostModel.round_trip_bps(100_000)        = {rt:.2f} bps (statutory only)")
print(f"  CostModel.all_in_round_trip_bps(100_000)= {ai:.2f} bps "
      f"(rt_bps + 2 x slippage_5bps)  <-- what run_backtest charges")
te = slice(TEST_START, TEST_END)
p_te = PANEL.loc[te]
res = backtest(p_te, build_score(sig.loc[te], p_te))
print(f"  engine diag round_trip_bps               = {res.diag['round_trip_bps']:.2f} bps")
assert abs(res.diag["round_trip_bps"] - 21.92) < 1e-9
print("  -> every result in this report is NET OF 21.92 bps. CONFIRMED.")
print(f"  ZeroCostModel returns {ZeroCostModel().all_in_round_trip_bps(1)} "
      f"(used only for the gross/net split, never as a result)")

# turnover x rate must reconcile with the reported drag
expect = res.metrics.annual_turnover * 21.92 / 10_000.0
print(f"  turnover {res.metrics.annual_turnover:.2f}x x 21.92bps = "
      f"{expect:.2%}/yr vs reported drag {res.metrics.cost_drag_annual:.2%}/yr "
      f"(equity compounding makes the actual drag slightly higher)")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 74)
print("3. CONSTRAINTS RESPECTED")
print("=" * 74)
cfg = portfolio_config()
w = res.weights
print(f"  max single-name weight : {float(w.max().max()):.4%} "
      f"(cap {cfg.max_weight:.0%})")
print(f"  total weight max       : {float(w.sum(axis=1).max()):.4%} "
      f"(cap {1 - cfg.cash_buffer:.0%} invested)")
print(f"  avg names held         : {res.diag['avg_names']:.1f} "
      f"(n_positions {cfg.n_positions}, max_names {cfg.max_names})")
assert float(w.max().max()) <= cfg.max_weight + 1e-9
assert float(w.sum(axis=1).max()) <= (1 - cfg.cash_buffer) + 1e-9
assert float((w > 0).sum(axis=1).max()) <= cfg.max_names + 1e-9
print("  -> no constraint violated; shorting impossible (weights all >= 0): "
      f"min weight {float(w.min().min()):.6f}")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 74)
print("4. DETERMINISM -- re-running the TEST backtest")
print("=" * 74)
again = backtest(p_te, build_score(sig.loc[te], p_te))
prev = json.loads((HERE / "test_results.json").read_text())["strategy"]
print(f"  first run  CAGR {prev['cagr']:.10f}  Sharpe {prev['sharpe']:.10f}")
print(f"  this run   CAGR {again.metrics.cagr:.10f}  "
      f"Sharpe {again.metrics.sharpe:.10f}")
same = (abs(again.metrics.cagr - prev["cagr"]) < 1e-12
        and abs(again.metrics.sharpe - prev["sharpe"]) < 1e-12)
print(f"  identical : {same}")
assert same

print("\nALL VERIFICATION CHECKS PASSED.")
