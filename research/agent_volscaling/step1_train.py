"""Step 1 — TRAIN sweep over the 5 declared variants. Selection on TRAIN only.

The winner (highest TRAIN Sharpe, tie-break Calmar) is written to `frozen.txt`.
TEST is not touched in this script.
"""

from __future__ import annotations

from harness import (
    TRAIN_END,
    TRAIN_START,
    bh_row,
    build_score,
    print_table,
    run_on,
)
from step0_audit import main as _audit_unused  # noqa: F401  (ensures path setup)

#: (label, kwargs-for-build_score). Exactly the 5 variants declared in REPORT.md.
VARIANTS = [
    ("V1_shipped_mom126", dict(min_vol=0.001, ranking="mom126", period=14, use_direction=True)),
    ("V2_shipped_lowvol", dict(min_vol=0.001, ranking="lowvol", period=14, use_direction=True)),
    ("V3_gate_p50_mom126", dict(min_vol=0.025284, ranking="mom126", period=14, use_direction=True)),
    ("V4_gateonly_mom126", dict(min_vol=0.025284, ranking="mom126", period=14, use_direction=False)),
    ("V5_gate_p25_mom126", dict(min_vol=0.020323, ranking="mom126", period=14, use_direction=True)),
]


def main() -> None:
    print("=" * 92)
    print("STEP 1 — TRAIN (2016-01-01 -> 2023-12-31), selection set")
    print("=" * 92)
    rows = []
    for label, kw in VARIANTS:
        score = build_score(**kw)
        rows.append(run_on(label, "TRAIN", score, TRAIN_START, TRAIN_END))
    variant_rows = list(rows)
    rows.append(bh_row("TRAIN_buy_and_hold", "TRAIN", TRAIN_START, TRAIN_END))
    print_table(rows)

    # Selection is among the declared variants only -- buy-and-hold is a benchmark,
    # never a candidate strategy.
    best = max(variant_rows, key=lambda r: (r.sharpe, r.calmar))
    params = dict(VARIANTS)[best.label]
    with open("frozen.txt", "w") as f:
        f.write(best.label + "\n")
        f.write(repr(params) + "\n")
    print(f"\nFROZEN: {best.label}  (TRAIN Sharpe {best.sharpe:.2f}, Calmar {best.calmar:.2f})")
    print(f"params: {params}")
    print("Written to frozen.txt. TEST untouched in this script.")


if __name__ == "__main__":
    main()
