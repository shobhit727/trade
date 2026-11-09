# Research Platform Completion and Review Audit

**Document ID:** RPA-AUDIT-2026-11-10  
**Document status:** Audit report  
**Audit date:** 10 November 2026  
**Repository:** shobhit727/trade  
**Audited branch:** feature/hybrid-evolution-research  
**Audited source commit:** 619a56a18ddd4511b05582bd52d8a0ad102197c6  
**Base branch:** main  
**Branch comparison at audit time:** 341 commits ahead; 0 commits behind  
**Main implementation package:** research/platform/  
**Related specification:** GOAL.md, v2 research-platform specification  
**Related architecture record:** docs/RESEARCH_PLATFORM_ARCHITECTURE.md

---

## 1. Purpose

This document records the current implementation status of the v2 research platform.

It records four groups of work:

1. Work that is implemented.
2. Work that is not complete.
3. Work that requires a code, design, data, or method review.
4. Work that this audit could not complete.

The report also records the tests that have passed. It records the limits of those tests.

This report does not claim that the platform can find profitable strategies. It does not claim that the platform is ready for real trading. It does not approve the use of real capital.

The v2 platform is for research, historical simulation, and paper portfolios. The v2 specification does not permit live order placement or access to brokerage or exchange accounts.

## 2. Writing and status rules

This report uses short sentences and controlled technical terms. It follows the style of ASD-STE100 Simplified Technical English.

This report is not a formal ASD-STE100 compliance certificate. A formal compliance check must use the current ASD-STE100 specification and its full writing rules.

The status terms have the meanings below.

| Status | Meaning |
|---|---|
| COMPLETE | The code or document exists in the audited branch. The stated scope is implemented. |
| TESTED | A test or CI job has passed for the stated scope. |
| PARTIAL | Some parts work. One or more required parts are missing. |
| REVIEW REQUIRED | The code exists, but its correctness or its assumptions need an independent review. |
| NOT IMPLEMENTED | The required code or service does not exist in the audited branch. |
| BLOCKED | Work needs data, hardware, a licence, a policy decision, or another external input. |
| NOT VERIFIED | The audit did not find enough evidence to make a reliable status claim. |
| NOT APPLICABLE | The item is outside the v2 platform scope. |

A passing unit test does not change a PARTIAL item to COMPLETE when the missing work is not covered by the test.

A code path that runs on synthetic data does not prove that it works on real market data.

A historical result does not prove that a strategy has an independent edge.

A candidate classification does not approve a trade.

## 3. Executive result

<summary>
The branch contains a large, additive v2 research platform. It has data adapters, experiment records, validation stages, search methods, evolutionary workers, portfolio simulation, statistical diagnostics, a local API, a dashboard, and persistent job records.

The focused research-platform CI passed for the latest code-bearing implementation commit listed in the repository documentation.

The platform is not complete. The final holdout remains locked. The v2 specification does not define an OOS acceptance gate. The platform therefore records unknown OOS acceptance results as inconclusive.

The normal worker path uses a checksum-verified non-holdout file. This reduces accidental access to protected rows. It does not create an operating-system security boundary. A process with access to the full file system can still read other files.

The data layer imports local NSE and crypto files. It does not acquire market data. The imported data still needs licence review. The data set does not represent a complete point-in-time historical universe.

The simulator is a long-only INR cash simulator. It does not model all tax, corporate-action, derivative, funding, borrow, margin, liquidation, and order-book rules.

The evolutionary workers are separate workers. They do not share one mixed population. GP uses a numeric grammar. Neuroevolution does not evolve network topology. Strategy composition uses a fixed component registry.

The statistical diagnostics need an independent method review. The GPU path needs tests on the target GPU. The whole system needs tests with licence-cleared data.

**Current decision: the platform is suitable for continued engineering and controlled research development. It is not ready for a claim of validated strategy performance or secure final-holdout confirmation.**
</summary>

## 4. Audit basis and limits

### 4.1 Source examined

The audit used the GitHub branch listed in the document header.

The audit reviewed the following source and test areas:

- GOAL.md.
- AGENTS.md.
- docs/RESEARCH_PLATFORM_ARCHITECTURE.md.
- docs/RUNBOOK.md.
- research/platform/README.md.
- research/platform/adapters.py.
- research/platform/api.py.
- research/platform/app.py.
- research/platform/classification.py.
- research/platform/composition.py.
- research/platform/composition_policy.py.
- research/platform/compute.py.
- research/platform/costs.py.
- research/platform/data_catalog.py.
- research/platform/domain.py.
- research/platform/evaluation.py.
- research/platform/experiments.py.
- research/platform/features.py.
- research/platform/fx.py.
- research/platform/genetic_programming.py.
- research/platform/jobs.py.
- research/platform/market.py.
- research/platform/metrics.py.
- research/platform/model_evaluation.py.
- research/platform/neuroevolution.py.
- research/platform/optimizers.py.
- research/platform/pareto.py.
- research/platform/portfolio.py.
- research/platform/runners.py.
- research/platform/statistics.py.
- research/platform/storage.py.
- research/platform/strategy_catalog.py.
- research/platform/strategy_signals.py.
- research/platform/validation.py.
- tests/unit/test_research_platform*.py.
- .github/workflows/research-platform.yml.
- PROJECT_MEMORY/12_Feature_Status.md.
- PROJECT_MEMORY/13_Bug_Tracker.md.

The audit used the repository documentation as a source for the last successful CI result. It also reviewed the workflow definition.

### 4.2 Work not performed during this audit

This audit did not run a new local test suite.

This audit did not run a full-market backtest.

This audit did not download or ingest new market data.

This audit did not verify any external data licence.

This audit did not run the optional CuPy path on the target NVIDIA GPU.

This audit did not run a hardware benchmark.

This audit did not perform a formal independent statistical review.

This audit did not inspect a user's uncommitted local files. It describes the GitHub branch only.

This audit did not merge the feature branch into main.

### 4.3 Important scope separation

The repository contains older trading systems and the new v2 research platform.

The v2 package is additive. It does not replace or silently change the existing systems.

The main legacy areas include:

- src/nsealgo/
- src/cryptobot/
- crates/
- research/optimize/
- the older backtest and execution modules.

A v2 test result does not prove that every legacy module is correct.

The legacy bug tracker contains findings from an audit dated 22 August 2026. The current v2 status document says that the legacy module table has not been re-audited by the v2 work.

This report therefore treats those legacy findings as historical risks that require a fresh status check. It does not claim that every listed issue is still present.

## 5. Repository and branch state

### 5.1 Branch state

At the start of this audit, the branch head was:

619a56a18ddd4511b05582bd52d8a0ad102197c6

The branch comparison reported:

| Item | Result |
|---|---:|
| Commits ahead of main | 341 |
| Commits behind main | 0 |
| Comparison status | ahead |
| Merge status | Not merged by this audit |

The branch includes the v2 platform implementation and its supporting documentation.

The branch is not the main branch. A user or maintainer must review the branch before a merge.

### 5.2 Important implementation commits

The repository documentation identifies these implementation milestones:

| Commit | Work |
|---|---|
| e039dbb7f102d2919817b0bc6e6b2e3f3c051a3f | Persistent per-job holdout lifecycle. |
| 0c34610e3141ed1fe59b5c53a8ee359a4d6b1c45 | Correct OOS lifecycle boundary and concurrent OOS authorisation test. |
| 7ea38112df28fb91d29c00e5206685281e7fd4c1 | Evidence-based candidate classifications and the tested code snapshot. |
| 619a56a18ddd4511b05582bd52d8a0ad102197c6 | Documentation updates for the verified platform state. |

The commit list is a record of implementation milestones. It is not a complete file-by-file attribution of every change in the branch.

### 5.3 Current branch documentation

The following documentation was updated before this audit:

- README.md.
- GOAL.md.
- CHANGELOG.md.
- PROJECT_MEMORY/12_Feature_Status.md.
- docs/RESEARCH_PLATFORM_ARCHITECTURE.md.
- docs/RUNBOOK.md.
- research/platform/README.md.

The documentation separates the v2 research platform from the older runtime.

## 6. Work completed

This section records the code and documentation that exist in the audited branch.

### 6.1 A separate v2 research platform

**Status: COMPLETE for the current foundation.**

The new package is research/platform/.

The package is separate from the legacy strategy and execution modules.

The platform uses explicit market and research-track types.

The platform supports four research tracks:

1. NSE individual securities.
2. NSE multi-security portfolios.
3. Crypto individual assets.
4. Crypto multi-asset portfolios.

The platform records the market for each experiment and data set.

The platform keeps NSE and crypto financial state separate.

The platform does not provide a combined financial portfolio.

The v2 runtime does not place live orders.

The v2 runtime does not connect to brokerage or exchange accounts.

### 6.2 Separate simulated capital and account state

**Status: COMPLETE for long-only cash ledgers.**

The platform defines a separate simulated starting budget of ₹21,00,000 for NSE.

The platform defines a separate simulated starting budget of ₹21,00,000 for crypto.

The market ledger enforces market separation.

The ledger checks for:

- Duplicate fills.
- Invalid or excessive sells.
- Cash balance errors.
- Cross-market position use.
- Invalid position state.

The ledger uses INR cash accounting.

The platform does not combine market capital, positions, returns, taxes, or risk.

**Limit:** The ledger does not model crypto derivatives, margin, liquidation, or short positions.

