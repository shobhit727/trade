# Platform buildout v1 — final engineering report (master prompt §24)

Date: 2026-11-16.
Scope: the hybrid-evolution-research platform buildout (`research/platform/`) on branch
`feature/hybrid-evolution-research`. This is the living status report for the buildout;
the frozen point-in-time review it closes out is
`docs/ASD_STE100_IMPLEMENTATION_COMPLETION_AUDIT.md` (fix backlog F-001..F-040).
Every number below is grounded in a command output (git log / git diff / pytest / ls);
the grounding command is quoted per section. No benchmark result is reported that was
not executed on this host.

Verification basis:
- `git -C /home/ph03n1x/trade/.worktrees/feature log --oneline 7ea3811..HEAD | wc -l` → 44
- `git -C /home/ph03n1x/trade/.worktrees/feature diff --stat 7ea3811..HEAD | tail -1`
  → `90 files changed, 27309 insertions(+), 160 deletions(-)`
- `PYTHONPATH=src:. .venv/bin/python -m pytest tests/unit -k "research_platform" -q`
  at HEAD `ceb9e02` → `598 passed, 3 skipped, 2024 deselected in 106.59s`
- `tem/verification-log.md` for the full-repo suite classification.
- `lspci | grep -i -E "vga|3d|display"` → `Advanced Micro Devices, Inc. [AMD/ATI] Renoir
  [Radeon Vega Series / Radeon Vega Mobile Series] (rev c2)` (no NVIDIA GPU).

Status labels used: **Implemented**, **Tested**, **Partial**, **Designed but not
implemented**, **Blocked** (by unavailable data or external dependencies).

---

## 1. Branch name

**Implemented.** Branch `feature/hybrid-evolution-research`, HEAD `ceb9e02`
(`git branch --show-current` / `git rev-parse HEAD`).

## 2. Commits created

**Implemented.** 44 commits since `7ea3811` (`git log --oneline 7ea3811..HEAD | wc -l`).

Audit and documentation wave (5):
- `619a56a` docs(research): sync guides with verified platform implementation
- `14812c3` docs(audit): add detailed ASD-STE100 implementation audit
- `c77f064` docs(audit): expand implementation traceability and test register
- `c934de3` docs(audit): correct detailed test inventory counts
- `666c0de` docs(audit): deepen source-level platform review

P0 hardening wave (8): `ae0e969` + `009740b` (F-002/F-003/CR-002 holdout isolation),
`4446642` (F-004/F-008 licence gate + local-only API guard), `165033f` (F-001/CR-001
versioned OOS acceptance policy), `4f14786` (F-006/CR-003 candidate-level evidence),
`7f26cab` + `0d78ac7` (F-007/F-022 DSR/PBO/PSR/FDR reference fixtures), `ea05ce3`
(F-005 OOS boundary independence).

P1 capability wave (20): `ef3709f` (F-009 PIT universe), `6928cc3` (F-014 perpetual
funding ledger), `5d884dd` + `2732c96` (F-009/F-014 review fixes), `5a32f62` +
`a323fef` + `dd3d82a` + `8cb23a4` (F-010/F-011 manifests + Binance public client),
`8ace967` (CR-013 seed-robust accounting tests), `ce25563` (F-012/F-013 dated fee
schedules + FIFO lots + corporate actions), `57bf185` + `f936b29` (F-016/F-017 purge
integration + PIT causal features), `35e798f` (F-018 GP boolean/control-flow grammar),
`5f87e98` (F-019 bounded topology evolution), `087ba46` (F-021 strategy compatibility
register), `27231d4` (F-020 full component registry), `c411a6d` + `5a84951` (F-023
reproducibility metadata + reproduce_check), `9582fa6` (F-021/F-024 review tests),
`7899fe5` (F-024 four-track end-to-end validation).

P2 wave (6): `31e209b` (F-025 mixed-genome co-evolution), `99c3603` + `396c68d`
(F-030/F-031/F-032/F-033 dashboard), `c744666` + `4cece6f` + `ceb9e02` (F-026/F-027
resumable checkpoints + worker leases).

