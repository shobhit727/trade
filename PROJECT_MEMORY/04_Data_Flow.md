# 04. Data Flow

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High for the parts of the flow that are implemented; Low for ML.

## Verified paths

### Market data → strategy

```
Binance WS
  └─► market_data.manager.BinanceWSClient
        └─► core.events.KlineEvent / TickerEvent / TradeEvent / FundingRateEvent
              └─► core.bus.EventBus.publish
                    └─► strategies.base.BaseStrategy.on_market_data(event)
                          └─► List[OrderEvent]
```

### Order → risk → venue

```
OrderEvent
  └─► execution.engine.ExecutionEngine.submit_order(order)
        ├─► risk.manager.RiskManager.check_order(order)
        │     └─► RiskCheckResult.to_event("pre_trade", order) → EventBus
        ├─► if rejected → OrderEvent.status = REJECTED, publish
        └─► if accepted → execution.venue.base.Venue.submit_order(order)
              └─► filled OrderEvent → EventBus (EventType.ORDER_FILLED)
```

### Backtest loop

```
data_stream: AsyncIterator[Event]
  └─► backtest.engine.BacktestEngine.run(stream)
        ├─► SimulatedClock.step(event.timestamp)
        ├─► event.type.TICKER/KLINE → _handle_market_data (mark price, unrealized PnL)
        ├─► event.type.ORDER_FILLED → _handle_order_fill (open/close/flip position)
        ├─► event.type.POSITION_UPDATE → _handle_position_update
        └─► event.type.PNL_UPDATE → _handle_pnl_update
  └─► BacktestResult (Sharpe, drawdown, win_rate, profit_factor, equity_curve)
```

## Verified event types

`EventType` enum in `core/events.py` covers 40+ values across market data, signals, orders, positions, P&L, risk, system.

## Unverified / missing

- `cryptobot.ml` pipeline: empty directory. No inference path.
- `cryptobot.execution.venue.binance`: not implemented. Live mode uses `SimulatedVenue` only.
- `data/features.py`: missing.
- `data/backtest/data.py`: missing. Backtest stream is constructed by the caller.
- `backtest/reporting.py`: missing.

## External data dependencies

- Binance public WS (testnet default).
- ccxt (declared in `requirements/prod.txt`, not used in current source).
- TimescaleDB (declared, not exercised).
- Redis (declared in `requirements/prod.txt`, used by `market_data.manager` only).

## Confidence

- High: backtest, execution, event bus paths.
- Medium: market data WS subscription (network-dependent).
- Low: ML pipeline, live exchange adapter.