### 6.3 Domain and experiment records

**Status: COMPLETE for the current experiment schema.**

The platform defines market, track, data, cost, execution, and objective records.

An experiment specification can record:

- Experiment ID.
- Market.
- Research track.
- Dataset IDs.
- Random seed.
- Git commit.
- Code version.
- Research window.
- Train window.
- Validation window.
- OOS window.
- Embargo.
- Resolution.
- Objective definition.
- Cost model ID.
- Execution model ID.
- Compute backend.
- Instrument and market scope.

The data catalogue checks that a dataset belongs to the requested market.

The data catalogue checks that the dataset covers the declared experiment windows.

The platform rejects missing or cross-market dataset references.

**Limit:** The schema does not guarantee that every environment detail is recorded. A complete run record still needs dirty-tree state, dependency lock state, hardware detail, resource use, and all feature transformation versions.

### 6.4 Data manifests and local adapters

**Status: PARTIAL.**

The platform has immutable dataset manifests.

The manifest records source information and a source-file hash.

The platform has an NSE adapter.

The platform has an exchange-scoped crypto CSV and Parquet adapter.

The adapters do not download data.

The local crypto adapter records licence status as REVIEW_REQUIRED.

The adapters require declared timestamp units and candle timestamp positions.

The adapters check required OHLCV columns.

The adapters check for missing and non-finite data.

The adapters check that prices are positive.

The adapters check that volume is not negative.

The adapters check that open values are within the low-to-high range.

The adapters check that high and low values are consistent.

The NSE daily import uses a strict absolute close-return threshold below 20 percent. Crypto does not use this NSE-specific rule.

The platform records quality information as canonical JSON in manifest metadata.

**Limit:** These checks do not form a complete data-quality score. They do not prove complete market coverage. They do not detect every gap, delisting, symbol change, corporate action, or point-in-time universe error.

### 6.5 Physical non-holdout partition materialisation

**Status: PARTIAL.**

The trusted ingestion path can create a physical non-holdout file.

The file ends before the declared final-holdout boundary.

The new manifest records the materialised partition.

The normal production worker path loads the materialised file.

The reader verifies the file hash.

The reader checks that the loaded rows end before the protected boundary.

The production default requires partitioned data.

The environment variable RESEARCH_PARTITION_DATA_ROOT selects the partition store.

The default RESEARCH_REQUIRE_PARTITIONED_DATA policy is strict.

The explicit value 0 enables a compatibility path. That path can parse a combined source file before it clips rows. It must not be used for protected-holdout research.

**Limit:** A local process can still access other files on the same filesystem. The partition copy does not create OS-level access control. The current design is not a secure holdout service.

### 6.6 Time alignment and FX conversion

**Status: COMPLETE for the implemented rules. REVIEW REQUIRED for data coverage.**

The platform has an FX rate series.

The converter uses backward-only time alignment.

The converter rejects future rates.

The converter rejects stale rates.

The converter uses an explicit maximum staleness rule.

The platform records the FX source.

The adapter accounts for candle timestamp positions.

An open-stamped FX candle becomes available only after its interval closes.

Fixed intervals use explicit durations.

Monthly candles use the next calendar-month boundary.

**Limit:** The converter does not provide the FX dataset. The operator must register a valid and approved FX dataset.

### 6.7 Causal price and volume features

**Status: PARTIAL.**

The platform has a trailing price and volume feature engine.

The feature engine uses information available at the feature timestamp.

The platform stores forward labels separately.

The feature engine does not use negative shifts to create features.

The worker path separates feature data from future labels.

**Limit:** The platform does not yet integrate point-in-time fundamentals, news, macroeconomic data, sentiment, or crypto on-chain data.

The platform does not yet prove that every production feature has a correct publication-time join.

### 6.8 Chronological validation and embargo rules

**Status: PARTIAL.**

The platform has chronological experiment windows.

The platform checks the declared embargo between adjacent windows.

The platform has a purged walk-forward split helper.

The helper uses sample label start and end times.

The helper removes training samples that overlap the validation period and the embargo.

The helper is an index splitter.

The caller must still supply correct point-in-time data.

**Limit:** Not every optimiser or trainer calls this helper. Each worker and trainer needs an integration review. The presence of a helper does not prove that every training path uses it.

### 6.9 Candidate and experiment persistence

**Status: COMPLETE for append-only records and lifecycle events. PARTIAL for process recovery.**

The platform uses SQLite.

The store persists experiments.

The store persists candidates.

The store persists candidate lineage.

The store persists job status.

The store persists job events.

The store records validation lifecycle events.

The event history is append-only.

The store reconstructs lifecycle state from events.

The store uses a write lock for state transitions.

The current lifecycle includes:

- Candidate freeze.
- OOS start.
- OOS completion.
- Final-holdout approval.
- Final-holdout access.

The system prevents a candidate from changing after it is frozen.

The OOS path checks the frozen candidate digest.

The system records one-time holdout access state.

The store rejects a repeated holdout access transition.

The repository tests include restart recovery and concurrent OOS authorisation cases.

**Limit:** The event history survives restart. The running calculation does not resume after process death. The job must be submitted again.

**Limit:** Persistent lifecycle state does not provide file-system isolation.

### 6.10 Existing strategy discovery and signal adapter

**Status: PARTIAL.**

The platform has an existing strategy registry.

The platform can discover registered strategies and their searchable parameters.

The platform has a signal adapter.

The adapter feeds bars to strategies in time order.

The adapter does not give a strategy future bars.

The adapter converts strategy output into long or flat signals.

The platform can use supported existing strategies in research workers.

**Limit:** The adapter supports long and flat signals. It does not establish that every existing catalogue strategy is compatible.

The adapter does not fully support every legacy order, short, position, or execution semantic.

A strategy compatibility matrix is still required.

### 6.11 Conventional search methods

**Status: COMPLETE for the implemented methods. REVIEW REQUIRED for method comparisons.**

The platform includes:

- Random search.
- Capped grid search.
- Differential evolution.
- Seeded Optuna TPE.
- A separate Parzen-style heuristic search.
- A multi-method hybrid ensemble.

The hybrid ensemble gives each method an equal declared candidate budget.

The methods use deterministic seeds.

The workers retain successful candidate records.

The workers retain failed trial records.

The platform records candidate ancestry and search metadata.

The validation stage selects from the final eligible candidate set.

The selected candidate is frozen before OOS evaluation.

**Limit:** The separate Parzen-style method is a heuristic baseline. It must not be described as canonical Optuna TPE.

**Limit:** The hybrid ensemble combines conventional search methods. It does not yet combine all evolutionary genome types into one population.

### 6.12 Genetic programming

**Status: PARTIAL.**

The platform has a bounded numerical genetic programming engine.

The GP engine uses a closed abstract syntax tree interpreter.

The engine does not execute generated Python.

The engine has bounded expressions.

The engine has population and generation controls.

The engine stores candidate identifiers.

The engine records parent and child lineage.

The worker evaluates candidates on TRAIN.

The worker uses VALIDATION to select from the final TRAIN population.

The worker evaluates the frozen selection on OOS.

The worker stores candidate and lineage records.

**Limit:** The grammar is numeric only.

**Limit:** The grammar does not yet include a full Boolean and control-flow system.

**Limit:** The engine does not yet share a population with the neural, composition, and existing-strategy genomes.

### 6.13 Neuroevolution

**Status: PARTIAL.**

The platform has a dense neural network policy.

The current network has one hidden layer.

The worker uses mirrored-noise evolution strategies.

The worker evolves network parameter vectors.

The worker stores candidate ancestry.

The worker has bounded candidate batches.

The inference path can use NumPy.

The inference path can use optional CuPy.

The automatic backend can fall back to NumPy after a runtime CUDA error.

The explicit CuPy backend does not silently change to NumPy after an error.

The neural path has scalar and batch parity tests.

The worker uses TRAIN for evolution.

The worker uses VALIDATION for selection.

The worker evaluates a frozen selected candidate on OOS.

**Limit:** The worker does not evolve network topology.

**Limit:** Portfolio fitness uses the CPU portfolio simulator.

**Limit:** The CuPy path has not been verified on the target NVIDIA GPU.

### 6.14 Strategy composition

**Status: PARTIAL.**

The platform has a declarative composition genome.

The platform uses a closed component registry.

The genome can contain known component roles, including:

- Entry.
- Exit.
- Filter.
- Sizing.
- Risk.
- Regime.
- Allocation.

The registry does not allow an evolved genome to create arbitrary callable code.

The current component set includes simple momentum and trend rules.

The component set includes volatility and volume filters.

The component set includes regime and risk gates.

The worker stores candidate IDs and lineage.

The worker evolves on TRAIN.

The worker selects on VALIDATION.

The worker evaluates a frozen selection on OOS.

**Limit:** The component registry does not yet adapt every production strategy module.

**Limit:** It does not implement every intended portfolio, execution, sizing, and regime component.

**Limit:** It does not share one mixed population with GP and neural genomes.

### 6.15 Multi-objective search

**Status: PARTIAL.**

The platform has NSGA-II support.

The NSGA-II implementation supports objective vectors.

The implementation supports Pareto dominance.

The implementation supports non-dominated sorting.

The implementation supports crowding distance.

The implementation supports survivor selection.

The current research worker applies the method to existing-strategy parameter genomes.

The worker records candidate ancestry.

