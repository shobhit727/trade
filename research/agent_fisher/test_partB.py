"""PART B — supplementary experiment, DISCLOSED AS BEYOND THE 5-VARIANT BUDGET.

Problem (report §6.2): the binary Fisher gate flags ~13 of 48 names, fewer than the
22-name target, so the turnover-budget blend leaves ~59% of the book as stale residue
and only 41% Fisher-positive. That construction barely tests the indicator.

Fix: use the Fisher value as a **continuous cross-sectional rank** instead of a gate.
Every name gets a score, the 22-name target is reachable, and the book is 100% the
strategy's idea by construction.

DECLARED BUDGET FOR PART B: 3 variants — `period` in {5, 10, 20}, NO threshold.
Selection on TRAIN only; a single frozen TEST evaluation.
"""

from __future__ import annotations

import json

from common import TEST, TRAIN, bt, fisher_panel, fmt, load, slice_metrics, window_diag

VARIANTS = [("B1", 5), ("B2", 10), ("B3", 20)]


def continuous_score(panel, period: int):
    """Score = cross-sectional percentile rank of the *negated* Fisher value.

    High score = oversold (Fisher very negative) = most attractive, which is the
    strategy's own contrarian intent expressed in a long-only book.
    """
    f = fisher_panel(panel, period)
    return (-f).rank(axis=1, pct=True, na_option="keep")


def main() -> None:
    panel, _ = load()

    print("=== PART B — TRAIN (2016-2023), continuous Fisher rank ===")
    rows = []
    for name, period in VARIANTS:
        sc = continuous_score(panel, period)
        res = bt(panel, sc)
        gross = bt(panel, sc, zero_cost=True)
        m = slice_metrics(res.equity, res.returns, *TRAIN)
        dg = window_diag(res, *TRAIN, gross_result=gross)
        gm = slice_metrics(gross.equity, gross.returns, *TRAIN)
        rows.append((name, period, m, dg, gm.cagr))
        print(fmt(m, f"{name} period={period} (NET)"))
        print(f"{'':22} gross CAGR {gm.cagr*100:.2f}%  drag {dg['cost_drag_annual']*100:.2f}%/y  "
              f"names {dg['avg_material_names']:.1f}  bookwt {dg['avg_book_weight']:.3f}")

    pick = max(rows, key=lambda r: r[2].sharpe)
    print(f"\nPART B selection (TRAIN Sharpe): {pick[0]} period={pick[1]}")
    with open("partB_selection.json", "w") as fh:
        json.dump({"selected": pick[0], "period": pick[1]}, fh)

    # ---------------- single frozen TEST evaluation ----------------
    with open("partB_selection.json") as fh:
        sel = json.load(fh)
    print(f"\nfrozen: {sel['selected']} (period={sel['period']})")
    print(f"=== PART B — TEST ({TEST[0]} -> {TEST[1]}), net of 21.92 bps ===")
    sc = continuous_score(panel, sel["period"])
    res = bt(panel, sc)
    gross = bt(panel, sc, zero_cost=True)
    m = slice_metrics(res.equity, res.returns, *TEST)
    dg = window_diag(res, *TEST, gross_result=gross)
    gm = slice_metrics(gross.equity, gross.returns, *TEST)
    print(fmt(m, "Part B (NET)"))
    print(f"{'':22} gross CAGR {gm.cagr*100:.2f}%  drag {dg['cost_drag_annual']*100:.2f}%/y")
    print(f"{'':22} vol {m.volatility*100:.1f}%  names {dg['avg_material_names']:.1f}  "
          f"bookwt {dg['avg_book_weight']:.3f}  purity 100% (by construction)")

    with open("test_partB.json", "w") as fh:
        json.dump({"selected": sel["selected"], "period": sel["period"],
                   "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
                   "calmar": m.calmar, "gross_cagr": gm.cagr, **dg}, fh, indent=2)
    print("saved test_partB.json")


if __name__ == "__main__":
    main()