Support commits (5): `2f0951c` harvest wave1 factor corpus (30 sweep modules),
`d406391` FX merge_asof unit normalisation, `426477f` declare cmaes dependency,
`2af6886` existing_strategy worker ordering fix, `c2d3cc1` neuro/gp review hardening.

## 3. Files added

**Implemented.** 55 new files
(`git diff --name-status 7ea3811..HEAD | awk '$1=="A"' | wc -l`):

- Platform modules (10): `research/platform/acquisition/{__init__,binance,validation}.py`,
  `coevolution.py`, `derivatives.py`, `licensing.py`, `lots.py`, `reproducibility.py`,
  `sandbox.py`, `universe.py`.
- Platform tests (15): `tests/unit/test_research_platform_{acquisition,boundary,
  coevolution,composition_registry,dated_costs,derivatives,four_track_validation,
  jobs_resume,licensing,reproducibility,runner_reproducibility,sandbox,
  statistics_reference,strategy_compatibility,universe}.py`.
- Factor corpus (31... counted from the diff): `research/sweep/factors_a00.py` through
  `factors_a39.py` in the wave1 harvest (`2f0951c`).
- Docs (1): `docs/ASD_STE100_IMPLEMENTATION_COMPLETION_AUDIT.md`.
- This report is additionally new at `reports/PLATFORM_BUILDOUT_v1.md` (created after
  the diff above was taken; committed as the follow-up named in §2).

## 4. Files modified

**Implemented.** 35 files modified
(`git diff --name-status 7ea3811..HEAD | awk '$1=="M"' | wc -l`):

- Platform modules (18): `adapters.py`, `api.py`, `app.py`, `classification.py`,
  `composition.py`, `composition_policy.py`, `costs.py`, `data_catalog.py`,
  `evaluation.py`, `features.py`, `fx.py`, `genetic_programming.py`, `jobs.py`,
  `model_evaluation.py`, `neuroevolution.py`, `portfolio.py`, `runners.py`,
  `storage.py`.
- Platform tests (8): `test_research_platform.py`, `test_research_platform_api.py`,
  `test_research_platform_catalog.py`, `test_research_platform_classification.py`,
  `test_research_platform_evaluation.py`, `test_research_platform_models.py`,
  `test_research_platform_runners.py`, `test_research_platform_search.py`.
- Docs and meta (7): `GOAL.md`, `CHANGELOG.md`, `README.md`, `PROJECT_MEMORY/
  12_Feature_Status.md`, `docs/RESEARCH_PLATFORM_ARCHITECTURE.md`, `docs/RUNBOOK.md`,
  `requirements/research.txt`. (CHANGELOG's Unreleased section predates the
  acquisition/checkpoint/lease waves — 10 November refresh — see §17.)

Totals check: `git diff --stat 7ea3811..HEAD | tail -1` → 90 files changed,
27309 insertions(+), 160 deletions(-); by area: `research/` 59 files / +12491 −135,
`tests/` 23 files / +7680 −8, `docs/` 3 files / +7046 −8.

## 5. Architecture changes

**Implemented.**

- **Separate v2 research stack** (`research/platform/`, 40 Python modules incl. the
  `acquisition/` subpackage — `find research/platform -name '*.py' | wc -l`): SQLite-
  persisted experiments/candidates/jobs/datasets, isolated from the legacy runtime.
- **Point-in-time universe** (`universe.py`): membership history drives historical
  symbol sets; listings/delistings represented (F-009).
- **Data engineering** (`data_catalog.py`): immutable provenance manifests, gap/
  missing-bar audits, explicit `DataAvailabilityCatalog.availability_matrix()`;
  licence-gated acquisition (`licensing.py`, `acquisition/binance.py`, F-004/F-011).
- **Market separation**: NSE INR cash accounting (`lots.py` FIFO + corporate actions +
  dated fee schedules, F-012/F-013) vs crypto perpetual ledger with margin,
  liquidation and 8h-UTC funding settlement (`derivatives.py`, F-014).