The worker records TRAIN Pareto information.

The worker uses VALIDATION for selection.

The worker evaluates the frozen candidate on OOS.

**Limit:** The current worker does not evolve a population that contains existing strategies, GP expressions, neural networks, and composition genomes together.

**Limit:** A final objective policy and its trade-offs still need review.

### 6.16 Portfolio simulation

**Status: PARTIAL.**

The platform has a long-only multi-asset cash simulator.

The simulator selects target weights from information available at close t.

The simulator attempts execution at open t+1.

The simulator uses the previous completed bar volume for participation and impact calculations.

The simulator applies adverse slippage.

The simulator applies square-root market impact.

The simulator uses market-specific fee calculators.

The simulator rejects invalid cash states.

The simulator enforces long-only exposure.

The simulator limits participation.

The simulator uses whole-share quantities for NSE.

The simulator uses integer affordability checks for NSE buys.

The simulator preserves fractional units for crypto spot.

The simulator checks that fees do not make account cash negative.

The simulator records fills and portfolio metrics.

**Limit:** The simulator is an OHLCV model. It does not replay order-book events.

**Limit:** It does not model queue priority, trade prints, auction rules, or measured execution latency.

**Limit:** It is not a margin, derivative, or short-selling simulator.

### 6.17 Market cost calculators

**Status: PARTIAL.**

The NSE fee calculator delegates to the existing itemised delivery cost model in src/nsealgo/costs.py.

The crypto spot fee calculator uses a configured venue maker and taker basis-point schedule.

The current crypto market-order path uses taker fees.

The simulator records fee charges.

**Limit:** The configured NSE fee schedule is applied uniformly.

**Limit:** Historical statutory changes, broker-specific rates, venue tiers, and date-effective schedules are not fully represented.

**Limit:** The platform does not yet calibrate execution cost against tick and order-book data.

### 6.18 Statistical diagnostics

**Status: COMPLETE for diagnostic plumbing. REVIEW REQUIRED for statistical validity.**

The platform includes:

- Probabilistic Sharpe Ratio-derived p-values.
- Benjamini-Hochberg false discovery rate adjustment.
- Deflated Sharpe Ratio.
- Combinatorially symmetric cross-validation.
- Probability of backtest overfitting.
- Moving-block bootstrap helpers.
- Label-interval purging helpers.

The workers attach TRAIN-only family diagnostics.

The diagnostics include the successful candidate family.

The FDR and DSR calculations use the full successful candidate family.

The CSCV/PBO calculation uses a deterministic, evenly spaced subset. The subset has a maximum size of 128 candidates.

The diagnostics are stored with the research result.

The diagnostics do not change candidate selection.

**Limit:** The DSR implementation uses an independent Gaussian trial-Sharpe approximation.

**Limit:** Evolutionary candidates are correlated. The independence assumption may be weak.

**Limit:** PBO uses a bounded subset. The selected subset may not represent every candidate relationship.

**Limit:** PSR-derived p-values use a zero per-period Sharpe benchmark.

**Limit:** The diagnostics do not correct survivorship bias, publication-time leakage, bad data, bad costs, or unrealistic execution.

### 6.19 Candidate classification

**Status: COMPLETE for the evidence classifier. PARTIAL for its protocol and integration.**

The classifier supports these labels:

- Failed.
- Inconclusive.
- Overfit.
- Training only.
- Validation success.
- Historical OOS success.
- Robust research candidate.
- Requires independent confirmation.

The classifier uses explicit evidence fields.

Unknown evidence is not treated as positive evidence.

Explicit failure and detected overfit take priority.

An OOS result with an unknown acceptance result remains inconclusive.

A historical or exposed OOS success is not independent confirmation.

A robust research candidate requires explicit evidence for OOS success, independent confirmation, data integrity, robustness, and diagnostics.

The classifier does not invent numeric performance thresholds.

**Limit:** The v2 specification does not yet define numeric OOS acceptance criteria.

**Limit:** The result integration needs a per-candidate review. Some worker outputs report aggregate classification data. Candidate storage and candidate-level evidence must be checked to make sure every candidate has its own correct evidence record.

### 6.20 API and dashboard

**Status: PARTIAL.**

The platform has a local WSGI API.

The platform has a dashboard.

The API uses the experiment and job store.

The dashboard can create and inspect experiment records.

The dashboard can show registered data.

The dashboard can queue allow-listed worker types.

The supported worker groups include:

- Existing strategy evaluation.
- Parameter search.
- Hybrid search.
- GP.
- Neuroevolution.
- Strategy composition.
- Pareto search.

The dashboard can inspect jobs.

The dashboard can request cooperative cancellation.

The API binds to loopback by default.

The application rejects a non-loopback bind unless the operator supplies the remote-enable option.

**Limit:** The API does not have a completed remote authentication system.

**Limit:** Do not expose the API to a network until authentication and transport security are implemented and tested.

**Limit:** The dashboard does not yet provide complete experiment comparison, full population monitoring, GPU telemetry, or full job artefact views.

### 6.21 Job lifecycle

**Status: PARTIAL.**

The job manager uses a bounded local thread pool.

The job manager accepts registered runner names.

A client cannot select an arbitrary Python callable.

The job manager stores job status.

The job manager stores events and results.

The job manager supports cooperative cancellation.

The lifecycle event history survives a process restart.

**Limit:** Worker calculations do not resume after process death.

The manager marks an interrupted job as failed.

The operator must submit the job again.

**Limit:** There is no distributed worker cluster.

### 6.22 Compute backend

**Status: PARTIAL.**

The platform has a NumPy backend.

The platform can probe optional CuPy and CUDA support.

The platform has batched linear, long/flat, and dense-neural inference paths.

The platform has runtime backend information.

The platform has CPU fallback behaviour.

The platform has scalar and batch parity tests for supported neural inference.

**Limit:** The target GPU has not been benchmarked.

**Limit:** The portfolio simulator and portfolio fitness calculations remain CPU-based.

**Limit:** No end-to-end GPU speedup claim is supported.

### 6.23 Verification and CI

**Status: TESTED for the focused v2 test suite.**

The dedicated workflow is .github/workflows/research-platform.yml.

The workflow uses Python 3.13.

The workflow installs test and research requirements.

The workflow compiles research/platform.

The workflow runs the focused research-platform test files.

The test command is:

python -m pytest tests/unit/test_research_platform*.py -q --tb=short --maxfail=1

The documented code-bearing commit 7ea38112df28fb91d29c00e5206685281e7fd4c1 passed the workflow on 10 November 2026.

The later commit 619a56a18ddd4511b05582bd52d8a0ad102197c6 changed documentation. It did not change the tested implementation.

**Limit:** This workflow does not prove that the full repository test suite passes.

**Limit:** It does not prove that the whole legacy runtime is correct.

**Limit:** It does not prove that the market data is valid.

**Limit:** It does not prove a profitable strategy.

**Limit:** It does not prove the target GPU works.

### 6.24 Documentation completed

**Status: COMPLETE for the current documentation update.**

The branch contains the following documentation updates:

| File | Completed work |
|---|---|
| README.md | Adds the v2 research platform overview, setup, test, and launch information. |
| GOAL.md | Adds the v2 target specification and a dated implementation snapshot. It preserves the older v1 material. |
| CHANGELOG.md | Records the v2 platform capabilities and limits. |
| PROJECT_MEMORY/12_Feature_Status.md | Adds a v2 status table and preserves the historical legacy audit. |
| docs/RESEARCH_PLATFORM_ARCHITECTURE.md | Records architecture, implementation status, validation limits, and remaining priorities. |
| docs/RUNBOOK.md | Adds the v2 quick start and identifies the legacy runbook scope. |
| research/platform/README.md | Records the package scope, usage, test commands, and explicit limits. |

This audit file adds a detailed completion and review register.

## 7. Work not complete

This section lists the incomplete work by subsystem.

### 7.1 Final OOS acceptance policy

**Priority: P0 — BLOCKING.**  
**Status: NOT IMPLEMENTED.**

The platform does not have an approved numeric OOS acceptance policy.

The code can evaluate a selected candidate on OOS.

The code can record the OOS result.

The code does not have a protocol-approved rule that defines when OOS passes.

The current workers therefore record the acceptance result as unknown.

The classifier treats unknown OOS evidence as inconclusive.

The final holdout remains locked.

Required work:

1. Define the OOS performance metrics.
2. Define minimum trade and observation counts.
3. Define maximum drawdown limits.
4. Define cost and liquidity limits.
5. Define robustness tests.
6. Define risk and stability requirements.
7. Define a rule for failed or missing data.
8. Define the rule for all four research tracks.
9. Version the policy.
10. Approve the policy before the workers use it.

The policy must not be selected after the team sees the OOS result.

The policy must be fixed before OOS evaluation.

The policy must not use a return target to hide a failed risk test.

### 7.2 Secure final-holdout isolation

**Priority: P0 — BLOCKING.**  
**Status: PARTIAL.**

The system creates a safe non-holdout copy.

The worker uses the safe copy by default.

The manifest stores a checksum.

The reader verifies the checksum.

This is not enough for a strong security claim.

A process may still read other files when file permissions allow it.

Required work:

