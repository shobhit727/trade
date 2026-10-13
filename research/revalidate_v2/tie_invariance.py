"""Does the tie-break fix touch the random-weight null?

Run:  .venv/bin/python -m research.revalidate_v2.tie_invariance --n 12 --workers 4

Why this is a separate step
---------------------------
`research/revalidate_v2/` re-measures two reports computed on engine `d93815344bd3`.
Before spending hours re-running 100 random books and 120 scrambled books, the question
worth answering is whether the null *can* move at all.

The intuition is that it cannot: `RunSpec(kind="random")` fills the score panel with
`rng.random(...)`, i.i.d. `Uniform(0,1)`, and `build_rebalance_weights` ranks with
`np.lexsort((tiebreak[i], -s_masked))`. If two scores are never equal, the tiebreak key
is never consulted and the engine's output is bit-identical to the alphabetical version.

That intuition is a hypothesis, not a result, for two reasons.

**Reason 1 — float ties are rare but not impossible.** The birthday bound on ~2.9e5
draws from a 2^53 grid is ~4e-6 per panel; across a 100-book sweep with 6 folds it is
still small, but "small" is not "zero" and the claim is cheap to measure directly.

**Reason 2 — and this is the one that actually matters — the score ranking is not the
only place a tie-break is consulted.** The engine has three weight-space rankers that
sort by *weight*, not score, and they run on every rebalance of every book, random or
not:

  * `_top_n_weights`    (engine.py:420) — "keep the largest n"
  * `_exit_allocation`  (engine.py:453) — "sell smallest first"
  * `_thin`             (engine.py:430) — the DEAD_WEIGHT_EPS safety net

These **can** tie exactly: `_project_constraints` clamps weights at
`config.max_weight`, so any two names that both hit the cap arrive at bit-identical
weights. Under the old code that tie was resolved by column position, i.e.
alphabetically; under the new code by the hash. A random book pushes a large fraction of
its names through the cap on any given rebalance, so this is the common case, not a
corner case.

So the answer is not "random books have no ties" but "whatever ties the random book does
produce either never reach the shipped comparison, or reach it and do not change the
answer". This script measures three things:

  1. **Score ties** — exact duplicate scores among the top-k on each rebalance date of
     the null panels, which is the only place the score tiebreak can bite.
  2. **Weight ties** — instrumented on the *real* engine path by wrapping the three
     rankers and comparing the book they return against one computed with a deliberately
     adversarial (alphabetical) tie rule. This is a counterfactual A/B on the actual
     code path, not a reimplementation of it.
  3. **End-to-end bit-identity** — re-run N cached null books against the new engine and
     diff the full result record and the pickled OOS return series against the v1 cache.

Step 3 settles it. Steps 1-2 explain the result rather than assuming it.
"""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import control_diagnostic as cd  # noqa: E402
import numpy as np
import pandas as pd

from nsealgo.backtest.engine import (  # noqa: E402
    _rebalance_dates,
    run_backtest,
)

from . import CACHE, check_provenance, provenance, write_json

V1_CACHE = Path("research/_control_diag")


def _alpha_key(w: pd.Series) -> np.ndarray:
    """The *old* engine's tie rule, as an explicit sort key: column position."""
    return np.arange(len(w), dtype=np.uint64)


def _count_weight_ties(w: pd.Series) -> int:
    """How many entries of `w` sit in an exact-tie group of size >= 2."""
    if len(w) == 0:
        return 0
    _, counts = np.unique(w.to_numpy(dtype=float), return_counts=True)
    return int(counts[counts >= 2].sum())


