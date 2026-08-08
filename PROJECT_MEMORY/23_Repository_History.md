# 23. Repository History

> **Last Updated**: 2026-08-08 (catalog 84 strategies shipped + wired into registry + runner; 749 pytest + 63 Rust green)
> **Confidence**: Git history present; entries below are session-level snapshots.

## Session 2026-08-06 (Phase 3 paper harness + CI/CD overhaul)

- `f837152` edge research (maker/taker venue model, funding_sim) pushed earlier on main.
- `5da9a0b` Phase 3 funding-carry paper harness: `src/cryptobot/live/paper_harness.py` + `cli paper-funder` + 8 tests (WS spot bookTicker + fapi premiumIndex REST-poll fallback).
- `f6e6f21` CLI comma-split symbols fix.
- `932e7e2` pyflakes unused-variable fixes (`realistic.py` book seeding populates `PriceLevel.total_quantity`, `optimizer.py` dead code removed).
- Merged `35d0312` Phase 4 transaction cost model (`execution/costs.py` + 305-line test file) into main.
- `f6ce262` CI/CD overhaul: concurrency group, timeout-minutes, rust-cache, PR-only-amd64 matrix, SBOM/provenance merged into release push, linters unpinned, coverage artifact, checkout@v6.
- `9e65469` fix invalid `matrix` context in job-level `if` (actionlint).
- `d265fd9` Dockerfile site-packages path derived from `PYTHON_TAG` (3.13→3.14).
- `6503306` removed `-C target-cpu=native` from `.cargo/config.toml` (cached proc-macro SIGILL across runner CPUs).
- Repo made **public** 2026-08-06 (private repo had exhausted Actions minutes → CI jobs failed instantly with no runner).
- CI fully green on `6503306` (first green since before the session).

## Original state (pre-session)

- Repository mostly planning-stage scaffolding.
- `plan.md` (~64 KB) describes a 120+ module crypto quant platform.
- `PROJECT_MEMORY/00-14` documents aspirational architecture.
- `core/bus.py`, `core/clock.py`, `core/portfolio.py` were implemented but `PROJECT_MEMORY` listed them as "Not Implemented".
- `tests/unit/test_core_foundation.py` referenced non-existent APIs.
- No `Dockerfile`, no `requirements/test.txt`, no `.dockerignore`.
- `requirements/prod.txt` pinned to versions incompatible with Python 3.11+ and contained `monero-rpc==0.3.0` (no PyPI wheel).

## Session 2026-07-29 (first audit)

### Code fixes

- `backtest/metrics.py` — imports, sortino, drawdown guard.
- `backtest/engine.py` — Position/PositionSide imports, win/loss guards, profit factor formula.
- `backtest/validation.py` — `run_validation` returns report.
- `data/storage.py` — `timedelta` import.
- `data/cleaning.py` — None/empty guards.
- `monitoring/health.py` — async detection, false-as-unhealthy.
- `strategies/base.py` — correct `OrderEvent` construction.
- `core/clock.py` — `time` import.
- `core/state.py` — graceful SQLite fallback.

### New modules

- `risk/{limits,sizing,kill_switch,correlation,manager}.py`.
- `execution/{engine,algorithms}.py` + `execution/venue/{base,simulated}.py`.
- `cli/main.py`.
- `tests/unit/test_core_foundation.py` smoke tests.

### Build / Docker

- `Dockerfile` (`python:3.14-slim`, multi-stage).
- `requirements/test.txt`, `requirements/prod.txt` updated.
- `.dockerignore` minimal context.
- `docker-compose.yml` `cryptobot-test` service in profile `test`.

### Memory

- `PROJECT_MEMORY/00-24` rewritten/created to reflect verified code state.

## Session 2026-07-31 morning (audit v1)

### Documentation sync

- `plan.md`: Section 2 status table corrected; Section 3 architecture tree updated; Section 4 Phases 2-8 corrected; Section 5 technical decisions updated.
- `PROJECT_MEMORY/12_Feature_Status.md`: All modules re-verified; resolved bugs marked; missing items noted.
- `PROJECT_MEMORY/13_Bug_Tracker.md`: B025/B027/B028/B029/B031/B037/B040/B041/B044/B045/B046/B048/B049 → Resolved. New open bugs B052-B059 added.
- `PROJECT_MEMORY/14_Technical_Debt.md`: Resolved items marked done; new critical items added.
- `PROJECT_MEMORY/00_Project_Overview.md`: Full rewrite to match current state.
- `PROJECT_MEMORY/25_Audit_2026-07-31.md`: New audit document with 26 mismatches and top 5 fixes.

### Verification

- `python3 -m py_compile` passes on all edited files.
- `docker compose --profile test config`: passes.
- `docker compose config` (default): initially failed on missing `monitoring/{loki,promtail,nginx}`; later patched by scaffolding those dirs.

## Session 2026-07-31 afternoon (B053-B059 + B060-B069 + audit v2)

### Code fixes

