"""Selection Study v2 — re-measure v1's findings on the fixed engine.

    Run:  .venv/bin/python research/selection_v2/run.py --phase sweeps --workers 4
          .venv/bin/python research/selection_v2/run.py --phase report

Why this exists
---------------
`reports/SELECTION_STUDY.md` was computed on engine `d93815344bd3`. The tie-break in
`build_rebalance_weights` has since changed from `np.argsort(-score, kind="stable")` —
which resolved tied scores by *column position*, and the panel's columns are
alphabetical — to a `blake2b("{date}|{symbol}")` key via `np.lexsort`. Every number
in v1 is therefore on a dead engine.

The single most decision-relevant figure in the repo lives in that report: removing
train-window parameter selection takes production from +9.71%/yr to +11.36%/yr and
its percentile against the signal-scrambled null from the 65th to the 90th. That is
the only thing in the repository that suggests a path from "no demonstrable edge" to
"real edge". It has to be re-measured before anyone acts on it.

Method
------
**The sweep, the schemes, the statistics and the nulls are v1's, imported, never
reimplemented** (`research/selection_study.py`). Re-running v1's exact machinery on
the new engine is the only way "does it still hold?" has an answer: any difference is
then attributable to the engine, not to a re-derivation. Only three things are new:

  * `CACHE_DIR` is redirected to `research/selection_v2/_cache`, so v1's cache is
    read-only input and the two studies cannot contaminate each other;
  * the v1 cache is re-analysed through the *same* `analyse()` as the v2 cache, so
    the §7 diff table is a measured diff between two engines rather than a
    transcription of one report and a re-run of the other;
  * a cross-process determinism probe gates everything (`research/selection_v2/
    determinism.py`), because v1 §2.5 reported a 15/18-cell cross-process spread
    and a spread that size would swamp a 0.31pp/yr effect.

`analyse()` is pure post-processing of a cached sweep, so it is deterministic and
cheap; running it twice on the same cache is a self-check, not a re-measurement.

TEST-window disclosure
----------------------
Unchanged from v1: every scheme and hyper-parameter was pre-registered from
TRAIN-window information or chosen a priori. Nothing here was re-tuned after seeing
the new engine's test windows, which is the whole point — v1's pre-registrations are
carried over verbatim so that "did it survive the engine change" is answerable.
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research"))
sys.path.insert(0, str(HERE))

# v1's machinery, unchanged. Redirect the cache BEFORE anything reads it.
import selection_study as ss  # noqa: E402

V2_CACHE = HERE / "_cache"
V1_CACHE = REPO / "research" / "_selection_study"
ss.CACHE_DIR = V2_CACHE

EXPECTED_PROVENANCE = {
    "engine": "29764f562cd5",
    "loader": "c1badf5f7df8",
    "costs": "ba350aef75b3",
    "panel": "389b082b832f",
}
V1_ENGINE = "d93815344bd3"


# --------------------------------------------------------------------------- #
# Provenance gate — refuse to run on an unexpected engine
# --------------------------------------------------------------------------- #


def check_provenance() -> dict:
    pv = ss.provenance()
    if pv != EXPECTED_PROVENANCE:
        raise SystemExit(
            "ABORT: working-tree provenance does not match the engine this study was\n"
            f"  commissioned for.\n    expected {EXPECTED_PROVENANCE}\n    actual   {pv}\n"
            "Re-read the task brief; every number below would be on an unnamed engine."
        )
    return pv


# --------------------------------------------------------------------------- #
# Sweeps
# --------------------------------------------------------------------------- #


def run_sweeps(n_scramble: int, n_random: int, workers: int, force: bool) -> dict:
    specs = (
        [ss.PROD, ss.CTRL]
        + ss.scramble_specs(n_scramble, 40_000)
        + ss.random_specs(n_random, 50_000)
    )
    print(f"    {len(specs)} specs -> {V2_CACHE}", flush=True)
    return ss.run_sweeps(specs, force=force)


def load_all(n_scramble: int, n_random: int) -> dict:
    labels = (
        ["PRODUCTION", "CONTROL_REVERSAL"]
        + [f"SCRAMBLE_C_{i:03d}" for i in range(n_scramble)]
        + [f"RANDOM_{i:03d}" for i in range(n_random)]
    )
    out, bad = {}, []
    for lab in labels:
        sw = ss.load_sweep(lab)
        if sw is None:
            bad.append(lab)
            continue
        if sw.get("provenance", {}).get("engine") != EXPECTED_PROVENANCE["engine"]:
            bad.append(f"{lab} (engine {sw.get('provenance', {}).get('engine')})")
            continue
        out[lab] = sw
    if bad:
        raise SystemExit(
            f"missing or wrong-engine sweeps in {V2_CACHE}: {bad[:5]}"
            f"{' ...' if len(bad) > 5 else ''} ({len(bad)} total)"
        )
    return out


def load_v1(n_scramble: int, n_random: int) -> dict:
    """v1's cache, read-only, verified to be on the old engine."""
    labels = (
        ["PRODUCTION", "CONTROL_REVERSAL"]
        + [f"SCRAMBLE_C_{i:03d}" for i in range(n_scramble)]
        + [f"RANDOM_{i:03d}" for i in range(n_random)]
    )
    out, bad = {}, []
    for lab in labels:
        p = V1_CACHE / f"sweep_{lab}.pkl"
        if not p.exists():
            bad.append(lab)
            continue
        sw = pickle.loads(p.read_bytes())
        if sw.get("provenance", {}).get("engine") != V1_ENGINE:
            bad.append(f"{lab} (engine {sw.get('provenance', {}).get('engine')})")
            continue
        out[lab] = sw
    if bad:
        raise SystemExit(f"v1 cache incomplete or wrong engine: {bad[:5]}")
    return out


