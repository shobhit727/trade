from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptobot")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser("backtest", help="Run a backtest with synthetic OHLCV against a strategy")
    backtest.add_argument("--strategy", choices=["mean_reversion", "trend_following"], default="mean_reversion")
    backtest.add_argument("--bars", type=int, default=200)
    backtest.add_argument("--seed", type=int, default=42)
    backtest.add_argument("--vol", type=float, default=0.01)
    backtest.add_argument("--capital", type=Decimal, default=Decimal("10000"))
    backtest.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    sub.add_parser("validate", help="Validate latest backtest artifact placeholder")
    sub.add_parser("paper", help="Start paper trading dry-run placeholder")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "backtest":
        from cryptobot.backtest.runner import generate_synthetic_ohlcv, make_strategy, run_backtest

        bars = generate_synthetic_ohlcv(
            datetime(2024, 1, 1),
            n_bars=args.bars,
            seed=args.seed,
            vol=args.vol,
        )
        strategy = make_strategy(args.strategy)
        result = await run_backtest(bars, strategy=strategy, initial_capital=args.capital)
        if args.json:
            json.dump(result.to_dict(), sys.stdout, default=str)
            sys.stdout.write("\n")
        else:
            print(f"strategy={args.strategy} bars={len(bars)} trades={result.n_trades}")
            print(f"initial_capital={result.initial_capital} final_equity={result.final_equity}")
            print(f"total_return={result.total_return:.4%}")
        return 0
    if args.command == "validate":
        print("validate command OK: pass BacktestResults object from code path")
        return 0
    if args.command == "paper":
        print("paper command OK: execution engine dry-run available")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