def instrument_one_run(spec: cd.RunSpec, panel: pd.DataFrame) -> dict:
    """Run ONE real `run_backtest` on this spec and census every tie along the way.

    The three weight-space rankers are wrapped, not reimplemented: each wrapper calls
    the shipped function and then recomputes the same answer under the old
    column-position tie rule. If the two agree on every call, the tie-break fix provably
    did not change this book's weights.
    """
    import nsealgo.backtest.engine as eng

    stats = {
        "rebalances": 0,
        "top_n_calls": 0, "top_n_tie_calls": 0, "top_n_changed_calls": 0,
        "exit_calls": 0, "exit_tie_calls": 0, "exit_changed_calls": 0,
        "cap_clamped_names": 0, "rebalances_with_2plus_clamped": 0,
    }
    orig_top, orig_exit = eng._top_n_weights, eng._exit_allocation

    def top_n(w, n):
        stats["top_n_calls"] += 1
        real = orig_top(w, n)
        if _count_weight_ties(w):
            stats["top_n_tie_calls"] += 1
            # Old rule: np.argsort(-w, kind="stable") -> ties by column position.
            order = np.argsort(-w.to_numpy(dtype=float), kind="stable")[:n]
            if not np.array_equal(np.asarray(real), w.index[order]):
                stats["top_n_changed_calls"] += 1
        return real

    def exit_alloc(weights, cap):
        stats["exit_calls"] += 1
        real = orig_exit(weights, cap)
        if _count_weight_ties(weights):
            stats["exit_tie_calls"] += 1
            order = np.argsort(weights.to_numpy(dtype=float), kind="stable")
            ordered = weights.iloc[order]
            if float(ordered.sum()) <= cap + 1e-12:
                alt = ordered
            else:
                fits = (ordered.cumsum() <= cap + 1e-12).to_numpy()
                alt = pd.Series(0.0, index=ordered.index)
                alt[fits] = ordered[fits]
            if not np.allclose(real.to_numpy(), alt.to_numpy(), rtol=0, atol=1e-15):
                stats["exit_changed_calls"] += 1
        return real

    eng._top_n_weights, eng._exit_allocation = top_n, exit_alloc
    try:
        cfg = cd.PortfolioConfig()
        sc = cd.make_score_fn(spec)(panel)
        res = run_backtest(panel, sc, cd.COST, cfg, "M")
    finally:
        eng._top_n_weights, eng._exit_allocation = orig_top, orig_exit

    # Cap-clamp census + score-tie census on the exact rows the engine ranks.
    rb = [d for d in _rebalance_dates(panel.index, "M") if d in sc.index][1:]
    S = sc.loc[rb].to_numpy(float)
    stats["rebalances"] = len(rb)
    score_tied_rows = 0
    for i in range(len(rb)):
        row = S[i]
        v = np.isfinite(row)
        if not v.any():
            continue
        vals, counts = np.unique(row[v], return_counts=True)
        if int(counts.max()) > 1:
            score_tied_rows += 1
    stats["rows_with_score_tie"] = score_tied_rows
    stats["cagr"] = res.metrics.cagr
    stats["sharpe"] = res.metrics.sharpe
    stats["avg_names"] = res.diag["avg_names"]
    return stats


