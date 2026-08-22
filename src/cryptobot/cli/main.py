from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType

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
    backtest.add_argument(
        "--timeframe",
        default="1h",
        help="Bar spacing for synthetic data (e.g. 1m, 5s, 1s, 100ms for sub-second HFT runs)",
    )
    backtest.add_argument("--seed", type=int, default=42)
    backtest.add_argument("--vol", type=float, default=0.01)
    backtest.add_argument("--capital", type=Decimal, default=Decimal("10000"))
    backtest.add_argument("--start", default="2024-01-01T00:00:00")
    backtest.add_argument("--end", default="2024-01-02T00:00:00")
    backtest.add_argument("--json", action="store_true")
    backtest.add_argument(
        "--show-trades",
        action="store_true",
        help="Print every closed trade from the backtest (entry/exit, prices, pnl)",
    )
    backtest.add_argument(
        "--algorithms",
        default=None,
        help="JSON file with a list of backtest jobs "
        '([{"strategy": "trend_following", "params": {"fast": 8}}, ...]) to run in parallel',
    )
    backtest.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Number of parallel worker processes for --algorithms (default: one per CPU core)",
    )

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
        help="Run the live/paper trading loop (market data -> strategy -> execution)",
    )
    bot.add_argument("--host", default="127.0.0.1")
    bot.add_argument("--port", type=int, default=8080)
    bot.add_argument("--strategy", default="trend_following")
    bot.add_argument("--symbol", default="BTCUSDT")
    bot.add_argument("--timeframe", default="1m")
    bot.add_argument("--mode", choices=["paper", "live"], default="paper")
    bot.add_argument("--warmup", type=int, default=300, help="REST bars used to prime indicators")
    bot.add_argument("--max-bars", type=int, default=None, help="stop after N closed bars (dry-run)")

    validate_cmd = sub.add_parser("validate", help="Validate backtest statistical significance")
    validate_cmd.add_argument("--source", choices=["synthetic"], default="synthetic")
    validate_cmd.add_argument("--bars", type=int, default=200)
    validate_cmd.add_argument("--splits", type=int, default=5)
    validate_cmd.add_argument("--permutations", type=int, default=200)
    validate_cmd.add_argument("--json", action="store_true")

    tax_cmd = sub.add_parser(
        "tax",
        help="India VDA tax summary + Schedule VDA CSV export (from bot state)",
    )
    tax_cmd.add_argument("--state", default="state/tax_engine.json")
    tax_cmd.add_argument("--export-csv", default=None, help="Write Schedule-VDA CSV to this path")

    paper_cmd = sub.add_parser("paper", help="Run paper trading dry-run")
    paper_cmd.add_argument("--symbol", default="BTCUSDT")
    paper_cmd.add_argument("--source", choices=["synthetic"], default="synthetic")
    paper_cmd.add_argument("--bars", type=int, default=200)
    paper_cmd.add_argument("--json", action="store_true")

    funder_cmd = sub.add_parser(
        "paper-funder",
        help="Live paper monitor for the funding-carry edge (public WS, no API keys)",
    )
    funder_cmd.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"],
                            help="comma- or space-separated symbols")
    funder_cmd.add_argument("--hours", type=float, default=24, help="0 = run forever")
    funder_cmd.add_argument("--log", default="paper_funding.csv")
    funder_cmd.add_argument("--spot-ws", default=None)
    funder_cmd.add_argument("--futures-ws", default=None)
    funder_cmd.add_argument("--poll-fapi", action="store_true", help="Use fapi REST polling for perp leg (futures WS is blocked on some networks)")
    funder_cmd.add_argument("--poll-interval", type=float, default=5.0)
    funder_cmd.add_argument("--sample-interval", type=float, default=60.0, help="Seconds between basis/funding CSV sample rows (default 60)")
    funder_cmd.add_argument("--json", action="store_true")

    carry = sub.add_parser(
        "carry",
        help="Two-leg funding-carry backtest (long spot, short perp) with real funding history",
    )
    carry.add_argument("--spot", required=True, help="Spot CSV (Binance klines: open_time,open,high,low,close,volume)")
    carry.add_argument("--perp", required=True, help="Perp CSV (same format; must be time-aligned to spot)")
    carry.add_argument("--funding", default=None, help="Binance fundingRate CSV (funding_time,funding_rate); omit for fixed rate")
    carry.add_argument("--fixed-rate", default=None, help="Fixed funding rate per 8h (e.g. 0.001) when no CSV")
    carry.add_argument("--symbol", default="BTCUSDT")
    carry.add_argument("--perp-symbol", default="BTCUSDTPERP")
    carry.add_argument("--entry", type=float, default=0.0003, help="Enter when funding rate >= this")
    carry.add_argument("--exit", type=float, default=0.00005, help="Exit when funding rate <= this")
    carry.add_argument("--qty", type=Decimal, default=Decimal("0"), help="Quantity per leg (default: USD 10k / spot price)")
    carry.add_argument("--capital", type=Decimal, default=Decimal("10000"))
    carry.add_argument(
        "--risk",
        type=float,
        default=0.0,
        help="Equity fraction per pair (0 = fixed qty); sizes legs at entry from current equity",
    )
    carry.add_argument("--max-notional", type=Decimal, default=Decimal("0"), help="Cap pair notional in USD (0 = uncapped)")
    carry.add_argument("--commission-bps", type=int, default=5)
    carry.add_argument("--json", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    if args.command == "backtest" and args.algorithms:
        import json as _json

        from cryptobot.backtest.parallel import run_parallel

        with open(args.algorithms, encoding="utf-8") as fh:
            jobs = _json.load(fh)
        if not isinstance(jobs, list):
            raise ValueError("--algorithms file must contain a JSON list of jobs")
        results = run_parallel(jobs, workers=args.workers or None)
        for r in results:
            _json.dump(r, sys.stdout, default=str)
            sys.stdout.write("\n")
        return 0

    if args.command == "backtest":
        from cryptobot.backtest.data import load_bars
        from cryptobot.backtest.runner import make_strategy, run_backtest

        ds = load_bars(
            source=args.source,
            path=args.path,
            symbol="BTCUSDT",
            timeframe=args.timeframe,
            n_bars=args.bars,
        )
        if args.source == "synthetic":
            ds.bars = ds.bars[: args.bars]
        strategy = make_strategy(args.strategy)
        result = await run_backtest(
            ds.bars,
            strategy=strategy,
            symbol=ds.symbol,
            initial_capital=args.capital,
            collect_trades=args.show_trades,
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
            if args.show_trades:
                for t in result.trades:
                    logger.info(
                        "%s %-5s %s @ %s -> %s  pnl=%s  pnl_pct=%s%%  fees=%s",
                        t["exit_time"],
                        t["side"],
                        t["quantity"],
                        t["entry_price"],
                        t["exit_price"],
                        t["pnl"],
                        t["pnl_pct"],
                        t["fees"],
                    )
        return 0

    if args.command == "mm":
        from cryptobot.backtest.data import load_bars
        from cryptobot.execution.engine import ExecutionEngine
        from cryptobot.execution.venue.simulated import SimulatedVenue
        from cryptobot.risk.manager import RiskManager
        from cryptobot.strategies.market_making import MarketMakingConfig, MarketMakingStrategy

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
        from cryptobot.backtest.data import load_bars
        from cryptobot.ml.features import build_features
        from cryptobot.ml.models.direction import DirectionClassifier

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

    if args.command == "tax":
        import json as _json
        from pathlib import Path as _Path

        from cryptobot.core.tax import TaxEngine

        state_file = _Path(args.state)
        if not state_file.exists():
            print(f"no tax state at {args.state}; run the bot first")
            return 1
        engine = TaxEngine()
        engine.restore(_json.loads(state_file.read_text(encoding="utf-8")))
        if args.export_csv:
            out = engine.export_schedule_vda(args.export_csv)
            print(f"Schedule VDA CSV written: {out}")
        summary = engine.summary()
        print("India VDA tax estimate (Section 115BBH, strict no-loss-offset):")
        for key, value in summary.items():
            print(f"  {key:>20}: {value}")
        return 0

    if args.command == "serve":
        from cryptobot.utils.health_server import serve_health

        await serve_health(host=args.host, port=args.port)
        return 0

    if args.command == "bot":
        from cryptobot.live.trader import LiveTrader, LiveTraderConfig

        if args.mode == "live":
            logger.warning(
                "LIVE mode: orders will be sent to the exchange with real funds. "
                "Ctrl+C to abort within 5s..."
            )
            await asyncio.sleep(5)

        trader = LiveTrader(LiveTraderConfig(
            strategy=args.strategy,
            symbol=args.symbol,
            timeframe=args.timeframe,
            mode=args.mode,
            host=args.host,
            port=args.port,
            warmup_bars=args.warmup,
            max_bars=args.max_bars,
        ))
        loop = asyncio.get_running_loop()
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, trader.request_stop)
            except NotImplementedError:  # pragma: no cover - windows
                pass
        logger.info("bot running: %s %s %s mode=%s health=http://%s:%d/health",
                    args.strategy, args.symbol, args.timeframe, args.mode, args.host, args.port)
        await trader.run()
        return 0

    if args.command == "validate":
        from cryptobot.backtest.data import load_bars
        from cryptobot.backtest.validation import run_validation

        ds = load_bars(source=args.source, symbol="BTCUSDT", timeframe="1h")
        bars = ds.bars[: args.bars]
        returns = [
            float(bars[i + 1].close - bars[i].close) / float(bars[i].close)
            for i in range(len(bars) - 1)
        ]
        if not returns:
            logger.error("no bars to validate")
            return 1
        report = run_validation(returns, n_splits=args.splits, n_permutations=args.permutations)
        if args.json:
            json.dump(report, sys.stdout, default=str)
            sys.stdout.write("\n")
        else:
            logger.info("passed=%s", report["passed"])
            logger.info("walk_forward=%s", report["walk_forward"])
            logger.info("monte_carlo=%s", report["monte_carlo"])
            logger.info("deflated_sharpe=%s", report["deflated_sharpe"])
        return 0 if report["passed"] else 1

    if args.command == "paper-funder":
        from cryptobot.live.paper_harness import FundingPaperHarness

        symbols = [s for item in args.symbols for s in item.split(",") if s]
        harness = FundingPaperHarness(
            symbols=symbols, log_path=args.log, sample_interval_s=args.sample_interval,
        )
        logger.info(
            "paper-funder monitoring %s for %.0fh (log=%s, sample_every=%.0fs)",
            ", ".join(symbols), args.hours, args.log, args.sample_interval,
        )
        await harness.run(
            hours=args.hours,
            spot_ws=args.spot_ws,
            futures_ws=args.futures_ws,
            poll_fapi=args.poll_fapi,
            poll_interval_s=args.poll_interval,
        )
        if args.json:
            json.dump(
                {
                    s: st.to_live_row(
                        harness._spot_price.get(s),
                        harness._perp_price.get(s),
                        harness._funding_rate.get(s),
                    )
                    for s, st in harness.states.items()
                },
                sys.stdout,
                default=str,
            )
            sys.stdout.write("\n")
        return 0

    if args.command == "carry":
        from cryptobot.backtest.carry import align_spot_to_perp, run_carry
        from cryptobot.backtest.data import load_csv
        from cryptobot.backtest.funding import (
            CsvFundingProvider,
            FixedFundingProvider,
        )
        from cryptobot.strategies.funding_arb import FundingArbConfig, FundingArbStrategy

        spot = load_csv(args.spot, symbol=args.symbol)
        perp = load_csv(args.perp, symbol=args.perp_symbol)
        if len(spot.bars) != len(perp.bars):
            aligned = align_spot_to_perp(spot.bars, perp.bars)
            if not aligned:
                logger.error(
                    "spot (%d) and perp (%d) bars not time-aligned; no overlap on the 8h grid",
                    len(spot.bars),
                    len(perp.bars),
                )
                return 1
            aligned_ts = {b.timestamp for b in aligned}
            spot.bars = aligned
            perp.bars = [b for b in perp.bars if b.timestamp in aligned_ts]
            logger.info(
                "auto-aligned spot to perp 8h grid: %d bars (U+7h spot close == perp close instant)",
                len(aligned),
            )
        elif not perp.bars or not spot.bars:
            logger.error("empty bars")
            return 1
        provider = CsvFundingProvider(args.funding) if args.funding else FixedFundingProvider(
            Decimal(args.fixed_rate) if args.fixed_rate else Decimal("0.0001")
        )
        first_spot = Decimal(str(spot.bars[0].close))
        qty = args.qty if args.qty > 0 else (args.capital / first_spot).quantize(Decimal("0.000001"))
        strategy = FundingArbStrategy(
            FundingArbConfig(
                symbol=args.symbol,
                perp_symbol=args.perp_symbol,
                min_funding_rate=args.entry,
                max_funding_rate=0.0,  # no cap in backtest
                quantity=qty,
                risk_fraction=Decimal(str(args.risk)),
                max_notional=args.max_notional,
            )
        )
        engine = await run_carry(
            spot.bars,
            perp.bars,
            strategy,
            provider,
            symbol=args.symbol,
            perp_symbol=args.perp_symbol,
            initial_capital=float(args.capital),
            commission_bps=args.commission_bps,
        )
        result = {
            "symbol": args.symbol,
            "perp_symbol": args.perp_symbol,
            "initial_capital": str(args.capital),
            "final_equity": str(engine._portfolio.get_state().total_equity),
            "n_trades": len(engine.get_trades()),
            "n_bars": len(spot.bars),
            "funding_provider": "csv" if args.funding else "fixed",
        }
        if args.json:
            json.dump(result, sys.stdout, default=str)
            sys.stdout.write("\n")
        else:
            logger.info("carry %s: %s", args.symbol, result)
        return 0

    if args.command == "paper":
        from cryptobot.backtest.data import load_bars
        from cryptobot.execution.engine import ExecutionEngine
        from cryptobot.execution.venue.simulated import SimulatedVenue
        from cryptobot.risk.manager import RiskManager

        ds = load_bars(source=args.source, symbol=args.symbol, timeframe="1h")
        bars = ds.bars[: args.bars]
        venue = SimulatedVenue(
            prices={args.symbol: Decimal(str(bars[0].close))} if bars else {}
        )
        engine = ExecutionEngine(venue=venue, risk_manager=RiskManager())
        fills = 0
        for bar in bars:
            mark = Decimal(str(bar.close))
            if mark <= 0:
                continue
            order = OrderEvent(
                symbol=args.symbol,
                type=OrderType.MARKET,
                side=OrderSide.BUY,
                quantity=Decimal("1"),
                strategy="paper",
            )
            order.price = mark
            filled = await engine.submit_order(order)
            if filled.status == OrderStatus.FILLED:
                fills += 1
        if args.json:
            json.dump(
                {"symbol": args.symbol, "bars": len(bars), "fills": fills},
                sys.stdout,
                default=str,
            )
            sys.stdout.write("\n")
        else:
            logger.info("paper fills=%d bars=%d symbol=%s", fills, len(bars), args.symbol)
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    from cryptobot.utils.logging import configure_logging_from_settings, setup_logging

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code in (None, 0):
            raise
        return int(exc.code) if isinstance(exc.code, int) else 2
    if getattr(args, "json", False):
        # Route logs to stderr so machine-readable JSON stays clean on stdout.
        from cryptobot.config import settings

        setup_logging(
            level=settings.app.log_level,
            json_output=settings.app.env != "development",
            include_caller=settings.app.env == "development",
            stream=sys.stderr,
        )
    else:
        configure_logging_from_settings()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
