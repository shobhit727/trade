"""Step 1 — TRAIN only. Selects one variant of the declared 5 by TRAIN Sharpe.

TEST is not touched anywhere in this file. The selected variant is printed and
frozen; `frozen.txt` records it so step 2 cannot silently pick something else.
"""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research/agent_voltarget")

from harness import (  # noqa: E402  # noqa: E402
    HDR,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    assert_engine_pinned,
    bh_row,
    line,
    load_panel,
    natr,
    row_for_variant,
    run,
    source_flag,
)


def main() -> None:
    assert_engine_pinned()
    panel, _ = load_panel()

    print("=" * 92)
    print("STEP 1 — TRAIN (2016-01-01 -> 2023-12-31). TEST untouched.")
    print("=" * 92)

    n = len(panel.loc[TRAIN_START:TRAIN_END])
    print(f"bars in TRAIN: {n}  (~{n / 244:.2f} years)")
    print()

    flag = source_flag(panel).loc[TRAIN_START:TRAIN_END]
    cnt = flag.sum(axis=1)
    print("ELIGIBILITY on TRAIN (how many names the source flag admits per bar):")
    for q in (0, 10, 25, 50, 75, 90, 100):
        print(f"  p{q:<3} {np.percentile(cnt, q):6.1f} names")
    print(f"  mean {cnt.mean():.2f}   bars with >=22 eligible: "
          f"{(cnt >= 22).mean() * 100:.1f}%   bars with >=1: {(cnt >= 1).mean() * 100:.1f}%")
    print()

    rows = []
    for v in VARIANTS:
        r = row_for_variant(v, "TRAIN", v, panel, TRAIN_START, TRAIN_END)
        rows.append(r)
        print(line(r))
    print()
    print(line(bh_row("TRAIN buy-and-hold", "TRAIN", panel, TRAIN_START, TRAIN_END)))
    print()
    print(HDR)

    # selection rule, fixed in advance: highest TRAIN Sharpe, tie-break Calmar
    best = max(rows, key=lambda r: (round(r.sharpe, 6), round(r.calmar, 6)))
    print()
    print(f"SELECTED (highest TRAIN Sharpe): {best.label}  "
          f"Sharpe {best.sharpe:.2f}  CAGR {best.cagr * 100:.2f}%")

    with open("research/agent_voltarget/frozen.txt", "w") as f:
        f.write(best.label + "\n")

    # naive grid-free read: how much of the result is the flag at all?
    # (diagnostic on TRAIN only -- not a selection input)
    print()
    print("TRAIN diagnostic — momentum ranking with NO flag at all:")
    res = run(panel, panel / panel.shift(126) - 1.0, TRAIN_START, TRAIN_END)
    print(f"  mom126 unflagged   CAGR {res.metrics.cagr * 100:6.2f}%  "
          f"Sharpe {res.metrics.sharpe:5.2f}  MaxDD {res.metrics.max_drawdown * 100:7.2f}%  "
          f"Names {res.diag['avg_names']:.1f}")
    print(f"  NATR14 median on TRAIN {np.nanmedian(natr(panel, 14).loc[TRAIN_START:TRAIN_END].to_numpy()):.4f}")


if __name__ == "__main__":
    main()