- **Four evolution engines**: genetic programming with boolean/control-flow grammar
  (F-018), bounded neuroevolution topology evolution (F-019), full strategy-composition
  registry (F-020), mixed-genome co-evolution with controlled component exchange
  (`coevolution.py`, F-025), plus conventional baselines and NSGA-II.
- **Statistical validation**: chronological splits, label-interval-aware purging with
  strict-gt embargo in every training path (F-016), DSR/PBO/PSR/FDR with independent
  reference fixtures (F-007/F-022), versioned OOS acceptance policy (F-001).
- **Reproducibility**: complete environment records + `reproduce_check` (F-023),
  spec-anchored checkpoint validation reusing the same semantics (F-026).
- **Jobs**: resumable checkpoint stream with integrity digest and idempotent candidate
  persistence (F-026), opt-in `RESEARCH_WORKER_LEASE` distributed execution wired into
  `build_default_job_manager` (F-027).
- **Compute**: optional CuPy batch backend with tested NumPy CPU fallback and real CUDA
  device probing (`compute.py`).
- **API/dashboard**: loopback-only research API with comparisons, evolution monitor,
  resource telemetry, and full job-artefact export (F-030..F-033).

Full detail: `docs/RESEARCH_PLATFORM_ARCHITECTURE.md` (modified in this range).

## 6. Research capabilities implemented

**Implemented and tested** unless noted:

- Four-track experiment scaffolding with per-track data and classification reports
  (F-024; `test_research_platform_four_track_validation.py`).
- Existing-strategy optimisation (NSGA-II parameter search, signal adapters,
  compatibility register F-021) and strategy discovery (GP / neuro / composition).
- Conventional optimisation baselines and equal-budget hybrid search.
- Multi-objective search with Pareto fronts; mixed-population comparison fronts (F-025).
- Portfolio simulation (target weights at close t, execution at open t+1,
  participation + square-root impact on previous-bar volume) — **Partial**: an OHLCV
  approximation with documented assumptions; not calibrated against tick/order-book
  data (F-015 open, see §8/§17).
- Perpetual funding ledger with margin, liquidation, two-payment 24h funding hold,
  no retroactive charge before open (F-014).
- Candidate classification with evidence at candidate level and explicit unknown
  states (F-006); versioned OOS acceptance policy with no invented thresholds (F-001).

## 7. Data sources integrated

**Implemented (licence-gated where applicable):**

- **NSE daily panel**: local gitignored dataset (`data/nse`, ~68 MB), symlinked into
  the worktree per `tem/verification-log.md`; provenance manifests + gap audits via
  `data_catalog.py`.
- **PIT membership history**: drives `universe.py` point-in-time symbol sets (F-009).
- **Binance public market data**: acquisition client for public klines, funding-rate
  (`/fapi/v1/fundingRate` schema-validated) and open-interest endpoints with validation
  and versioning (F-011; commits `5a32f62`, `a323fef`, `8cb23a4`); gated by
  `licensing.py` — no fetch without a licence-cleared configuration (F-004).

**Recorded as available-by-catalogue only**: the `DataAvailabilityCatalog` in
production is populated by test fixtures (e.g. `{"nse:NSE": {"1d": 1}}` at
`tests/unit/test_research_platform.py:249`); there is no production registration path
populating it from live manifests yet (see §17 limitations).

## 8. Data sources investigated but unavailable

**Blocked (unavailable data), recorded as gaps in the availability matrix:**

- **Order-book / tick history** — required for F-015 execution calibration (the
  completion condition is "fill assumptions have a measured reference"); no source
  acquired on this host; the fill model remains OHLCV-approximate
  (`docs/RESEARCH_PLATFORM_ARCHITECTURE.md`, execution-realism note).
- **On-chain data** — no provider integration; listed as an extension target in the
  architecture docs.
- **Sentiment / news / macro** — no provider integration.
- **Point-in-time fundamentals** — no publication-timestamped fundamentals source.

