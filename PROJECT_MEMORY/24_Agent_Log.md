## Session 2026-07-31 (audit v5 — final cleanups)

### Goal

Resolve remaining low/medium items from audit v4 blockers list:
- BinanceWSClient silent fallback → add warning log (B066 was fixed but didn't warn)
- Dockerfile USER directive (already present in production stage)
- Dead empty dirs (already removed from repo)
- Dead seccomp/ dir (already gone)
- Refresh plan.md status + Section 11

### Sequence

1. Added warning logs in `BinanceWSClient.__init__` when `settings.exchange.symbols` or `timeframes` are empty (falls back to `default_symbol` / `["1m"]`).
2. Verified `Dockerfile` already has `USER 1000:1000` in production stage (build-as-root, run-as-non-root).
3. Confirmed dead dirs (`allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`) already removed from repo.
4. Confirmed `seccomp/` dir already gone.
5. Updated `plan.md` status + blockers + Section 11 to mark all items resolved/deferred.

### Verified

- `cargo build` + `cargo test` still clean.
- `pytest tests/unit/test_monitoring_lazy_imports.py` → 5 passed, 2 skipped (prometheus_client present in env).
- `python -m py_compile` on modified files clean.

### Updated plan.md

- Status: "all blockers resolved"
- Section 12 blockers: all items marked resolved/deferred
- Section 11 "To Create Next": all items marked ✅

### Remaining after this pass

- ML volatility/regime/ensemble models (deferred — out of audit scope)
- Integration test fixtures for TimescaleDB/Redis/Prometheus (out of audit scope)

## Session 2026-07-31 (audit v4 — B051 close-out)

### Goal

Resolve the **Medium** item from audit v2: B051 — `cryptobot.monitoring.{metrics, alerting}` failed to import when `prometheus_client` or `aiohttp` were absent. The `monitoring/__init__.py` facade was already lazy via `__getattr__`, so package-level `import cryptobot.monitoring` worked, but submodule imports (and any direct `from cryptobot.monitoring.metrics import ...` call) still required the optional deps.

### Sequence

1. Confirmed initial state: `metrics.py` does `from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry, generate_latest` at module load + constructs ~80 metric objects at module level. `alerting.py` does `import aiohttp` at line 21 for HTTP webhook channels (Telegram, Discord, PagerDuty).
2. Verified `monitoring/__init__.py` already routes symbol access through `__getattr__` (122 symbols listed, lazy load).
3. Patched `metrics.py`: wrapped the Prometheus import in try/except; defined `_NoOpMetric`, `_NoOpLabels`, `_NoOpRegistry` stubs that swallow `.inc/.dec/.set/.observe/.labels/.time/.info` calls; bound module-level names to the stubs when Prometheus is unavailable; exposed `PROMETHEUS_AVAILABLE` flag.
4. Patched `alerting.py`: removed module-level `import aiohttp`; moved it inside the 3 `_send_async` methods of Telegram, Discord, PagerDuty channels.
5. Wrote `tests/unit/test_monitoring_lazy_imports.py` with 6 tests verifying: (a) `cryptobot.monitoring` package facade imports without deps, (b) `cryptobot.monitoring.alerting` imports without aiohttp, (c) AST-level check that alerting has no module-level `import aiohttp`, (d) health + dashboard import cleanly, (e) when Prometheus is unusable, `PROMETHEUS_AVAILABLE` is False and metric ops are no-ops, (f) the no-op fallback classes work via a subprocess injecting a broken `prometheus_client` stub (so the test always exercises the fallback regardless of host env).
6. Test run: `pytest tests/unit/test_monitoring_lazy_imports.py -v` → 5 passed, 2 skipped (skips because `/usr/bin/python3` has a working `prometheus_client`); the subprocess stub-injection test always passes and is the durable proof.

### Verified facts

- `metrics.py` exposes `PROMETHEUS_AVAILABLE` flag.
- `_NoOpMetric` + `_NoOpLabels` + `_NoOpRegistry` defined as fallbacks; all calls no-op.
- `alerting.py` no longer imports `aiohttp` at module level (AST-checked).
- `monitoring/__init__.py` `__getattr__` already lazy (unchanged).
- `py_compile` clean on `metrics.py`, `alerting.py`, `__init__.py`, `health.py`, `dashboard.py`.

### Pre-existing test failures (NOT from this B051 fix)

`tests/unit/test_monitoring_alerting.py` failures and many `tests/unit/test_monitoring_health.py` failures are caused by pre-existing test bugs (e.g. `severity.value` on a string, `datetime.utcnow()` deprecation). They reproduce on the untouched `main` branch (verified by `git stash`). Out of scope for B051.

### Refreshed memory docs

`13_Bug_Tracker.md` (B051 → Resolved with fix description), `14_Technical_Debt.md` (new "Lazy noop fallbacks for monitoring" section), `15_Design_Patterns.md` (anti-pattern entry crossed out), `05_Control_Flow.md` (No-Prometheus failure mode → tolerant), `20_Assumptions.md` (AV-2 → Resolved), `21_Risk_Assessment.md` (R13 → Resolved), `22_Improvement_Ideas.md` (related item marked done), `00_Project_Overview.md` (architecture + remaining gaps).

### Remaining gaps after this pass

- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.
- ML `volatility.py`, `regime.py`, `ensemble.py` missing.

## Session 2026-07-31 (audit v3 — Rust workspace fix)

### Goal

Resolve the **High** item from audit v2: `cargo build` fails because `Cargo.toml [workspace] members` listed 7 crates but only `cryptobot-core` had a `Cargo.toml`.

### Sequence

1. Verified `crates/cryptobot-{backtest,features,orderbook,py,risk,stats}/` contain only empty `src/`, `tests/`, `benches/` skeletons (no source files, no manifest). Deleted all 6 dirs.
2. Trimmed `[workspace] members` in `Cargo.toml` to `["crates/cryptobot-core"]` only.
3. First `cargo build` failed: `[target.*] rustflags` illegal in virtual manifests → moved those key/values to `.cargo/config.toml`.
4. Second `cargo build` failed: `python = ["pyo3"]` feature in `cryptobot-core/Cargo.toml` referenced a dep that wasn't in `[dependencies]`. Dropped the feature (Python bindings are deferred until the `cryptobot-py` crate is reintroduced).
5. Created `crates/cryptobot-core/src/lib.rs` stub: `pub fn placeholder() -> &'static str` + 1 unit test.
6. Third `cargo build` ran but warned `unused manifest key: build-profile` → renamed `[build-profile.dev]` and `[build-profile.release]` to `[profile.dev]` and `[profile.release]` (current cargo syntax).
7. `cargo build` clean (~1m 6s). `cargo test`: 1 test passing. `cargo build --release` clean. Rustup stable 1.97.1.
8. Added `target/` to `.gitignore` and `target/` to `.dockerignore`. Added `Cargo.toml`, `Cargo.lock`, `!crates/`, `!.cargo/` to `.dockerignore` allowlist (Rust sources may need to be built inside the buildx layer).
9. Refreshed memory docs: `01` (Rust layer block + table), `09` (Rust section), `10` (Build system table), `12` (feature status rows for cryptobot-core and the deleted siblings), `13` (Rust workspace defect → Resolved), `14` (Rust fix → Done), `21` (R9 → Resolved), `22` (Rust quick-win status), `26` (audit v2 §1 + §7 status block), `00_Project_Overview` (Remaining real gaps).

### Verified

- `cargo build` (debug + release) clean — no warnings.
- `cargo test`: `tests::placeholder_returns_name` passes.
- `cargo metadata --no-deps`: workspace has 1 member `cryptobot-core@0.1.0`; resolve has no errors.
- 6 empty sibling crate dirs gone from `crates/`.

### Remaining gaps after this pass

- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.
- `monitoring` optional-deps hygiene (B051).
- ML `volatility.py`, `regime.py`, `ensemble.py` missing.

## Session 2026-07-31 (audit v2 — current pass)

### User goals

1. "look at plan.md and PROJECT_MEMORY and run a full audit"
2. "update plan.md and PROJECT_MEMORY and push to github"

### Sequence

1. Walked every directory (`src/`, `tests/`, `crates/`, `configs/`, `deploy/`, `monitoring/`, `docker/`, `scripts/`, `migrations/`, `docs/`) and produced a verified inventory.
2. Read every `PROJECT_MEMORY/0X_*.md` plus `25_Audit_2026-07-31.md`.
3. Cross-referenced against actual code: `grep` for `lightgbm` (gone), `ml_strategy.py` (present), `data/features.py` (present), K8s `Service`/`HPA` (present), Rust manifests (only `cryptobot-core`), monitoring subdirs (scaffolded).
4. Found v1 audit (`25_Audit_2026-07-31.md`) and many `PROJECT_MEMORY/0X_*.md` files were **stale** post-B051-B069 fixes. v1 audit still claimed `ml_strategy.py` missing, K8s lacking Service/HPA, lightgbm in prod.txt — all wrong.
5. Wrote `PROJECT_MEMORY/26_Audit_2026-07-31_v2.md` capturing current state and remaining drift.
6. Refreshed stale memory docs: `01`, `02`, `04`, `05`, `06`, `07`, `09`, `11`, `13`, `14`, `15`, `17`, `19`, `20`, `21`, `22`. Marked `25` superseded.
7. Deduped duplicate B026/B042/B043/B053 rows in `13_Bug_Tracker.md`; added "Open" row for Rust workspace defect and dead-dirs defect.
8. Marked `12_Feature_Status.md` `data/features.py`, `ml_strategy.py`, `deploy/k8s/` to ✅; corrected Rust notes.
9. Updated `00_Project_Overview.md` to current state.
10. Refreshed `23_Repository_History.md` and this log.

### Verified facts (post-fix)

- ✅ `ml_strategy.py` (145 lines, `MLStrategy` + `MLStrategyConfig`).
- ✅ `data/features.py` (28 lines, re-export of `cryptobot.ml.features`).
- ✅ `deploy/k8s/05-service.yaml` (ClusterIP) + `06-hpa.yaml` (v2 CPU/memory) + `kustomization.yaml` references both.
- ✅ `lightgbm` removed from `requirements/prod.txt`.
- ✅ `configs/base.yaml` `ml.models.direction.type: sklearn_logreg`; `volatility`/`regime` `enabled: false`.
- ✅ `strategies/registry.py` defines `load_strategies_from_config` + `_STRATEGY_REGISTRY_MAP` (6 strategies).
- ✅ `monitoring/{loki,promtail,nginx}` scaffolded with config files; default compose profile validates.
- ✅ `BinanceDataIngestion` uses `_ensure_session()` with lock (B042).
- ✅ `HealthMonitor.unregister_check`, `update_check_interval`, `get_check` added (B043).
- ✅ `RiskManager.check_order` skips notional when no valid price (B060); `ExecutionEngine` fetches `venue.get_price()` for market orders (B061).
- ✅ `BacktestEngine._handle_order_fill` no longer double-counts unrealized PnL (B063); guards entry_price=0 (B064).
- ✅ `DirectionClassifier` persists `_feature_means/_stds` from `fit` for `predict` (B065).
- ✅ Health checks fall back to `[settings.exchange.default_symbol]` (B066).
- ✅ `AlertManager` shared `ThreadPoolExecutor(max_workers=2)` for email (B067).
- ✅ `StateManager` DB path: `/app/data` if mounted, else cwd (B069).

### Remaining real gaps

- `Cargo.toml [workspace] members` declares 7 crates but only `crates/cryptobot-core/Cargo.toml` exists; `cargo build` from root errors on the other 6 missing manifests. Trivial fix: trim members array or add minimal manifest per crate.
- `crates/cryptobot-core/src/{events,math,time,types}/` are empty subdirs; no `lib.rs` so the crate doesn't produce a lib artifact.
- 6 dead empty dirs under `src/cryptobot/`: `allocator/`, `altdata/`, `api/`, `exchanges/`, `funding/`, `xmr/`.
- `monitoring/__init__.py` eager-imports `cryptobot.monitoring.metrics` (B051 still Open).
- `ml/models/{volatility,regime,ensemble}.py` missing (disabled in YAML).
- `plan.md` self-contradicts: Section 2 table still claims "No Service, no HPA" while Section 8 says they're done. Stray `)` in Section 3 tree.

### Decisions

- Sync all docs to match code reality.
- Mark v1 audit superseded and point readers to v2.
- Treat the Rust workspace defect as **out-of-scope** for this audit pass (5 min fix but requires touching workspace + each empty crate); flagged in `14_Technical_Debt.md`.

### Open questions

- Should the Rust workspace be trimmed to `["crates/cryptobot-core"]` or fleshed out with minimal `lib.rs` per crate?
- Should the 6 dead `src/cryptobot/` dirs be deleted or documented?
- Should `BinanceWSClient` fallback log a warning when fired?

### Confidence

- High on facts in `00`, `02`, `04`, `05`, `06`, `07`, `09`, `11`, `12`, `13`, `14`, `15`, `17`, `19`, `20`, `21`, `22`, `23`, `26`.
- Medium on behavior of modules not exercised by tests.
- Low on live Binance behavior and Rust performance layer.
