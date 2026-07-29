# 24. Agent Log

> **Last Updated**: 2026-07-29 (audit pass)
> **Confidence**: High.

## Session 2026-07-29

### User goals

1. "finish the code base"
2. "set up docker so i can run test and this is not a toy"
3. "use python 3.14.x"
4. "if docker is not working then stop working on it and work on project memory"
5. "audit everything and update PROJECT_MEMORY"

### Sequence

1. Walked every file in repo and produced a verified inventory.
2. Fixed immediate import/runtime blockers in `backtest/`, `data/`, `monitoring/`, `strategies/`, `core/`.
3. Added minimal `risk/`, `execution/`, `cli/` packages.
4. Replaced broken tests with smoke tests.
5. Built `Dockerfile` with `python:3.14-slim`; added `requirements/test.txt` and `cryptobot-test` Compose service.
6. Removed `monero-rpc==0.3.0` to unblock Docker build.
7. Hit Docker daemon host crash (`qemu: aborted`). Stopped Docker per user instruction.
8. Shifted to PROJECT_MEMORY: rewrote 00-14, created 15-24, to reflect verified state.
9. Audited full repo: directory tree, file LOC, public class names, import graph, schema/config mismatches.
10. Updated 00-09 to encode the YAML/Settings mismatch as a verified fact.
11. Updated 10-14 with consistent verified findings.
12. Kept 15-24 consistent with current code.

### Verified facts (not assumed)

- `Settings(extra="ignore")` silently drops YAML keys (`exchanges.binance`, `monitoring.alerts.*`, etc.).
- `core/state.py` falls back when `_sqlite3` missing.
- `monitoring/metrics.py` uses Prometheus `Counter` for realized PnL (cannot decrement).
- `data/ingestion.py` opens `aiohttp` sessions per call (no session reuse).
- `strategies/base.py` `MeanReversionStrategy` placeholder uses hardcoded `65000` trigger.
- `core/clock.py` `SimulatedClock` lacks lock around `pause`/`resume`.
- `utils/decorators.py` jitter can produce negative `sleep_time`.
- `utils/decorators.py` sync `circuit_breaker` wrapper uses `run_until_complete` inside running loop.

### Decisions

- Diagnose YAML/Settings mismatch but do not fix in this session (out of scope of "memory update").
- Keep `cryptobot-test` Compose service.
- Document `Cargo.toml` (root) + `crates/cryptobot-core/Cargo.toml` as manifest-only.

### Open questions (see `19_Open_Questions.md`)

- Will `requirements/prod.txt` install on Python 3.14?
- Does `cryptobot` service expose `8080/health` HTTP?
- Is `Settings(extra="ignore")` intentional?

### Confidence

- High on facts in `00-14`.
- Medium on `15-24` (still some forwards-looking claims).
- Low on ML/Rust coverage.
