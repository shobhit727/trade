# 24. Agent Log

> **Last Updated**: 2026-07-31 (audit sync)
> **Confidence**: High.

## Session 2026-07-31

### User goals

1. "look at plan.md and PROJECT_MEMORY and run a full audit"
2. "update plan.md and PROJECT_MEMORY and push to github"

### Sequence

1. Walked every file in repo and produced a verified inventory (src/, tests/, crates/, configs/, deploy/, monitoring/, docker/, scripts/, migrations/, root).
2. Cross-referenced `plan.md`, `PROJECT_MEMORY/12_Feature_Status.md`, `13_Bug_Tracker.md`, `14_Technical_Debt.md`, `00_Project_Overview.md`, `23_Repository_History.md`, `24_Agent_Log.md` against actual code.
3. Found 26 distinct mismatches across the three sources (plan over-claims, Memory under-claims, both stale vs code).
4. Created `PROJECT_MEMORY/25_Audit_2026-07-31.md` documenting all mismatches.
5. Updated `plan.md`:
   - Section 2 status table: corrected all stale ✅/🔲/⚠️ for 40+ modules.
   - Section 3 architecture tree: fully updated to match actual file tree.
   - Section 4 Phases 2-8: corrected statuses (Phase 2 ✅, Phase 4 ⚠️, Phase 6 ⚠️, Phase 8 ⚠️).
   - Section 5 technical decisions: updated Rust and ML framework status.
6. Updated `PROJECT_MEMORY/12_Feature_Status.md`: all modules re-verified, bugs resolved added, new open bugs noted.
7. Updated `PROJECT_MEMORY/13_Bug_Tracker.md`: 23 bugs moved Resolved; 12 new open bugs added (B052-B059).
8. Updated `PROJECT_MEMORY/14_Technical_Debt.md`: resolved items marked done; new critical items added.
9. Updated `PROJECT_MEMORY/00_Project_Overview.md`, `23_Repository_History.md`, `24_Agent_Log.md`.
10. Prepared commit + push.

### Verified facts (not assumed)

- `Settings(extra="ignore")` silently drops YAML keys — mitigated by `_flatten_yaml` + `from_yaml_safe`.
- `core/state.py` falls back when `_sqlite3` missing + logs warning.
- `monitoring/metrics.py` uses `Gauge` for PnL (not Counter).
- `data/ingestion.py` opens `aiohttp` sessions per call (no reuse) — B042 open.
- `strategies/base.py` no longer prints on import.
- `core/clock.py` no longer prints.
- `backtest/engine.py` no longer prints.
- `utils/decorators.py` jitter clamped to ≥0; `circuit_breaker` raises in running loop.
- `execution/engine.py` emits `ORDER_REJECTED` with reason + check_type on risk/venue reject.
- `core/portfolio.py` `update_equity` auto-resets daily PnL on UTC day boundary.
- `core/bus.py` `publish_batch` dispatches atomically under single lock.
- `monitoring/alerting.py` `init_alerting()` skips start when no channels; `stop()` idempotent.
- `BinanceVenue` exists (240 lines) and tested.
- `ml_strategy.py` does NOT exist — plan.md Phase 4 wrong.
- `data/features.py` does NOT exist — use `ml/features.py`.
- `deploy/k8s/` missing Service + HPA.
- `docker-compose.yml` default profile broken (missing monitoring/{loki,promtail,nginx}).
- Rust workspace: 7 crates with empty `src/` — `cargo build` fails.
- 6 dead empty dirs under `src/cryptobot/`.

### Decisions

- Sync all docs to match code reality (not aspirational state).
- Leave `ml_strategy.py` as 🔲 in plan.md and add B054 to bug tracker — user to decide implement or downgrade.
- Leave compose default profile broken (B052) — user to scaffold missing dirs or remove services.
- Leave K8s missing Service/HPA (B053) — user to add.
- Drop `lightgbm` from requirements if unused (B055) — user to confirm.
- Fix config mismatches (B058, B059) — user to confirm.

### Open questions

- Should `ml_strategy.py` be implemented now or plan.md Phase 4 downgraded?
- Should `monitoring/{loki,promtail,nginx}` be scaffolded or removed from compose?
- Should `lightgbm` be removed from `requirements/prod.txt`?
- Should `data/features.py` be created as alias or plan reference removed?
- Should Rust crates get minimal `lib.rs` or be removed from workspace?
- Should `configs/base.yaml` `strategies.enabled` be wired to registry auto-load?

### Confidence

- High on facts in `00`, `12`, `13`, `14`, `23`, `24`, `25`.
- Medium on behavior of modules not exercised by tests.
- Low on ML/Rust coverage.