"""Step 1 — TRAIN sweep over the 5 declared variants. TEST is NOT touched here."""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "research/agent_gaussian")

from harness import (  # noqa: E402
    TRAIN,
    VARIANTS,
    build_score,
    cost_model,
    fmt_rows,
    row,
    run_window,
)

from nsealgo.data.loader import load_universe  # noqa: E402


def main() -> None:
    panel, symbols, _rep = load_universe("data/nse")

    cm = cost_model()
    from decimal import Decimal

    print("=== cost sanity ===")
    print("  round_trip_bps(100k)      :", float(cm.round_trip_bps(Decimal("100000"))))
    print("  all_in_round_trip_bps(1e5):", float(cm.all_in_round_trip_bps(Decimal("100000"))))
    print()

    rows = []
    print("=== TRAIN 2016-01-01 -> 2023-12-31 (selection window) ===")
    for vid, per, ent, con in VARIANTS:
        score = build_score(panel, per, ent, con)
        res = run_window(panel, score, TRAIN)
        r = row(res, vid)
        r.update(period=per, entry=ent, construction=con)
        rows.append(r)
        print(
            f"  {vid} p={per:<4} e={ent:<4} {con:<9} "
            f"CAGR {r['cagr'] * 100:>7.2f}%  Sharpe {r['sharpe']:>6.2f}  "
            f"MaxDD {r['maxdd'] * 100:>7.2f}%  names {r['names']:>5.1f}"
        )
    print()
    print(fmt_rows(rows))

    df = pd.DataFrame(rows).set_index("id")
    print()
    print("=== declared selection rule: max TRAIN Sharpe; ties (<=0.02) -> lower MaxDD ===")
    best_sharpe = df["sharpe"].max()
    tie = df[df["sharpe"] >= best_sharpe - 0.02]
    if len(tie) > 1:
        winner = tie["maxdd"].idxmax()  # maxdd is negative; closest to 0 wins
        print(f"  {len(tie)} variants within 0.02 Sharpe of {best_sharpe:.2f}: "
              f"{list(tie.index)} -> tie-break on MaxDD -> {winner}")
    else:
        winner = df["sharpe"].idxmax()
        print(f"  single winner: {winner} (Sharpe {best_sharpe:.2f})")
    print(f"\nWINNER = {winner}")
    df.to_csv("research/agent_gaussian/train_results.csv")


if __name__ == "__main__":
    main()
