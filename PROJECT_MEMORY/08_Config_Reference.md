# 08. Config Reference

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High for Settings fields; High for mismatch with YAML.

## Source of truth

- `src/cryptobot/config.py` defines `Settings` (Pydantic v2 BaseSettings, `extra="ignore"`).
- `configs/base.yaml` is loaded via `Settings.from_yaml_safe` (flattens nested groups) or `Settings.from_yaml` (legacy direct `**` spread). `get_settings()` calls `from_yaml_safe` indirectly via `from_yaml` since both paths share the loader.

## Historical note

Prior to 2026-07-29, `configs/base.yaml` keys did not match `Settings` flat field names; `extra="ignore"` silently dropped unknowns. `Settings.from_yaml_safe` and `_flatten_yaml` translate the nested YAML structure into the flat Settings shape so YAML keys like `exchanges.binance.symbols` reach `settings.exchange.symbols`.

For reference, here is the original nested→flat mapping that `_flatten_yaml` implements:

| YAML key | Settings field |
|----------|----------------|
| `exchanges.binance.*` | `exchange.*` |
| `market_data.redis.*` | `market_data.redis_host`/`redis_port`/`redis_db`/`redis_max_connections` |
| `monitoring.prometheus.port` | `monitoring.prometheus_port` |
| `monitoring.grafana.port` | `monitoring.grafana_port` |
| `monitoring.alerts.telegram_*` | `monitoring.telegram_*` |
| `monitoring.alerts.discord_webhook` | `monitoring.discord_webhook` |
| `monitoring.alerts.email_enabled` | `monitoring.email_enabled` |
| `xmr.daemon.*` | `xmr.daemon_*` |
| `xmr.wallet_rpc.*` | `xmr.wallet_*` |
| `xmr.funding.*` | `xmr.funding_*`, `xmr.min_balance_xmr`, etc. |
| `version: "1.0"` | dropped |

## Settings groups (verified)

| Group | Env prefix | Notes |
|-------|------------|-------|
| `app` | `APP_` | name, env, log_level, timezone |
| `exchange` | `BINANCE_` | enabled, testnet, api_key, api_secret, base_url, ws_url, rate_limit, symbols, default_symbol, timeframes, max_positions, position_size_pct |
| `market_data` | `MARKET_DATA_` | buffer_size, orderbook_depth, update_interval_ms, cache_ttl_seconds, redis_host, redis_port, redis_db, redis_max_connections |
| `risk` | `RISK_` | max_total_exposure_pct, max_single_position_pct, max_daily_loss_pct, max_drawdown_pct, max_correlation, kill_switch_enabled, kill_switch_daily_loss_pct, position_sizing, kelly_fraction, volatility_target, min_order_size_usd, max_order_size_usd |
| `execution` | `EXECUTION_` | mode, order_type, limit_offset_bps, ioc_timeout_ms, max_slippage_bps, retry_attempts, retry_delay_ms, smart_routing |
| `ml` | `ML_` | enabled, inference_mode, model_path, features, min_samples_train, feature_lookback |
| `xmr` | `XMR_` | enabled, daemon_host/port/ssl/credentials, wallet_host/port/ssl/credentials, funding_enabled, min_balance_xmr, target_balance_xmr, withdraw_threshold_xmr, withdraw_address, confirmations, subaddress_lookahead |
| `monitoring` | `MONITORING_` | prometheus_enabled, prometheus_port, grafana_enabled, grafana_port, telegram_enabled, telegram_bot_token, telegram_chat_id, discord_webhook, email_enabled, health_check_interval |
| `database` | `DB_` | type, host, port, name, user, password, pool_size, max_overflow |
| `backtest` | `BACKTEST_` | enabled, start_date, end_date, initial_capital, commission_bps, slippage_bps, funding_rate_included |

## Blockers

- Fix `configs/base.yaml` to match Settings field names OR add a nested-upgrade step (`yaml.safe_load` then `Settings(**renamed_dict)`).
- Without this fix, `settings.exchange.symbols` is an empty list in production.

## Resolution (2026-07-29)

`Settings.from_yaml_safe` and `_flatten_yaml` in `src/cryptobot/config.py` translate the nested YAML structure (`exchanges.binance`, `monitoring.alerts.*`, etc.) into the flat Settings shape. `Settings.from_yaml` retains the legacy behavior; new code should use `from_yaml_safe`.

## Confidence

- High: every line of `config.py` and `bases/base.yaml` checked.
