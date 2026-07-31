# 04. Data Flow

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: High for implemented paths; Low for live Binance.

## Verified paths

### Market data → strategy

```
Binance WS
  └─► market_data.manager.BinanceWSClient
        └─► core.events.KlineEvent / TickerEvent / TradeEvent / FundingRateEvent
              └─► core.bus.EventBus.publish
                    └─► strategies.base.BaseStrategy.on_market_data(event)
                          └─► List[OrderEvent]
                        (or ml_strategy.MLStrategy.feed(symbol, price))
```

### Order → risk → venue

```
OrderEvent
  └─► execution.engine.ExecutionEngine.submit_order(order)
        ├─► risk.manager.RiskManager.check_order(order, price)
        │     └─► RiskCheckResult.to_event("pre_trade", order) → EventBus
        ├─► if rejected → emit ORDER_REJECTED with reason + check_type (B040)
        ├─► optional execution.router.SmartOrderRouter picks best venue
        └─► execution.venue.{binance,simulated}.Venue.submit_order(order)
              └─► filled OrderEvent → EventBus (EventType.ORDER_FILLED)
        Optional: execution.adverse_selection.AdverseSelectionGuard.attach_to_engine
                  cancels resting orders on mid-move / spread-widen / toxicity.
```

### Backtest loop

```
data_stream: AsyncIterator[Event]
  └─► backtest.engine.BacktestEngine.run(stream)
        ├─► SimulatedClock.step(event.timestamp)
        ├─► event.type.TICKER/KLINE → _handle_market_data (mark price, unrealized PnL)
        ├─► event.type.ORDER_FILLED → _handle_order_fill (open/close/flip position; B063 fixed double-count; B064 zero entry-price guarded)
        ├─► event.type.POSITION_UPDATE → _handle_position_update
        └─► event.type.PNL_UPDATE → _handle_pnl_update
  └─► BacktestResult (Sharpe, drawdown, win_rate, profit_factor, equity_curve)
```

End-to-end wiring in `backtest.runner.run_backtest`: OHLCV → strategy → ExecutionEngine → SimulatedVenue (with `FillSimulator` factory + slippage/commission).

## Verified event types

`EventType` enum in `core/events.py` covers 40+ values across market data, signals, orders, positions, P&L, risk, system. Includes `ORDER_REJECTED`, `ORDER_FILLED`, `KILL_SWITCH`, `RISK`, `HEARTBEAT`, `ERROR`, plus ALL `ml_*` types.

## Unverified / missing

- `cryptobot.ml.models.{volatility,regime,ensemble}`: not implemented (disabled in YAML).
- `cryptobot.execution.adverse_selection`: unit-tested via `test_adverse_selection.py`; not exercised end-to-end against real market data.
- Live Binance behavior under load: not exercised in CI; needs sandbox credentials.

## External data dependencies

- Binance public WS (testnet default `wss://testnet.binance.vision`).
- `ccxt.async_support` for BinanceVenue REST + WS in live/testnet mode.
- TimescaleDB (mounted via compose; migrations `001_extension.sql`, `002_hypertables.sql`).
- Redis (used by `market_data.manager` only).

## Confidence

- High: backtest, execution, event bus, risk, ML core paths.
- Medium: market data WS subscription (network-dependent).
- Low: live exchange behavior under real load.
