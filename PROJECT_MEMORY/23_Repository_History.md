# 23. Repository History

> **Last Updated**: 2026-07-31 (audit sync)
> **Confidence**: Git history present; entries below are session-level snapshots.

## Original state (pre-session)

- Repository mostly planning-stage scaffolding.
- `plan.md` (51 KB) describes a 120+ module crypto quant platform.
- `PROJECT_MEMORY/00-14` documents aspirational architecture.
- `core/bus.py`, `core/clock.py`, `core/portfolio.py` were implemented but `PROJECT_MEMORY` listed them as "Not Implemented".
- `tests/unit/test_core_foundation.py` referenced non-existent APIs (`SubscriptionMode`, `update_on_trade`).
- No `Dockerfile`, no `requirements/test.txt`, no `.dockerignore`.
- `requirements/prod.txt` pinned to versions incompatible with Python 3.11+ and contained `monero-rpc==0.3.0` (no PyPI wheel).

## Session 2026-07-29 (audit)

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

## Session 2026-07-31 (audit sync)

### Documentation sync

- `plan.md`: Section 2 status table corrected (binance.py ✅, ml/features.py ✅, backtest/data/runner/reporting/validation ✅, router/adverse_selection ✅, health_server ✅, K8s ⚠️ missing Service/HPA, Rust 🔲 empty scaffolding, compose ⚠️ default profile broken). Section 3 architecture tree fully updated. Section 4 Phases 2-8 corrected (Phase 2 ✅, Phase 4 ⚠️ ml_strategy missing, Phase 6 ⚠️ core only, Phase 8 ⚠️ compose broken + K8s missing Service/HPA). Section 5 technical decisions updated (Rust status, ML framework).
- `PROJECT_MEMORY/12_Feature_Status.md`: All modules re-verified; resolved bugs marked; missing items noted (ml_strategy.py, data/features.py, k8s Service/HPA, compose default profile, Rust crates).
- `PROJECT_MEMORY/13_Bug_Tracker.md`: B025/B027/B028/B029/B031/B037/B040/B041/B044/B045/B046/B048/B049 moved from Open → Resolved. New open bugs added: B052-B059 (compose broken, K8s missing, ml_strategy missing, lightgbm unused, data/features.py missing, Rust crates empty, config mismatches, strategies.enabled not read).
- `PROJECT_MEMORY/14_Technical_Debt.md`: Resolved items removed/marked done. New critical items: fix compose default profile, add K8s Service/HPA, implement ml_strategy.py or downgrade plan, remove dead dirs, drop lightgbm, fix config mismatches.
- `PROJECT_MEMORY/00_Project_Overview.md`: Full rewrite to match current state.
- `PROJECT_MEMORY/25_Audit_2026-07-31.md`: New audit document with 26 mismatches and top 5 fixes.

### Verification

- `python3 -m py_compile` passes on all edited files.
- `docker compose --profile test config`: passes.
- `docker compose config` (default): fails on missing `monitoring/{loki,promtail,nginx}`.
- Docker run blocked by host daemon instability.
- 22 unit test files in `tests/unit/`.
- `cargo build` not tested (Rust crates empty).