All four remain documented extension targets (`docs/RESEARCH_PLATFORM_ARCHITECTURE.md`
"next data work" items); none is claimed as integrated.

## 9. GPU functionality implemented

**Partial — the code path is implemented and unit-tested against CPU semantics; real
GPU execution is BLOCKED BY HARDWARE on this host.**

- `compute.py`: optional CuPy backend with automatic NumPy fallback, explicit
  `cupy`-strict mode that refuses silent fallback, real CUDA device probing
  (`cp.cuda.runtime.getDeviceCount()`), device-property telemetry, and mid-run
  fallback after device/runtime failures in auto mode.
- Tests present at HEAD: `test_compute_engine_cpu_batch_matches_reference`,
  `test_compute_engine_auto_backend_is_consistent`,
  `test_compute_engine_auto_falls_back_after_runtime_gpu_failure`,
  `test_compute_engine_explicit_cupy_mode_does_not_silently_fallback`,
  `test_compute_engine_batched_dense_predictions_match_scalar_networks`
  (`tests/unit/test_research_platform.py:538-766`).
- Hardware fact: `lspci` shows only AMD Radeon Vega (Renoir iGPU); no NVIDIA GPU, and
  CuPy is not installed in the venv (`import cupy` → `ModuleNotFoundError`). F-028
  (GPU portfolio simulation parity) and F-029 (target-GPU benchmark) remain open,
  pending the user's GPU-equipped PC.

## 10. GPU benchmarks

**Blocked by hardware.** No GPU benchmark was run — none can be run on this host
(§9). Per §24's rule, no GPU benchmark numbers are reported. F-029 requires a
reproducible benchmark report on the target machine; the audit's §10.2 records the
same blocker. The compute backend's benchmark scaffold (batched dense prediction path
in `compute.py`) is ready to run once CuPy + CUDA hardware is available.

## 11. CPU benchmarks

**Partial — only suite wall-clock timings were measured; no dedicated
compute-engine throughput benchmark was executed.**

- Platform slice at HEAD `ceb9e02`: `598 passed, 3 skipped, 2024 deselected in
  106.59s` (pytest output, this host, 2026-11-16).
- Full-repo suite (from `tem/verification-log.md`, at `f936b29`): run 1 `12 failed,
  2564 passed, 11 skipped, 2 errors (242s)`; run 2 (after `data` symlink + cmaes
  install) exit 0 green with 2 known order-dependent legacy flakes in one run's tail.
- No standalone CPU throughput microbenchmark (e.g. candidates×observations batch
  timing) was run in this buildout; none is claimed.

## 12. Backtesting functionality

**Implemented and tested:**

- Individual-asset backtesting (NSE cash, crypto perps) with market-specific cost
  calculators (F-012 dated fee schedules) and FIFO tax lots + corporate actions
  (F-013), accounting invariants pinned by seed-robust tests (CR-013, `8ace967`).
- Portfolio-level backtesting (F-009 PIT membership, target-weight execution model,
  participation + square-root impact on previous-bar volume).
- Crypto derivative accounting: perpetual funding ledger, margin, liquidation,
  boundary-crossing settlement with two-payment hold tests (`2732c96`, F-014).
- **Partial**: execution realism remains an OHLCV approximation (no order-book replay,
  queue priority, partial prints, auction mechanics, measured latency — documented in
  `docs/RESEARCH_PLATFORM_ARCHITECTURE.md`).

## 13. Statistical validation methods

**Implemented and fixture-tested:**

- Chronological split definitions with label-interval-aware purging and explicit
  embargo, integrated into **every** training path with leakage tests (F-016,
  `57bf185`; strict-gt embargo semantics documented in `f936b29`).
- Independent reference fixtures + sensitivity analysis for DSR, PBO, PSR, FDR
  (F-007/F-022, `7f26cab`).
- Versioned OOS acceptance policy (F-001, `165033f`) with candidate-level evidence
  (F-006/CR-003, `4f14786`); no invented numeric acceptance thresholds.