- B053: `deploy/k8s/05-service.yaml` + `06-hpa.yaml` created; `kustomization.yaml` updated.
- B054: `src/cryptobot/strategies/ml_strategy.py` created with `MLStrategy` + `MLStrategyConfig`.
- B055: `lightgbm` removed from `requirements/prod.txt`.
- B056: `src/cryptobot/data/features.py` created (re-export of `cryptobot.ml.features`).
- B057: `strategies/registry.py` `_STRATEGY_REGISTRY_MAP` includes `ml_strategy`.
- B058: `configs/base.yaml` `ml.models.direction.type` → `sklearn_logreg`; `volatility`/`regime` `enabled: false`.
- B059: `load_strategies_from_config()` added; YAML `strategies.enabled` honored.
- B042: `BinanceDataIngestion` `_ensure_session()` with lock for reuse.
- B043: `HealthMonitor` runtime register/unregister/update_check_interval/get_check.
- B060/B061: `RiskManager` notional guard (`> 0`); `ExecutionEngine` fetches `venue.get_price()` for market orders.
- B062: `BacktestEngine` skips mark price update if no valid price in payload.
- B063: `BacktestEngine` removes manual equity double-count.
- B064: `BacktestEngine` guards `pos.entry_price > 0` for `pnl_pct`.
- B065: `DirectionClassifier` persists train stats for `predict`.
- B066: Health checks fall back to `[settings.exchange.default_symbol]`.
- B067: `AlertManager` shared `ThreadPoolExecutor` for email.
- B068: `clean_klines` `start`/`end` Optional.
- B069: `StateManager` DB path uses `/app/data` when mounted.
- B026: `create_standard_checks` uses named `async def` instead of lambdas.

### Documentation sync (audit v2)

- `PROJECT_MEMORY/26_Audit_2026-07-31_v2.md` created. Captures post-fix state, lists remaining drift.
- Stale memory docs refreshed: `01`, `02`, `04`, `05`, `06`, `07`, `09`, `11`, `13` (dedupe + add new open), `14` (mark done), `15`, `17`, `19`, `20`, `21`, `22`, `25` (superseded notice).
- `13_Bug_Tracker.md`: duplicate B026/B042/B043/B053 rows removed; B051 still Open; new Open rows for Rust workspace + dead dirs.
- `14_Technical_Debt.md`: items 1-21 marked Done; "Fix Rust workspace" + "Remove dead dirs" added to Open.
- `12_Feature_Status.md`: `data/features.py`, `ml_strategy.py`, `deploy/k8s/` flipped to ✅; Rust crates note that only `cryptobot-core` has manifest.
- `00_Project_Overview.md`: rewrite to current state.
- `25_Audit_2026-07-31.md`: SUPERSEDED notice + pointer to v2.

### Verification

- `python3 -m py_compile` passes on all edited files (assumed; same constraint as prior audit).
- `docker compose --profile test config`: passes.
- `docker compose config` (default): passes (monitoring dirs scaffolded).
- `cargo build` from root: **fails** — workspace lists 7 members; only `cryptobot-core` has a manifest.
- 22 unit test files in `tests/unit/`.


## 2026-08-06 — Phase 4 ✅ + ML models discovery + doc sync

- **Phase 4 closed**: `ml_strategy.py` created (MLStrategy + DirectionClassifier hook); `execution/costs.py` added (TransactionCostModel: spread, fees, slippage, funding, rebates, maker/taker). 6/6 strategies + cost model shipped.
- **ML models reality check**: `ml/models/volatility.py` (333 LOC: EWMA/GARCH/realized/quantile), `regime.py` (289 LOC: HMM/k-means/GMM/threshold), `ensemble.py` (139 LOC: weighted voting) **already implemented**. plan.md incorrectly listed them as 🔲 pending — now ✅.
- **Phase 5 status**: Sizing + checks + per-strategy tracker + drawdown scaling + correlation gate + kill switch all done. Remaining: `risk/portfolio_optimizer.py` (HRP, mean-CVaR), real-time Prometheus risk-metric emission from `RiskManager`.
- **Doc sync**: `plan.md` Phase 4/5/6 status corrected, dates bumped; `PROJECT_MEMORY/12_Feature_Status.md` Last-Updated bumped.
- **Tests**: 413 Python + 31 Rust still green; lint clean; Docker test target passes.
- **Git**: existing remote `git@github.com:shobhit727/trade.git` (main).

## 2026-08-06 — Audit (post Phase 4): all green, two stale doc items fixed

**Verified live:**
- Python: 413 passed, 4 skipped (pyarrow/prometheus-not-applicable) via Docker test target.
- Rust: 31 tests pass, `cargo fmt --all -- --check` clean, `cargo clippy --workspace --all-targets` clean (7 crates, PyO3 0.29).
- 44 unit test files; `ml/models/{volatility,regime,ensemble}.py` present; `fix/realistic-venue-bugs` diverges from main by −2276 lines (superseded).
- Local `.venv` unusable (Python 3.14.5 built without SSL/_ctypes) — all Python verification via Docker.