# --------------------------------------------------------------------------- #
# Significance table — identical comparisons to v1 §4, recomputed on both engines
# --------------------------------------------------------------------------- #

SIGNIFICANCE_ROWS = (
    ("(b) walk-forward — production vs control", "b_train_sharpe", True),
    ("(a) no selection — production vs control", "a_fixed_modal", True),
    ("(c) reduced grid — production vs control", "c_reduced_grid", True),
    ("(a) − (b): does removing selection help?", "a_fixed_modal", False),
    ("(c) − (b): does shrinking the grid help?", "c_reduced_grid", False),
    ("(d) Calmar-selection − (b)", "d_train_calmar", False),
    ("(e) shrinkage − (b)", "e_shrink", False),
)


#: The a-priori fixed cell. v1 §6.1 recommended this cell *by name*, on the ground
#: that "it cannot be accused of being the cell that happened to win", so it is
#: pre-registered by v1 rather than chosen here. It uses no search output at all,
#: unlike scheme (a), whose "modal cell" is a function of the very selection layer
#: being evaluated.
A_PRIORI_CELL = "22|126|0.35"


def significance(R: dict) -> dict:
    S, FX, rp = R["schemes"], R["fixed"], R["repro"]
    rows = []
    for name, scheme, prod_vs_ctrl in SIGNIFICANCE_ROWS:
        if prod_vs_ctrl:
            a = S[scheme]["PRODUCTION"]["net"]
            b = S[scheme]["CONTROL_REVERSAL"]["net"]
        else:
            a = S[scheme]["PRODUCTION"]["net"]
            b = S["b_train_sharpe"]["PRODUCTION"]["net"]
        rows.append((name, ss._bs(a, b)))
    for tag in ("cell_A", "cell_B"):
        kk = rp["cells"][tag]["kk"]
        rows.append(
            (f"{tag} fixed — production vs control",
             ss._bs(FX["PRODUCTION"][kk]["net"], FX["CONTROL_REVERSAL"][kk]["net"]))
        )
    # The a-priori fixed cell, on both sides of the comparison that matters.
    kk = A_PRIORI_CELL
    rows.append((f"a-priori fixed cell `{kk}` — production vs control",
                 ss._bs(FX["PRODUCTION"][kk]["net"], FX["CONTROL_REVERSAL"][kk]["net"])))
    rows.append((f"(f) a-priori fixed cell `{kk}` − (b): does a search-free fix help?",
                 ss._bs(FX["PRODUCTION"][kk]["net"], S["b_train_sharpe"]["PRODUCTION"]["net"])))
    return {name: bs for name, bs in rows}


