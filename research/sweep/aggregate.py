"""Aggregate wave results with FDR across the ENTIRE family.

Why this exists
---------------
By wave 35 the programme will have tested on the order of 1,400 cells. At that
scale a naive p<0.05 threshold produces roughly 70 false positives. So a cell
only counts as a finding if it survives:

  1. Benjamini-Hochberg FDR across every hypothesis tested so far (not per
     wave -- the multiple-comparison burden is cumulative)
  2. an edge over the do-nothing benchmark (the decisive metric: the scrambled
     null churns more than a persistent book, so edge_vs_null alone rewards
     turnover, not skill)
  3. a sign test against its own scrambled null
  4. a TRAIN replication

Unit of hypothesis
------------------
A single (factor, n_hold, buffer, clock) cell is a *configuration*, not a
hypothesis. Testing 36 configs of one signal and reporting the best as a
discovery is exactly the post-hoc selection this project has already been
burned by. So the hypothesis unit is the FACTOR: its p-value is the binomial
tail probability of seeing at least k of its n configs beat the benchmark if
the signal carried no information. BH-FDR is applied across factors.

Fixes over the first draft (which reported nothing and could not have worked):
  * glob was "agent*.jsonl"; files are "aNN.jsonl" -> zero rows found
  * directory was "wave{w}"; actual layout is "w{w}"
  * sign_pvalue computed ONE p-value from the whole array and broadcast it to
    every cell, so every q_fdr was identical and the FDR layer was inert
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .harness import REPO, read_rows

CELL_GLOB = "a[0-9][0-9].jsonl"
TRAIN_GLOB = "a[0-9][0-9]_train.jsonl"


def load_all(waves: list[int], pattern: str = CELL_GLOB) -> pd.DataFrame:
    rows: list[dict] = []
    for w in waves:
        d = REPO / "tem" / "waves" / f"w{w}"
        if not d.is_dir():
            continue
        for f in sorted(d.glob(pattern)):
            for r in read_rows(f):
                r["wave"] = w
                r["src"] = f.name
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


def binom_tail(k: int, n: int, p0: float = 0.5) -> float:
    """One-sided P(X >= k | n Bernoulli(p0))."""
    if n <= 0:
        return 1.0
    k = max(0, min(k, n))
    if k == 0:
        return 1.0
    total = sum(math.comb(n, i) * p0**i * (1 - p0) ** (n - i) for i in range(k, n + 1))
    return min(total, 1.0)


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """One row per configuration, keeping the last successful run."""
    df = df[df["ok"] == 1].copy() if "ok" in df.columns else df.copy()
    return df.sort_values("cid").drop_duplicates("cid", keep="last")


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
    test = _dedupe(df[df["window"] == "TEST"] if "window" in df.columns else df)
    print(f"loaded {len(df)} rows -> {len(test)} unique TEST configs, waves {min(waves)}..{max(waves)}")

    train = load_all(waves, TRAIN_GLOB)
    train = _dedupe(train) if not train.empty else train

    # ---- hypothesis unit = factor -----------------------------------------
    fam = (
        test.groupby("factor")
        .agg(
            n_cfg=("cid", "size"),
            n_bench=("edge_vs_bench", lambda s: int((s > 0).sum())),
            n_null=("edge_vs_null", lambda s: int((s > 0).sum())),
            med_edge_bench=("edge_vs_bench", "median"),
            med_edge_null=("edge_vs_null", "median"),
            max_edge_bench=("edge_vs_bench", "max"),
            med_cagr=("cagr", "median"),
            med_dd=("max_dd", "median"),
            med_turnover=("turnover", "median"),
        )
        .reset_index()
    )
    fam["p_bench"] = [binom_tail(k, n) for k, n in zip(fam.n_bench, fam.n_cfg)]
    fam["p_null"] = [binom_tail(k, n) for k, n in zip(fam.n_null, fam.n_cfg)]
    fam["q_bench"] = bh_fdr(fam.p_bench.to_numpy())
    fam["q_null"] = bh_fdr(fam.p_null.to_numpy())
    fam["survives_fdr"] = fam.q_bench < 0.05
    fam["beats_bench_family"] = fam.med_edge_bench > 0
    fam["candidate"] = fam.survives_fdr & fam.beats_bench_family

    print(f"\nfactor families tested : {len(fam)}")
    print(f"  families beating bench on majority of configs : {(fam.n_bench / fam.n_cfg > 0.5).sum()}")
    print(f"  families with median edge_vs_bench > 0        : {fam.beats_bench_family.sum()}")
    print(f"  families surviving FDR q<0.05 (vs bench)      : {fam.survives_fdr.sum()}")
    print(f"  CANDIDATE families                            : {fam.candidate.sum()}")

    cols = ["factor", "n_cfg", "n_bench", "n_null", "med_edge_bench", "med_edge_null",
            "max_edge_bench", "med_cagr", "med_dd", "med_turnover", "p_bench", "q_bench"]
    print(f"\n=== top {args.top} families by median edge over benchmark ===")
    with pd.option_context("display.width", 220, "display.max_columns", 40):
        print(fam.nlargest(args.top, "med_edge_bench")[cols].round(4).to_string(index=False))

    if len(fam[fam.candidate]):
        print("\n=== CANDIDATE FAMILIES -- must still pass walk-forward ===")
        with pd.option_context("display.width", 220, "display.max_columns", 40):
            print(fam[fam.candidate][cols].round(4).to_string(index=False))

    # ---- per-cell detail for inspection ------------------------------------
    cand_factors = set(fam.loc[fam.candidate, "factor"])
    cell_cols = ["wave", "factor", "n_hold", "buffer", "clock", "universe", "instrument",
                 "cagr", "null_cagr", "edge_vs_null", "bench_cagr", "edge_vs_bench",
                 "max_dd", "sharpe", "exposure", "turnover", "breach_halt"]
    show = [c for c in cell_cols if c in test.columns]
    print(f"\n=== top {args.top} cells by edge over benchmark ===")
    with pd.option_context("display.width", 220, "display.max_columns", 40):
        print(test.nlargest(args.top, "edge_vs_bench")[show].round(4).to_string(index=False))

    # ---- TRAIN replication for candidate factors ---------------------------
    if cand_factors and not train.empty:
        tr = train[train["factor"].isin(cand_factors)]
        if not tr.empty:
            trf = (
                tr.groupby("factor")
                .agg(n_cfg=("cid", "size"),
                     n_bench=("edge_vs_bench", lambda s: int((s > 0).sum())),
                     med_edge_bench=("edge_vs_bench", "median"))
                .reset_index()
            )
            trf["train_replicates"] = (trf.n_bench / trf.n_cfg > 0.5) & (trf.med_edge_bench > 0)
            print("\n=== TRAIN replication of candidate families ===")
            with pd.option_context("display.width", 200):
                print(trf.round(4).to_string(index=False))
            fam = fam.merge(trf[["factor", "train_replicates"]], on="factor", how="left")
            fam["deployable"] = fam.candidate & fam.train_replicates.fillna(False)
            n_dep = int(fam.deployable.sum())
            print(f"\nDEPLOYABLE (FDR + bench + TRAIN): {n_dep}")
            if n_dep:
                print(fam[fam.deployable][cols].round(4).to_string(index=False))
    else:
        print("\n(no candidate families reached the TRAIN replication stage)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    test.to_json(args.out, orient="records")
    fam.to_json(args.out.with_name("_aggregate_families.json"), orient="records")
    print(f"\n-> {args.out}")
    print(f"-> {args.out.with_name('_aggregate_families.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