1. Create a separate holdout service or isolated worker.
2. Store protected data outside the normal worker file system.
3. Give normal workers no file permission for protected data.
4. Give the holdout service a narrow input interface.
5. Send only a frozen candidate to the holdout service.
6. Reject any candidate that changes after the freeze.
7. Record every holdout request.
8. Record every holdout response.
9. Limit access to one approved evaluation.
10. Test access denial from normal workers.
11. Test process and user boundaries.
12. Test restart and concurrency behaviour.
13. Test that a worker cannot copy protected rows into its own artefacts.
14. Document the threat model.

The environment variable RESEARCH_REQUIRE_PARTITIONED_DATA=0 must not be used in protected-holdout research.

### 7.3 Point-in-time market data

**Priority: P0 — BLOCKING for credible market research.**  
**Status: NOT COMPLETE.**

The platform imports local files.

It does not acquire full market data.

The current data layer does not provide a complete point-in-time historical universe.

NSE data needs:

- Historical index constituents.
- Historical symbol changes.
- Delisted securities.
- Corporate actions.
- Dividends.
- Historical sector classifications.
- Historical listing and suspension states.
- Full missing-bar reports.
- Correct adjustment policies.

Crypto data needs:

- Historical instrument listings and delistings.
- Exchange-specific symbol history.
- Venue outages.
- Historical exchange rules.
- Historical fees.
- Historical liquidity.
- Funding history.
- Open interest.
- Liquidations.
- Derivative contract rules.
- On-chain history where required.

Every data source needs a valid licence.

Every data source needs a clear acquisition record.

Every data source needs an immutable manifest.

The platform must not claim complete coverage when it has partial data.

### 7.4 Automated data acquisition

**Priority: P1.**  
**Status: NOT IMPLEMENTED.**

The current adapters read local CSV and Parquet files.

They do not download data.

Required work:

1. Define approved providers.
2. Review their licences.
3. Add provider clients.
4. Add rate-limit handling.
5. Add retry and backoff rules.
6. Add data versioning.
7. Add incremental updates.
8. Add checksum validation.
9. Add gap reports.
10. Add acquisition logs.
11. Add failure recovery.
12. Add a provider availability matrix.

Do not add a provider before licence review.

### 7.5 Fundamental, news, macro, and on-chain features

**Priority: P1.**  
**Status: NOT IMPLEMENTED in the current v2 feature layer.**

The current feature engine uses trailing price and volume inputs.

The platform does not yet provide complete publication-time features for:

- Financial statements.
- Earnings data.
- Company announcements.
- News.
- Sentiment.
- Economic series.
- Interest rates.
- Inflation.
- FX macro series.
- Crypto network data.
- Token supply events.
- Token unlocks.
- Exchange funding and open interest.

Required work:

1. Record when each item became public.
2. Record the source publication time.
3. Record the time that the platform ingested the item.
4. Preserve later revisions.
5. Join only information that was available at the decision time.
6. Record transformations and missing values.
7. Test for future-data access.
8. Run feature ablation tests.

### 7.6 Unified mixed-genome evolution

**Priority: P1.**  
**Status: NOT IMPLEMENTED.**

The current workers are separate.

The platform does not have one population that contains all required genome types.

The intended population must support:

- Existing strategy parameter genomes.
- GP expression genomes.
- Neural network genomes.
- Strategy composition genomes.
- Hybrid or ensemble genomes where defined.

Required work:

1. Define a common candidate interface.
2. Define a common immutable genome record.
3. Define genome validation rules.
4. Define a common fitness contract.
5. Define a common lineage contract.
6. Define a shared candidate budget.
7. Define equal-cost comparisons.
8. Define cross-family mutation rules.
9. Define cross-family crossover rules where valid.
10. Define selection across genome types.
11. Define population diversity measures.
12. Define archive and duplicate rules.
13. Define stopping rules.
14. Define CPU, RAM, and VRAM limits.
15. Add reproducible mixed-population tests.

Do not add a cross-family operator when the two genome types do not have a valid common representation.

### 7.7 Full genetic programming grammar

**Priority: P1.**  
**Status: PARTIAL.**

The current grammar is numeric.

The target needs bounded Boolean and control-flow logic.

Required work:

- Typed Boolean expressions.
- Numeric comparisons.
- Logical operators.
- Conditional expressions.
- Entry and exit control.
- Risk gates.
- Regime conditions.
- Complexity limits.
- Type validation.
- Safe evaluation.
- Mutation and crossover tests.
- Behaviour tests for invalid or missing values.

The engine must continue to reject arbitrary generated Python.

### 7.8 Neural topology evolution

**Priority: P1.**  
**Status: NOT IMPLEMENTED.**

The current neural worker evolves parameters for a fixed one-hidden-layer dense network.

The target also calls for topology evolution.

Required work:

1. Define a bounded architecture representation.
2. Define permitted layer types.
3. Define maximum layer count.
4. Define maximum hidden width.
5. Define parameter and memory limits.
6. Define topology mutation.
7. Define compatible crossover.
8. Define network validation.
9. Define deterministic initialisation.
10. Compare fixed and evolved topologies under equal budgets.
11. Test numerical stability.
12. Test CPU and GPU parity.

### 7.9 Complete strategy composition

**Priority: P1.**  
**Status: PARTIAL.**

The current registry contains a limited set of numerical components.

The target includes entry, exit, filter, regime, sizing, risk, allocation, rebalancing, and execution behaviour.

Required work:

- Review every current registry component.
- Define parameter ranges.
- Define component compatibility.
- Add missing components.
- Add adapters for compatible production strategies.
- Test each component alone.
- Test component order.
- Test duplicate and conflicting components.
- Test missing data.
- Test risk and sizing limits.
- Record exact composition genomes.
- Add mixed-genome evaluation.

### 7.10 Full existing strategy compatibility

**Priority: P1.**  
**Status: PARTIAL.**

The current signal adapter uses long and flat signals.

The legacy strategy catalogue has other position and execution behaviour.

Required work:

1. List every registered strategy.
2. Record its input requirements.
3. Record its parameter space.
4. Record whether it supports streaming input.
5. Record its position model.
6. Record whether it uses short signals.
7. Record its warm-up period.
8. Record its execution assumptions.
9. Test its signal output against its original runtime.
10. Test each compatible strategy in the research simulator.
11. Record unsupported strategies.
12. Do not silently map a short signal to a flat signal.

### 7.11 Portfolio accounting

**Priority: P1 — BLOCKING for the products that need these rules.**  
**Status: PARTIAL.**

The simulator is long-only INR cash.

Required NSE accounting:

- Tax lots.
- Capital gains.
- Dividends.
- Corporate actions.
- Splits.
- Consolidations.
- Rights issues.
- Delisting settlement.
- Historical instrument changes.
- Date-effective tax rules where applicable.

Required crypto accounting:

- Funding payments.
- Borrow costs.
- Margin.
- Collateral.
- Liquidation.
- Contract specifications.
- Perpetual swap accounting.
- Dated futures.
- Settlement.
- Exchange-specific rules.
- Fees and rebates.

A separate ledger is required for each instrument type.

Do not use the spot cash ledger to represent derivatives.

### 7.12 Execution realism

**Priority: P1.**  
**Status: PARTIAL.**

The current simulator uses OHLCV data.

The simulator uses next-open execution.

The simulator uses prior completed bar volume for participation and impact.

This model is more realistic than a same-close fill, but it is not a full execution simulator.

Required work:

1. Add tick data.
2. Add order-book snapshots or event data.
3. Model spread.
4. Model queue position where data supports it.
5. Model partial fills.
6. Model order rejection.
7. Model auction rules.
8. Model venue outages.
9. Model exchange limits.
10. Model measured latency.
11. Calibrate slippage.
12. Calibrate impact.
13. Compare simulated fills with known execution data.
14. Record model uncertainty.

### 7.13 Date-effective fee schedules

**Priority: P1.**  
**Status: PARTIAL.**

The current fee calculators do not cover every historical schedule change.

Required work:

- Add dated NSE statutory schedules.
- Add broker fee tiers.
- Add exchange fee tiers.
- Add maker and taker rules by venue and date.
- Add rebates where verified.
- Add tax and duty changes.
- Add instrument-specific rules.
- Add tests at each schedule boundary.
- Record the fee schedule version in every experiment.

### 7.14 Statistical method review

**Priority: P0/P1.**  
**Status: REVIEW REQUIRED.**

The statistical functions need an independent review.

The main items are:

1. Confirm the PSR formula and its input assumptions.
2. Confirm the benchmark Sharpe definition.
3. Confirm sample frequency and annualisation.
4. Confirm skew and kurtosis handling.
5. Confirm the BH FDR ordering and edge cases.
6. Confirm the DSR expected maximum calculation.
7. Test the independent-Gaussian assumption.
8. Test correlated candidate families.
9. Test duplicate candidates.
10. Test a very large candidate family.
11. Test small samples.
12. Test missing return vectors.
13. Test non-finite return values.
14. Test candidate failures.
15. Confirm the PBO fold construction.
16. Confirm how the 128-candidate subset is selected.
17. Test whether subset selection changes the result.
18. Confirm moving-block bootstrap block selection.
19. Confirm confidence interval construction.
20. Compare outputs with independent fixtures.

The diagnostic output must remain separate from model selection until the method review is complete.

### 7.15 Purged split integration

**Priority: P1.**  
**Status: PARTIAL.**

The helper exists.

Not every worker or trainer uses it.

Required work:

- Map every training code path.
- Identify every label interval.
- Identify every feature lookback.
- Identify each validation boundary.
- Integrate the correct purge and embargo.
- Add boundary tests.
- Add leakage tests.
- Record split parameters in the experiment.
- Reject trainers that do not provide the required interval information.

### 7.16 GPU acceleration

**Priority: P1/P2.**  
**Status: PARTIAL and BLOCKED by target hardware verification.**

The platform has optional CuPy inference paths.

The portfolio simulator remains on CPU.

The target GPU model and driver have not been verified by this audit.

Required work:

1. Record the exact GPU model.
2. Record VRAM.
3. Record the driver version.
4. Record the CUDA runtime.
5. Record compute capability.
6. Record host CPU and RAM.
7. Test the CuPy path on the target machine.
8. Test batch and scalar parity.
9. Test numerical tolerances.
10. Benchmark data transfer.
11. Benchmark population inference.
12. Benchmark feature computation.
13. Benchmark portfolio fitness.
14. Profile VRAM use.
15. Add CPU fallback tests.
16. Publish measured results only.

The code must not claim GPU speedup before these tests pass.

### 7.17 Multi-asset GPU simulation

**Priority: P2.**  
**Status: NOT IMPLEMENTED.**

The GPU path does not execute the complete portfolio simulator.

Required work:

- Define vectorised position state.
- Define vectorised cash state.
- Define fill calculations.
- Define fee calculations.
- Define deterministic ordering.
- Define numerical tolerances.
- Define memory limits.
- Compare all outputs with the CPU reference.
- Benchmark complete experiment workloads.

### 7.18 Job recovery and distributed work

**Priority: P2.**  
**Status: PARTIAL.**

The current job manager uses local threads.

The manager stores events.

The manager does not resume a calculation after restart.

Required work:

1. Add a durable task queue.
2. Store a complete job input record.
3. Store a resumable checkpoint.
4. Store the current generation or trial.
5. Store random generator state.
6. Store candidate archive state.
7. Store worker heartbeat.
8. Recover interrupted jobs.
9. Prevent duplicate execution.
10. Define worker leases.
11. Define cancellation semantics.
12. Add crash-recovery tests.
13. Add multi-worker tests.
14. Add resource limits.

### 7.19 Dashboard capability

**Priority: P2.**  
**Status: PARTIAL.**

The dashboard can create, inspect, and cancel supported jobs.

Required work:

- Compare experiments.
- Compare candidate families.
- Show population size.
- Show generation progress.
- Show diversity.
- Show Pareto fronts.
- Show failed trials.
- Show candidate lineage.
- Show CPU usage.
- Show GPU usage.
- Show RAM and VRAM.
- Show job artefacts.
- Show data quality summaries.
- Show run provenance.
- Export a complete experiment bundle.

### 7.20 Remote access security

**Priority: P0 before remote exposure.**  
**Status: NOT IMPLEMENTED.**

The API binds to loopback by default.

The application has a remote-enable option.

The current code does not establish full remote authentication and transport security.

Do not expose the service to a public or shared network.

Required work:

- User authentication.
- Role-based access.
- Session control.
- Request authorisation.
- Transport encryption.
- CSRF protection where required.
- Rate limits.
- Audit logs.
- Secret management.
- Security tests.
- Deployment review.

### 7.21 Full reproducibility

**Priority: P1.**  
**Status: PARTIAL.**

The experiment schema records important provenance.

A full reproduction bundle still needs:

- Clean or dirty working tree state.
- Exact uncommitted diff, if any.
- Python version.
- Full dependency lock.
- OS and architecture.
- CPU model.
- RAM.
- GPU model.
- Driver and CUDA versions.
- Compute backend.
- Precision mode.
- Thread count.
- Resource use.
- Feature definitions.
- Feature version.
- Data transformation versions.
- Data licensing reference.
- Complete trial family.
- Full candidate archive.
- Random generator state.
- Checkpoint state.
- Cost schedule version.
- Execution model version.
- Time zone rules.
- Experiment start and end time.

A Git commit alone does not reproduce the machine environment.

### 7.22 Four-track end-to-end validation

**Priority: P0/P1.**  
**Status: NOT VERIFIED.**

The four intended tracks are:

| Track | Status |
|---|---|
| NSE individual securities | Software path exists; complete market validation is not established. |
| NSE multi-security portfolios | Software path exists; complete market validation is not established. |
| Crypto individual assets | Local spot-data path exists; licence and market coverage are not established. |
| Crypto multi-asset portfolios | Software path exists; complete market validation is not established. |

The system needs sufficient licence-cleared data beyond the exposed historical boundary.

The tests must include negative results.

The report must not select only successful strategies.

## 8. Code review register

This section lists items that need direct review. A review item is not automatically a confirmed bug.

### CR-001 — OOS acceptance evidence

**Severity:** Critical  
**Status:** Review and protocol decision required.

The evaluator records that OOS was evaluated.

The evaluator records the OOS pass value as unknown when no approved policy exists.

This is correct for the current policy state.

The team must define the policy before it can classify OOS performance as a pass or failure.

Review question: does every worker use the same versioned acceptance policy?

Required tests:

- No policy configured.
- Policy configured.
- Policy version mismatch.
- Missing metrics.
- Failed metric.
- Passing metrics.
- Repeated OOS call.
- Candidate digest mismatch.

### CR-002 — Holdout isolation threat model

**Severity:** Critical  
**Status:** Review required.

The materialised non-holdout copy is useful.

The SQLite lifecycle log is also useful.

Neither one prevents a local process from reading another file when operating-system permissions allow it.

Review the complete path from ingestion to worker execution.

Test the normal worker with no access to the protected path.

Test an attempted read of a protected source file.

Test the explicit compatibility override.

Test a worker restart.

Test a concurrent worker.

Do not describe the current solution as a secure holdout boundary.

### CR-003 — Candidate classification integration

**Severity:** High  
**Status:** Review required.

The classifier itself uses explicit evidence fields.

The evaluator for existing strategies currently constructs evidence with validation_selected=False and oos_passed=None.

The evaluator output can therefore be training-only or inconclusive, depending on the available partitions.

This may be correct for a fixed evaluator that does not perform model selection. It may also be too broad if the evaluator has a validation-selected candidate.

Review the intended meaning of validation_selected for each worker.

Review all candidate records.

Review all aggregate job reports.

Confirm that each candidate has its own classification evidence.

Do not copy an aggregate classification onto every candidate.

### CR-004 — Statistical dependence

**Severity:** High  
**Status:** Independent method review required.

The DSR approximation uses independent Gaussian trial Sharpe estimates.

Evolutionary candidates are related by common parents, mutations, and shared data.

The independence assumption may not hold.

Run sensitivity tests with correlated candidate families.

Review the DSR implementation against independent published or validated fixtures.

### CR-005 — PBO candidate subset

**Severity:** High  
**Status:** Review required.

The PBO path uses a deterministic evenly spaced subset capped at 128 candidates.

The full candidate archive may be larger.

The subset can omit important candidate relationships.

Measure how much PBO changes with different bounded subsets.

Compare the result with a full calculation on smaller test fixtures.

Record the selection method and subset size.

### CR-006 — PSR and FDR interpretation

**Severity:** High  
**Status:** Review required.

PSR-derived p-values use a zero per-period Sharpe benchmark.

Review the frequency assumptions.

Review the annualisation rules.

Review the p-value interpretation.

Review the full successful candidate family.

Confirm that failed candidates and baselines receive the intended treatment.

Confirm that FDR is calculated on the correct family.

### CR-007 — Purging and embargo coverage

**Severity:** High  
**Status:** Review required.

The split helper exists.

The code documentation states that every optimiser and model trainer does not yet use the helper.

Create a call map.

Add tests for every worker.

Confirm label start and end times.

Confirm feature lookbacks.

Confirm the embargo unit.

### CR-008 — Existing strategy compatibility

**Severity:** High  
**Status:** Review required.

The signal adapter uses long and flat signals.

The legacy catalogue can contain position and execution logic that does not map directly to this interface.

Create a strategy compatibility table.

Compare original and adapted output on the same bars.

Test warm-up behaviour.

Test state reset behaviour.

Test missing bars.

Test short signals.

### CR-009 — OHLCV quality checks

**Severity:** High  
**Status:** Review required.

The current checks cover required fields, finite values, positive prices, non-negative volume, and open/high/low relationships.

They do not form a complete quality grade.

Review missing sessions.

Review missing bars.

Review duplicate timestamps.

Review out-of-order timestamps.

Review split and dividend effects.

Review delisting coverage.

Review price spikes.

Review trading halts.

Review venue outages.

Review stale instruments.

### CR-010 — NSE return threshold

**Severity:** Medium/High  
**Status:** Review required.

The default strict absolute daily close-return threshold below 20 percent is NSE-specific.

The threshold is a quality gate. It is not proof that every valid observation has a return below this value.

Review valid exceptional sessions.

Review corporate actions.

Review adjusted and unadjusted data.

Review the effect of the threshold on data retention.

Record rejected rows and the reason.

### CR-011 — Portfolio fill model

**Severity:** High  
**Status:** Review required.

The simulator makes a next-open fill decision.

It uses prior completed bar volume for participation and impact.

It does not replay a live order book.

Review price gaps.

Review open auctions.

Review partial fills.

Review limit prices.

Review market impact.

Review liquidity limits.

Review fills during halted or illiquid sessions.