# --------------------------------------------------------------------------- #
# The diff table: every headline number, old engine vs new engine
# --------------------------------------------------------------------------- #

#: (label, getter) over the analysed dict. Getters return a float.
def _sch(R, s, f):
    return R["schemes"][s]["PRODUCTION"][f]


DIFF_SPECS = [
    # (report label, fn(R) -> float)
    ("§1.1 walk-forward PRODUCTION CAGR", lambda R: _sch(R, "b_train_sharpe", "metrics")["cagr"]),
    ("§1.1 walk-forward PRODUCTION Sharpe", lambda R: _sch(R, "b_train_sharpe", "metrics")["sharpe"]),
    ("§1.1 walk-forward PRODUCTION MaxDD", lambda R: _sch(R, "b_train_sharpe", "metrics")["maxdd"]),
    ("§1.1 walk-forward PRODUCTION gross CAGR", lambda R: _sch(R, "b_train_sharpe", "gross_cagr")),
    ("§1.1 walk-forward CONTROL CAGR", lambda R: R["schemes"]["b_train_sharpe"]["CONTROL_REVERSAL"]["metrics"]["cagr"]),
    ("§1.1 walk-forward CONTROL Sharpe", lambda R: R["schemes"]["b_train_sharpe"]["CONTROL_REVERSAL"]["metrics"]["sharpe"]),
    ("§1.1 walk-forward CONTROL MaxDD", lambda R: R["schemes"]["b_train_sharpe"]["CONTROL_REVERSAL"]["metrics"]["maxdd"]),
    ("§1.5 modal (best) fixed cell CAGR", lambda R: R["fixed_stats"]["prod_max"]),
    ("§1.5 median fixed cell CAGR", lambda R: R["fixed_stats"]["prod_median"]),
    *[(f"§1.5 fixed cell `{kk}` prod CAGR",
       (lambda kk_: (lambda R: R["fixed"]["PRODUCTION"][kk_]["cagr"]))(kk))
      for kk in ss.ALL_IDS],
    *[(f"§1.5 fixed cell `{kk}` control CAGR",
       (lambda kk_: (lambda R: R["fixed"]["CONTROL_REVERSAL"][kk_]["cagr"]))(kk))
      for kk in ss.ALL_IDS],
    ("§1.5 worst fixed cell CAGR", lambda R: R["fixed_stats"]["prod_min"]),
    ("§1.5 fixed cells prod beats ctrl", lambda R: R["fixed_stats"]["prod_cells_beating_ctrl"]),
    ("§1.5 fixed cells at >=75th pct of scramble null", lambda R: R["n_cells_75"]),
    ("§2.3 prod mean rho(TRAIN Sharpe -> TEST CAGR)", lambda R: R["rankcorr"]["PRODUCTION"]["rho_mean"]),
    ("§2.3 ctrl mean rho(TRAIN Sharpe -> TEST CAGR)", lambda R: R["rankcorr"]["CONTROL_REVERSAL"]["rho_mean"]),
    ("§2.3 prod mean rho(TRAIN Calmar -> TEST CAGR)", lambda R: R["rankcorr"]["PRODUCTION"]["rho_calmar_mean"]),
    ("§2.3 ctrl mean rho(TRAIN Calmar -> TEST CAGR)", lambda R: R["rankcorr"]["CONTROL_REVERSAL"]["rho_calmar_mean"]),
    ("§2.4 prod distinct cells selected", lambda R: float(len(R["modal_counts"]))),
    ("§2.4 modal cell of the TRAIN selection trace", lambda R: _modal_label(R)),
    ("§3.1 (a) fixed  prod CAGR", lambda R: _sch(R, "a_fixed_modal", "metrics")["cagr"]),
    ("§3.1 (a) fixed  prod Sharpe", lambda R: _sch(R, "a_fixed_modal", "metrics")["sharpe"]),
    ("§3.1 (a) fixed  prod MaxDD", lambda R: _sch(R, "a_fixed_modal", "metrics")["maxdd"]),
    ("§3.1 (a) fixed  prod gross CAGR", lambda R: _sch(R, "a_fixed_modal", "gross_cagr")),
    ("§3.1 (a) fixed  prod pct of scramble null", lambda R: R["scheme_table"]["a_fixed_modal"]["pct_scr_cagr"]),
    ("§3.1 (b) walkfwd prod CAGR", lambda R: _sch(R, "b_train_sharpe", "metrics")["cagr"]),
    ("§3.1 (b) walkfwd prod Sharpe", lambda R: _sch(R, "b_train_sharpe", "metrics")["sharpe"]),
    ("§3.1 (b) walkfwd prod MaxDD", lambda R: _sch(R, "b_train_sharpe", "metrics")["maxdd"]),
    ("§3.1 (b) walkfwd prod gross CAGR", lambda R: _sch(R, "b_train_sharpe", "gross_cagr")),
    ("§3.1 (b) walkfwd prod pct of scramble null", lambda R: R["scheme_table"]["b_train_sharpe"]["pct_scr_cagr"]),
    ("§3.1 (c) prod CAGR", lambda R: _sch(R, "c_reduced_grid", "metrics")["cagr"]),
    ("§3.1 (c) prod pct of scramble null", lambda R: R["scheme_table"]["c_reduced_grid"]["pct_scr_cagr"]),
    ("§3.1 (d) prod CAGR", lambda R: _sch(R, "d_train_calmar", "metrics")["cagr"]),
    ("§3.1 (d) prod pct of scramble null", lambda R: R["scheme_table"]["d_train_calmar"]["pct_scr_cagr"]),
    ("§3.1 (e) prod CAGR", lambda R: _sch(R, "e_shrink", "metrics")["cagr"]),
    ("§3.1 (e) prod pct of scramble null", lambda R: R["scheme_table"]["e_shrink"]["pct_scr_cagr"]),
    ("§3.1 (a) fixed  control CAGR", lambda R: R["schemes"]["a_fixed_modal"]["CONTROL_REVERSAL"]["metrics"]["cagr"]),
    ("§3.1 (b) walkfwd control CAGR", lambda R: R["schemes"]["b_train_sharpe"]["CONTROL_REVERSAL"]["metrics"]["cagr"]),
    ("§3.1 (a) selection delta, PRODUCTION", lambda R: R["repro"]["sel_delta"]["PRODUCTION"]),
    ("§3.1 (b) selection delta, CONTROL", lambda R: R["repro"]["sel_delta"]["CONTROL_REVERSAL"]),
    ("§3.1 (a)−(b) ΔCAGR", lambda R: R["ab_bs"]["obs_d_cagr"]),
    ("§3.1 TRAIN-argmax cell vs median cell, PRODUCTION", lambda R: _sel_vs_median(R, "PRODUCTION")),
    ("§3.1 TRAIN-argmax cell vs median cell, CONTROL", lambda R: _sel_vs_median(R, "CONTROL_REVERSAL")),
    ("§3.4 scramble null mean CAGR, scheme (b)", lambda R: R["scheme_table"]["b_train_sharpe"]["scr_mean"]),
    ("§3.4 scramble null mean CAGR, scheme (a)", lambda R: R["scheme_table"]["a_fixed_modal"]["scr_mean"]),
]


