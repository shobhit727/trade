"""STEP 3 — TRAIN-only ablation. Explains WHY the TEST result came out negative.

Deliberately TRAIN-only: the holdout has already been spent on the single selected
variant, and re-opening it for a second configuration would turn TEST into a second
training set. Everything here is diagnostic, not selection -- nothing here can change
the headline number already reported.

Three questions:
  1. Does the EMA gate carry any information at all? (forward 6m return of flagged
     vs unflagged symbol-bars, TRAIN only)
  2. How much does the gate actually change the book? (top-22 overlap on rebalance dates)
  3. What does the strategy score to with the gate removed? (pure 6m momentum)
"""

from __future__ import annotations

import json
from pathlib import Path

import common as C
import numpy as np

HERE = Path(__file__).parent


def main() -> None:
    px = C.panel()
    fast, slow = 50, 200
    sig = C.build_signal(px, fast, slow)
    train = C.win_mask(px, C.TRAIN)

    # ---- 1. information content of the gate --------------------------- #
    fwd = (px.shift(-126) / px - 1.0)          # forward 6m return, for scoring only
    fwd_t = fwd.loc[train]
    s_t = sig.loc[train]
    ok = s_t.notna() & fwd_t.notna()
    a = fwd_t.to_numpy()[ok.to_numpy()]
    b = s_t.to_numpy()[ok.to_numpy()] > 0
    long_r, flat_r = a[b], a[~b]
    diff = float(long_r.mean() - flat_r.mean())
    se = float(np.sqrt(long_r.var(ddof=1) / len(long_r) + flat_r.var(ddof=1) / len(flat_r)))
    print("=== TRAIN: does the EMA gate predict anything? ===")
    print(f"  flagged   n={len(long_r):>8,}  mean fwd-6m {long_r.mean() * 100:>7.3f}%  "
          f"hit>0 {(long_r > 0).mean() * 100:5.1f}%")
    print(f"  unflagged n={len(flat_r):>8,}  mean fwd-6m {flat_r.mean() * 100:>7.3f}%  "
          f"hit>0 {(flat_r > 0).mean() * 100:5.1f}%")
    print(f"  spread {diff * 100:+.3f}% per 6m   t = {diff / se:+.2f}")
    print(f"  -> the gate is {'informative' if abs(diff / se) > 2 else 'NOT informative'}"
          f" at the 2-sigma level on TRAIN")

    # ---- 2. how much does the gate change the book? ------------------- #
    mom = px / px.shift(126) - 1.0
    top22_gated = mom.where(sig > 0).rank(axis=1, ascending=False)
    months = px.loc[train].index.to_period("M").unique()
    overlaps: list[float] = []
    gate_blocks: list[float] = []
    for p in months:
        sel = train & (px.index.to_period("M") == p)
        if not sel.any():
            continue
        g22 = top22_gated.loc[sel].iloc[-1]
        n = min(22, int(g22.notna().sum()))
        kept = float((g22 <= n).fillna(False).sum())
        overlaps.append(kept / max(n, 1))
        gate_blocks.append(1.0 - float((sig.loc[sel].iloc[-1] > 0).sum()) / px.shape[1])
    print("\n=== TRAIN: how binding is the gate? ===")
    print(f"  months examined            {len(overlaps)}")
    print(f"  mean fraction of gated top-22 slots filled "
          f"{np.mean(overlaps) * 100:.1f}%")
    print(f"  mean fraction of the universe the gate excludes "
          f"{np.mean(gate_blocks) * 100:.1f}%")
    print(f"  mean scorable names/day    {float(sig.loc[train].gt(0).sum(axis=1).mean()):.1f}"
          f"  (we can hold 22 of {px.shape[1]})")

    # ---- 3. ablation: same score, no gate ------------------------------ #
    ungated = mom.rank(axis=1, pct=True)
    res_s = C.run(px, C.build_score(px, sig), C.TRAIN)
    res_u = C.run(px, ungated, C.TRAIN)
    comp = C.run(px, C.composite_score(px), C.TRAIN)
    bh = C.buy_and_hold(px, C.TRAIN)
    print("\n=== TRAIN: with vs without the EMA gate ===")
    print(C.table([
        C.row("dual_momentum V3", res_s.metrics, res_s),
        C.row("ABLATION: 6m mom, no gate", res_u.metrics, res_u),
        C.row("composite_baseline", comp.metrics, comp),
        C.row("buy_and_hold", bh),
    ]))
    print(f"\n  gate effect on TRAIN: CAGR "
          f"{(res_s.metrics.cagr - res_u.metrics.cagr) * 100:+.2f}pp  "
          f"Sharpe {res_s.metrics.sharpe - res_u.metrics.sharpe:+.2f}  "
          f"Calmar {res_s.metrics.calmar - res_u.metrics.calmar:+.2f}")
    print("  (ABLATION is a diagnostic, not one of the 5 declared variants, and it "
          "never sees TEST)")

    (HERE / "ablation_train.json").write_text(json.dumps({
        "gate_spread_6m": diff,
        "gate_t_stat": float(diff / se),
        "mean_gated_top22_fill": float(np.mean(overlaps)),
        "cagr_with_gate": float(res_s.metrics.cagr),
        "cagr_no_gate": float(res_u.metrics.cagr),
        "sharpe_with_gate": float(res_s.metrics.sharpe),
        "sharpe_no_gate": float(res_u.metrics.sharpe),
    }, indent=2))
    print(f"\nwrote {HERE / 'ablation_train.json'}")


if __name__ == "__main__":
    main()
