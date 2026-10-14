"""CLI entry point for the per-stock optimisation sweep.

    python -m research.optimize.run --smoke
    python -m research.optimize.run --budget 40 --workers 8 --resume

``--smoke`` runs a deliberately tiny subset (2 strategies x 2 stocks x 4 configs) purely to
prove the pipeline executes end to end. It is a correctness check, not a result.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import config as C
from . import splitter as S
from .catalog import discover
from .engine import run_sweep, set_thread_env


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m research.optimize.run",
        description="Per-stock parameter optimisation over the strategy catalog.",
    )
    p.add_argument("--strategies", nargs="*", default=[], help="subset of strategy names")
    p.add_argument("--stocks", nargs="*", default=[], help="subset of symbols")
    p.add_argument("--budget", type=int, default=C.DEFAULT_BUDGET,
                   help="configs evaluated per (strategy, stock) pair")
    p.add_argument("--null-replicas", type=int, default=C.DEFAULT_NULL_REPLICAS)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--rebalance", choices=["M", "W", "D"], default="M")
    p.add_argument("--seed", type=int, default=C.MASTER_SEED)
    p.add_argument("--timeframe", default="1d", help="1d only; GOAL.md bans intraday")
    p.add_argument("--no-tax", action="store_true",
                   help="disable capital gains tax (pre-tax view)")
    p.add_argument("--resume", action="store_true", default=True,
                   help="skip pairs already in out/test_results.jsonl (this is the default; "
                        "accepted explicitly so the documented command line is valid)")
    p.add_argument("--no-resume", action="store_true",
                   help="ignore existing results and start over (deletes the results file)")
    p.add_argument("--smoke", action="store_true",
                   help="tiny correctness run: 2 strategies x 2 stocks x 4 configs")
    p.add_argument("--dry-run", action="store_true",
                   help="list the work and exit without backtesting")
    p.add_argument("--list", action="store_true", help="print the strategy catalog and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("optimize")
    set_thread_env(1)

    if args.list:
        specs = discover(args.strategies or ())
        print(f"{len(specs)} strategies\n")
        for s in specs:
            p = ", ".join(f"{x.name}[{x.kind}]" for x in s.params)
            print(f"  {s.name:30} {s.strategy_cls.__name__:32} {p}")
        return 0

    specs = discover(tuple(args.strategies))
    stocks = args.stocks or S.available_symbols(args.timeframe)

    if args.smoke:
        specs = specs[:2]
        stocks = stocks[:2]
        args.budget = 4
        args.null_replicas = 32
        # A smoke run is a correctness check, so it must always execute its pairs. If it
        # resumed, a previous smoke run's results would make it report "[0/0] done" and
        # appear to pass while testing nothing.
        args.no_resume = True
        log.warning("SMOKE MODE: 2 strategies x 2 stocks x 4 configs. Correctness only.")

    if not specs:
        log.error("no strategies loaded")
        return 2
    stocks = [s for s in stocks if not S.bars(s, S.FULL, args.timeframe).empty]
    if not stocks:
        log.error("no symbols with usable data")
        return 2

    cfg = C.RunConfig(
        budget=args.budget,
        null_replicas=args.null_replicas,
        workers=args.workers,
        rebalance=args.rebalance,
        tax_enabled=not args.no_tax,
        seed=args.seed,
        strategies=tuple(s.name for s in specs),
        stocks=tuple(stocks),
    )

    log.info("%d strategies x %d stocks = %d pairs | budget=%d | workers=%d | tax=%s",
             len(specs), len(stocks), len(specs) * len(stocks),
             cfg.budget, cfg.workers, "ON" if cfg.tax_enabled else "OFF")

    if args.dry_run:
        print(f"would run {len(specs) * len(stocks)} pairs")
        return 0

    manifest = run_sweep(specs, stocks, cfg,
                         resume=not args.no_resume,
                         workers=args.workers,
                         timeframe=args.timeframe)
    print("\nMANIFEST " + str(manifest.get("n_pairs_run")) + " run, "
          + str(manifest.get("n_failed")) + " failed")
    print("next: python -m research.optimize.analyze")
    return 0


if __name__ == "__main__":
    sys.exit(main())