def _modal_label(R: dict) -> float:
    """A stable numeric fingerprint, so the diff table can *detect* a modal-cell change.

    The readable id and its counts are attached to the row by `diff_table`; this
    value only has to move when the cell moves.
    """
    counts = R["modal_counts"]
    cell = max(counts, key=lambda k: (counts[k], k))
    return float(sum(ord(ch) * (i + 1) for i, ch in enumerate(cell)))


def _modal_of(R: dict) -> tuple[str, str]:
    counts = R["modal_counts"]
    cell = max(counts, key=lambda k: (counts[k], k))
    return cell, ", ".join(f"{k}x{v}" for k, v in sorted(counts.items()))


def _sel_vs_median(R: dict, lab: str) -> float:
    rc = R["rankcorr"][lab]
    sel = float(np.mean(rc["per_fold_selected_cagr"]))
    med = float(np.mean(rc["per_fold_median_cagr"]))
    return sel - med


def driver_picks(val: dict, R: dict) -> dict:
    """Correct fold-order comparison between the sweep driver and `walk_forward`.

    v1's `validate_driver` zips `wf.folds` (fold 1 = most recent first) against
    `apply_scheme(...)["picks"]`, which `apply_scheme` emits in reverse (fold 6
    first, because it walks `reversed(sw["folds"])`). The two are in opposite
    orders, so that comparison reports 0/6 even when every fold agrees. This
    compares like with like, and `val["max_abs_diff"]` independently confirms
    it: if any fold picked a different cell the concatenated daily series could
    not be bit-identical.
    """
    wf = [f["cell"] for f in val["wf_folds"]]
    emitted = [p["cell"] for p in R["schemes"]["b_train_sharpe"]["PRODUCTION"]["picks"]]
    swept = list(reversed(emitted))  # back into fold order (1 = most recent)
    return {
        "walk_forward_order": wf,
        "driver_order": swept,
        "n_match": sum(a == b for a, b in zip(wf, swept, strict=True)),
        "n_folds": len(wf),
        "all_match": all(a == b for a, b in zip(wf, swept, strict=True)),
        "daily_series_identical": bool(val.get("same_len")) and val.get("max_abs_diff", 1.0) == 0.0,
        "max_abs_daily_diff": val.get("max_abs_diff"),
    }


