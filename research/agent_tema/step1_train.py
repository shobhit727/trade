"""Step 1 -- TRAIN-only sweep over the 5 declared variants.

TRAIN window only: 2016-01-01 -> 2023-12-31. TEST is NOT loaded as a price window in
this script at all; `panel_full` is loaded for indicator history but sliced to TRAIN
before any metric is computed.

Emits: train_results.json, liveness.json, fidelity.json
"""

from __future__ import annotations

import json
import os

from harness import (
    COST_MODEL,
    HERE,
    RT_BPS,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    ZERO_COST,
    ZERO_RT_BPS,
    build_score,
    composite,
    fidelity_check,
    fmt,
    liveness,
    load_panel,
    run,
    summarise,
)

OUT = {}


def main() -> None:
    print(f"cost: round trip = {RT_BPS:.2f} bps   (zero-cost control = {ZERO_RT_BPS:.2f} bps)")
    panel = load_panel()
    # Indicator history is computed on the FULL panel, then sliced. Never the reverse.
    panel_full = panel

    # ---- TRAIN window only -------------------------------------------------
    tr = panel_full.loc[:TRAIN_END].loc[TRAIN_START:]

    OUT["window"] = {
        "train": [str(TRAIN_START.date()), str(TRAIN_END.date())],
        "train_bars": int(len(tr)),
    }

    # ---- signal liveness, per variant period (diagnostic, not a variant) ----
    lv = {f"period_{p}": liveness(panel_full, p) for p in (20, 50, 100)}
    OUT["liveness_full_panel"] = lv
    print("\nSIGNAL LIVENESS (full panel)")
    for k, v in lv.items():
        print(
            f"  {k:<12} long {v['frac_bars_long'] * 100:>5.1f}%  "
            f"short {v['frac_bars_short'] * 100:>5.1f}%  "
            f"mean eligible {v['mean_eligible_names']:>5.1f}  min {v['min_eligible_names']:>3.0f}"
        )

    # ---- streaming-buffer fidelity ----------------------------------------
    fid = {f"period_{p}": fidelity_check(panel_full, period=p, n_sym=2)
           for p in (20, 50, 100)}
    OUT["fidelity"] = fid
    print("\nSTREAMING-BUFFER FIDELITY (full-history EMA vs source maxlen=300)")
    for p, d in fid.items():
        for s, v in d.items():
            print(
                f"  {p:<12} {s:<12} max_rel {v['max_rel']:.3e}  "
                f"p99_rel {v['p99_rel']:.3e}  signal disagreements "
                f"{v['signal_disagreements']}/{v['n_bars']}"
            )

    # ---- the 5 declared variants on TRAIN ----------------------------------
    rows = []
    print(f"\nTRAIN SWEEP (net of {RT_BPS:.2f} bps round trip)")
    for name, spec in VARIANTS.items():
        score = build_score(panel_full, spec["period"], spec["rank"])
        score_tr = score.loc[:TRAIN_END].loc[TRAIN_START:]
        res = run(tr, score_tr, COST_MODEL)
        d = summarise(res, f"{name} p{spec['period']}/{spec['rank']}")
        d["variant"] = name
        d["period"] = spec["period"]
        d["rank"] = spec["rank"]
        rows.append(d)
        print("  " + fmt(d))

        # zero-cost control on the same variant (diagnostic)
        res0 = run(tr, score_tr, ZERO_COST)
        d0 = summarise(res0, f"{name} ZERO-COST")
        d0["variant"] = name
        d0["zero_cost"] = True
        rows.append(d0)
        print("  " + fmt(d0))

    OUT["train"] = rows

    # ---- composite reference on TRAIN (context only) ----------------------
    comp = composite(tr, COST_MODEL)
    cs = {k: v for k, v in comp.items() if k not in ("equity", "returns")}
    OUT["train_composite"] = cs
    print("\n  " + fmt(cs))

    # ---- selection: best TRAIN Sharpe, tie-break Calmar -------------------
    real = [r for r in rows if not r.get("zero_cost")]
    best = max(real, key=lambda r: (round(r["sharpe"], 6), round(r["calmar"], 6)))
    OUT["selected"] = best
    print(f"\nSELECTED (best TRAIN Sharpe, tie-break Calmar): {best['variant']} "
          f"period={best['period']} rank={best['rank']} "
          f"TRAIN Sharpe {best['sharpe']:.3f} Calmar {best['calmar']:.3f}")
    with open(os.path.join(HERE, "selected.json"), "w") as f:
        json.dump({"variant": best["variant"], "period": best["period"],
                   "rank": best["rank"]}, f, indent=2)

    with open(os.path.join(HERE, "train_results.json"), "w") as f:
        json.dump(OUT, f, indent=2, default=str)
    print("\nwrote train_results.json + selected.json")


if __name__ == "__main__":
    main()
