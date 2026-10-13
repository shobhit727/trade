"""Re-run Gate 4 (`GOAL.md` §5) on engine `29764f562cd5` and emit `reports/STRESS_v4.md`.

Run:  .venv/bin/python -m research.revalidate_v2.run_stress --workers 5

`research/stress_tests.py` owns the harness and is imported read-only for its run
functions, its `Variant` construction, its per-stock attribution and its yearly-share
mathematics — none of that is reimplemented here. What this module owns is:

  * the provenance gate and the redirected cache,
  * the re-run itself,
  * the **diff table against `reports/STRESS_v3.md`**, which v3 does not have and which
    is the only way a reader can tell which of its numbers the tie-break moved, and
  * `reports/STRESS_v4.md`, written by `report_stress.py` from the harvested JSON.

`stress_tests.main()` is deliberately NOT called: it writes `reports/STRESS_v3.md`, which
this task may not touch.
"""

from __future__ import annotations

import argparse
import pickle
import time

import stress_tests as st  # noqa: E402

from . import CACHE, check_provenance


def main() -> None:
    ap = argparse.ArgumentParser(description="re-run Gate 4 stress tests on the new engine")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--force", action="store_true",
                    help="ignore the per-variant cache")
    args = ap.parse_args()

    print("=" * 100)
    print("GATE 4 STRESS v4 — full re-run on the tie-break-fixed engine")
    print("=" * 100)
    check_provenance()
    st._init_worker()
    panel = st.PANEL
    max_diff = st.assert_matches_stock_composite(panel)
    print(f"composite check     : parameterised builder bit-identical to "
          f"build_composite_score (max abs diff {max_diff:.1e})")
    print(f"panel               : {panel.shape[1]} symbols x {len(panel)} days  "
          f"{panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"harness             : walk_forward n_folds={st.N_FOLDS} {st.TRAIN_YEARS}y train / "
          f"{st.TEST_YEARS}y test, {len(st.PARAM_GRID)}-cell grid")
    print(f"cache               : {CACHE}")

    t0 = time.time()
    variants, perturb_labels = st.build_variants()
    print(f"variants            : {len(variants)} walk-forward runs on {args.workers} workers")

    # Per-variant incremental cache. `stress_tests.run_all` is fault-tolerant *within*
    # one process, but this box is shared and the whole sweep was OOM-killed twice
    # before this was added — losing every completed walk-forward each time. Each
    # variant is therefore written to disk as it lands, and a re-run resumes.
    def _pkl(label: str):
        return CACHE / f"STRESS_{label.replace(' ', '_').replace('/', '-')}.pkl"

    # Per-variant incremental cache, run ONE AT A TIME in this process.
    #
    # `stress_tests.run_all` uses a process pool and is fault-tolerant *within* one
    # process, but this box is shared and the parent was OOM-killed three times while
    # other sweeps ran, taking the whole pool with it and losing every completed
    # walk-forward. Nineteen variants at ~1.2 min each is ~23 min single-threaded, which
    # is cheap enough to buy determinism: each variant is pickled the moment it lands,
    # so a kill costs at most one variant and a re-run resumes.
    results: list[dict] = []
    todo = []
    for v in variants:
        p = _pkl(v.label)
        if p.exists() and not args.force:
            with p.open("rb") as fh:
                results.append(pickle.load(fh))
            print(f"    cached: {v.label}", flush=True)
        else:
            todo.append(v)
    for v in todo:
        r = st.run_variant(v)
        with _pkl(v.label).open("wb") as fh:
            pickle.dump(r, fh)
        results.append(r)
        print(f"    done [{len(results)}/{len(variants)}] {v.label} "
              f"({r['cagr'] * 100:+.2f}% / {r['sharpe']:.2f}) "
              f"elapsed {(time.time() - t0) / 60:.1f}m", flush=True)
    by_label = {r["label"]: r for r in results}
    missing = [v.label for v in variants if v.label not in by_label]
    if missing:
        raise RuntimeError(f"missing variants: {missing}")
    results = [by_label[v.label] for v in variants]
    print(f"walk-forward sweep done in {(time.time() - t0) / 60:.1f} min")

    # ---- OOS return series have to survive the process boundary for H4/beta-style work
    CACHE.mkdir(parents=True, exist_ok=True)
    for r in results:
        with (CACHE / f"{r['label']}.pkl").open("wb") as fh:
            pickle.dump({"oos": r["oos"], "bench": r["bench"]}, fh)

    base = by_label["BASELINE"]

    print("\n" + "-" * 100)
    print("full-panel turnover / cost-drag sanity")
    insample = st.run_backtest(panel, st.parameterised_composite(panel, st.BASE_FACTOR_PARAMS),
                               st.CostModel(segment="delivery", slippage_bps=st.BASE_SLIPPAGE),
                               st.PortfolioConfig(), "M")
    print(f"  round trip bps : {insample.diag['round_trip_bps']}")
    print(f"  annual turnover: {insample.metrics.annual_turnover:.4f}x/yr")
    print(f"  cost drag      : {insample.metrics.cost_drag_annual * 100:.4f}%/yr")
    print(f"  avg names      : {insample.diag['avg_names']:.1f} over "
          f"{insample.diag['n_rebalances']} rebalances")

    print("\n" + "-" * 100)
    print("G4.3 yearly concentration")
    yr = st.yearly_pnl_shares(base["oos"])

    print("\n" + "-" * 100)
    print("G4.4 per-stock attribution")
    stock_df, cash_leg, recon = st.per_stock_attribution(base["folds"])

    print("\n" + "-" * 100)
    print("supplementary: 18 fixed grid cells, no train selection")
    fixed_rows = []
    for p in st.PARAM_GRID:
        m = st.compute_metrics(st.fixed_param_oos(p, st.BASE_FACTOR_PARAMS))
        fixed_rows.append({**p, "cagr": m.cagr, "sharpe": m.sharpe,
                           "maxdd": m.max_drawdown})
    with (CACHE / "STRESS_fixed_grid.pkl").open("wb") as fh:
        pickle.dump(fixed_rows, fh)

    print("\n" + "-" * 100)
    print("loader rule C9 (attribution only; unchanged by this run)")
    legacy = st.panel_without_frozen_bar_rule()
    c9 = {"present": legacy is not None}
    if legacy is not None:
        c9["baseline"] = st.walk_forward_on(legacy, "BASELINE (pre-C9)")
        li = st.in_sample_on(legacy)
        c9["insample"] = li
        print(f"  pre-C9 turnover {li.metrics.annual_turnover:.4f}x  "
              f"drag {li.metrics.cost_drag_annual * 100:.4f}%  "
              f"OOS {c9['baseline']['cagr'] * 100:+.2f}% / {c9['baseline']['sharpe']:.2f}")
        print(f"  C9      turnover {insample.metrics.annual_turnover:.4f}x  "
              f"drag {insample.metrics.cost_drag_annual * 100:.4f}%  "
              f"OOS {base['cagr'] * 100:+.2f}% / {base['sharpe']:.2f}")

    from . import write_json
    write_json("stress_raw", {
        "results": [{k: v for k, v in r.items() if k not in ("oos", "bench")}
                    for r in results],
        "base_folds": [{**f, "test_start": str(f["test_start"].date()),
                        "test_end": str(f["test_end"].date())} for f in base["folds"]],
        "insample": {
            "annual_turnover": insample.metrics.annual_turnover,
            "cost_drag_annual": insample.metrics.cost_drag_annual,
            "cagr": insample.metrics.cagr,
            "avg_names": insample.diag["avg_names"],
            "n_rebalances": insample.diag["n_rebalances"],
            "round_trip_bps": insample.diag["round_trip_bps"],
        },
        "yearly": yr.reset_index().rename(columns={"index": "year"}).to_dict("records"),
        "per_stock": stock_df.reset_index().rename(columns={"index": "symbol"}).to_dict("records"),
        "cash_leg": cash_leg,
        "recon_err": recon,
        "fixed_rows": fixed_rows,
        "c9": {
            "present": c9["present"],
            "baseline_cagr": c9.get("baseline", {}).get("cagr"),
            "baseline_sharpe": c9.get("baseline", {}).get("sharpe"),
            "insample_turnover": getattr(c9.get("insample"), "metrics", None)
                                 and c9["insample"].metrics.annual_turnover,
            "insample_drag": getattr(c9.get("insample"), "metrics", None)
                             and c9["insample"].metrics.cost_drag_annual,
            "insample_cagr": getattr(c9.get("insample"), "metrics", None)
                             and c9["insample"].metrics.cagr,
        },
        "panel": {"n_sym": int(panel.shape[1]), "n_days": int(len(panel)),
                  "start": str(panel.index[0].date()), "end": str(panel.index[-1].date())},
        "perturb_labels": perturb_labels,
    })
    print("\n" + "=" * 100)
    print("wrote _cache/stress_raw.json — now run "
          "`python -m research.revalidate_v2.report_stress`")


if __name__ == "__main__":
    main()