def _kind(label: str) -> str:
    """Display kind inferred from the label. Cell ids contain `|`, so labels are
    escaped before they ever reach a markdown table."""
    if label.endswith("Sharpe") or "rho" in label or "rho(" in label:
        return "num"
    if (label.endswith("ΔCAGR") or "selection delta" in label
            or "d_cagr_ci" in label or "cell vs median cell" in label):
        return "diff"  # a CAGR *difference*: percentage points in every column
    if label.endswith("pct of scrambled null") or "pct of scramble" in label:
        return "pctile"
    if "prod beats ctrl" in label or "at >=75th" in label or "distinct cells" in label:
        return "int"
    return "pct"


def diff_table(R1: dict, R2: dict) -> list[dict]:
    rows = []
    for label, fn in DIFF_SPECS:
        try:
            a, b = float(fn(R1)), float(fn(R2))
        except (KeyError, TypeError, IndexError):
            continue
        row = {
            "label": label, "kind": _kind(label), "v1": a, "v2": b, "delta": b - a,
            "changed": abs(b - a) > 5e-4,
        }
        if "modal cell" in label:
            c1, n1 = _modal_of(R1)
            c2, n2 = _modal_of(R2)
            row.update(modal=True, v1_cell=c1, v2_cell=c2, v1_counts=n1, v2_counts=n2,
                       changed=c1 != c2)
        rows.append(row)
    for name, bs2 in R2["sig"].items():
        bs1 = R1["sig"].get(name)
        if bs1 is None:
            continue
        rows.append({
            "label": f"§4 ΔCAGR [{name}] observed",
            "kind": "diff",
            "v1": bs1["obs_d_cagr"], "v2": bs2["obs_d_cagr"],
            "delta": bs2["obs_d_cagr"] - bs1["obs_d_cagr"],
            "changed": abs(bs2["obs_d_cagr"] - bs1["obs_d_cagr"]) > 5e-4,
        })
        for bound in ("d_cagr_ci_lo", "d_cagr_ci_hi"):
            rows.append({
                "label": f"§4 CI [{name}] {bound}",
                "kind": "diff",
                "v1": bs1[bound], "v2": bs2[bound],
                "delta": bs2[bound] - bs1[bound],
                "changed": abs(bs2[bound] - bs1[bound]) > 5e-4,
            })
    return rows


# --------------------------------------------------------------------------- #
# Self-check: does the pipeline reproduce v1's *published* numbers?
# --------------------------------------------------------------------------- #

