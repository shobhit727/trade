from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from decimal import Decimal


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptobot")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser(
        "backtest", help="Run a backtest from synthetic, CSV, Parquet, or TimescaleDB data"
    )
    backtest.add_argument("--strategy", choices=["mean_reversion", "trend_following", "stat_arb"], default="mean_reversion")
    backtest.add_argument("--source", choices=["synthetic", "csv", "parquet", "timescale"], default="synthetic")
    backtest.add_argument("--path", default=None)
    backtest.add_argument("--bars", type=int, default=200)
    backtest.add_argument("--seed", type=int, default=42)
    backtest.add_argument("--vol", type=float, default=0.01)
    backtest.add_argument("--capital", type=Decimal, default=Decimal("10000"))
    backtest.add_argument("--start", default="2024-01-01T00:00:00")
    backtest.add_argument("--end", default="2024-01-02T00:00:00")
    backtest.add_argument("--json", action="store_true")

    market_maker = sub.add_parser("mm", help="Run the market-making strategy against order book")
    market_maker.add_argument("--symbol", default="BTCUSDT")
    market_maker.add_argument("--bars", type=int, default=300)
    market_maker.add_argument("--source", choices=["synthetic"], default="synthetic")
    market_maker.add_argument("--vol", type=float, default=0.005)
    market_maker.add_argument("--gamma", type=float, default=0.5)
    market_maker.add_argument("--sigma", type=float, default=0.01)
    market_maker.add_argument("--kappa", type=float, default=1.5)
    market_maker.add_argument("--max-inventory", type=Decimal, default=Decimal("5"))
    market_maker.add_argument("--json", action="store_true")

    predict = sub.add_parser("ml", help="Train a direction classifier and emit predictions")
    predict.add_argument("--source", choices=["synthetic"], default="synthetic")
    predict.add_argument("--bars", type=int, default=400)
    predict.add_argument("--horizon", type=int, default=5)
    predict.add_argument("--json", action="store_true")

    serve = sub.add_parser("serve", help="Run the health/metrics HTTP server only")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    bot = sub.add_parser(
        "bot",
        help="Long-running bot stub: starts the health server and keeps the process alive",
    )
    bot.add_argument("--host", default="127.0.0.1")
    bot.add_argument("--port", type=int, default=8080)

    sub.add_parser("validate", help="Validate latest backtest artifact placeholder")
    sub.add_parser("paper", help="Start paper trading dry-run placeholder")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "backtest":
        from cryptobot.backtest.data import load_bars
        from cryptobot.backtest.runner import make_strategy, run_backtest

        ds = load_bars(
            source=args.source,
            path=args.path,
            symbol="BTCUSDT",
            timeframe="1h",
        )
        if args.source == "synthetic":
            ds.bars = ds.bars[: args.bars]
        strategy = make_strategy(args.strategy)
        result = await run_backtest(
            ds.bars,
            strategy=strategy,
            symbol=ds.symbol,
            initial_capital=args.capital,
        )
        if args.json:
            json.dump(
                {"source": ds.source, "n_bars": len(ds.bars), **result.to_dict()},
                sys.stdout,
                default=str,
            )
            sys.stdout.write("\n")
        else:
            logger.info(
                "strategy=%s source=%s symbol=%s bars=%d trades=%d",
                args.strategy,
                ds.source,
                ds.symbol,
                len(ds.bars),
                result.n_trades,
            )
            logger.info(
                "initial_capital=%s final_equity=%s total_return=%.4f%%",
                result.initial_capital,
                result.final_equity,
                result.total_return * 100,
            )
        return 0

    if args.command == "mm":
        from cryptobot.backtest.data import load_bars
        from cryptobot.execution.engine import ExecutionEngine
        from cryptobot.execution.venue.simulated import SimulatedVenue
        from cryptobot.risk.manager import RiskManager
        from cryptobot.strategies.market_making import MarketMakingStrategy, MarketMakingConfig

        ds = load_bars(source=args.source, symbol=args.symbol, timeframe="1h")
        ds.bars = ds.bars[: args.bars]
        venue = SimulatedVenue()
        engine = ExecutionEngine(venue=venue, risk_manager=RiskManager())
        cfg = MarketMakingConfig(
            symbol=args.symbol,
            gamma=args.gamma,
            sigma=args.sigma,
            kappa=args.kappa,
            max_inventory=args.max_inventory,
        )
        strategy = MarketMakingStrategy(cfg)
        strategy.attach_execution(engine)
        fills = strategy.run_on_history(ds.bars)
        if args.json:
            json.dump(
                {
                    "symbol": args.symbol,
                    "bars": len(ds.bars),
                    "fills": [
                        {
                            "timestamp": f.timestamp.isoformat(),
                            "side": f.side.value,
                            "quantity": str(f.filled_quantity),
                            "price": str(f.avg_fill_price),
                        }
                        for f in fills
                    ],
                },
                sys.stdout,
                default=str,
            )
            sys.stdout.write("\n")
        else:
            logger.info("mm fills=%d bars=%d symbol=%s", len(fills), len(ds.bars), args.symbol)
            for f in fills[:5]:
                logger.info("  %s %s %s @ %s", f.timestamp, f.side.value, f.filled_quantity, f.avg_fill_price)
        return 0

    if args.command == "ml":
        from cryptobot.ml.features import build_features
        from cryptobot.ml.models.direction import DirectionClassifier
        from cryptobot.backtest.data import load_bars

        ds = load_bars(source=args.source, symbol="BTCUSDT", timeframe="1h")
        bars = ds.bars[: args.bars]
        features = build_features(bars)
        clf = DirectionClassifier(horizon=args.horizon)
        score = clf.walk_forward_score(features, n_splits=4)
        out = {
            "n_samples": len(features),
            "n_features": features.shape[1] if hasattr(features, "shape") else len(features[0]),
            "walk_forward_score": score,
            "model": clf.summary(),
        }
        if args.json:
            json.dump(out, sys.stdout, default=str)
            sys.stdout.write("\n")
        else:
            for k, v in out.items():
                logger.info("%s: %s", k, v)
        return 0

    if args.command == "serve":
        from cryptobot.utils.health_server import serve_health

        await serve_health(host=args.host, port=args.port)
        return 0

    if args.command == "bot":
        from cryptobot.utils.health_server import HealthServer

        server = HealthServer(host=args.host, port=args.port)
        server.start()
        logger.info("bot stub running; health at http://%s:%d/health", args.host, args.port)
        try:
            while True:
                await asyncio.sleep(60)
        finally:
            server.stop()
        return 0

    if args.command == "validate":
        logger.info("validate command OK: pass BacktestResults object from code path")
        return 0
    if args.command == "paper":
        logger.info("paper command OK: execution engine dry-run available")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code in (None, 0):
            raise
        return int(exc.code) if isinstance(exc.code, int) else 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
