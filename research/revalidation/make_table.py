"""Build `reports/TIEBREAK_REVALIDATION.md` from `results.json`.

Classification is decided on the TEST window (that is the number CATALOG_TRIALS publishes)
with TRAIN as a secondary column, because a selection rule is moved by TRAIN noise even
when the out-of-sample book is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROWS = json.loads((HERE / "results.json").read_text())

BH_TEST_CAGR = 0.0826
BH_TEST_SHARPE = 0.1891

#: A published number is called invalidated when the engine move is large enough that
#: quoting the old figure would be wrong -- 0.5pp of CAGR or 0.10 of Sharpe. Chosen before
#: looking at the distribution, and roughly 1/4 of the spread CATALOG_TRIALS itself treats
#: as meaningful ("cross-agent comparisons below ~1.5pp should not be treated as
#: meaningful"). "Suspect" is anything the tie-break touched at all.
CAGR_EPS = 0.005
SHARPE_EPS = 0.10


def verdict(r: dict) -> str:
    moved = r["book_diff_frac"] > 0.0 or r["empty_rebalances"] > 0
    material = abs(r["delta_cagr_pp"]) >= CAGR_EPS * 100 or abs(r["delta_sharpe"]) >= SHARPE_EPS
    if material:
        return "INVALIDATED"
    return "SUSPECT" if moved else "UNAFFECTED"


def main() -> None:
    te = {r["label"].split("|")[0]: r for r in ROWS if r["label"].endswith("|TEST") and "old" in r}
    tr = {r["label"].split("|")[0]: r for r in ROWS if r["label"].endswith("|TRAIN") and "old" in r}

    order = sorted(
        te,
        key=lambda k: (
            {"INVALIDATED": 0, "SUSPECT": 1, "UNAFFECTED": 2}[verdict(te[k])],
            -abs(te[k]["delta_cagr_pp"]),
            k,
        ),
    )
    counts: dict[str, int] = {}
    for k in order:
        counts[verdict(te[k])] = counts.get(verdict(te[k]), 0) + 1

    lines: list[str] = []
    w = lines.append
    w("| agent | frozen variant | old turn | new turn | old CAGR | new CAGR | ΔCAGR | old Shp | new Shp | book moved | verdict |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for k in order:
        r, t = te[k], tr.get(k)
        ag, var = k.split("::", 1)
        w(
            f"| `{ag}` | {var.split('|')[0]} | {r['old']['turnover']:.2f} | {r['new']['turnover']:.2f} "
            f"| {r['old']['cagr'] * 100:.2f}% | {r['new']['cagr'] * 100:.2f}% "
            f"| **{r['delta_cagr_pp']:+.2f}pp** | {r['old']['sharpe']:.2f} | {r['new']['sharpe']:.2f} "
            f"| {r['book_diff_frac']:.0%} | **{verdict(r)}** |"
            + (f" _(TRAIN {t['old']['cagr'] * 100:.2f}% → {t['new']['cagr'] * 100:.2f}%)_" if t else "")
        )

    (HERE / "table.md").write_text("\n".join(lines) + "\n")

    print(f"counts: {counts}")
    print("\nINVALIDATED:")
    for k in order:
        if verdict(te[k]) == "INVALIDATED":
            r = te[k]
            print(
                f"  {k:52s} {r['old']['cagr'] * 100:6.2f}% -> {r['new']['cagr'] * 100:6.2f}% "
                f"({r['delta_cagr_pp']:+.2f}pp)  shp {r['old']['sharpe']:+.2f} -> {r['new']['sharpe']:+.2f} "
                f"bk {r['book_diff_frac']:.0%} flat {r['tie']['flat_mask_frac']:.0%}"
            )
    print("\nSUSPECT:")
    for k in order:
        if verdict(te[k]) == "SUSPECT":
            r = te[k]
            print(f"  {k:52s} {r['delta_cagr_pp']:+.2f}pp bk {r['book_diff_frac']:.0%}")

    print("\nbest new TEST CAGR:", max(te.values(), key=lambda r: r["new"]["cagr"])["label"])
    print("beating BH:", [k for k, r in te.items() if r["new"]["cagr"] > BH_TEST_CAGR])
    print("sharpe sign flips:", [k for k, r in te.items() if (r["old"]["sharpe"] > 0) != (r["new"]["sharpe"] > 0)])
    print("bit-identical TEST:", sum(1 for r in te.values() if r["book_diff_frac"] == 0.0), "/", len(te))


if __name__ == "__main__":
    main()
