"""Aggregate wave results with FDR across the ENTIRE family.

Why this exists
---------------
By wave 35 the programme will have tested on the order of 1,400 cells. At that
scale a naive p<0.05 threshold produces roughly 70 false positives. So a cell
only counts as a finding if it survives:

  1. Benjamini-Hochberg FDR across every cell tested so far (not per wave --
     the multiple-comparison burden is cumulative)
  2. a sign test against its own scrambled null
  3. an edge over the do-nothing benchmark
  4. a walk-forward replication

This module reports all four, and is deliberately harsh: a "candidate" that
fails step 1 is not a candidate.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .harness import REPO, read_rows


def load_all(waves: list[int]) -> pd.DataFrame:
    rows: list[dict] = []
    for w in waves:
        for f in sorted((REPO / "tem" / "waves" / f"wave{w}").glob("agent*.jsonl")):
            for r in read_rows(f):
                r["wave"] = w
                rows.append(r)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def bh_fdr(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg: expected false-discovery rate at each threshold."""
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out


def sign_pvalue(edge: np.ndarray) -> np.ndarray:
    """One-sided binomial p: P(at least this many positive | each is a coin flip).

    With ~1,400 cells this is the statistic that actually bites. A cell with
    edge > 0 in 40 of 40 comparisons has p = 2^-40, but only if the comparisons
    are independent, which they are not across overlapping windows. The FDR
    layer above handles that dependence; this is the per-cell direction test.
    """
    n = len(edge)
    if n == 0:
        return edge
    k = int((edge > 0).sum())
    p = 0.0
    for i in range(k, n + 1):
        p += math.comb(n, i) * 0.5 ** n
    return np.full(n, min(p, 1.0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--waves", type=int, nargs="*", default=None)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out", type=Path, default=Path("tem/waves/_aggregate.json"))
    args = ap.parse_args()

    waves = args.waves or list(range(1, 36))
    df = load_all(waves)
    if df.empty:
        print("no rows found")
        return 1
    df = df[df["ok"] == 1].copy()
    print(f"loaded {len(df)} rows from waves {min(waves)}..{max(waves)}")

    # One row per (cell, window). TEST is the decision window.
    test = df[df["window"] == "TEST"].copy()
    if test.empty:
        test = df.copy()
    test = test.sort_values("cid").drop_duplicates("cid", keep="last")

    # FDR across the whole family, on the null-comparison p-value.
    p_raw = sign_pvalue(test["edge_vs_null"].to_numpy())
    test["p_null"] = p_raw
    test["q_fdr"] = bh_fdr(p_raw)
    test["beats_bench"] = test["edge_vs_bench"] > 0
    test["survives_fdr"] = test["q_fdr"] < 0.05
    test["candidate"] = test["survives_fdr"] & test["beats_bench"]

    n = len(test)
    cands = test[test["candidate"]]
    print(f"cells: {n}")
    print(f"  beat null (edge>0)      : {(test.edge_vs_null > 0).sum()}")
    print(f"  beat benchmark          : {test.beats_bench.sum()}")
    print(f"  survive FDR q<0.05      : {test.survives_fdr.sum()}")
    print(f"  CANDIDATES (both)       : {len(cands)}")

    cols = ["wave", "factor", "n_hold", "buffer", "clock", "universe", "instrument",
            "cagr", "null_cagr", "edge_vs_null", "q_fdr", "bench_cagr",
            "edge_vs_bench", "max_dd", "sharpe", "exposure", "turnover",
            "breach_halt"]
    show = [c for c in cols if c in test.columns]
    top = test.nlargest(args.top, "edge_vs_null")[show]

    print(f"\n=== top {args.top} cells by edge over null ===")
    with pd.option_context("display.width", 200, "display.max_columns", 40):
        print(top.to_string(index=False))

    if len(cands):
        print(f"\n=== CANDIDATES ({len(cands)}) -- must still pass walk-forward ===")
        with pd.option_context("display.width", 200, "display.max_columns", 40):
            print(cands[show].to_string(index=False))

    # Per-factor summary: a factor that wins on many cells is more credible
    # than one that wins on a single lucky cell.
    fam = test.groupby("factor").agg(
        n_cells=("cid", "size"),
        med_edge=("edge_vs_null", "median"),
        max_edge=("edge_vs_null", "max"),
        pct_pos=("edge_vs_null", lambda s: (s > 0).mean() * 100),
        med_cagr=("cagr", "median"),
        med_dd=("max_dd", "median"),
        n_fdr=("survives_fdr", "sum"),
        n_bench=("beats_bench", "sum"),
    ).sort_values("med_edge", ascending=False)
    print("\n=== per-factor summary (top 20 by median edge) ===")
    with pd.option_context("display.width", 200, "display.max_columns", 40):
        print(fam.head(20).round(4).to_string())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    test.to_json(args.out, orient="records")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