### CR-012 — Fee schedules

**Severity:** High  
**Status:** Review required.

The NSE fee model uses the configured schedule.

The schedule is not date-effective for all historical periods.

The crypto fee model uses configured maker and taker rates.

Review historical fee and statutory changes.

Review all venue tiers.

Review maker rebates.

Review the current market-order taker assumption.

### CR-013 — Accounting invariants

**Severity:** High  
**Status:** Review required.

The cash simulator has core checks.

It still needs a wider financial invariant test suite.

Required tests include:

- Cash conservation.
- Position conservation.
- Fill idempotency.
- No negative cash.
- No unintended negative position.
- Fee accounting.
- Slippage accounting.
- Split accounting.
- Dividend accounting.
- Delisting settlement.
- Decimal and floating-point boundaries.
- Very small order sizes.
- Very large order sizes.
- Repeated timestamps.

### CR-014 — GPU execution path

**Severity:** Medium/High  
**Status:** Hardware review required.

The code has optional CuPy paths and fallback behaviour.

The target hardware is not verified.

Run on the target GPU.

Compare NumPy and CuPy outputs.

Measure memory transfer and full-workload throughput.

### CR-015 — Job lifecycle after a crash

**Severity:** Medium/High  
**Status:** Review required.

The lifecycle record survives restart.

The computation does not resume.

Review the job state after a forced process stop.

Confirm that an interrupted job cannot continue with stale in-memory state.

Confirm that the next submitted job receives a new job ID.

Add resume support only after checkpoint semantics are defined.

### CR-016 — Experiment metadata completeness

**Severity:** Medium  
**Status:** Review required.

The experiment record contains important provenance.

It does not guarantee a complete machine and environment record.

Define a required provenance schema.

Reject a result when required provenance is missing.

### CR-017 — API boundary

**Severity:** Critical before remote use  
**Status:** Review required.

The server is loopback-only by default.

The remote flag is not a substitute for authentication.

Test that a normal configuration cannot bind to a public interface.

Test that remote access is rejected without the required controls.

### CR-018 — Dashboard correctness

**Severity:** Medium  
**Status:** Review required.

The dashboard displays persisted state.

Review whether each progress value is current.

Review behaviour when a job is cancelled.

Review behaviour when a worker fails.

Review stale records.

Review long-running results.

Review missing or partial artefacts.

### CR-019 — Test coverage

**Severity:** High  
**Status:** Review required.

The focused workflow tests the v2 platform.

It does not test all market data or the full legacy system.

Create a test-to-requirement matrix.

Mark each feature as unit tested, integration tested, market tested, or unverified.

Do not use a focused suite result as a full repository test result.

### CR-020 — Legacy findings

**Severity:** Critical/High until status is refreshed  
**Status:** Historical findings require fresh verification.

The legacy tracker is dated 22 August 2026.

The v2 work did not re-audit the legacy runtime.

Review the legacy issue list in Section 12.

## 9. Fix backlog

The backlog uses the following priority definitions.

| Priority | Meaning |
|---|---|
| P0 | Work that blocks a secure or valid validation claim. |
| P1 | Work required for credible market research or the target research design. |
| P2 | Work required for scale, usability, or full compute capability. |
| P3 | Useful improvement that does not block the first controlled research release. |

### 9.1 P0 — Must fix before a validation claim

| ID | Required change | Completion condition |
|---|---|---|
| F-001 | Approve and version the OOS acceptance policy. | All OOS tests use one fixed policy version. |
| F-002 | Isolate the final holdout at the OS or service boundary. | Normal workers cannot read protected files. |
| F-003 | Test the holdout access model with adversarial tests. | Access attempts are denied and recorded. |
| F-004 | Define a licence-cleared data set for the selected research track. | Licence, provenance, coverage, and quality are recorded. |
| F-005 | Confirm the independent OOS boundary and the data source. | The boundary is not exposed to model selection. |
| F-006 | Review all candidate evidence and classification output. | Candidate evidence is accurate and stored at candidate level. |
| F-007 | Independently validate critical statistical calculations. | Reference fixtures and assumptions are approved. |
| F-008 | Keep the API local until remote security is ready. | No remote bind is allowed in an unprotected deployment. |

### 9.2 P1 — Required for credible research

| ID | Required change | Completion condition |
|---|---|---|
| F-009 | Build a point-in-time universe. | Historical symbols, listings, delistings, and changes are represented. |
| F-010 | Add missing-bar and gap audits. | Every manifest reports gaps and missing intervals. |
| F-011 | Add acquisition clients for approved providers. | Data can be fetched, validated, and versioned. |
| F-012 | Add date-effective cost schedules. | Each fill uses the correct dated fee rules. |
| F-013 | Add tax lots and corporate actions. | Cash and positions remain correct after each event. |
| F-014 | Add crypto funding and derivatives accounting. | Each derivative contract has a separate tested ledger. |
| F-015 | Calibrate execution against tick or order-book data. | Fill assumptions have a measured reference. |
| F-016 | Integrate purging into every training path. | Every trainer has a leakage test. |
| F-017 | Extend causal features to point-in-time data. | Each feature records availability time and source. |
| F-018 | Add Boolean and control-flow GP grammar. | Typed expression tests pass. |
| F-019 | Add neural topology evolution. | Topology changes are bounded and reproducible. |
| F-020 | Add full strategy composition components. | Required roles and compatibility tests pass. |
| F-021 | Add strategy compatibility tests. | Every supported strategy has an explicit test record. |
| F-022 | Review DSR, PBO, PSR, and FDR. | Independent fixture results match approved results. |
| F-023 | Complete reproducibility metadata. | Each experiment has a complete environment record. |
| F-024 | Validate all four tracks. | Each track has a data and test report. |

### 9.3 P2 — Required for scale and usability

| ID | Required change | Completion condition |
|---|---|---|
| F-025 | Build mixed-genome co-evolution. | One bounded population can compare supported genome families. |
| F-026 | Add resumable jobs. | A worker can resume from a verified checkpoint. |
| F-027 | Add distributed workers. | Work can run under a controlled worker lease. |
| F-028 | Add GPU portfolio simulation. | CPU and GPU results match within approved tolerances. |
| F-029 | Benchmark the target GPU. | A reproducible benchmark report exists. |
| F-030 | Add dashboard experiment comparisons. | A user can compare complete experiment records. |
| F-031 | Add population and generation monitoring. | The dashboard displays the actual worker state. |
| F-032 | Add CPU, RAM, GPU, and VRAM telemetry. | Resource data is stored with the job. |
| F-033 | Add full job artefact export. | A job can export its specification, candidates, results, and logs. |
| F-034 | Add secure remote access, only if required. | Authentication and transport security tests pass. |

### 9.4 P3 — Additional engineering

| ID | Required change | Completion condition |
|---|---|---|
| F-035 | Add wider benchmark suites. | Benchmarks cover small, medium, and large candidate families. |
| F-036 | Add more execution models. | Every model has explicit assumptions and tests. |
| F-037 | Add richer experiment reports. | Reports include negative and inconclusive findings. |
| F-038 | Add provider and data-quality dashboards. | The dashboard shows coverage and quality by source. |
| F-039 | Add documented performance budgets. | Each worker has CPU, RAM, and time limits. |
| F-040 | Add reproducible environment images. | A run can use a fixed container and dependency set. |

## 10. Work that this audit could not complete

This section records blockers and missing access. It does not mean that the work is impossible.

### 10.1 Data licence and provider access

The repository contains local data adapters.

The audit did not have a verified provider licence.

The audit did not have provider credentials.

The audit did not acquire additional NSE or crypto history.

The audit did not validate redistribution rights.

The next owner must select the provider and approve its terms.

### 10.2 Target GPU and driver access

The platform has optional CuPy code.

The audit did not have a verified target GPU session.

The audit did not measure CUDA compatibility.

The audit did not measure VRAM use.

The audit did not compare CPU and GPU throughput.

The next owner must run the benchmark on the target machine.

### 10.3 OOS policy approval

The code does not define an approved performance gate.

The audit must not invent a trading acceptance threshold.

The research owner must approve the rules.

The rules must be versioned before an OOS evaluation uses them.

### 10.4 Independent statistical review

The audit inspected the code and documented assumptions.

The audit did not obtain an independent statistical sign-off.

A reviewer must compare the methods with independent fixtures and published definitions.

The reviewer must test correlated candidate populations.

### 10.5 Secure holdout deployment

The audit can describe the code-level lifecycle.

The audit cannot create a secure operating-system boundary from a documentation change.

The deployment owner must configure the isolated storage and process permissions.

The team must test those permissions from an untrusted worker.

### 10.6 Full market validation

The audit did not run the four tracks against complete, licence-cleared market data.

The current post-exposed NSE period is short.

The audit does not claim enough independent observations for a robust strategy conclusion.

The team must wait for sufficient independent data before it makes a performance claim.

### 10.7 Full legacy runtime review

The audit reviewed the legacy status and bug tracker.

It did not repeat the complete legacy code audit.

The legacy tracker is from 22 August 2026.

The team must verify every issue against the current code and current GitHub issue state.

### 10.8 Merge to main

This task did not request a merge.

The branch remains feature/hybrid-evolution-research.

The branch was 341 commits ahead and zero commits behind at the audit snapshot.

A reviewer must approve the branch before a merge.

## 11. Test and verification report