- **Partial / caveat**: CR-004 (statistical dependence), CR-005 (PBO candidate
  subset), CR-006 (PSR/FDR interpretation) are closed by fixture validation only; an
  independent statistical-method review is still warranted (audit §10.4).

## 14. Dashboard functionality

**Implemented and tested (loopback-only, F-008 guard active):**

- Research overview: experiments, datasets, classification reports.
- Experiment comparisons: `GET /api/experiments/compare?ids=…` with comparable records
  and explicit nulls for never-stored fields (F-030).
- Evolution monitor: population/generation state aggregated from stored candidates,
  works after workers exit (F-031).
- Telemetry: job resource snapshots (RSS, CPU, threads, elapsed) recorded as job
  events and returned by `GET /api/jobs/{id}` (F-032).
- Artefact export: `GET /api/experiments/{id}/export` full JSON bundle (F-033),
  with job-results fallbacks for compare verdicts and jobs in the export bundle
  (`396c68d`).
- Remote access: **not implemented** (F-034 open; API guarded to loopback by F-008).

## 15. Test results

**Tested at HEAD `ceb9e02` (this host, 2026-11-16):**

- Platform slice (the wave gate): `PYTHONPATH=src:. .venv/bin/python -m pytest
  tests/unit -k "research_platform" -q` → **598 passed, 3 skipped** in 106.59s.
  The 3 skips are sandbox tests that only run their privileged-tier record
  trails as root (`tests/unit/test_research_platform_sandbox.py:128,363,397`).
- Full repository suite (from `tem/verification-log.md`, at `f936b29`): first run
  `12 failed, 2564 passed, 11 skipped, 2 errors (242s)` — all failures classified:
  8 = missing `data/nse` panel in the worktree (fixed by symlinking the gitignored
  dataset), 1 = undeclared transitive `cmaes` dependency (installed and declared in
  `426477f`), 2 = known order-dependent legacy flakes in `test_utils_logging.py`
  (pass solo). Second run after fixes: exit 0, green, same 2 order-dependent legacy
  flakes in one run's tail.
- Platform slice earlier in the buildout: 562 passed / 3 skipped (see
  `tem/verification-log.md`); grew to 598 with the F-025..F-027 test additions.

## 16. Known bugs

No open platform (v2) bugs are known at HEAD. Known issues, all outside the platform
slice or resolved:

- **Legacy order-dependent test pollution** (pre-existing, not platform): two
  `test_utils_logging.py` tests fail in some full-suite orderings and pass solo
  (`tem/verification-log.md` run 2). Not fixed in this buildout; not platform code.
- **Environment quirks fixed during the buildout**: missing `data` symlink in the
  worktree (operator fix, documented); undeclared `cmaes` transitive dependency
  (fixed in `426477f`).
- **Fixed during review waves** (closed, listed for the record): sandbox
  snapshot/restore gap (`009740b`), funding-rate schema mismatch (`a323fef`),
  month-end denominator + loader-path depth + boundary carry (`5d884dd`),
  half-open acquisition coverage + non-contractual funding endpoint (`8cb23a4`),
  lag warm-up / skip shapes / cap rejection / log replay in neuro+gp (`c2d3cc1`),
  environment_recorded ordering (`2af6886`).

## 17. Known limitations

- **Runner-side checkpoint wiring is Partial** (F-026 follow-up): the job manager
  passes the verified checkpoint to runners as `resumed_state`
  (`research/platform/jobs.py:408`) and resume tests exercise it with test runners
  (`tests/unit/test_research_platform_jobs_resume.py`), but the shipped production
  runners do not yet consume `resumed_state` (no `restore_checkpoint` /
  `resumed_state` usage in `research/platform/runners.py` beyond lease wiring from
  `4cece6f`). Production jobs get startup recovery + `recover_interrupted_jobs`, but
  a crashed production runner restarts from scratch rather than resuming mid-run
  until its runner opts in.
- **Data licence review outstanding**: no provider terms approved, no redistribution
  rights validated, no licence-cleared real dataset onboarded (audit §10.1; F-004
  gate and `licensing.py` exist and are tested, but the business decision is open).
