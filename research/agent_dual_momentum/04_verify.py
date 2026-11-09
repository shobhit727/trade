"""STEP 4 — integrity checks. TRAIN-scoped so the holdout stays untouched.

  1. My vectorised EMA is numerically the catalog's ``ema()``, not a lookalike.
  2. No look-ahead: perturbing every price *after* the TRAIN window must leave the
     TRAIN result bit-for-bit identical. If any future price leaked into a TRAIN
     decision, this breaks immediately.
  3. AGENT_BRIEF sec.6 plausibility: weight count is ~22, not 48, and the CAGR is
     nowhere near the 200% tell-tale of a compounding bug.
"""

from __future__ import annotations

import json
from pathlib import Path

import common as C
import numpy as np

from cryptobot.strategies.catalog.dual_momentum_strategy import (
    DualMomentumConfig,
    DualMomentumStrategy,
)
from cryptobot.strategies.indicators import ema as catalog_ema

HERE = Path(__file__).parent


def main() -> None:
    px = C.panel()
    ok = True

    # ---- 1. EMA fidelity ------------------------------------------------ #
    print("=== 1. EMA == catalog ema() ===")
    fast, slow = 50, 200
    col = px.columns[0]
    closes = px[col].dropna().to_numpy()
    strat = DualMomentumStrategy(DualMomentumConfig(fast=fast, slow=slow))
    for period in (fast, slow):
        ref = catalog_ema(closes, period)
        mine = float(C.ema_panel(px[[col]], period)[col].dropna().iloc[-1])
        d = abs(ref - mine)
        flag = "OK " if d < 1e-6 else "MISMATCH"
        print(f"  period {period:>3}: catalog {ref:12.4f}  mine {mine:12.4f}  "
              f"|diff| {d:.3e}  {flag}")
        ok &= d < 1e-6
    # and the signal itself, from the catalog object, on the last bar
    sig_cat = strat.signal(closes, closes, closes, closes)
    sig_mine = C.build_signal(px[[col]], fast, slow)[col].dropna().iloc[-1]
    print(f"  signal on last bar: catalog {sig_cat:+.0f}  mine {sig_mine:+.0f}  "
          f"{'OK ' if (sig_cat > 0) == (sig_mine > 0) else 'MISMATCH'}")
    ok &= (sig_cat > 0) == (sig_mine > 0)

    # ---- 2. look-ahead perturbation test ------------------------------- #
    print("\n=== 2. no look-ahead: perturb all post-TRAIN prices ===")
    score = C.build_score(px, C.build_signal(px, fast, slow))
    base = C.run(px, score, C.TRAIN)
    b = {"cagr": base.metrics.cagr, "sharpe": base.metrics.sharpe,
         "maxdd": base.metrics.max_drawdown, "total": base.equity.iloc[-1]}
    print(f"  baseline TRAIN: CAGR {b['cagr'] * 100:.6f}%  Sharpe {b['sharpe']:.6f}  "
          f"equity_end {b['total']:.10f}")

    cut = pd_ts(px, C.TRAIN[1])
    rng = np.random.default_rng(12345)
    shocks = {}
    for scale in (0.05, 0.30):
        tampered = px.copy()
        m = tampered.index > cut
        tampered.loc[m] = tampered.loc[m] * (
            1.0 + scale * rng.standard_normal((int(m.sum()), tampered.shape[1]))
        )
        r = C.run(tampered, C.build_score(tampered, C.build_signal(tampered, fast, slow)),
                  C.TRAIN)
        t = {"cagr": r.metrics.cagr, "sharpe": r.metrics.sharpe,
             "maxdd": r.metrics.max_drawdown, "total": r.equity.iloc[-1]}
        same = all(abs(t[k] - b[k]) < 1e-12 for k in b)
        shocks[f"shock{scale}"] = {"identical": bool(same), **t}
        print(f"  shock +/-{scale * 100:.0f}% post-cut -> TRAIN CAGR "
              f"{t['cagr'] * 100:.6f}%  equity_end {t['total']:.10f}  "
              f"{'IDENTICAL' if same else 'CHANGED  <-- LEAK'}")
        ok &= same

    # ---- 3. AGENT_BRIEF sec.6 sanity ------------------------------------ #
    print("\n=== 3. sanity checks (TRAIN) ===")
    names = base.diag["avg_names"]
    print(f"  avg names held {names:.1f}  (48 would mean residual accretion; "
          f"expect ~22)")
    ok &= 15 <= names <= 30
    print(f"  CAGR {base.metrics.cagr * 100:.2f}%  "
          f"(>50% for an unlevered long-only NIFTY-50 book = bug)")
    ok &= base.metrics.cagr < 0.50
    lt = C.signal_liveness(C.build_signal(px, fast, slow))
    print(f"  signal long {lt['frac_bars_long'] * 100:.1f}% of symbol-bars  "
          f"(brief floor 5%)")
    ok &= lt["frac_bars_long"] > 0.05
    print(f"  max single weight {base.diag['avg_top_weight'] * 100:.2f}% "
          f"(cap 12%)  |  round-trip {base.diag['round_trip_bps']:.2f} bps")
    ok &= base.diag["avg_top_weight"] <= 0.12 + 1e-6
    print(f"\nALL CHECKS {'PASS' if ok else 'FAIL'}")

    (HERE / "integrity.json").write_text(json.dumps(
        {"all_pass": bool(ok), "baseline_train": b, "shock": shocks}, indent=2))


def pd_ts(px, s: str):
    import pandas as pd

    return pd.Timestamp(s, tz=px.index.tz)


if __name__ == "__main__":
    main()
