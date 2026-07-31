# 22. Improvement Ideas

> **Last Updated**: 2026-07-31 (audit v2)
> **Confidence**: Suggestions, not commitments.

## Done (resolve tracking by removing from this doc)

The following were listed previously and are now resolved or shipped:

- ✅ Align `configs/base.yaml` with `Settings` field names — mitigated via `_flatten_yaml` + `from_yaml_safe` (B050).
- ✅ Add `pyproject.toml` + `setuptools-scm` — done.
- ✅ Add `pytest.ini` with `asyncio_mode = auto` — done (`pytest.ini` + `pyproject.toml [tool.pytest.ini_options]`).
- ✅ Bounce retry jitter so `sleep_time ≥ 0` — done (B027).
- ✅ Replace `Counter` with `Gauge` for realized PnL — done (B025/B037).
- ✅ Replace `print(...)` in `core/clock.py`, `backtest/engine.py`, `strategies/base.py` with `get_logger` — done (B046/B049).
- ✅ Add `USER` directive in `Dockerfile` for non-root runtime — pending review; investigate.
- ✅ Replace `backtest/validation.py` stubs with rolling-window logic — done (real walk-forward + MC + deflated Sharpe).
- ✅ Add `cryptobot.execution.venue.binance` adapter using `ccxt.async_support` — done.
- ✅ Add `cryptobot.ml.features` with at least one technical indicator module — done (`build_features` + helpers).
- ✅ Add `cryptobot.ml.models.direction` v0 (sklearn logreg) — done.
- ✅ Wire `cryptobot.cli.main` `backtest` to `BacktestEngine` — done (subcommands have real logic).

## Quick wins (1-2 hours each, post-fix)

- Fix Rust workspace so `cargo build` doesn't error: trim `Cargo.toml [workspace] members` to just `["crates/cryptobot-core"]`, OR add minimal `Cargo.toml` to each empty member.
- Remove dead empty dirs `src/cryptobot/{allocator,altdata,api,exchanges,funding,xmr}/`.
- Add `USER` directive in `Dockerfile` for non-root runtime.
- Add blank-env defaults in `docker-compose.yml` to silence warnings.
- Remove duplicate `B026/B042/B043/B053` rows in `13_Bug_Tracker.md`.

## Medium (1-2 days)

- Implement `ml/models/volatility.py` (quantile / GARCH) + `ml/models/regime.py` (HMM) + `ml/models/ensemble.py` (stacking). Wire enabled/disabled flags in `configs/base.yaml`.
- Add minimal `lib.rs` skeletons for the 6 empty Rust crates (even `pub fn placeholder() {}` is enough to make `cargo build -p <name>` succeed).
- Property-based tests (hypothesis) for `risk/sizing.py` + `backtest/metrics.py`.
- Integration tests (TimescaleDB / Redis / Prometheus — gated on Docker presence).
- Live `BinanceVenue` smoke test against testnet.

## Large (1+ weeks)

- Implement `crates/cryptobot-features` SIMD features.
- Wire `cryptobot.ml` online inference + drift detection (already in `ml/online.py`; needs Engine hookup).
- Add walk-forward service.
- Implement `cryptobot.execution.algorithms` server with TWAP/VWAP/POV/IS algos.

## Architectural

- DI container (`dependency-injector`).
- Replace global singletons with `Settings` + lifetime.
- Add OpenTelemetry tracing for `EventBus.publish`/`_dispatch`.
- Add `prometheus_client` switch: `MetricsCollector` interface so non-Prometheus backend can be used (avoid eager import — related to B051).

## Nice-to-have

- `cryptobot dashboard` TUI command.
- `cryptobot replay` command for replaying events from `state.py` DB.
- `pre-commit` config with `ruff` + `black`.
- `cryptobot` CLI command to regenerate `configs/base.yaml` from `Settings`.

## Confidence

- High: each item is identifiable.
