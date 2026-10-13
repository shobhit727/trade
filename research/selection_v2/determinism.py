"""Cross-process determinism probe for the current engine.

Run this FIRST, before any sweep. It answers the question v1 left open:

  v1 (`research/selection_study.py`, §2.5) found that a fresh in-process
  recomputation of fold 1 differed from the worker-pool sweep in **15/18 cells**,
  by up to **0.013 Sharpe**, while an in-process repeat was bit-identical. It
  could not tell "nondeterministic engine" from "different realisation depending
  on the process".

  The tie-break has since changed from `np.argsort(kind="stable")` (a pure
  function of column position) to a `blake2b`-keyed `np.lexsort` (a pure
  function of the date and symbol strings). Neither is salted, so if the
  cross-process spread survives the fix it comes from somewhere else -- and any
  per-cell Sharpe spread of that size would be the same order as the 0.31pp/yr
  selection effect this study is trying to measure. That makes this the gate on
  everything downstream.

  Emits `probe.json`: for a set of folds x cells, the train/test Sharpe of every
  cell as computed in *this* process, plus the argmax. Run the script twice and
  diff `probe.json` against itself.

Usage:
    .venv/bin/python -m research.selection_v2.determinism          # writes probe.json
    .venv/bin/python -m research.selection_v2.determinism --check   # diffs probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research"))

OUT = Path(__file__).resolve().parent / "probe.json"

# Imported, never reimplemented: the sweep machinery is v1's, unchanged, so
# this probe measures the *engine*, not a difference in how we drive it.
import selection_study as ss  # noqa: E402


def compute(folds_to_probe: list[int]) -> dict:
    if ss.PANEL is None:
        ss._init_worker()
    score_fn = ss.make_score_fn(ss.PROD)
    slices = ss.fold_slices(ss.PANEL)
    out: dict[str, dict] = {}
    for k in folds_to_probe:
        train, test = slices[k - 1]
        sc_tr, sc_te = score_fn(train), score_fn(test)
        cells = {}
        for key, params in zip(ss.CELL_KEYS, ss.PARAM_GRID, strict=True):
            kk = ss.cell_id(key)
            mtr, *_ = ss.run_cell(train, params, sc_tr, want_gross=False)
            mte, net, *_ = ss.run_cell(test, params, sc_te, want_gross=True)
            # Shaped like a sweep cell so v1's argmax helpers apply unchanged.
            cells[kk] = {
                "train": {"sharpe": float(mtr.sharpe), "calmar": float(mtr.calmar)},
                "test": {
                    "cagr": float(mte.cagr), "sharpe": float(mte.sharpe),
                    "maxdd": float(mte.max_drawdown),
                },
            }
        out[f"fold{k}"] = {
            "train_window": [str(train.index[0].date()), str(train.index[-1].date())],
            "test_window": [str(test.index[0].date()), str(test.index[-1].date())],
            "argmax_train_sharpe": ss._argmax_first(cells, ss.ALL_IDS, "sharpe"),
            "argmax_train_calmar": ss._argmax_first(cells, ss.ALL_IDS, "calmar"),
            "cells": cells,
        }
    return out


def summarise(probe: dict) -> dict:
    """Second pass, same process, same inputs: must be bit-identical.

    This separates "the engine is nondeterministic" from "the engine is
    deterministic but its output depends on the process it runs in".
    """
    again = compute([1])
    d = []
    for kk, a in probe["folds"]["fold1"]["cells"].items():
        b = again["fold1"]["cells"][kk]
        d.append(max(abs(a["train"]["sharpe"] - b["train"]["sharpe"]),
                     abs(a["test"]["sharpe"] - b["test"]["sharpe"])))
    d = np.array(d)
    return {
        "in_process_repeat_max_abs_d_sharpe": float(d.max()),
        "in_process_repeat_n_differing": int((d > 0).sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="cross-process determinism probe")
    ap.add_argument("--check", action="store_true",
                    help="compare a fresh run against the stored probe.json")
    ap.add_argument("--folds", default="1,2,3")
    args = ap.parse_args()
    folds = [int(x) for x in args.folds.split(",") if x]

    probe = {
        "pid": os.getpid(),
        "python_hash_seed": os.environ.get("PYTHONHASHSEED", "<unset>"),
        "provenance": ss.provenance(),
        "panel": None,
        "folds": compute(folds),
    }
    if ss.PANEL is not None:
        probe["panel"] = [int(ss.PANEL.shape[1]), int(len(ss.PANEL)),
                          str(ss.PANEL.index[0].date()), str(ss.PANEL.index[-1].date())]
    probe["in_process_repeat"] = summarise(probe)

    if args.check:
        if not OUT.exists():
            raise SystemExit(f"no stored probe at {OUT}; run without --check first")
        old = json.loads(OUT.read_text())
        diffs, worst = 0, 0.0
        flips = []
        for fk in sorted(set(old["folds"]) & set(probe["folds"])):
            for kk, a in old["folds"][fk]["cells"].items():
                b = probe["folds"][fk]["cells"][kk]
                for side in ("train", "test"):
                    for m, av in a[side].items():
                        dd = abs(av - b[side][m])
                        worst = max(worst, dd)
                        if dd > 1e-12:
                            diffs += 1
            for m in ("argmax_train_sharpe", "argmax_train_calmar"):
                if old["folds"][fk][m] != probe["folds"][fk][m]:
                    flips.append((fk, m, old["folds"][fk][m], probe["folds"][fk][m]))
        print(f"stored pid={old['pid']}  fresh pid={probe['pid']}")
        print(f"engine   : {old['provenance']['engine']} / {probe['provenance']['engine']}")
        print(f"differing (cell, metric) pairs : {diffs}")
        print(f"max |delta|                    : {worst:.3e}")
        print(f"argmax flips                   : {flips if flips else 'none'}")
        print(f"in-process repeat              : "
              f"{probe['in_process_repeat']['in_process_repeat_n_differing']} differ, "
              f"max {probe['in_process_repeat']['in_process_repeat_max_abs_d_sharpe']:.1e}")
        sys.exit(1 if (diffs or flips) else 0)

    OUT.write_text(json.dumps(probe, indent=2))
    print(f"wrote {OUT}  (pid {probe['pid']}, PYTHONHASHSEED={probe['python_hash_seed']})")
    for fk in sorted(probe["folds"]):
        print(f"  {fk}: argmax_sharpe={probe['folds'][fk]['argmax_train_sharpe']} "
              f"argmax_calmar={probe['folds'][fk]['argmax_train_calmar']}")
    print(f"  in-process repeat: "
          f"{probe['in_process_repeat']['in_process_repeat_n_differing']} differ, "
          f"max {probe['in_process_repeat']['in_process_repeat_max_abs_d_sharpe']:.1e}")


if __name__ == "__main__":
    main()
