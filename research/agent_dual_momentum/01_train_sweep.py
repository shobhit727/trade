"""STEP 1 — TRAIN-window sweep over the 5 declared variants.

TRAIN = 2016-01-01 .. 2023-12-31. Nothing in this script touches TEST.
Writes the TRAIN table + the selected variant to train_result.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import common as C

HERE = Path(__file__).parent

#: The declared budget. Do not edit after the fact -- see 00_DECLARED_BUDGET.md.
VARIANTS: list[tuple[str, int, int]] = [
    ("V1_ema10_30", 10, 30),
    ("V2_ema20_60", 20, 60),
    ("V3_ema50_200", 50, 200),
    ("V4_ema10_100", 10, 100),
    ("V5_ema30_120", 30, 120),
]


def main() -> None:
    px = C.panel()
    print(f"panel {px.shape}  {px.index[0].date()} .. {px.index[-1].date()}")
    print(f"universe: {len(C.symbols())} names\n")

    rows: list[dict] = []
    live: dict[str, dict] = {}

    for name, fast, slow in VARIANTS:
        sig = C.build_signal(px, fast, slow)
        live[name] = C.signal_liveness(sig)
        score = C.build_score(px, sig)
        res = C.run(px, score, C.TRAIN)
        rows.append(C.row(name, res.metrics, res))
        print(f"{name:<14} liveness {live[name]['frac_bars_long'] * 100:5.1f}%  "
              f"flagged/day {live[name]['mean_flagged_per_day']:5.1f}")

    # Reference points on the identical TRAIN window.
    comp = C.composite_score(px)
    res_comp = C.run(px, comp, C.TRAIN)
    rows.append(C.row("composite_baseline", res_comp.metrics, res_comp, extra="nsealgo"))

    bh = C.buy_and_hold(px, C.TRAIN)
    rows.append(C.row("buy_and_hold", bh, extra="equal-weight, 1 round trip"))

    print("\n=== TRAIN  2016-01-01 .. 2023-12-31 ===")
    print(C.table(rows))

    print("\nyearly returns (TRAIN):")
    for name, _f, _s in VARIANTS:
        sig = C.build_signal(px, _f, _s)
        r = C.run(px, C.build_score(px, sig), C.TRAIN).returns
        print(f"  {name:<14} {C.yearly(r)}")
    print(f"  {'composite':<14} {C.yearly(res_comp.returns)}")

    # Selection: TRAIN Calmar, TRAIN CAGR as tie-break. Declared up front.
    cands = [r for r in rows if r["name"] in {v[0] for v in VARIANTS}]
    best = max(cands, key=lambda r: (round(r["calmar"], 6), round(r["cagr"], 6)))
    print(f"\nSELECTED ON TRAIN: {best['name']}  "
          f"Calmar {best['calmar']:.2f}  CAGR {best['cagr'] * 100:.2f}%")

    # Sanity check 3 from AGENT_BRIEF sec.6, on the selected variant.
    sel_fast, sel_slow = next((f, s) for n, f, s in VARIANTS if n == best["name"])
    sig = C.build_signal(px, sel_fast, sel_slow)
    score = C.build_score(px, sig)
    lv = C.signal_liveness(sig)
    rb = C.run(px, score, C.TRAIN)
    n_scored = score.loc[C.win_mask(score, C.TRAIN)].notna().sum(axis=1)
    print(f"  signal long on {lv['frac_bars_long'] * 100:.1f}% of symbol-bars "
          f"(AGENT_BRIEF floor: 5%)")
    print(f"  avg names held {rb.diag['avg_names']:.1f} (expect ~22, not 48)")
    print(f"  round-trip bps charged {rb.diag['round_trip_bps']:.2f}")
    print(f"  TRAIN days with <22 scorable names: "
          f"{int((n_scored < 22).sum())} of {len(n_scored)}")

    (HERE / "train_result.json").write_text(
        json.dumps(
            {
                "window": C.TRAIN,
                "rows": [
                    {k: (v if isinstance(v, str) else (None if v is None else float(v)))
                     for k, v in r.items()}
                    for r in rows
                ],
                "liveness": live,
                "selected": best["name"],
                "selected_params": {"fast": sel_fast, "slow": sel_slow},
            },
            indent=2,
        )
    )
    print(f"\nwrote {HERE / 'train_result.json'}")




if __name__ == "__main__":
    main()