- **Statistical-method review is fixture-validated only**: CR-004/CR-005/CR-006 lack
  independent human review (audit §10.4).
- **Availability catalogue is fixture-populated**: production code validates
  experiments against a `DataAvailabilityCatalog` (`experiments.py:143`), but no
  production registration path populates it from live manifests — registered entries
  exist only in tests (`test_research_platform.py:249`).
- **Execution realism** remains an OHLCV approximation (§12), pending F-015 data.
- **Single-process default**: leased distributed execution is opt-in
  (`RESEARCH_WORKER_LEASE`, `4cece6f`); default deployments use one worker.
- **No live trading**: no brokerage connection or order placement in the v2 platform.
- **CHANGELOG Unreleased section is stale** relative to the latest waves (its refresh
  note predates acquisition/checkpoint/lease work); the architecture doc is current.

## 18. Incomplete requirements

Explicit list (labels per §24):

- **Blocked by hardware**: F-028 GPU portfolio simulation with CPU/GPU result parity
  within approved tolerances; F-029 reproducible target-GPU benchmark; the CPU/GPU
  parity tests built on the compute scaffold. Awaiting the user's GPU-equipped PC
  (§9). All CPU-side scaffolding (fallback, device detection, strict-mode semantics,
  unit tests) is implemented and tested.
- **Partial**: runner-side consumption of `resumed_state` checkpoints in shipped
  production runners (§17, first bullet) — the F-026 protocol, storage, integrity
  digest, spec-anchored validation and resume machinery are Implemented and Tested;
  production-runner opt-in is not.
- **Blocked by external dependency / decision**: F-015 execution calibration (the
  single open P1 item — fee schedules and cost models are implemented, but its
  completion condition requires a measured reference from order-book/tick data,
  which is unavailable, §8); licence-cleared real dataset onboarding (F-004's
  completion condition requires provider terms approval).
- **Designed but not implemented**: F-034 secure remote access (loopback guard from
  F-008 is implemented and tested; remote authentication/transport is not started).
- **Not started (P3 backlog)**: F-035 wider benchmark suites, F-036 more execution
  models, F-037 richer experiment reports (negative/inconclusive findings), F-038
  provider/data-quality dashboards, F-039 performance budgets, F-040 reproducible
  environment images.
- **Four-track market validation caveat**: the four-track end-to-end validation
  (F-024) is Implemented and Tested on local data; no performance claim is made
  against licence-cleared complete market data (audit §10.6).

Backlog tally at HEAD: **30 of F-001..F-040 closed** (P0: 8/8; P1: 15/16 — F-015
open, data-blocked; P2: 7/10 — F-028/F-029/F-034 open; P3: 0/6). Grounded in the
commit map in §2; the audit doc is the frozen record, this report the living status.

## 19. Next implementation priorities

1. **GPU work on the user's GPU PC**: install CuPy, run F-029 benchmark report,
   implement and pass CPU/GPU portfolio-simulation parity within approved tolerances
   (F-028), close the parity-test scaffold. Everything needed CPU-side is in place.
2. **Licence decision + real dataset onboarding**: approve a provider, record terms,
   onboard the first licence-cleared dataset through the existing gate; populate the
   production `DataAvailabilityCatalog` (fixes the fixture-only limitation).
3. **Runner-side checkpoint consumption**: make shipped production runners accept
   `resumed_state`, then re-run the resume tests against the real runner path.
4. **Independent statistical review** of CR-004/CR-005/CR-006 methods beyond
   fixtures (audit §10.4).
5. **F-015 execution calibration** when order-book/tick data becomes obtainable.
6. **F-034 secure remote access** if remote access is actually required.
7. **P3 backlog** (F-035..F-040) in audit order.

---

Cross-references: fix backlog and per-item completion conditions —
`docs/ASD_STE100_IMPLEMENTATION_COMPLETION_AUDIT.md` §9; suite classifications —
`tem/verification-log.md`; architecture detail — `docs/RESEARCH_PLATFORM_ARCHITECTURE.md`.
