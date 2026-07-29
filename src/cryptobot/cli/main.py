from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptobot")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser("backtest", help="Run a backtest placeholder until strategy/data wiring is complete")
    backtest.add_argument("--start", default="2024-01-01T00:00:00")
    backtest.add_argument("--end", default="2024-01-02T00:00:00")
    backtest.add_argument("--capital", type=float, default=10000.0)

    sub.add_parser("validate", help="Validate latest backtest artifact placeholder")
    sub.add_parser("paper", help="Start paper trading dry-run placeholder")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "backtest":
        datetime.fromisoformat(args.start)
        datetime.fromisoformat(args.end)
        print("backtest command OK: data/strategy wiring pending")
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