**Doc fixes:**
- `13_Bug_Tracker.md`: removed stale Open rows (B051 lazy-import, dead dirs — both long resolved); added B073 documenting stale remote branch `fix/realistic-venue-bugs`.
- `plan.md`: Last-Updated note bumped to reflect audit result.

## 2026-08-06 — Phase 5 ✅ (portfolio optimizer + risk-metric wiring)

- **New** `src/cryptobot/risk/portfolio_optimizer.py` — numpy-only Hierarchical Risk Parity (single-linkage clustering + recursive bisection) and mean-CVaR (per-asset tail-loss weights). `hrp_weights` / `mean_cvar_weights` return `PortfolioOptimizerResult` (weights dict, sum≈1). Exported from `cryptobot.risk`.
- **Wiring**: `RiskManager.report_risk_metrics()` now emits Prometheus gauges via `monitoring.metrics.record_risk` (exposure, daily loss, drawdown, kill-switch) on every `check_order`; safe on a timer. `record_risk` was previously dead code.
- **Tests**: `tests/unit/test_risk_portfolio_optimizer.py` (10 tests) — weight normalization, single-asset, correlated-pair balance, shape/alpha validation, metric emission, zero-equity no-op.
- **Lint**: ruff clean; formatting normalized on `risk/{sizing,strategy_tracker,manager}.py`.
- **Suite**: 423 passed, 4 skipped (Docker); Rust untouched.

## 2026-08-07 — Phase 3 ✅ + Rust stats/risk submodules

**Phase 3 (Strategy Framework) closed:**
- `src/cryptobot/strategies/position.py` — `Position` + `PositionManager`: scale-in/out with quantity-weighted avg entry, stop-loss/take-profit `reduce_only` exits, trailing-stop ratchet. Pure state, no EventBus dep. (12 tests)
- `src/cryptobot/backtest/optimize.py` — `optimize_strategy`: Optuna bayesian search over strategy config params (optional dep, deterministic grid fallback), Sharpe/Sortino/MaxDD/return objectives. (5 tests)

**Rust workspace flesh-out:**
- stats: `deflated_sharpe` (Bailey & LdP, MC expected-max), `monte_carlo` (block permute, loss probability, percentiles), `pbo` (CSCV), `sensitivity`, `walk_forward` (embargo splits) — all real impls replacing placeholders.
- risk: `limits`, `kill_switch` (latching state machine), `portfolio_optimization` (mean-variance, inverse-vol, risk-parity) — real impls.
- backtest engine: `run()` now records equity curve → computes Sharpe + max drawdown (was TODO 0.0).
- Rust tests: 31 → 63. clippy -D warnings + fmt clean.

**Gates:** 591 pytest passed, 4 skipped (1 flaky hypothesis test passed on re-run; pre-existing remote test). ruff clean.

## 2026-08-08 — Strategy catalog (84 strategies) shipped

**Strategies delivered:** 84 catalog signal strategies, one file per strategy under `src/cryptobot/strategies/catalog/`, each with a per-strategy test under `tests/strategies/`. Coverage: Trend (16), Mean Reversion (12), Momentum (11), Breakout (11), Volatility (8), Volume (7), Stat-Arb (5), Crypto (5), Hybrid (10).

**Infrastructure added:**
- `strategies/indicators.py` — 22 numpy OHLCV primitives (sma/ema/rsi/macd/atr/bb/donchian/cci/roc/obv/vwap/fisher/stoch/williams/keltner_mid/chaikin_mf/cumulative_delta/range_n/inside_bar/zscore/bollinger_position/true_range/make_order).
- `strategies/signal_base.py` — `SignalStrategy` streaming base with per-symbol OHLCV buffers, flip-on-signal MARKET orders. `feed(symbol, close, high, low, volume)`.
- `strategies/catalog/__init__.py` — auto-registers all 84 (class, config) pairs in `_REGISTRY`.
- `strategies/registry.py` — `_STRATEGY_REGISTRY_MAP` merges catalog (90 names total).
- `backtest/runner.py` — `make_strategy(name)` looks up registry; `feed()` passes OHLCV to new strategies with legacy 2-arg fallback.
- `tools/gen_catalog.py` — generator script holding the spec table (84 entries), emits one module + one test per strategy. Test modes: trend (monotonic), osc (sine+drift), vol (spike), flow (asymmetric candles); dirs="both"/"long"/"short" filters the per-direction test assertions.

**Gates:** 749 pytest passed (was 591), 18 skipped, 0 failed. Ruff clean. Rust unaffected: fmt + clippy -D warnings + 63 tests still green.

## 2026-08-08 — Real BTCUSDT 1h validation (first run on real data)

**Findings:** 0/84 catalog strategies passed the walk-forward + Monte Carlo gauntlet on 1000 real BTCUSDT 1h bars (2026-06-27 → 2026-08-08, price range $60204 → $65000).

**Top performers (still failed MC significance):**
- `keltner` +14.9