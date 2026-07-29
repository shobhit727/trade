# 18. Security

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: Medium.

## Verified

- `state.py` does not embed keys; reads from `cryptobot.config.settings`.
- `RiskManager` blocks orders that violate min/max notional, total exposure, or kill switch.
- `EventBus` does not log payload bodies (only delivery counts).
- `Dockerfile` runs as root by default; no `USER` directive.

## Open issues

- `BINANCE_API_KEY`/`SECRET` env vars empty in compose defaults.
- `monitoring/alerting.py` may serialize webhook URLs in env.
- `risk/manager.py` reads `kill_switch_daily_loss_pct` at construction; restart needed for changes.
- `strategies/base.py` `MeanReversionStrategy` example uses hardcoded `65000` trigger.
- `core/portfolio.py` `StrategyAllocation` defaults `max_weight=0.2` only; explicit register passes through.
- `monitoring/metrics.py` Prometheus `Counter` cannot decrement; misuse → runtime error.
- `BacktestEngine._handle_order_fill` does not subtract fees from equity.

## Recommendations

- Add `seccomp` and `read_only` profiles.
- Add redaction middleware for `core/bus.py` history persistence.
- Validate input range on `BacktestEngine.run(data_stream)`.
- Add permission checks for any future remote control endpoints.
- Run container as non-root user.

## Confidence

- Medium.