#: Published in reports/SELECTION_STUDY.md §1.1/§1.2/§1.5, quoted to 2dp.
V1_PUBLISHED = {
    "wf_prod_cagr": 0.0971, "wf_prod_sharpe": 0.34, "wf_prod_maxdd": -0.1492,
    "wf_ctrl_cagr": 0.1004, "wf_ctrl_sharpe": 0.37, "wf_ctrl_maxdd": -0.2505,
    "cellA_prod": 0.1101, "cellA_ctrl": 0.0800, "cellA_prod_sharpe": 0.45,
    "cellB_prod": 0.0928, "cellB_ctrl": 0.0525, "cellB_prod_sharpe": 0.30,
    "best_fixed": 0.1136, "best_fixed_cell": "22|126|0.6",
    "a_pct": 0.90, "b_pct": 0.65,
    "sel_delta_prod": -0.0130, "sel_delta_ctrl": 0.0203,
    "rho_prod": 0.134, "rho_ctrl": 0.753,
}


def self_check(R1: dict) -> dict:
    """Recompute v1 from v1's cache; compare against v1's printed report.

    If these fail, the pipeline is not v1's pipeline and the §7 diff table is
    meaningless. If they pass, the diff table isolates the engine change.
    """
    tol_c, tol_s = 5e-4, 5e-3
    S, FX = R1["schemes"], R1["fixed"]
    wb = S["b_train_sharpe"]
    got = {
        "wf_prod_cagr": wb["PRODUCTION"]["metrics"]["cagr"],
        "wf_prod_sharpe": wb["PRODUCTION"]["metrics"]["sharpe"],
        "wf_prod_maxdd": wb["PRODUCTION"]["metrics"]["maxdd"],
        "wf_ctrl_cagr": wb["CONTROL_REVERSAL"]["metrics"]["cagr"],
        "wf_ctrl_sharpe": wb["CONTROL_REVERSAL"]["metrics"]["sharpe"],
        "wf_ctrl_maxdd": wb["CONTROL_REVERSAL"]["metrics"]["maxdd"],
        "cellA_prod": FX["PRODUCTION"]["22|126|0.35"]["cagr"],
        "cellA_ctrl": FX["CONTROL_REVERSAL"]["22|126|0.35"]["cagr"],
        "cellA_prod_sharpe": FX["PRODUCTION"]["22|126|0.35"]["sharpe"],
        "cellB_prod": FX["PRODUCTION"]["15|126|0"]["cagr"],
        "cellB_ctrl": FX["CONTROL_REVERSAL"]["15|126|0"]["cagr"],
        "cellB_prod_sharpe": FX["PRODUCTION"]["15|126|0"]["sharpe"],
        "best_fixed": R1["fixed_stats"]["prod_max"],
        "a_pct": R1["scheme_table"]["a_fixed_modal"]["pct_scr_cagr"],
        "b_pct": R1["scheme_table"]["b_train_sharpe"]["pct_scr_cagr"],
        "sel_delta_prod": R1["repro"]["sel_delta"]["PRODUCTION"],
        "sel_delta_ctrl": R1["repro"]["sel_delta"]["CONTROL_REVERSAL"],
        "rho_prod": R1["rankcorr"]["PRODUCTION"]["rho_mean"],
        "rho_ctrl": R1["rankcorr"]["CONTROL_REVERSAL"]["rho_mean"],
    }
    out = {}
    for k, exp in V1_PUBLISHED.items():
        if k == "best_fixed_cell":
            continue
        v = got[k]
        if "sharpe" in k or "rho" in k:
            t = tol_s
        elif k.endswith("_pct"):
            # A percentile over n books can only land on a multiple of 1/n.
            t = 1.0 / 48 + 1e-9
        else:
            t = tol_c
        out[k] = {"published": exp, "recomputed": float(v), "pass": abs(v - exp) <= t}
    best_cell = max(FX["PRODUCTION"], key=lambda kk: FX["PRODUCTION"][kk]["cagr"])
    out["best_fixed_cell"] = {
        "published": V1_PUBLISHED["best_fixed_cell"], "recomputed": best_cell,
        "pass": best_cell == V1_PUBLISHED["best_fixed_cell"],
    }
    # Counted before the counters are added, so `_n` is the number of checks.
    n_pass = sum(1 for v in out.values() if isinstance(v, dict) and v.get("pass"))
    out["_n"] = len(out)
    out["_n_pass"] = n_pass
    return out


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description="Selection study v2")
    ap.add_argument("--phase", default="all", help="all|sweeps|report")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--n-scramble", type=int, default=48)
    ap.add_argument("--n-random", type=int, default=24)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    print("=" * 96)
    print("SELECTION STUDY v2 — re-measure v1 on the fixed tie-break engine")
    print("=" * 96)
    pv = check_provenance()
    print("provenance : " + "  ".join(f"{k}={v}" for k, v in sorted(pv.items())))
    print(f"cost model : all-in round trip {ss.COST.all_in_round_trip_bps(100_000):.2f} bps")
    print(f"v1 engine  : {V1_ENGINE} (cache at {V1_CACHE}, read-only)")
    print(f"v2 cache   : {V2_CACHE}")

    ss._init_worker()
    print(f"panel      : {ss.PANEL.shape[1]} symbols x {len(ss.PANEL)} days  "
          f"{ss.PANEL.index[0].date()} -> {ss.PANEL.index[-1].date()}")

    ss.WORKERS = max(1, args.workers)
    ss.hr("SWEEPS")
    run_sweeps(args.n_scramble, args.n_random, args.workers, args.force)
    if args.phase == "sweeps":
        return

    ss.hr("DRIVER VALIDATION — scheme (b) vs the untouched walk_forward")
    out = load_all(args.n_scramble, args.n_random)
    val = ss.validate_driver(out["PRODUCTION"])
    ss.dump(val, "v2_driver_validation.json")

    ss.hr("STABILITY CHECK — recompute fold 1 in this process and diff it")
    stab = ss.stability_check(out["PRODUCTION"])
    ss.dump(stab, "v2_stability_check.json")
    print(f"  {stab['n_differing']}/{stab['n_cells']} cells differ, "
          f"max |dSharpe| = {stab['max_abs_d_sharpe']:.3e}")

    ss.hr("ANALYSIS v2 (current engine)")
    t0 = time.time()
    R2 = ss.analyse(out, val)
    R2["sig"] = significance(R2)
    R2["driver"] = driver_picks(val, R2)
    R2["panel"] = [int(ss.PANEL.shape[1]), int(len(ss.PANEL)),
                   str(ss.PANEL.index[0].date()), str(ss.PANEL.index[-1].date())]
    print(f"  done in {time.time() - t0:.0f}s")

    ss.hr("ANALYSIS v1 (old engine, v1 cache, same pipeline) — self-check + diff base")
    v1out = load_v1(args.n_scramble, args.n_random)
    R1 = ss.analyse(v1out, val)
    R1["sig"] = significance(R1)
    R1["driver"] = driver_picks(val, R1)
    sc = self_check(R1)
    ss.dump(sc, "v1_self_check.json")
    n_bad = [k for k, v in sc.items()
             if isinstance(v, dict) and v.get("pass") is False]
    print(f"  pipeline reproduces v1's published report: "
          f"{sc['_n_pass']}/{sc['_n']} checks pass")
    if n_bad:
        print(f"  MISMATCH: {n_bad}")
    print(f"  driver == walk_forward, fold-for-fold: {R2['driver']['n_match']}/"
          f"{R2['driver']['n_folds']} | daily series identical: "
          f"{R2['driver']['daily_series_identical']}")
    print(f"  v1 verdict was: {R1['verdict_headline']}")
    print(f"  v2 verdict is : {R2['verdict_headline']}")

    rows = diff_table(R1, R2)
    ss.dump(rows, "v2_diff_table.json")
    print(f"  diff table: {sum(r['changed'] for r in rows)}/{len(rows)} entries changed")

    ss.hr("REPORT")
    import write_v2
    write_v2.write(R1, R2, val, stab, rows, sc, pv)
    print(f"\nwrote {HERE.parent.parent / 'reports' / 'SELECTION_STUDY_v2.md'}")


if __name__ == "__main__":
    main()