### 11.1 Verified CI command

The dedicated workflow uses:

python -m compileall -q research/platform

It then runs:

python -m pytest tests/unit/test_research_platform*.py -q --tb=short --maxfail=1

The workflow installs requirements/test.txt and requirements/research.txt.

The workflow sets RESEARCH_REQUIRE_PARTITIONED_DATA to 1.

The workflow uses Python 3.13.

### 11.2 What the passing workflow supports

The passing workflow supports these statements:

- The platform modules compile in the CI environment.
- The focused research-platform tests pass in that environment.
- The tested code snapshot passed the configured checks.

### 11.3 What the passing workflow does not support

The workflow does not support these statements:

- The whole repository test suite passes.
- Every legacy module is correct.
- Every market data file is correct.
- Every data licence is valid.
- The final holdout is secure.
- The OOS acceptance policy is approved.
- A strategy is profitable.
- A strategy is deployable.
- The GPU path works on the target hardware.
- The system can recover an in-progress calculation after a process crash.
- The platform can run every intended research track with complete historical data.

### 11.4 Documentation-only commit behaviour

The dedicated workflow path filter covers platform code, selected strategy code, tests, and dependency files.

It does not include a general docs/** path.

A documentation-only change may not start the dedicated research-platform workflow.

This audit file is a documentation change.

The tested code snapshot remains 7ea38112df28fb91d29c00e5206685281e7fd4c1 unless a later code commit runs the workflow.

### 11.5 Required next test stages

The next test stages are:

1. Focused unit tests.
2. Full repository unit tests.
3. Integration tests for each worker.
4. Data contract tests with approved real data.
5. Financial invariant tests.
6. Leakage and holdout access tests.
7. Statistical reference tests.
8. CPU and GPU parity tests.
9. Crash and resume tests.
10. Four-track end-to-end tests.

## 12. Legacy runtime findings that need a fresh audit

**Status: Historical issue register. Do not assume that each issue remains open.**

PROJECT_MEMORY/13_Bug_Tracker.md records a full-repository audit dated 22 August 2026.

The tracker records issues #20 through #53.

PROJECT_MEMORY/12_Feature_Status.md says that its legacy module table has not been re-audited by the v2 platform work.

The following list preserves the important findings. Each issue needs a fresh check against the current main branch and the current feature branch.

### 12.1 Historical critical findings

| Issue | Historical finding | Required fresh check |
|---|---|---|
| #20 | Backtest equity timestamps used wall-clock time. This caused invalid annualisation for bar-based runs. | Re-run metric timing tests. |
| #21 | ML future-return labels were backward returns and matched a return feature. | Review label direction and feature leakage. |
| #22 | The production Docker command used a duplicated module flag. | Build and run the production image. |
| #23 | The Docker Compose configuration had invalid paths and flags. | Validate each Compose file and run the declared services. |
| #24 | Rust risk-parity logic could converge to a single-asset corner. | Compare against an independent reference implementation. |
| #25 | Strategy flip signals did not establish short positions. | Test every strategy with long, flat, and short states. |
| #26 | Transaction cost calculations mixed basis points, currency, and fractions. | Reconcile cost calculations against a hand-calculated fixture. |
| #27 | Walk-forward optimisation had non-functional trials and an in-sample fallback. | Run a full walk-forward test and inspect every objective. |
| #28 | Kubernetes resources and probes were invalid. | Build and validate the current manifests. |

### 12.2 Historical high-severity findings

| Issue | Historical finding | Required fresh check |
|---|---|---|
| #29 | Email monitoring settings were missing fields. | Test email alert configuration. |
| #30 | Funding settlement could be skipped on some bar grids. | Test settlement on every supported interval. |
| #31 | Funding simulation used a future close. | Run a time-causality test. |
| #32 | Bar backtests did not mark positions to market between fills. | Reconcile equity and unrealised P&L. |
| #33 | Backtest mode disabled important risk checks. | Confirm that all hard risk limits remain active. |
| #34 | Data-freshness checks could pass with no tickers. | Test empty symbol and missing feed states. |
| #35 | Component health did not use all health-check results. | Test the health endpoint and kill-switch state. |
| #36 | Regime prediction could return stale in-sample labels. | Test prediction on unseen data. |
| #37 | Some imported modules were absent from dependency manifests. | Run clean environment installation tests. |
| #38 | Release workflow used a different Python tag. | Verify every release build uses the approved version. |
| #39 | Python Sortino used the wrong downside deviation calculation. | Compare the formula against a reference fixture. |
| #40 | Rust Sortino and drawdown calculations had formula errors. | Compare Rust and Python outputs. |
| #41 | Rust risk checks could accept non-finite values and invalid sizing. | Add NaN, infinity, and leverage boundary tests. |
| #42 | Some Rust backtest modules referenced missing APIs. | Build and test every reachable Rust module. |
| #43 | Binance venue retry logic could repeat non-retryable orders. | Test retry classification and idempotency. |
| #44 | The ML CLI command used incompatible function arguments. | Run the full ML CLI path. |

### 12.3 Historical medium and low severity groups

| Issue | Historical scope | Required fresh check |
|---|---|---|
| #45 | Market-making code did not submit correct orders. | Run order lifecycle tests. |
| #46 | VWAP schedule indexing used an incorrect scale. | Test every schedule segment. |
| #47 | Absolute momentum neutral values were incorrect. | Test positive, neutral, and negative cases. |
| #48 | ML sweep included probability, variance, feature, label, cache, detector, and clustering issues. | Review every sub-finding and add isolated tests. |
| #49 | Risk sweep included correlation, daily loss, volatility cap, and kill-switch issues. | Review every risk check from signal to order. |
| #50 | Monitoring sweep included gauges, alerts, history, intervals, and dashboard queries. | Compare emitted metrics with dashboard queries. |
| #51 | Backtest and data sweep included alignment, marks, fill logic, annualisation, optimisation, storage, and timestamp issues. | Review every sub-finding against current code. |
| #52 | Infrastructure sweep included CI, dependency, environment, Grafana, Prometheus, ports, release, and versioning issues. | Run current deployment and release workflows. |
| #53 | Rust sweep included numerical, validation, and annualisation issues. | Compare Rust functions with reference fixtures. |

The same tracker records B073 as a stale remote branch. It says that the branch must not be merged as-is.

This audit did not verify the current remote branch state for B073.

### 12.4 Legacy review rule

Do not use old legacy backtest results as current v2 evidence.

Do not assume that a v2 test fixed a legacy issue.

Do not assume that a legacy issue is still open because the old tracker lists it.

Check the current code.

Check the current issue state.

Run the relevant test.

Record the result.

## 13. Recommended work order

The order below reduces the risk of building advanced search methods before the research evidence is valid.

### Stage 1 — Freeze the research rules

1. Approve the four research track definitions.
2. Approve the OOS acceptance policy.
3. Approve the final-holdout use policy.
4. Define a candidate freeze rule.
5. Define the data integrity gates.
6. Define the required evidence for a robust research candidate.
7. Version the protocol.

**Exit condition:** The research protocol is fixed before any new OOS result is used.

### Stage 2 — Secure the validation boundary

1. Put the final holdout outside normal worker access.
2. Add an isolated holdout service or process.
3. Add restrictive file permissions.
4. Add access logs.
5. Add frozen candidate verification.
6. Add adversarial access tests.
7. Test concurrent requests.
8. Test restart behaviour.

**Exit condition:** A normal worker cannot read protected rows or files.

### Stage 3 — Establish data quality

1. Select approved data providers.
2. Confirm the licence for every dataset.
3. Build point-in-time NSE history.
4. Build point-in-time crypto venue history.
5. Add missing-bar audits.
6. Add gap and duplicate reports.
7. Add corporate-action handling.
8. Add instrument history.
9. Add FX provenance.
10. Publish a data availability matrix.

**Exit condition:** Each research track has a documented, licence-cleared data set with known coverage and quality.

### Stage 4 — Validate the simulator

1. Add dated fee schedules.
2. Add corporate actions.
3. Add tax lots.
4. Add dividends.
5. Add crypto funding.
6. Add borrow and margin where required.
7. Add liquidation rules.
8. Add execution calibration.
9. Add financial invariant tests.
10. Compare simulated results with independent calculations.

**Exit condition:** Every supported instrument type has a tested accounting and execution model.

### Stage 5 — Validate statistics and splits

1. Audit PSR.
2. Audit FDR.
3. Audit DSR.
4. Audit PBO.
5. Audit moving-block bootstrap.
6. Test correlated strategy families.
7. Test small samples.
8. Integrate purge and embargo in every trainer.
9. Add leakage tests.
10. Record all method versions.

**Exit condition:** An independent reviewer approves each diagnostic method and the split protocol.

### Stage 6 — Complete evolutionary research

1. Add Boolean GP.
2. Add control-flow GP.
3. Add neural topology evolution.
4. Complete strategy composition.
5. Complete existing strategy adapters.
6. Define the common genome contract.
7. Add mixed-genome populations.
8. Equalise budgets.
9. Add diversity controls.
10. Add reproducible stopping rules.

**Exit condition:** The supported candidate families can be compared under the same data, protocol, and budget.

### Stage 7 — Complete compute and operations

1. Benchmark the target GPU.
2. Add CPU/GPU parity for all supported workloads.
3. Add GPU portfolio simulation.
4. Add checkpoints.
5. Add crash recovery.
6. Add distributed worker control if needed.
7. Add experiment comparisons.
8. Add resource telemetry.
9. Add artefact export.
10. Add remote security only when it is required.

**Exit condition:** The platform can run, monitor, recover, and reproduce its declared workloads.

### Stage 8 — Run the four research tracks

Run one track at a time.

Use the approved data.

Use a fixed protocol.

Use the same declared cost assumptions for comparable candidates.

Record all candidates and failures.

Report negative and inconclusive results.

Do not use the final holdout to tune a model.

**Exit condition:** Each track has a complete report with data coverage, assumptions, validation, uncertainty, and failure analysis.

## 14. Release and research readiness checklist

The following conditions must pass before the platform can make a strong research validation claim.

### 14.1 Validation and data

- [ ] OOS acceptance policy is approved and versioned.
- [ ] Final holdout is isolated from normal workers.
- [ ] Normal workers cannot read protected files.
- [ ] Candidate freeze is immutable.
- [ ] OOS access is recorded.
- [ ] Data licences are approved.
- [ ] Point-in-time universe coverage is recorded.
- [ ] Delisted instruments are represented.
- [ ] Corporate actions are represented.
- [ ] Missing bars and data gaps are reported.
- [ ] Feature publication times are correct.
- [ ] Purging and embargo are used by every trainer.

### 14.2 Simulation and execution

- [ ] Dated fee schedules are implemented.
- [ ] NSE whole-share rules are tested.
- [ ] Tax lots are implemented.
- [ ] Corporate actions are tested.
- [ ] Dividends are tested.
- [ ] Crypto funding is implemented where required.
- [ ] Margin and liquidation are implemented where required.
- [ ] Execution assumptions are calibrated.
- [ ] Accounting invariants pass.
- [ ] Every fill records its cost model version.

### 14.3 Search and statistics

- [ ] Existing strategy compatibility is documented.
- [ ] GP Boolean grammar is implemented.
- [ ] GP control flow is implemented.
- [ ] Neural topology evolution is implemented.
- [ ] Strategy composition is complete for the intended scope.
- [ ] Mixed-genome evolution is implemented.
- [ ] Candidate budgets are comparable.
- [ ] PSR is independently checked.
- [ ] FDR is independently checked.
- [ ] DSR assumptions are reviewed.
- [ ] PBO sensitivity is checked.
- [ ] Bootstrap settings are versioned.
- [ ] Statistical diagnostics do not leak into model selection.

### 14.4 Compute and operations

- [ ] The target GPU is identified.
- [ ] The GPU environment is tested.
- [ ] CPU/GPU parity passes.
- [ ] GPU performance is measured.
- [ ] Job checkpoints are implemented.
- [ ] Job recovery is tested.
- [ ] Dashboard comparisons are implemented.
- [ ] Population monitoring is implemented.
- [ ] Resource telemetry is recorded.
- [ ] Experiment artefacts are exportable.
- [ ] Remote access is disabled unless secure access is implemented.

### 14.5 Four research tracks

- [ ] NSE individual track has a complete data report.
- [ ] NSE portfolio track has a complete data report.
- [ ] Crypto individual track has a complete data report.
- [ ] Crypto portfolio track has a complete data report.
- [ ] Each track uses the approved protocol.
- [ ] Each track reports failed and inconclusive candidates.
- [ ] Each track reports all costs.
- [ ] Each track reports data limitations.
- [ ] Each track has independent review.
- [ ] No result is described as a guarantee.

## 15. Key source files

The following files are the main entry points for future work.

| Area | Main source |
|---|---|
| Project requirements | GOAL.md |
| Repository agent rules | AGENTS.md |
| Architecture and known limits | docs/RESEARCH_PLATFORM_ARCHITECTURE.md |
| Package guide | research/platform/README.md |
| Domain types | research/platform/domain.py |
| Experiment schema | research/platform/experiments.py |
| Data catalogue | research/platform/data_catalog.py |
| Data adapters | research/platform/adapters.py |
| Time and FX alignment | research/platform/fx.py |
| Feature generation | research/platform/features.py |
| Validation windows | research/platform/validation.py |
| Persistent store | research/platform/storage.py |
| Candidate classification | research/platform/classification.py |
| Strategy catalogue | research/platform/strategy_catalog.py |
| Strategy signals | research/platform/strategy_signals.py |
| Existing-strategy evaluation | research/platform/evaluation.py |
| Search methods | research/platform/optimizers.py |
| Genetic programming | research/platform/genetic_programming.py |
| Neuroevolution | research/platform/neuroevolution.py |
| Strategy composition | research/platform/composition.py |
| Multi-objective search | research/platform/pareto.py |
| Portfolio simulation | research/platform/portfolio.py |
| Costs | research/platform/costs.py |
| Statistical methods | research/platform/statistics.py |
| Compute backend | research/platform/compute.py |
| Research workers | research/platform/runners.py |
| Job manager | research/platform/jobs.py |
| API | research/platform/api.py |
| Application entry point | research/platform/app.py |
| Platform tests | tests/unit/test_research_platform*.py |
| CI workflow | .github/workflows/research-platform.yml |
| Feature status | PROJECT_MEMORY/12_Feature_Status.md |
| Legacy bug tracker | PROJECT_MEMORY/13_Bug_Tracker.md |

## 16. Final status by area

| Area | Status | Main reason |
|---|---|---|
| Separate v2 platform | COMPLETE | Additive package exists. |
| Market and track separation | COMPLETE | Explicit domain types and separate ledgers exist. |
| Experiment records | COMPLETE/PARTIAL | Main provenance exists; full environment provenance is missing. |
| Local data adapters | PARTIAL | Local files only; licence and coverage are not verified. |
| Point-in-time universe | NOT COMPLETE | Historical membership and instrument changes are missing. |
| Data acquisition | NOT IMPLEMENTED | No automated provider ingestion. |
| Price and volume features | PARTIAL | Causal base features exist. |
| Fundamental and news features | NOT IMPLEMENTED | No complete publication-time integration. |
| Validation helper | PARTIAL | Some split helpers exist; not all trainers use them. |
| Holdout lifecycle | COMPLETE for event state | Events persist and concurrency tests exist. |
| Secure holdout isolation | NOT COMPLETE | No OS-level or service boundary. |
| OOS policy | NOT IMPLEMENTED | No approved numeric acceptance gate. |
| Existing strategy adapter | PARTIAL | Long/flat only; catalogue compatibility needs review. |
| Conventional optimisers | COMPLETE for current methods | Random, grid, DE, TPE, and hybrid baseline exist. |
| Genetic programming | PARTIAL | Numeric grammar only. |
| Neuroevolution | PARTIAL | Fixed topology. |
| Strategy composition | PARTIAL | Limited fixed registry. |
| NSGA-II | PARTIAL | Existing strategy parameters only. |
| Mixed-genome evolution | NOT IMPLEMENTED | No shared population across all candidate families. |
| Cash portfolio simulator | PARTIAL | Long-only INR cash model. |
| Historical fees | PARTIAL | Dated schedules are incomplete. |
| Full accounting | NOT COMPLETE | Tax, corporate actions, funding, margin, and liquidation are missing. |
| Statistical diagnostics | REVIEW REQUIRED | Independent method review remains open. |
| GPU inference | PARTIAL | Optional CuPy path exists. |
| GPU portfolio simulation | NOT IMPLEMENTED | Portfolio fitness remains CPU-based. |
| Target GPU benchmark | NOT VERIFIED | Target hardware has not been tested. |
| Local API and dashboard | PARTIAL | Core worker operations exist; comparison and telemetry are incomplete. |
| Remote security | NOT IMPLEMENTED | No completed authentication boundary. |
| Job persistence | PARTIAL | State persists; computation does not resume. |
| Distributed workers | NOT IMPLEMENTED | Local thread pool only. |
| Focused CI | TESTED | Documented code commit passed the dedicated workflow. |
| Full repository verification | NOT VERIFIED | Not established by the focused workflow. |
| Four-track market validation | NOT VERIFIED | Complete licence-cleared data and end-to-end reports are missing. |
| Profitability claim | NOT ESTABLISHED | No independent validated result exists. |
| Live trading readiness | NOT APPLICABLE | The v2 mission excludes live trading. |

## 17. Final conclusion

The current branch contains a meaningful v2 research-platform foundation.

The code supports separate NSE and crypto research environments. It supports conventional search, several evolutionary workers, portfolio simulation, candidate persistence, validation lifecycle records, statistical diagnostics, and a local dashboard.

The focused platform CI passed for the documented code snapshot.

The system still has critical gaps.

The first work must be the research protocol, OOS acceptance policy, and secure holdout boundary.

The second work must be data quality, point-in-time history, and licences.

The third work must be simulator accounting and execution realism.

The fourth work must be independent statistical review and complete split integration.

The fifth work can complete mixed-genome evolution, GPU simulation, job recovery, and dashboard monitoring.

The four research tracks must not be treated as validated until they use approved data and pass the same fixed research protocol.

A passing CI run is evidence that tested software contracts pass. It is not evidence that a market strategy has an edge.

A historical return is not evidence of a future return.

A research classification is not approval to trade.

**Final status: PARTIAL IMPLEMENTATION. CONTINUED ENGINEERING REQUIRED. NO PROFITABILITY OR DEPLOYABILITY CLAIM IS APPROVED.**
