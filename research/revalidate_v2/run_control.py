"""Re-run the control diagnostic on engine `29764f562cd5`.

Run:  .venv/bin/python -m research.revalidate_v2.run_control --workers 5

Every phase of `research/control_diagnostic.py` is re-run through its own code, with two
changes and only two:

1. **The result cache is redirected** to `research/revalidate_v2/_cache/`, so the v1
   cache under `research/_control_diag/` (stamped `d93815344bd3`) is neither trusted nor
   overwritten.
2. **A provenance gate runs first.** If the working tree is not `29764f562cd5 /
   c1badf5f7df8 / ba350aef75b3 / 389b082b832f` the script stops before doing any work.

Nothing else differs: same 6 folds, same 18-cell grid, same `CostModel`, same top-N cut,
same caps, same turnover budget, same monthly rebalance, same `walk_forward`. The only
thing that changed between v1 and v2 is the engine's tie-break rule, which is the entire
subject of these reports.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

import control_diagnostic as cd  # noqa: E402

from . import CACHE, check_provenance


def main() -> None:
    ap = argparse.ArgumentParser(description="re-run the control diagnostic on the new engine")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--n-random", type=int, default=100)
    ap.add_argument("--n-scramble", type=int, default=60)
    ap.add_argument("--skip-tiecheck", action="store_true",
                    help="assume the tie-invariance phase is already done")
    ap.add_argument("--tiecheck-n", type=int, default=12,
                    help="cached null books to re-run for the bit-identity check")
    args = ap.parse_args()

    print("=" * 96)
    print("CONTROL DIAGNOSTIC v2 — full re-run on the tie-break-fixed engine")
    print("=" * 96)
    check_provenance()
    cd.CACHE_DIR = CACHE
    cd.WORKERS = max(1, args.workers)
    cd._init_worker()
    print(f"cost model         : {cd.COST.all_in_round_trip_bps(100_000):.2f} bps all-in "
          f"round trip (statutory + 2 x {cd.BASE_SLIPPAGE} bps slippage)")
    print(f"harness            : walk_forward n_folds={cd.N_FOLDS} {cd.TRAIN_YEARS}y train / "
          f"{cd.TEST_YEARS}y test, {len(cd.PARAM_GRID)}-cell grid")
    print(f"cache              : {CACHE}")
    print(f"panel              : {cd.PANEL.shape[1]} symbols x {len(cd.PANEL)} days  "
          f"{cd.PANEL.index[0].date()} -> {cd.PANEL.index[-1].date()}")

    if not args.skip_tiecheck:
        print("\n" + "=" * 96)
        print("PHASE 0 — tie-invariance of the null (required before quoting any null number)")
        print("=" * 96)
        subprocess.run(
            [sys.executable, "-m", "research.revalidate_v2.tie_invariance",
             "--n", str(args.tiecheck_n), "--workers", str(args.workers)],
            check=True,
        )

    def hr(t: str) -> None:
        print("\n" + "=" * 96)
        print(t)
        print("=" * 96)

    t0 = time.time()
    hr("PHASE 1 — reference: production + reversal control (gross and net)")
    cd.phase_reference()

    hr(f"PHASE 2 — H1: random-weight null, n={args.n_random}")
    cd.phase_h1(args.n_random)

    hr("PHASE 3 — H2: component singles + control without low_volatility")
    cd.phase_h2()

    hr("PHASE 4 — H3: regime overlay on vs off")
    cd.phase_h3()

    hr("PHASE 5 — H4: paired t-test + block bootstrap")
    cd.phase_h4()

    hr("PHASE 6 — H5: fixed unselected parameters + train/test profile")
    cd.phase_h5()

    hr(f"PHASE 7 — H6: signal-scrambled nulls, n={args.n_scramble} each")
    cd.phase_h6(args.n_scramble)

    hr("PHASE 8 — extras: turnover, beta, correlation, target beta")
    cd.phase_extras()

    print("\n" + "=" * 96)
    print(f"ALL PHASES DONE in {(time.time() - t0) / 60:.1f} min. "
          f"Now run `python -m research.revalidate_v2.report_control`.")
    print("=" * 96)


if __name__ == "__main__":
    main()