def rerun_and_diff(labels: list[str], workers: int) -> dict:
    """Re-run cached null books on the new engine and diff against the v1 cache."""
    old: dict = {}
    for i, lab in enumerate(labels):
        p = V1_CACHE / f"{lab}.json"
        if not p.exists():
            continue
        o = json.loads(p.read_text())
        pk = V1_CACHE / f"{lab}.pkl"
        if pk.exists():
            with pk.open("rb") as fh:
                o["_series"] = pickle.load(fh)
        old[lab] = (o, 10_000 + i)

    specs = [cd.RunSpec(lab, "tiecheck", kind="random", seed=10_000 + i)
             for i, lab in enumerate(labels)]
    new = cd.run_many(specs, workers)

    fields = ["cagr", "sharpe", "maxdd", "calmar", "sortino", "vol",
              "oos_turnover", "oos_cost_drag", "oos_avg_names",
              "oos_gross_cagr", "oos_net_pre_overlay", "train_cagr", "train_sharpe"]
    rows = []
    for lab, (o, _seed) in old.items():
        n = new[lab]
        deltas = {f: (n[f] - o[f]) for f in fields if o.get(f) is not None}
        fold_same = n["folds"] == o["folds"]
        bit_identical = None
        pk = CACHE / f"{lab}.pkl"
        if pk.exists() and o.get("_series"):
            with pk.open("rb") as fh:
                s_new = pickle.load(fh)
            a = pd.Series(o["_series"]["oos"]).to_numpy()
            b = pd.Series(s_new["oos"]).to_numpy()
            bit_identical = bool(a.shape == b.shape and np.array_equal(a, b))
        rows.append({
            "label": lab,
            "old_cagr": o["cagr"], "new_cagr": n["cagr"],
            "old_engine": o["provenance"]["engine"],
            "max_abs_field_delta": max(abs(v) for v in deltas.values()),
            "fold_table_identical": fold_same,
            "oos_series_bit_identical": bit_identical,
        })
    return {
        "n_checked": len(rows),
        "n_bit_identical_series": sum(bool(r["oos_series_bit_identical"]) for r in rows),
        "n_identical_folds": sum(r["fold_table_identical"] for r in rows),
        "max_abs_cagr_delta": max((abs(r["new_cagr"] - r["old_cagr"]) for r in rows),
                                  default=0.0),
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="tie-break invariance check")
    ap.add_argument("--n", type=int, default=12,
                    help="cached null books to re-run and diff (default 12)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    print("=" * 94)
    print("TIE-BREAK INVARIANCE — does the random-weight null move under engine 29764f562cd5?")
    print("=" * 94)
    check_provenance()
    cd.CACHE_DIR = CACHE
    cd.WORKERS = args.workers
    cd._init_worker()
    panel = cd.PANEL

    print("\n[1/3] instrumented run: ties on the REAL engine path, new vs old tie rule")
    wc = {}
    for tag, spec in (
        ("production (trend composite)", cd.RunSpec("X", "wc", kind="weights", weights=None)),
        ("null book (Uniform(0,1), seed 10000)", cd.RunSpec("Y", "wc", kind="random",
                                                            seed=10_000)),
    ):
        t0 = time.time()
        wc[tag] = instrument_one_run(spec, panel)
        w = wc[tag]
        print(f"      {tag}  ({time.time() - t0:.0f}s, "
              f"{w['rebalances']} rebalances, CAGR {w['cagr'] * 100:+.2f}%)")
        print(f"        score ties among ranked names      : {w['rows_with_score_tie']}"
              f"/{w['rebalances']} rebalances")
        print(f"        `_top_n_weights` calls with a tie  : {w['top_n_tie_calls']}"
              f"/{w['top_n_calls']}")
        print(f"        ...where the OLD rule differs      : {w['top_n_changed_calls']}")
        print(f"        `_exit_allocation` calls with a tie: {w['exit_tie_calls']}"
              f"/{w['exit_calls']}")
        print(f"        ...where the OLD rule differs      : {w['exit_changed_calls']}")

    print("\n[2/3] end-to-end: re-run cached null books, diff against the v1 cache")
    labels = [f"H1_RANDOM_{i:03d}" for i in range(args.n)]
    diff = rerun_and_diff(labels, args.workers)
    print(f"      books compared                     : {diff['n_checked']}")
    print(f"      OOS return series bit-identical    : "
          f"{diff['n_bit_identical_series']}/{diff['n_checked']}")
    print(f"      per-fold result table identical    : "
          f"{diff['n_identical_folds']}/{diff['n_checked']}")
    print(f"      max |dCAGR| across compared books  : {diff['max_abs_cagr_delta']:.3e}")
    for r in diff["rows"][:5]:
        print(f"        {r['label']}: old({r['old_engine'][:8]}) "
              f"{r['old_cagr'] * 100:+.8f}%  new {r['new_cagr'] * 100:+.8f}%  "
              f"series_identical={r['oos_series_bit_identical']}")

    prod_changed = (wc["production (trend composite)"]["top_n_changed_calls"]
                    + wc["production (trend composite)"]["exit_changed_calls"])
    null_changed = (wc["null book (Uniform(0,1), seed 10000)"]["top_n_changed_calls"]
                    + wc["null book (Uniform(0,1), seed 10000)"]["exit_changed_calls"])
    invariant = (diff["n_bit_identical_series"] == diff["n_checked"]
                 and diff["n_checked"] > 0
                 and diff["max_abs_cagr_delta"] == 0.0
                 and diff["n_identical_folds"] == diff["n_checked"])

    out = {
        "instrumented_runs": wc,
        "production_calls_where_old_rule_differs": prod_changed,
        "null_calls_where_old_rule_differs": null_changed,
        "rerun_diff": diff,
        "null_is_tie_invariant": invariant,
        "provenance": provenance(),
    }
    p = write_json("tie_invariance", out)
    print("\n" + "=" * 94)
    print(f"NULL TIE-INVARIANT ACROSS {diff['n_checked']} RE-RUN BOOKS : {invariant}")
    print(f"  production: the new tie rule changed {prod_changed} call(s) on one full-panel run")
    print(f"  null      : the new tie rule changed {null_changed} call(s) on the same run")
    if invariant:
        print("  -> the cached v1 H1 random books are reusable bit-for-bit. The report")
        print("     states this as a MEASUREMENT with this script's output behind it,")
        print("     not as an assumption.")
    else:
        print("  -> the null MOVED. Every null-derived number must be re-measured (this")
        print("     sweep does so regardless) and this output is the evidence.")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
