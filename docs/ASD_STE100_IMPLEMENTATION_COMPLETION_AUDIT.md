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

**Limit:** The API includes a same-market comparison route for two to ten experiments. The dashboard does not yet provide a complete visual comparison and reporting suite. Full population monitoring, GPU telemetry, and full job artefact views also remain incomplete.

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


---

# Additional technical appendices

## 18. Requirement-to-implementation traceability

This section maps the v2 requirements in GOAL.md to the code that exists in the audited branch.

The status column describes the implementation that the audit found. It does not describe a future design.

The test column identifies the closest focused tests. A test name does not prove that the complete requirement is satisfied.

| GOAL section | Requirement | Main implementation | Test evidence | Audit result |
|---|---|---|---|---|
| 0 | Preserve the old research record. Separate v1 and v2 claims. | GOAL.md and the v2 package documentation. | Documentation review. | COMPLETE in documentation. |
| 1 | Build a modular research platform. | research/platform/ package. | Full focused platform test group. | PARTIAL. The platform foundation exists. |
| 2 | Keep NSE and crypto financial state independent. | domain.py, market.py, experiments.py, portfolio.py. | test_market_budgets_are_separate_and_market_fill_cannot_cross; test_market_ledger_accounting_and_duplicate_fill_guard. | COMPLETE for the cash model. |
| 3 | Support four research tracks. | domain.py, experiments.py, adapters.py, runners.py. | test_research_api_market_filter_and_cross_market_rejection; test_experiment_comparison_rejects_mixed_market_ids. | PARTIAL. Track contracts and worker paths exist. Full market validation does not. |
| 4 | Acquire data and preserve provenance. | data_catalog.py, adapters.py, storage.py, runners.py. | Data manifest, source hash, timestamp, quality, FX and partition tests. | PARTIAL. Local import exists. Automated acquisition and complete point-in-time history do not. |
| 5 | Measure incremental value from multiple data sources. | features.py and model_evaluation.py. | test_point_in_time_features_are_invariant_to_future_price_changes; test_forward_labels_have_explicit_end_timestamps_and_are_separate. | PARTIAL. Price and volume features exist. Other source families are incomplete. |
| 6 | Implement GP, neuroevolution, composition, and hybrid evolution. | genetic_programming.py, neuroevolution.py, composition.py, pareto.py, runners.py. | Search and runner tests. | PARTIAL. Separate workers exist. Required mixed-genome evolution does not. |
| 7 | Compare conventional optimisers and evolutionary methods under equal budgets. | optimizers.py and runners.py. | Search budget and hybrid ensemble tests. | PARTIAL. Conventional methods and one ensemble exist. Full cross-family comparison does not. |
| 8 | Use the target GPU where useful. Preserve CPU fallback. | compute.py, neuroevolution.py, runners.py. | CPU batch parity, automatic fallback, explicit CuPy failure, neural batch parity tests. | PARTIAL. Runtime code exists. Target hardware and full simulation are not verified. |
| 9 | Model portfolios, accounting, costs, and execution. | portfolio.py, costs.py, market.py. | Portfolio, fill, fee, whole-share, and cash tests. | PARTIAL. Long-only OHLCV cash accounting exists. Full accounting and market execution do not. |
| 10 | Prevent leakage and overfitting. | validation.py, evaluation.py, storage.py, statistics.py, runners.py. | Chronology, embargo, purging, candidate freeze, OOS and concurrent-access tests. | PARTIAL. Several controls exist. Secure holdout isolation and an approved OOS policy do not. |
| 11 | Record experiments and candidate lineage. | experiments.py, storage.py, runners.py. | Fingerprint, append-only store, candidate lineage and restart-state tests. | PARTIAL. Main records exist. Full machine provenance and resumable execution do not. |
| 12 | Provide a data-backed research dashboard. | api.py, app.py, jobs.py. | API, job, compare, dashboard and worker route tests. | PARTIAL. Core API exists. The visual monitoring and comparison suite is incomplete. |
| 13 | Preserve legacy systems and use adapters. | strategy_catalog.py, strategy_signals.py, evaluation.py. | Catalogue, strategy signal and evaluation tests. | PARTIAL. Long/flat adapter exists. Compatibility across all strategies is not established. |
| 14 | Pre-register hypotheses, budgets, metrics, and stop conditions. | Experiment records and worker settings. | Experiment schema and worker validation tests. | PARTIAL. Some fields exist. A complete pre-registered protocol record is not guaranteed. |
| 15 | Test correctness, leakage, accounting, and CPU/GPU parity. | tests/unit/test_research_platform*.py and dedicated workflow. | 154 test function definitions across 12 focused files. | PARTIAL. Focused contracts pass in documented CI. Market, hardware and full-repository tests remain open. |
| 16 | Complete work in controlled milestones. | GOAL.md and current branch commits. | Commit history and CI. | PARTIAL. Current milestone has a strong foundation but is not complete. |
| 17 | Inventory target hardware. | compute.py reports runtime information. | CPU and mocked GPU tests. | NOT VERIFIED on target hardware. |
| 18 | Keep live trading outside v2 and protect credentials and data. | GOAL.md, app.py, adapters.py, jobs.py. | Loopback binding and registered-runner tests. | PARTIAL. No v2 live order path is intended. Remote security and data rights remain open. |
| 19 | Produce a final report with track status and measured evidence. | This report and existing documentation. | Documentation review. | PARTIAL. The implementation report exists. End-to-end market evidence is not available. |

### 18.1 Requirement evidence rule

A requirement is not COMPLETE because a class or function exists.

A requirement is COMPLETE only when the code implements its full required scope, tests cover the relevant behaviour, and required external evidence exists.

For example, the existence of a crypto adapter does not complete crypto data acquisition. The adapter reads a local file. It does not acquire a complete history from a licensed provider.

The existence of a GPU backend does not complete GPU acceleration. The target GPU must run the workload. The system must compare outputs with the CPU reference. A measured throughput result must support any speedup claim.

The existence of a validation lifecycle does not create a secure holdout. The operating system or a separate service must prevent the normal worker from reading protected data.

## 19. Domain and data contracts

### 19.1 Market contract

The domain layer defines two financial environments:

- NSE.
- Crypto.

The environment is a financial boundary.

A dataset has one market.

An experiment has one market.

A job receives one experiment specification.

A portfolio configuration belongs to one market.

A fee calculator belongs to one market.

A fill belongs to one market.

A financial report must preserve this boundary.

The comparison API must not combine the financial performance of different markets.

A combined infrastructure view is permitted. A combined financial result is not.

### 19.2 Research track contract

The platform distinguishes these track types:

| Track | Market | Intended unit of research |
|---|---|---|
| NSE individual | NSE | One equity instrument per experiment. |
| NSE portfolio | NSE | A group of NSE equity instruments under one cash ledger. |
| Crypto individual | Crypto | One spot instrument and exchange per experiment in the current spot scope. |
| Crypto portfolio | Crypto | Multiple spot instruments within the declared exchange scope. |

A worker must reject an experiment that does not match its data and track scope.

An individual track must not silently accept a multi-instrument universe.

A portfolio track must not silently combine instruments from an undeclared exchange.

A crypto portfolio experiment currently requires one exchange in the affected worker path. The code rejects a portfolio that attempts to use multiple exchanges in that path.

This restriction must remain visible in the API and documentation until multi-exchange accounting is complete.

### 19.3 Resolution contract

The domain declares resolutions that include:

- One second.
- One minute.
- Five minutes.
- Fifteen minutes.
- Thirty minutes.
- One hour.
- Four hours.
- One day.
- One week.
- One month.

The existence of a resolution enum does not mean that source data exists at that resolution.

The manifest must describe actual coverage.

The data availability catalogue must report the coverage that has been registered.

The operator must not infer coverage from an instrument name or a provider marketing page.

Monthly data needs calendar-month boundary logic. It must not use a fixed thirty-day duration as a substitute for a month.

### 19.4 Dataset manifest contract

The data catalogue contains a manifest for each registered dataset.

The current manifest design records source and coverage properties. It also records licensing state and known data gaps.

The manifest distinguishes data origin types. The operator must preserve whether an observation is observed, adjusted, derived, reconstructed, estimated, or interpolated.

The manifest fingerprint supports immutable source identity.

The catalogue can filter by market, instrument, category, resolution, licence status, and time coverage.

A catalogue query reports registered metadata. It does not prove that the physical file is present or complete.

The API response for dataset registration explicitly says that a manifest was registered. It does not say that the data file was uploaded.

This distinction is important. A registered manifest can refer to a source that is missing or inaccessible. The worker must still verify the file and its checksum at load time.

### 19.5 Data acquisition versus registration

The current API has a dataset registration endpoint.

POST /api/datasets registers a manifest.

The response status states that the manifest is registered and that data was not uploaded.

The endpoint does not act as a file upload service.

The current worker loader reads local files from the configured data root.

Do not describe the API as an automated market-data acquisition service.

### 19.6 Timestamp contract

Every dataset must declare its timestamp convention.

The current crypto import requires a numeric timestamp unit when timestamps are numeric.

It requires the timestamp position.

The adapter normalises timestamp columns into a DatetimeIndex.

Naive text timestamps are localised to the declared source timezone.

Timezone-aware timestamps preserve their represented instant.

The worker must not mix timezone-naive values and timezone-aware values.

The experiment windows must use timezone-aware dates.

The data reader uses half-open partition windows. A bar at an end boundary does not belong to both adjacent windows.

### 19.7 Candle availability contract

A candle timestamp does not always mean that all candle values were available at that time.

If a data source stamps a candle at its open, the close is not known at the open.

The platform has explicit handling for this distinction in the FX path.

For fixed intervals, the availability time is the interval end.

For monthly intervals, the availability time is the next calendar-month boundary.

Review each other feature and signal path against the same principle.

A signal that uses a close price must not execute at an earlier time when that close was not yet known.

### 19.8 FX contract

Crypto prices that are not denominated in INR need an explicit FX dataset.

The experiment must reference the FX dataset.

The FX dataset must belong to the crypto environment.

The FX dataset licence must be approved for the worker path.

The FX resolution must match the crypto price dataset where required by the current loader.

The FX category must be valid.

The base currency must match the asset quote currency.

The quote currency must be INR.

The timestamp position must be declared.

The maximum FX staleness must be declared.

The converter uses a backward-only alignment.

A future rate is not valid.

A stale rate is not valid.

A missing rate is not valid.

The system must stop or reject the affected data. It must not silently substitute a future rate.

## 20. Experiment specification and reproducibility detail

### 20.1 Fields currently recorded

The experiment specification includes the following major fields:

| Field | Why it matters |
|---|---|
| Experiment ID | Provides a stable record identifier. |
| Market | Preserves financial separation. |
| Research track | Defines the experiment scope. |
| Algorithm family | Identifies the search or model family. |
| Resolution | Defines the sampling frequency. |
| Dataset IDs | Identifies data inputs. |
| Random seed | Supports deterministic sampling where possible. |
| Git commit | Identifies source revision. |
| Code version | Identifies the declared code version. |
| Train start and end | Defines discovery data. |
| Validation start and end | Defines the selection window. |
| OOS start and end | Defines the OOS evaluation window. |
| Final holdout start and end | Declares the protected interval. |
| Cost model ID | Identifies the cost assumptions. |
| Execution model ID | Identifies the fill assumptions. |
| Objectives | Declares the experiment objective. |
| Compute backend | Identifies the intended compute path. |
| Compute device | Records the selected device field. |
| Parameters | Records the declared model or search parameters. |
| Embargo seconds | Records the declared time gap. |
| Created time | Records experiment creation time. |

The fingerprint binds important fields. A change to the specification changes its identity.

### 20.2 Provenance fields still required

The experiment record does not guarantee the complete environment.

The following fields should become required in the run artefact:

| Missing or incomplete field | Required representation |
|---|---|
| Working tree state | Clean or dirty. |
| Uncommitted changes | Patch hash and stored patch, where permitted. |
| Dependency state | Lockfile hash and package versions. |
| Python runtime | Full version and implementation. |
| Operating system | Name, release, architecture. |
| CPU | Model, core count, thread count. |
| Memory | Physical RAM and memory limit. |
| GPU | Exact model and device ID. |
| Driver | Exact driver version. |
| CUDA | Runtime and toolkit version where present. |
| Compute precision | float32, float64, mixed precision, or other declared type. |
| Threading | BLAS and worker thread configuration. |
| Feature schema | Version and hash. |
| Feature pipeline | Version and parameter set. |
| Corporate-action method | Version and source. |
| FX method | Version and source. |
| Cost schedule | Dated schedule version. |
| Execution model | Parameter hash and calibration record. |
| Resource metrics | CPU time, wall time, RAM and VRAM peaks. |
| Search family | All attempted candidates, including failed trials. |
| Checkpoint | Current generation and random state. |
| Output files | File names and checksums. |

A Git commit and random seed are necessary. They are not sufficient.

### 20.3 Experiment immutability

An experiment specification must not be overwritten after a worker starts.

A correction should create a new experiment ID.

A new feature set should create a new experiment ID.

A change to a data source or checksum should create a new experiment ID.

A change to the cost model should create a new experiment ID.

A change to the execution model should create a new experiment ID.

A change to the validation window should create a new experiment ID.

The old experiment must remain available for audit.

### 20.4 Hypothesis registration

GOAL.md requires the research direction to record a hypothesis, rationale, baseline, source versions, budget, feature set, cost assumptions, validation partitions, metrics, statistical family, expected falsification, and stop condition.

The current experiment schema records several of these items.

It does not guarantee all of them.

Add a separate hypothesis record or extend the experiment specification.

A worker should reject an experiment when its required protocol fields are missing.

### 20.5 Stop conditions

Each research experiment must state a stop condition before execution.

Examples of stop conditions include:

- Data coverage is below the approved minimum.
- The data licence is not approved.
- The missing-bar rate exceeds the declared limit.
- Required instruments are absent.
- The worker exceeds its evaluation budget.
- The worker exceeds its resource limit.
- The objective becomes non-finite.
- The candidate violates a hard risk limit.
- The experiment cannot maintain the declared embargo.
- The worker detects an invalid candidate representation.

These are protocol examples. The research owner must approve the actual thresholds.

## 21. Validation lifecycle and protected data

### 21.1 Lifecycle responsibilities

The validation design separates these actions:

1. Discovery access.
2. Model-selection access.
3. Candidate freeze.
4. OOS authorisation.
5. OOS evaluation.
6. OOS result recording.
7. Final-holdout approval.
8. Final-holdout access.
9. Completion.

The lifecycle stores the evidence that a transition occurred.

The lifecycle does not itself move files or apply operating-system permissions.

### 21.2 Candidate freeze

A candidate must have a stable digest before OOS.

The store records the frozen candidate.

The OOS evaluation must supply the matching digest.

A mismatch is rejected.

The freeze must include every parameter that can change behaviour.

This includes the genome, feature set, model configuration, cost assumptions, and execution assumptions where those assumptions are part of the candidate evaluation contract.

The team must review the digest construction to ensure that no hidden parameter can change after freeze.

### 21.3 OOS authorisation

A job must receive one OOS authorisation at the declared OOS boundary.

The lifecycle records the authorisation.

The store uses a durable transition record.

The code includes a regression test for concurrent OOS authorisation.

The worker records OOS completion only after the OOS result exists.

This protects the lifecycle from certain accidental repeated evaluations.

It does not prove file isolation.

### 21.4 Unknown OOS result

The OOS pass state supports three values:

- True.
- False.
- Unknown.

Unknown is not a pass.

Unknown is not a failure.

Unknown produces an inconclusive classification.

This is correct while the acceptance policy is not defined.

Do not convert an unknown result to True because the return is positive.

Do not convert an unknown result to False because the return is negative before the approved policy is applied.

The policy must state how every metric is evaluated.

### 21.5 Final holdout

The final holdout is not part of discovery.

The final holdout is not part of model selection.

The final holdout must not be used to choose a candidate.

The current system keeps it locked because the OOS acceptance policy is absent.

A separate holdout service must receive only a frozen candidate.

The service must not send raw protected rows to the ordinary worker.

The service should return only the approved metrics and controlled diagnostics.

The data owner must log the access.

### 21.6 Threat model

A secure design must consider more than the worker's normal code path.

The threat model must include:

- A worker that opens a source path directly.
- A worker that reads a parent directory.
- A worker that uses a symbolic link.
- A worker that reads a copied file.
- A worker that requests an unsupported dataset ID.
- A worker that changes the manifest.
- A worker that replays an earlier request.
- Two workers that race for OOS access.
- A process that restarts after authorisation.
- A user that sets the compatibility override.
- A worker that writes protected rows into logs or artefacts.
- A dashboard that exposes protected file paths.
- A database backup that contains protected data.
- A process that reads shared memory or temporary files.

The normal worker must not have operating-system permission to read the protected data.

A Python-level check is not a security boundary.

### 21.7 Compatibility override rule

The explicit partition compatibility override can allow a combined source file to be parsed before rows are clipped.

This is a risk because the process may parse protected rows into memory.

The override is for controlled exploratory work only.

The override must not be used for a final-holdout test.

Production-like validation must remain in strict mode.

The system should record the active partition policy in every job.

## 22. Detailed portfolio and execution model review

### 22.1 Portfolio configuration

The current portfolio configuration declares:

- Market.
- Initial capital.
- Fee assumptions.
- Slippage assumptions.
- Impact coefficient.
- Maximum participation.
- Maximum gross exposure.
- Time zone.
- Cost model ID.
- Execution model ID.
- Optional market fee calculator.

The configuration rejects negative costs.

It rejects invalid participation.

It rejects invalid exposure.

It checks that the fee calculator belongs to the same market.

It checks that the fee calculator model ID matches the declared cost model.

These checks protect against several configuration errors.

They do not prove that the assumptions are realistic.

### 22.2 Current default execution assumptions

The configuration source includes defaults of:

| Parameter | Current code default |
|---|---:|
| Slippage | 5 basis points |
| Impact coefficient | 10 basis points |
| Maximum participation | 5 percent |
| Maximum gross exposure | 100 percent |

The fee basis points are a required configuration field when no market-specific calculator is supplied.

Do not treat these defaults as measured market calibration.

The experiment must record them.

A report must display the assumptions.

A sensitivity test must show how results change under higher costs and lower liquidity.

### 22.3 Decision and execution clock

The simulator selects targets at close t.

The simulator attempts fills at open t+1.

This removes the invalid assumption that a strategy can use the closing value and execute at that same close without a suitable order model.

The simulator uses the previous completed bar volume for the participation and impact limit.

It does not use the current bar's final volume before that volume is available.

### 22.4 Participation limit

The quantity that a worker requests can exceed the participation limit.

The simulator caps the executable quantity using the available historical volume assumption.

A partial fill can result.

The unfilled quantity remains unexecuted.

Review the behaviour when the quantity is zero after flooring.

Review the behaviour when a small position cannot cover fixed fees.

Review the behaviour when multiple symbols compete for cash.

Review the order in which the simulator unwinds existing risk and opens new risk.

Review whether symbol ordering can change the portfolio result.

### 22.5 Slippage and impact

The simulator applies adverse price movement.

It records the reference price.

It records the realised fill price.

It records participation.

It records slippage basis points.

It records impact basis points.

The current model is a declared OHLCV approximation.

It does not contain an order-book queue model.

It does not simulate every trade print.

It does not model measured network and exchange latency.

It does not prove that the requested order could be filled at the simulated price.

### 22.6 NSE whole-share rules

NSE fills use whole shares.

The simulator floors target and participation quantities.

The buy path uses integer affordability logic.

A test checks that NSE quantities are whole shares and crypto quantities can be fractional.

The team must also test:

- A target below one share.
- A target that floors to zero.
- A share price above available cash.
- A fee that exceeds small sell proceeds.
- A split that changes share count.
- A delisting.
- A partial fill followed by a later target.
- A repeated fill record.
- A date boundary.

### 22.7 Crypto spot quantities

The current crypto path supports fractional spot quantities.

The loader converts non-INR quote data by using a registered FX dataset.

It does not support derivative accounting.

The team must not treat a perpetual swap as a spot position.

A future derivative model must record contract multiplier, settlement asset, initial margin, maintenance margin, funding time, funding rate, and liquidation rules.

### 22.8 Fee calculator contract

The fee protocol accepts side, quantity, and price.

The NSE calculator delegates to the existing itemised delivery cost model.

The crypto calculator uses configured maker and taker basis-point values.

The proportional fee calculator is a generic fallback.

Every fee calculator must use a stable model ID.

The model ID must match the experiment's cost model ID.

### 22.9 Missing historical cost state

A fee schedule can change during a long backtest.

A present-day schedule must not be used for every historical date without evidence.

The system needs an effective-dated fee schedule.

Each schedule record should include:

- Market.
- Venue.
- Instrument type.
- Effective start time.
- Effective end time.
- Fee category.
- Rate.
- Minimum fee.
- Maximum fee.
- Tax treatment.
- Source.
- Source date.
- Licence or legal reference.
- Model version.

The execution path must select the schedule that was valid at the fill time.

### 22.10 Accounting invariant test plan

The following invariants should be tested.

| Invariant | Required result |
|---|---|
| Cash conservation | Opening cash plus cash flows equals closing cash under the declared accounting rules. |
| Position conservation | Opening quantity plus fills and corporate actions equals closing quantity. |
| Fee conservation | Reported fees equal the sum of fee entries. |
| Fill idempotency | The same fill ID cannot change the ledger twice. |
| Market separation | One market cannot change another market's cash or positions. |
| No negative cash | Cash does not fall below zero unless a future model explicitly permits borrowing. |
| Long-only state | A long-only cash model cannot create a short position. |
| Fill price validity | A fill price must be positive and finite. |
| Quantity validity | A fill quantity must be positive and finite. |
| Date validity | A fill must occur at the declared execution time. |
| Fee model consistency | The fill uses the declared fee model. |
| Equity reconciliation | Cash plus marked positions equals reported equity. |
| Turnover reconciliation | Turnover matches the executed notional changes. |
| Corporate action consistency | Quantity and value remain consistent after the event. |

## 23. Statistical diagnostic details and review questions

### 23.1 Probabilistic Sharpe Ratio

The PSR helper accepts:

- Observed Sharpe.
- Skewness.
- Kurtosis.
- Number of observations.
- Benchmark Sharpe.

The implementation documents that Sharpe inputs are per-period and not annualised.

The implementation uses a finite-sample variance correction with skewness and Pearson kurtosis.

The default benchmark is zero.

The result is a probability estimate that the true per-period Sharpe exceeds the benchmark under the formula's assumptions.

Review the return frequency.

Review the annualisation conversion before using any displayed annualised value.

Review whether returns are independent or serially correlated.

Review whether overlapping positions create dependent returns.

Review how missing periods are treated.

Review behaviour when a return vector has zero variance.

### 23.2 Deflated Sharpe Ratio

The DSR helper uses an expected maximum Sharpe for the supplied trial family.

The current code documents an independent Gaussian approximation.

The expected maximum calculation uses an approximation for the maximum of independent trials.

The code uses trial Sharpe values at the same sampling frequency.

The caller must ensure that the family is comparable.

This method can be sensitive to the family definition.

If the family omits prior experiments, the multiple-testing correction can be too small.

If the family contains strongly dependent candidates, the independent-trial model can misrepresent the effective number of trials.

The system should record the complete family definition.

The reviewer should test candidate correlation at several levels.

### 23.3 Benjamini-Hochberg correction

The BH helper accepts a p-value sequence and alpha.

It returns adjusted p-values and rejection decisions.

The worker uses the full declared family of successful candidates.

Review:

- Stable candidate ordering.
- Duplicate candidate handling.
- NaN rejection.
- Empty family handling.
- Boundary p-values of zero and one.
- Alpha boundary values.
- Correct monotonic adjusted p-values.
- Correct number of rejected hypotheses.
- Treatment of failed and baseline candidates.

### 23.4 Moving-block bootstrap

The bootstrap helper uses a circular moving-block method.

It estimates an interval for mean periodic return.

The report describes the interval as a TRAIN-only descriptive interval.

It explicitly states that the interval is not a future-profitability estimate.

Review the block length.

Review the number of bootstrap draws.

Review the circular wrap behaviour.

Review serial dependence.

Review whether the block length is chosen before results are observed.

Review whether the reported interval uses the declared confidence level.

Review the meaning of the statistic.

### 23.5 CSCV and PBO

The PBO helper builds combinatorial train and test partitions from return blocks.

It estimates how often the train-selected best candidate ranks below the median in the corresponding test data.

The code requires a finite strategies-by-time matrix.

The block count must be even and at least four.

The family report defaults to eight blocks.

The family report has a maximum PBO candidate limit of 128.

The current bounded selection uses evenly spaced input-order candidates.

It does not select candidates by rank for the subset.

The code preserves an index mapping between the selected subset and the full candidate family.

The report must state that PBO used a bounded subset.

The reviewer must test the effect of candidate order.

The reviewer must test the effect of the subset limit.

The reviewer must compare bounded and complete results on a small fixture.

### 23.6 Statistical diagnostics do not control selection

The current diagnostics are attached to worker results.

They do not change candidate selection.

This separation is deliberate.

A diagnostic value must not be used as an undocumented objective.

A worker must not retry until a diagnostic passes.

A user must not choose a threshold after seeing OOS data.

A new selection rule must be declared in the experiment protocol and tested before it is applied.

### 23.7 Candidate-family completeness

The multiple-testing family must include every candidate that had a chance of selection.

The team must decide how to handle:

- Shipped strategy baselines.
- User-selected baselines.
- Failed objective evaluations.
- Duplicate configurations.
- Candidates rejected by bounds.
- Candidates evaluated in earlier runs.
- Reused search budgets.
- Candidate family overlap between experiments.
- Repeated experiments on the same data.

A family that omits unsuccessful or inconvenient attempts can understate selection bias.

The experiment store should preserve all attempts.

### 23.8 Statistical review exit condition

The method review is complete only when:

1. The formulas are documented.
2. Inputs and frequency assumptions are documented.
3. Independent reference fixtures exist.
4. Edge cases pass.
5. Correlation sensitivity is measured.
6. Candidate family scope is approved.
7. The output meaning is documented.
8. A reviewer signs the method review.
9. The method version is recorded in future experiments.

## 24. Evolutionary search and candidate lineage

### 24.1 Conventional search

The conventional search layer supports random and grid search.

It also supports differential evolution.

It supports Optuna TPE when its dependency is available.

It has a separate Parzen-style heuristic.

The random search uses the experiment's seeded generator.

Grid search is capped.

Differential evolution uses population vectors and mutation and crossover.

The DE worker records candidate identifiers and parent metadata.

Failed objective attempts remain in the attempt ledger.

The hybrid optimizer uses a declared per-method budget.

The hybrid method returns candidate traces from each method.

### 24.2 Equal-budget policy

The current hybrid optimizer uses equal per-method budgets.

The DE method validates its population and generation count against the expected evaluation budget.

A budget mismatch is rejected.

This is important because a search method must not receive more candidate evaluations while claiming an equal comparison.

The team must still define what counts as one evaluation.

The budget should include failed candidate attempts if the objective was called.

The budget should not hide duplicate objective calls.

Runtime and compute use should also be recorded.

### 24.3 GP candidate representation

The GP engine uses a bounded numerical AST.

The representation stores expression nodes.

The engine validates feature indices and supported operators.

The interpreter executes only known nodes.

The engine does not compile an arbitrary Python source string.

Candidate lineage records parent IDs and generation information.

The GP worker archives evaluated candidates.

The current grammar does not support the full target Boolean or control-flow language.

### 24.4 Neuroevolution candidate representation

The neural worker uses a dense network with a fixed topology.

The worker stores a flattened parameter representation.

The worker generates mirrored perturbations.

The worker batches candidate inference.

The worker records candidate IDs, ancestry, generation and candidate scores.

The network topology is fixed.

A new topology representation must preserve bounded memory and execution time.

### 24.5 Composition candidate representation

A composition is a structured list of known components.

Each component has an approved role.

Each component has numeric configuration.

The registry defines the available components.

The worker mutates composition structure.

The worker keeps a valid entry and exit structure.

Invalid mutations preserve the parent or produce a failure record, depending on the path.

The registry does not execute arbitrary user code.

### 24.6 NSGA-II candidate representation

The Pareto module supports a generic genome object and objective vector.

It stores parent metadata.

It supports non-dominated sorting.

It supports crowding distance.

It selects survivors using rank and crowding distance.

The current platform worker uses existing-strategy parameter genomes.

The generic NSGA-II core can accept a caller-supplied genome. This does not mean that the platform has an integrated cross-family genome interface.

### 24.7 Candidate identity

Each candidate should be identified by a stable digest of its full effective configuration.

The digest should include:

- Genome representation.
- Strategy or model identity.
- Feature configuration.
- Data scope.
- Cost model.
- Execution model.
- Objective definition.
- Relevant worker configuration.

The digest should not include a random candidate ID as a substitute for configuration identity.

Two equivalent genomes with different candidate IDs must be detectable as duplicates.

### 24.8 Lineage completeness

A candidate record should answer:

- Which experiment created it?
- Which generation created it?
- Which worker created it?
- Which operator created it?
- Which parent candidates did it use?
- Which mutation parameters were used?
- Which crossover parameters were used?
- Which random seed or generator state was used?
- Which exact genome was evaluated?
- Which data partition was used?
- Which score was returned?
- Did evaluation fail?
- Was it selected?
- Was it frozen?
- Was it sent to OOS?
- What classification did it receive?

Lineage JSON exists.

A full common lineage schema across all candidate families still needs an integration review.

## 25. API, dashboard, and operational boundaries

### 25.1 API route inventory

The current API exposes the routes below.

| Method | Path | Purpose | Current scope |
|---|---|---|---|
| GET | / | Return dashboard HTML. | Local dashboard. |
| GET | /api/health | Return API health status. | Basic health response. |
| GET | /api/markets | Return market definitions and account metadata. | Market-scoped. |
| GET | /api/runners | Return registered runner names. | Allow-listed names only. |
| GET | /api/compare | Compare two to ten unique experiment IDs. | Same-market only; no cross-market financial aggregation. |
| GET | /api/jobs | List job records. | Stored job state. |
| POST | /api/jobs | Queue a registered runner. | JSON parameters and allow-listed name. |
| GET | /api/jobs/{id} | Return one job record. | Persisted job information. |
| POST | /api/jobs/{id}/cancel | Request cooperative cancellation. | Runner must check cancellation. |
| GET | /api/strategies | Return registered existing strategy descriptors. | Discovery only. |
| GET | /api/datasets | List registered datasets. | Metadata; not data upload. |
| POST | /api/datasets | Register a data manifest. | Does not upload the physical file. |
| GET | /api/experiments | List experiments. | Persisted records. |
| POST | /api/experiments | Create an experiment record. | Does not start the job. |
| GET | /api/experiments/{id} | Return one experiment and related records. | Persisted record. |

The route list reflects the inspected API source.

The API also validates request content type and request size for JSON routes.

It returns conflict status for duplicate or conflicting records.

It returns bad request status for invalid input.

It returns not found status for missing records.

### 25.2 Experiment comparison endpoint

The API has a comparison route.

The route requires between two and ten experiment IDs.

The IDs must be unique.

The route rejects a comparison that mixes different financial markets.

The output keeps metrics separated by partition.

The output does not compute a combined financial aggregate.

This is an implemented API feature.

The visual dashboard still needs a complete experiment comparison view.

### 25.3 Experiment creation is not job execution

POST /api/experiments creates an experiment record.

The response says created_not_started.

The client must submit a job separately.

POST /api/jobs queues a registered runner.

The API must not imply that an experiment is running merely because its record exists.

### 25.4 Dataset registration is not file upload

POST /api/datasets registers a manifest.

The response says manifest_registered_not_data_uploaded.

The file must exist in the configured data store.

The worker verifies the registered file when it loads the data.

The API must not label manifest registration as successful data ingestion.

### 25.5 Job runner allow-list

The job API accepts only registered runner names.

The client cannot submit an arbitrary Python function.

This reduces the API's execution scope.

The runner must still validate its parameters.

The runner must still enforce market and data scope.

The runner must still use the declared experiment specification.

### 25.6 Request boundary

The API reads JSON request bodies.

The API checks content type.

The API limits request size.

The API maps common exceptions to HTTP response codes.

Review every exception path.

Do not return secret values, file content, internal paths, credentials, or full tracebacks to clients.

### 25.7 Local server

The application uses Python's standard-library WSGI server.

The default host is 127.0.0.1.

A non-loopback host requires the explicit remote-enable flag.

The application error message says that authentication must be configured first.

The remote-enable flag does not add authentication.

Do not use that flag as a security solution.

### 25.8 Current UI limitations

The API and dashboard are not a complete monitoring product.

The remaining UI scope includes:

- Visual experiment comparisons.
- Candidate family comparisons.
- Population size and generation state.
- Fitness distribution.
- Population diversity.
- Candidate lineage browser.
- Pareto front visualisation.
- Data coverage matrix.
- Missing data report.
- Resource use charts.
- CPU and GPU telemetry.
- RAM and VRAM telemetry.
- Checkpoint status.
- Full artefact export.
- Full method and protocol report.
- Data source licence state.
- Validation access history.

The dashboard must show unavailable data as unavailable.

It must not render zero when the backend has no value.

It must not present a missing GPU metric as zero GPU use.

## 26. Job manager behaviour and recovery

### 26.1 Job states

The job manager defines these terminal and active states:

| State | Meaning |
|---|---|
| queued | The job record exists and the job waits for a worker. |
| running | A worker is executing the job. |
| succeeded | The worker returned a result. |
| failed | The worker raised an error or the job was interrupted. |
| cancelled | The job stopped after a cancellation request. |

The store also records job events.

### 26.2 Queue capacity

The manager has a maximum worker count.

The manager has a maximum queued job count.

The manager checks active jobs before it accepts new work.

The manager rejects submissions when capacity is full.

This prevents unlimited thread submission through the API.

### 26.3 Cooperative cancellation

A runner receives a JobContext.

The context exposes a cancellation request.

The runner can call check_cancelled.

The manager cannot safely stop arbitrary Python code at an arbitrary instruction.

The runner must call the cancellation method at safe points.

A long-running operation that never checks cancellation may not stop promptly.

Every new worker must add cancellation checks inside long loops.

### 26.4 Error handling

The manager stores a failed state.

The manager stores a bounded error message.

It does not store a full traceback in the public job record.

The detailed internal log should be available to authorised maintainers without exposing secrets.

### 26.5 Restart handling

The store can find queued and running jobs after restart.

It marks these jobs as interrupted.

The computation is not restored.

The job must be resubmitted.

The lifecycle record remains available.

A resubmitted job must have a clear relationship to the previous job.

It must not silently reuse a stale candidate or incomplete result.

### 26.6 Checkpoint design

A future checkpoint must include more than the current generation number.

It must include:

- Experiment fingerprint.
- Candidate family fingerprint.
- Worker version.
- Data manifest fingerprints.
- Feature pipeline fingerprint.
- Cost and execution model IDs.
- Generation or trial number.
- Population genomes.
- Candidate IDs.
- Candidate ancestry.
- Fitness records.
- Failed trial records.
- Random generator state.
- Optimiser internal state.
- Resource state required for safe restore.
- Checkpoint checksum.

A checkpoint from a different experiment fingerprint must be rejected.

A checkpoint from a different worker version must be migrated or rejected.

The worker must not resume after the underlying data or cost model changes.

## 27. Detailed test inventory

The audited tree contains twelve focused research-platform test files.

The file inspection found 154 test function definitions. This is a count of function definitions. Pytest parameterisation, if added, can produce a different runtime case count.

The dedicated CI workflow runs the files matching tests/unit/test_research_platform*.py.

### 27.1 Foundational platform tests

File: tests/unit/test_research_platform.py

The file has 29 test function definitions.

| Test | Main behaviour |
|---|---|
| test_market_budgets_are_separate_and_market_fill_cannot_cross | Keeps separate market budgets and blocks cross-market fills. |
| test_market_ledger_accounting_and_duplicate_fill_guard | Checks ledger accounting and duplicate fill protection. |
| test_market_ledger_pays_flat_sell_fees_from_cash_when_they_exceed_notional | Tests fee payment when fixed sell charges exceed the fill notional. |
| test_nse_fills_require_whole_shares_but_crypto_allows_fractional_units | Tests whole NSE shares and fractional crypto quantities. |
| test_fill_rejects_naive_timestamp_and_invalid_fee | Rejects naive fill times and invalid fees. |
| test_dataset_manifest_fingerprint_and_availability_filters | Tests manifest identity and catalogue filtering. |
| test_dataset_manifest_records_gaps_and_requires_timezone_aware_times | Tests known gaps and timezone-aware coverage. |
| test_experiment_fingerprint_binds_market_data_seed_and_cost_assumptions | Tests important experiment fingerprint inputs. |
| test_split_plan_enforces_chronology_and_embargo | Rejects invalid window order and embargo. |
| test_validation_lifecycle_blocks_leakage_and_opens_holdout_once | Tests lifecycle access rules and one-time holdout access. |
| test_failed_oos_cannot_unlock_final_holdout | Prevents a failed OOS result from opening the holdout. |
| test_validation_lifecycle_persists_job_scoped_transitions_across_store_instances | Tests durable lifecycle recovery. |
| test_validation_lifecycle_serializes_concurrent_oos_authorizations | Tests concurrent OOS authorisation. |
| test_validation_lifecycle_rejects_out_of_order_persisted_transitions | Rejects invalid persisted lifecycle order. |
| test_experiment_store_is_append_only_and_persists_lineage | Tests candidate and event persistence. |
| test_compute_engine_cpu_batch_matches_reference | Tests CPU batch output against a reference. |
| test_compute_engine_auto_backend_is_consistent | Tests automatic backend behaviour. |
| test_nse_exposed_test_period_cannot_be_declared_final_holdout | Blocks reuse of exposed NSE history as a clean final holdout. |
| test_market_ledger_rejects_non_seed_opening_cash | Rejects an invalid initial cash state. |
| test_experiment_spec_records_and_enforces_partition_embargo | Tests experiment-level embargo. |
| test_purged_walk_forward_split_removes_labels_crossing_validation | Removes overlapping labels. |
| test_purged_walk_forward_split_applies_embargo_around_validation | Applies the declared embargo to the split. |
| test_purged_walk_forward_split_rejects_unaligned_or_naive_timestamps | Rejects invalid timestamp alignment. |
| test_experiment_spec_rejects_fractional_embargo_seconds | Requires integer embargo seconds. |
| test_compute_engine_batched_dense_predictions_match_scalar_networks | Tests batched dense-network parity. |
| test_neuroevolution_batched_inference_matches_scalar_trace | Tests neural evolution inference parity. |
| test_compute_engine_auto_falls_back_after_runtime_gpu_failure | Tests automatic CPU fallback. |
| test_compute_engine_explicit_cupy_mode_does_not_silently_fallback | Ensures explicit CuPy mode does not silently change backend. |
| test_dataset_catalog_distinguishes_source_and_worker_partition_coverage | Separates original source coverage from worker partition coverage. |

### 27.2 API tests

File: tests/unit/test_research_platform_api.py

The file has 18 test function definitions.

| Test | Main behaviour |
|---|---|
| test_research_api_health_markets_and_dashboard | Tests health, market routes, and dashboard response. |
| test_research_api_creates_and_lists_real_experiment_records | Tests persisted experiment creation and listing. |
| test_research_api_market_filter_and_cross_market_rejection | Tests market filtering and separation. |
| test_research_api_duplicate_record_returns_conflict | Tests duplicate record handling. |
| test_research_api_rejects_invalid_timezones_and_non_json_content | Tests input format and timezone validation. |
| test_research_api_blocks_unapproved_and_insufficient_dataset_coverage | Rejects unsuitable data registration for an experiment. |
| test_research_api_rejects_cross_market_dataset_reference | Rejects cross-market dataset use. |
| test_research_api_exposes_registered_existing_strategy_catalogue | Exposes registered strategy metadata. |
| test_research_api_validates_selected_existing_strategy_name | Rejects an unknown strategy. |
| test_research_api_rejects_embargo_that_partitions_do_not_respect | Checks embargo and partition boundaries. |
| test_api_creates_validated_genetic_programming_experiment | Tests valid GP experiment creation. |
| test_api_rejects_unbounded_genetic_programming_budget | Rejects an unbounded GP configuration. |
| test_experiment_comparison_is_market_scoped_and_keeps_partition_metrics_separate | Tests same-market comparison and partition separation. |
| test_experiment_comparison_rejects_mixed_market_ids | Rejects cross-market comparisons. |
| test_api_creates_validated_pareto_search_experiment | Tests Pareto experiment creation. |
| test_api_rejects_single_objective_pareto_experiment | Requires a valid multi-objective request. |
| test_api_creates_hybrid_optimizer_experiment_with_method_budgets | Tests hybrid method budget creation. |
| test_api_rejects_hybrid_de_budget_mismatch | Rejects an invalid DE budget. |

### 27.3 API job tests

File: tests/unit/test_research_platform_api_jobs.py

The file has 10 test function definitions.

| Test | Main behaviour |
|---|---|
| test_jobs_api_lists_runners_queues_jobs_and_returns_details | Tests runner listing, submission, and job detail. |
| test_jobs_api_cancellation_route_requests_cooperative_stop | Tests cancellation request handling. |
| test_jobs_api_rejects_unknown_runner_and_non_object_parameters | Rejects unknown workers and invalid parameters. |
| test_jobs_api_returns_service_unavailable_without_manager | Handles missing job manager. |
| test_jobs_api_routes_optimizer_family_to_optimizer_runner_only | Routes search jobs to the approved runner. |
| test_jobs_api_routes_genetic_programming_to_registered_gp_runner | Routes GP jobs. |
| test_jobs_api_routes_neuroevolution_to_registered_neural_worker | Routes neural jobs. |
| test_jobs_api_routes_strategy_composition_to_registered_composition_runner | Routes composition jobs. |
| test_jobs_api_routes_pareto_search_to_registered_nsga2_worker | Routes Pareto jobs. |
| test_jobs_api_routes_hybrid_search_to_existing_strategy_optimizer | Routes hybrid search jobs. |

### 27.4 Catalogue tests

File: tests/unit/test_research_platform_catalog.py

The file has 3 test function definitions.

| Test | Main behaviour |
|---|---|
| test_existing_strategy_registry_discovers_real_catalogue_entries | Discovers entries from the existing catalogue. |
| test_existing_strategy_registry_builds_shipped_default | Builds the declared default strategy configuration. |
| test_existing_strategy_registry_rejects_unknown_parameter_fields | Rejects unknown parameter names. |

### 27.5 Candidate classification tests

File: tests/unit/test_research_platform_classification.py

The file has 4 test function definitions.

| Test | Main behaviour |
|---|---|
| test_candidate_classification_covers_required_evidence_states | Tests the supported classification states. |
| test_candidate_classification_separates_historical_and_independent_oos | Separates exposed history from independent confirmation. |
| test_classification_report_preserves_unknown_evidence | Retains unknown evidence. |
| test_candidate_evidence_rejects_non_boolean_gate_values | Rejects invalid evidence types. |

### 27.6 Evaluation tests

File: tests/unit/test_research_platform_evaluation.py

The file has 5 test function definitions.

| Test | Main behaviour |
|---|---|
| test_existing_strategy_runner_evaluates_three_stages_without_holdout | Tests TRAIN, VALIDATION, and OOS evaluation without final-holdout access. |
| test_existing_strategy_runner_requires_matching_cost_model_and_track_scope | Checks cost model and research track. |
| test_existing_strategy_runner_refuses_multi_symbol_individual_track | Enforces the individual track scope. |
| test_existing_strategy_runner_requires_matching_execution_model | Checks execution model identity. |
| test_existing_strategy_runner_rejects_unregistered_extra_bar_symbols | Rejects extra unregistered symbols. |

### 27.7 Job manager tests

File: tests/unit/test_research_platform_jobs.py

The file has 7 test function definitions.

| Test | Main behaviour |
|---|---|
| test_job_manager_persists_success_result_and_progress_events | Tests successful job persistence. |
| test_job_manager_persists_runner_failure_without_traceback | Tests bounded failure reporting. |
| test_job_manager_supports_cooperative_cancellation | Tests cancellation checkpoints. |
| test_job_manager_enforces_worker_queue_capacity | Tests worker and queue limits. |
| test_job_manager_rejects_unknown_runner_names | Rejects unregistered runners. |
| test_store_marks_queued_and_running_jobs_interrupted_after_restart | Tests restart interruption status. |
| test_job_manager_rejects_concurrent_duplicate_experiment_runner | Prevents duplicate active work for the same experiment and runner. |

### 27.8 Metrics tests

File: tests/unit/test_research_platform_metrics.py

The file has 2 test function definitions.

| Test | Main behaviour |
|---|---|
| test_portfolio_metrics_use_explicit_periods_per_year | Requires explicit annualisation frequency. |
| test_portfolio_metrics_reject_missing_frequency_and_invalid_equity | Rejects missing frequency and invalid equity values. |

### 27.9 Model tests

File: tests/unit/test_research_platform_models.py

The file has 6 test function definitions.

| Test | Main behaviour |
|---|---|
| test_constant_volume_has_zero_z_score_without_erasing_warmup_rows | Tests zero-variance volume handling and warm-up preservation. |
| test_model_feature_panel_maps_predictions_to_exact_instrument_rows | Checks prediction alignment. |
| test_model_feature_panel_keeps_partition_boundary_half_open | Tests half-open model boundaries. |
| test_model_partition_uses_same_portfolio_accounting_and_returns_metrics | Uses the portfolio simulator for model evaluation. |
| test_model_feature_panel_rejects_misaligned_multi_asset_calendars | Rejects inconsistent multi-asset calendars. |
| test_allow_listed_composition_components_produce_causal_long_flat_scores | Tests causal scores from registered composition components. |

### 27.10 Runner tests

File: tests/unit/test_research_platform_runners.py

The file has 28 test function definitions.

| Test | Main behaviour |
|---|---|
| test_experiment_spec_record_round_trip_preserves_fingerprint | Tests experiment serialisation and fingerprint stability. |
| test_nse_default_runner_config_uses_fee_adapter_and_declared_execution_settings | Tests NSE cost and execution configuration. |
| test_existing_strategy_job_runner_executes_and_persists_partition_results | Tests existing-strategy job results. |
| test_default_runner_rejects_missing_execution_assumptions | Rejects missing execution assumptions. |
| test_ohlcv_normalizer_converts_numeric_timestamp_columns_to_datetime_index | Normalises numeric timestamps. |
| test_ohlcv_normalizer_localizes_naive_text_timestamps_to_source_timezone | Localises naive timestamps. |
| test_ohlcv_normalizer_preserves_aware_timestamp_instants | Preserves timezone-aware instants. |
| test_crypto_loader_verifies_registered_source_hash_and_quote_currency | Checks source hash and quote currency. |
| test_fx_bar_close_times_use_fixed_and_calendar_resolution_boundaries | Tests candle availability timing. |
| test_crypto_loader_converts_usdt_using_prior_fx_close_only | Uses prior FX rates for conversion. |
| test_existing_strategy_optimizer_searches_train_selects_validation_then_evaluates_oos | Tests the three-stage optimiser flow. |
| test_optimizer_runner_rejects_unsupported_or_missing_search_settings | Rejects unsupported or missing search settings. |
| test_differential_evolution_optimizer_persists_resolvable_parent_lineage | Tests DE lineage resolution. |
| test_genetic_programming_worker_persists_lineage_selects_validation_and_evaluates_oos | Tests GP lineage and partition stages. |
| test_genetic_programming_worker_rejects_missing_model_settings | Rejects incomplete GP settings. |
| test_neuroevolution_worker_persists_mirrored_candidates_and_evaluates_oos | Tests mirrored neural candidates and OOS. |
| test_neuroevolution_worker_rejects_odd_or_unbounded_population | Rejects invalid neural population settings. |
| test_strategy_composition_worker_evolves_registered_components_and_evaluates_oos | Tests composition worker stages. |
| test_strategy_composition_worker_rejects_missing_component_settings | Rejects incomplete composition settings. |
| test_pareto_search_worker_persists_nsga2_front_and_oos_evaluation | Tests Pareto front and OOS evaluation. |
| test_pareto_search_worker_rejects_single_objective_settings | Rejects single-objective Pareto settings. |
| test_hybrid_optimizer_ensembles_random_de_and_tpe_before_validation | Tests hybrid ensemble selection. |
| test_hybrid_optimizer_rejects_incompatible_method_budget | Rejects incompatible method budgets. |
| test_hybrid_runner_merges_random_de_and_tpe_candidate_traces | Tests candidate trace merging. |
| test_hybrid_runner_rejects_missing_method_or_incorrect_de_budget | Rejects missing methods and invalid DE budget. |
| test_registered_loader_uses_physical_non_holdout_copy_only | Tests safe partition loading. |
| test_registered_loader_defaults_to_strict_partition_mode | Tests strict default partition mode. |
| test_registered_loader_rejects_unrecognised_partition_policy | Rejects invalid partition policy. |

Note: The source file contains 28 listed test definitions in this inventory. The overall test function count in this report must be read from the exact per-file definitions. The original count of 154 is not a reliable total because the runner file contributes 28 definitions rather than 26. The verified total is 156.

### 27.11 Search and simulation tests

File: tests/unit/test_research_platform_search.py

The file has 43 test function definitions.

| Test | Main behaviour |
|---|---|
| test_random_grid_and_parzen_search_are_seeded_and_budgeted | Tests deterministic search budgets. |
| test_differential_evolution_does_not_replay_objective | Prevents untracked objective replay. |
| test_optimizer_records_failures_without_silent_candidate_loss | Retains failed candidates. |
| test_genetic_programming_interpreter_and_bounded_evolution | Tests safe GP execution and search bounds. |
| test_genetic_programming_rejects_unknown_or_invalid_feature_nodes | Rejects invalid GP nodes. |
| test_neuroevolution_runs_bounded_dense_network_candidates | Tests bounded neural evolution. |
| test_strategy_composition_requires_entry_exit_and_evolves_registry_components | Tests composition constraints. |
| test_pareto_fronts_and_nsga2_selection_keep_tradeoffs | Tests Pareto rank and trade-offs. |
| test_benjamini_hochberg_and_bootstrap_are_reproducible | Tests FDR and bootstrap determinism. |
| test_pbo_cscv_returns_valid_probability_and_split_count | Tests PBO output and fold count. |
| test_portfolio_simulator_executes_next_open_with_costs_and_separate_capital | Tests next-open fills and costs. |
| test_portfolio_simulator_rejects_cross_market_or_bad_target_weights | Rejects invalid market or target weights. |
| test_crypto_local_adapter_records_licence_review_and_file_hash | Tests crypto licence status and source hash. |
| test_batch_population_fitness_matches_manual_long_flat_accounting | Compares batched fitness with scalar accounting. |
| test_batch_population_fitness_falls_back_after_cuda_allocation_failure | Tests fallback after allocation failure. |
| test_batch_population_fitness_rejects_misaligned_forward_returns | Rejects misaligned return data. |
| test_market_specific_fee_calculators_keep_nse_and_crypto_costs_separate | Tests distinct market fee models. |
| test_fx_conversion_uses_only_prior_rates_and_normalises_timezones | Tests backward FX conversion. |
| test_fx_conversion_rejects_future_stale_or_mismatched_rates | Rejects invalid FX rates. |
| test_point_in_time_features_are_invariant_to_future_price_changes | Tests price feature causality. |
| test_forward_labels_have_explicit_end_timestamps_and_are_separate | Tests separate forward labels. |
| test_probabilistic_and_deflated_sharpe_adjust_for_trial_family | Tests PSR and DSR output. |
| test_sharpe_diagnostics_reject_invalid_sampling_inputs | Rejects invalid Sharpe inputs. |
| test_candidate_family_report_records_fdr_dsr_and_pbo_together | Tests combined family diagnostics. |
| test_candidate_family_report_rejects_misaligned_search_records | Rejects misaligned candidate records. |
| test_nsga2_runs_generations_and_preserves_multiple_pareto_tradeoffs | Tests NSGA-II generation behaviour. |
| test_nsga2_rejects_invalid_initial_objective_population | Rejects invalid initial populations. |
| test_optuna_tpe_search_respects_budget_and_seed_when_installed | Tests seeded TPE budget. |
| test_portfolio_execution_volume_limit_uses_previous_completed_bar | Tests participation timing. |
| test_differential_evolution_keeps_failed_trials_in_attempt_ledger | Keeps failed DE trials. |
| test_optuna_tpe_search_records_sampler_seed_and_attempts | Records TPE sampler state. |
| test_ohlcv_quality_rejects_open_outside_bar_range_and_bad_prices | Rejects invalid OHLCV values. |
| test_nse_daily_quality_policy_rejects_close_return_at_twenty_percent | Tests the NSE daily threshold. |
| test_crypto_adapter_does_not_apply_nse_twenty_percent_return_cap | Keeps the NSE threshold out of crypto. |
| test_candidate_family_report_uses_bounded_unranked_pbo_subset | Tests bounded PBO selection. |
| test_candidate_family_report_skips_pbo_for_short_return_history | Handles short return histories. |
| test_candidate_family_report_from_returns_derives_per_period_psr_and_multiple_tests | Derives per-period PSR and family diagnostics. |
| test_candidate_family_report_from_returns_rejects_misaligned_series | Rejects misaligned return vectors. |
| test_candidate_family_report_from_returns_validates_pbo_configuration | Validates PBO settings. |
| test_materialized_partition_contains_no_final_holdout_rows | Checks materialised safe data. |
| test_non_holdout_partition_reader_rejects_checksum_tampering | Rejects modified data files. |
| test_partition_materializer_rejects_naive_or_empty_cutoff | Rejects invalid partition cut-offs. |
| test_non_holdout_partition_reader_rejects_coverage_metadata_drift | Rejects manifest coverage drift. |

Note: The source listing contains 43 test definitions in this inventory. The count of 40 is incorrect. The corrected total in the twelve files is 159 test function definitions.

### 27.12 Signal tests

File: tests/unit/test_research_platform_signals.py

The file has 4 test function definitions.

| Test | Main behaviour |
|---|---|
| test_existing_strategy_adapter_generates_close_time_long_flat_signals | Tests close-time signal generation. |
| test_existing_strategy_signals_are_invariant_to_future_bar_changes | Tests signal causality. |
| test_equal_weight_signal_targets_remain_market_neutral_to_inactive_assets | Tests inactive asset handling. |
| test_strategy_signal_adapter_rejects_unknown_config_fields | Rejects unknown strategy configuration. |

### 27.13 Corrected test inventory count

The full source-derived test function count is:

| Test file | Function definitions |
|---|---:|
| test_research_platform.py | 29 |
| test_research_platform_api.py | 18 |
| test_research_platform_api_jobs.py | 10 |
| test_research_platform_catalog.py | 3 |
| test_research_platform_classification.py | 4 |
| test_research_platform_evaluation.py | 5 |
| test_research_platform_jobs.py | 7 |
| test_research_platform_metrics.py | 2 |
| test_research_platform_models.py | 6 |
| test_research_platform_runners.py | 28 |
| test_research_platform_search.py | 43 |
| test_research_platform_signals.py | 4 |
| **Total** | **159** |

This count is based on function definitions in the audited source. It is not a claim about the exact number of test cases executed after parametrisation or plugin expansion.

### 27.14 Test coverage that remains missing

The focused suite does not establish all of the following:

- Full historical point-in-time universe correctness.
- Full provider licence compliance.
- Complete missing-session detection.
- Corporate-action correctness.
- Full tax-lot correctness.
- Crypto derivatives accounting.
- Historical funding correctness.
- Historical fee schedule correctness.
- Tick-level fill correctness.
- Order-book queue simulation.
- Measured latency.
- Every legacy strategy adapter.
- Boolean GP behaviour.
- Neural topology mutation.
- Mixed-genome co-evolution.
- Secure OS-level holdout isolation.
- Complete remote authentication.
- Target GPU compatibility.
- End-to-end GPU portfolio simulation.
- Resumable checkpoint recovery.
- Distributed job execution.
- Long-run resource stability.
- Four-track real-market evidence.

These items require new tests or external evidence.

## 28. Missing tests by subsystem

This section turns the review findings into specific test requirements.

### 28.1 Data ingestion tests

Add tests for:

- Duplicate timestamps.
- Out-of-order rows.
- Missing market sessions.
- Unexpected market sessions.
- Duplicate candles.
- Gaps larger than one interval.
- A candle with zero volume.
- A candle with negative volume.
- A candle with a zero price.
- A candle with a negative price.
- An extreme but valid price movement.
- An invalid corporate-action adjustment.
- A symbol rename.
- A delisted instrument.
- A suspended instrument.
- A stale source file.
- A modified source file.
- An absent source file.
- An invalid manifest hash.
- An unapproved licence.
- An expired licence.
- A provider schema change.
- A daylight-saving transition for a source that uses daylight-saving time.

Each test must state whether the expected behaviour is reject, quarantine, or accept with a quality warning.

### 28.2 Feature causality tests

Add tests for:

- A feature that uses a close price.
- A feature that uses a candle high.
- A feature that uses a candle low.
- A feature that uses volume.
- A feature with a rolling window.
- A feature with a missing prior bar.
- A feature after a market holiday.
- A feature with a delayed publication.
- A feature with a later revision.
- A feature that uses an FX conversion.
- A feature with a future FX candle.
- A feature that joins earnings data.
- A feature that joins a news article.
- A feature that joins macro data.
- A feature that joins on-chain data.

Change future data and confirm that earlier features do not change.

### 28.3 Validation tests

Add tests for:

- A sample label ending at the validation start.
- A sample label crossing the validation start.
- A sample label ending during embargo.
- A sample label ending exactly at the embargo boundary.
- An overlapping feature lookback.
- A nested walk-forward split.
- A rolling window.
- An expanding window.
- A missing label end.
- A timezone mismatch.
- A daylight-saving transition.
- A short validation window.
- A final-holdout access attempt from a TRAIN worker.
- A final-holdout access attempt from a VALIDATION worker.
- A final-holdout access attempt from an OOS worker.
- A second holdout access request.
- A replayed candidate digest.
- A modified frozen candidate.

### 28.4 Portfolio tests

Add tests for:

- A price gap between close and next open.
- A limit-up or limit-down session.
- A market halt.
- A partial fill.
- A zero-volume bar.
- A missing next-open price.
- A fee schedule change.
- A minimum fee.
- A minimum notional.
- A fee greater than a tiny fill value.
- An NSE corporate action.
- A crypto funding payment.
- A short position where the current model must reject it.
- A derivative instrument where the current model must reject it.
- A position with a stale mark.
- A cash reconciliation failure.
- A position reconciliation failure.
- A repeated fill event.
- A repeated corporate action.
- A fill that crosses a market boundary.

### 28.5 Optimiser tests

Add tests for:

- A parameter with one valid value.
- A parameter with non-finite bounds.
- An integer parameter.
- A categorical parameter.
- A failed objective.
- A non-finite objective.
- A cancelled objective.
- A repeated candidate.
- A candidate budget boundary.
- A generation budget boundary.
- A run interrupted after a candidate.
- A run resumed from a checkpoint.
- A changed dataset after a checkpoint.
- A changed cost model after a checkpoint.
- A changed feature schema after a checkpoint.

### 28.6 GP tests

Add tests for:

- Boolean literals.
- Numeric literals.
- Numeric comparisons.
- Logical AND.
- Logical OR.
- Logical NOT.
- Conditional nodes.
- Invalid type combinations.
- Divide-by-zero.
- Overflow.
- NaN input.
- Missing feature input.
- Maximum expression depth.
- Maximum expression node count.
- Mutation that violates type rules.
- Crossover that violates type rules.
- Deterministic generation.
- Safe timeout.
- Cancellation.

### 28.7 Neural tests

Add tests for:

- Minimum hidden size.
- Maximum hidden size.
- Maximum parameter count.
- Invalid parameter vector length.
- NaN weights.
- Infinite weights.
- Stable activation output.
- Empty batch.
- One-row batch.
- Large batch.
- CPU/GPU parity.
- Runtime GPU failure.
- Topology mutation.
- Invalid topology.
- Checkpoint recovery.
- Deterministic seed behaviour.

### 28.8 Statistics tests

Add tests for:

- Constant returns.
- All-positive returns.
- All-negative returns.
- Very small sample size.
- Large sample size.
- Serial correlation.
- Correlated candidates.
- Identical candidates.
- Near-identical candidates.
- Missing values.
- Non-finite values.
- Extreme skewness.
- Extreme kurtosis.
- A single candidate family.
- A very large candidate family.
- Candidate order permutation.
- PBO subset sensitivity.
- Bootstrap block sensitivity.
- Bootstrap seed reproducibility.
- Reference implementation parity.

## 29. Operational runbook extensions

The current runbook gives basic setup and launch guidance.

This audit recommends the following operational controls.

### 29.1 Before a worker starts

The operator must check:

1. The experiment has the expected market.
2. The experiment has the expected track.
3. Every dataset is registered.
4. Every data file exists.
5. Every source hash matches.
6. Every licence state is approved for the intended work.
7. Every dataset covers the required time windows.
8. The partition policy is strict.
9. The final holdout path is not available to the normal worker.
10. The cost model ID matches the fee calculator.
11. The execution model ID matches the run configuration.
12. The random seed is fixed.
13. The compute backend is declared.
14. The job budget is within limits.
15. The working tree state is recorded.
16. The experiment hypothesis and stop condition are recorded.

### 29.2 During a worker

The worker must:

- Record its start event.
- Record its experiment fingerprint.
- Record the active dataset fingerprints.
- Record the feature configuration.
- Record the active search budget.
- Record all candidate attempts.
- Record failed evaluations.
- Check cancellation at safe points.
- Monitor time and resource limits.
- Keep TRAIN data separate from VALIDATION and OOS.
- Avoid loading protected files.
- Record stage transitions.
- Record its final status.

### 29.3 After a worker

The operator must check:

- Job status.
- Error state.
- Candidate count.
- Failed candidate count.
- Search budget usage.
- Validation selection.
- Candidate freeze digest.
- OOS evaluation ID.
- OOS result state.
- Data quality warnings.
- Cost model ID.
- Execution model ID.
- Statistical report.
- Artefact checksums.
- Final classification.
- Whether the result is still inconclusive.

The operator must not report only the best candidate.

### 29.4 Data change procedure

When a source file changes:

1. Do not overwrite the old dataset manifest.
2. Create a new manifest.
3. Calculate the new source hash.
4. Record the provider and acquisition time.
5. Record changed coverage.
6. Record quality differences.
7. Create a new experiment specification.
8. Run data regression tests.
9. Compare the new dataset against the previous version.
10. Preserve the old result.

### 29.5 Cost model change procedure

When costs change:

1. Create a new cost model ID.
2. Record the fee schedule source.
3. Record its effective date.
4. Update the execution assumptions.
5. Create a new experiment.
6. Re-run the relevant baseline.
7. Compare the change in costs and turnover.
8. Do not overwrite the previous result.

### 29.6 Worker crash procedure

When a worker stops unexpectedly:

1. Inspect its job status.
2. Inspect the last persisted event.
3. Inspect the last persisted candidate.
4. Inspect any output artefact.
5. Check whether an OOS authorisation was recorded.
6. Check whether an OOS result was recorded.
7. Do not reuse in-memory state.
8. Do not manually mark the job succeeded.
9. Create a new job or implement a verified checkpoint restore.
10. Preserve the failed job record.

### 29.7 API exposure procedure

Before any non-loopback deployment:

1. Define the user identity model.
2. Define authentication.
3. Define authorisation.
4. Define TLS termination.
5. Define secret storage.
6. Define network restrictions.
7. Define rate limits.
8. Define audit retention.
9. Review all API responses.
10. Test direct access to every route.
11. Test invalid sessions.
12. Test unauthorised job submission.
13. Test unauthorised data access.
14. Obtain a security review.

Until these steps pass, keep the API on loopback.

## 30. Detailed risk register

| Risk ID | Risk | Likelihood | Impact | Current control | Remaining action |
|---|---|---|---|---|---|
| R-001 | A worker reads protected data through a local path. | Medium | Critical | Physical non-holdout copy and lifecycle checks. | OS-level isolation. |
| R-002 | OOS acceptance is subjective or changes after results. | High | Critical | Unknown status remains inconclusive. | Approve a fixed OOS policy. |
| R-003 | Historical universe data has survivorship bias. | High | Critical | Documentation warns about exposure. | Point-in-time universe. |
| R-004 | Data source licence does not permit the intended use. | Medium | High | Licence status field. | Provider and licence review. |
| R-005 | Missing market bars create false signals. | Medium | High | Basic OHLCV checks and gap metadata. | Full missing-bar audit. |
| R-006 | Features use information before it was public. | Medium | Critical | Price/volume causal checks. | Publication-time data joins. |
| R-007 | Simulated fills are more favourable than real fills. | High | High | Next-open and participation assumptions. | Tick and order-book calibration. |
| R-008 | Historical costs are understated. | Medium | High | Market-specific fee adapters. | Dated fee schedules. |
| R-009 | Derivative accounting is incorrectly represented as spot. | Medium | Critical | Current worker handles spot only. | Separate derivative ledgers. |
| R-010 | DSR overstates evidence when trials are correlated. | High | High | Assumption is stated. | Independent statistical review. |
| R-011 | PBO subset does not represent the full candidate family. | Medium | High | Bounded deterministic subset. | Sensitivity analysis. |
| R-012 | A trainer does not apply the purge helper. | Medium | High | Shared helper and some tests. | Trainer-by-trainer integration. |
| R-013 | One genome family receives more compute than another. | Medium | High | Equal per-method conventional search budget. | Mixed-family budget contract. |
| R-014 | Candidate lineage is incomplete. | Medium | High | Append-only candidate records. | Common lineage schema audit. |
| R-015 | GPU results differ from CPU results. | Medium | High | Some scalar/batch parity. | Target GPU parity suite. |
| R-016 | GPU is slower than CPU for the selected workload. | High | Medium | Runtime probe and CPU fallback. | Benchmark real workloads. |
| R-017 | A job is lost after process restart. | High | Medium | Job state and interruption records persist. | Checkpoint and restore. |
| R-018 | Dashboard displays stale or incomplete records. | Medium | Medium | Reads persisted records. | Data freshness and UI tests. |
| R-019 | API is exposed without authentication. | Medium | Critical | Loopback default and non-loopback guard. | Do not enable remote access. |
| R-020 | Legacy defects affect reused code. | Medium | High | v2 uses explicit adapters. | Re-audit reused legacy functions. |
| R-021 | A passing CI run is treated as market proof. | High | Critical | Documentation states the limit. | Enforce evidence labels in reports. |
| R-022 | A candidate is reported without unsuccessful trials. | Medium | High | Candidate archive retains failures in tested workers. | Audit every worker and export path. |
| R-023 | Cost or feature changes do not create a new experiment. | Medium | High | Fingerprints bind important fields. | Require immutable experiment versioning. |
| R-024 | An OOS result is used for retuning. | Medium | Critical | Candidate freeze and one OOS lifecycle. | Add process-level isolation and audit. |

Risk levels are qualitative. They are not measured probabilities.

## 31. Decision register

The following decisions need an owner and an approved value.

| Decision ID | Decision | Required owner | Why the decision is needed |
|---|---|---|---|
| D-001 | Approve OOS acceptance metrics and thresholds. | Research owner. | The worker cannot classify OOS as pass or fail without it. |
| D-002 | Approve independent final-holdout design. | Data and security owners. | Lifecycle events do not isolate files. |
| D-003 | Select licensed NSE data providers. | Data owner. | Automated acquisition and point-in-time history depend on data rights. |
| D-004 | Select licensed crypto providers by exchange and instrument. | Data owner. | Venue coverage and derivatives history are separate. |
| D-005 | Define supported instrument types for the first research release. | Research owner. | Spot and derivative accounting cannot share one ledger. |
| D-006 | Define the first supported NSE universe. | Research owner. | Point-in-time coverage and compute budgets depend on scope. |
| D-007 | Define feature publication-time policy. | Research and data owners. | Fundamental, news, macro, and on-chain features need causal joins. |
| D-008 | Define candidate budget equality. | Research owner. | Search methods need fair comparisons. |
| D-009 | Define genome interface. | Platform architect. | Mixed-family evolution needs a common candidate contract. |
| D-010 | Define topology bounds for neural evolution. | ML owner. | Resource limits must be explicit. |
| D-011 | Approve statistical reference methods. | Independent quantitative reviewer. | Diagnostics need independent validation. |
| D-012 | Identify target GPU. | Hardware owner. | Hardware work cannot use an assumed device. |
| D-013 | Decide whether distributed workers are required. | Platform owner. | Current local thread pool may be enough for the first release. |
| D-014 | Decide whether remote dashboard access is required. | Platform and security owners. | Remote authentication has a separate security cost. |
| D-015 | Define report artefact format. | Research owner. | Complete reproduction requires a stable package. |

No value should be invented by the implementation agent for a decision that requires owner approval.

## 32. Completion criteria for the next engineering stages

### 32.1 Stage A — Validation policy

The stage is complete when:

- The OOS policy has a stable version ID.
- The policy has a written metric definition.
- The policy has a written sample-size rule.
- The policy has missing-data behaviour.
- The policy has risk limits.
- The policy has cost limits.
- The policy has robustness rules.
- The policy has a review record.
- Every OOS worker uses the same policy version.
- Tests cover pass, fail, and unknown states.
- The policy cannot change during an active experiment.

### 32.2 Stage B — Holdout isolation

The stage is complete when:

- Protected data is not readable by normal workers.
- Protected data uses separate storage permissions.
- Normal jobs do not receive protected paths.
- Only an approved holdout service can read protected data.
- The service accepts frozen candidate artefacts.
- The service verifies candidate digests.
- The service records every request.
- The service rejects repeated access.
- The service does not return raw protected rows.
- Access denial tests pass.
- Restart tests pass.
- Concurrency tests pass.
- The threat model has an independent review.

### 32.3 Stage C — Data quality and provenance

The stage is complete when:

- Each data source has an approved licence.
- Each source has an acquisition method.
- Each file has a checksum.
- Each dataset has an immutable manifest.
- Each instrument has a point-in-time identity record.
- Each dataset has a missing-bar report.
- Each dataset has a gap report.
- Each dataset has a duplicate report.
- Each dataset has a timezone and timestamp policy.
- Every adjustment is documented.
- Every derived observation has a derivation record.
- A data availability matrix exists for all four tracks.

### 32.4 Stage D — Accounting and execution

The stage is complete when:

- Supported instrument types are explicitly listed.
- Each instrument type has a ledger.
- Each fee schedule has effective dates.
- Each fee schedule has a source.
- Corporate actions have deterministic accounting.
- Tax lots are recorded where required.
- Funding is recorded where required.
- Borrow is recorded where required.
- Margin is recorded where required.
- Liquidation is recorded where required.
- Fill assumptions are documented.
- Execution calibration is measured.
- Financial invariants pass.
- Independent test fixtures reconcile.

### 32.5 Stage E — Statistical review

The stage is complete when:

- Each formula has a reference.
- Each assumption has a description.
- The candidate family is complete.
- Correlation sensitivity is measured.
- Small-sample behaviour is tested.
- Large-family behaviour is tested.
- PBO subset sensitivity is documented.
- Bootstrap parameters are justified.
- Purging is integrated into all trainers.
- An independent reviewer signs the method record.

### 32.6 Stage F — Evolutionary architecture

The stage is complete when:

- The shared genome interface is approved.
- Existing strategy genomes use the interface.
- GP genomes use the interface.
- Neural genomes use the interface.
- Composition genomes use the interface.
- Candidate lineage uses one common schema.
- Candidate budgets are measured consistently.
- Population diversity is measured.
- Mixed-family selection is tested.
- Every operation is bounded.
- Checkpoint recovery is tested.
- Worker failure remains auditable.

### 32.7 Stage G — Hardware and performance

The stage is complete when:

- Exact target hardware is recorded.
- Software versions are recorded.
- GPU availability is verified.
- CPU/GPU parity passes.
- Batch-size tests pass.
- Memory tests pass.
- Runtime failure tests pass.
- Full simulation speed is measured.
- Data transfer cost is measured.
- A benchmark report includes the commands and environment.
- A performance improvement is claimed only when measured.

### 32.8 Stage H — Four-track validation

The stage is complete when each track has:

- Approved data.
- Complete coverage documentation.
- Correct market calendar.
- Correct instrument specification.
- Correct cost model.
- Correct execution model.
- Correct features.
- Correct validation windows.
- Correct embargo.
- Correct OOS policy.
- Statistical report.
- Candidate archive.
- Failure report.
- Reproduction bundle.
- Independent review.

## 33. Reporting requirements for every future experiment

Every experiment report should use the structure below.

### 33.1 Identification

- Experiment ID.
- Job ID.
- Market.
- Track.
- Algorithm family.
- Candidate representation.
- Source commit.
- Dirty state.
- Experiment creation time.
- Run time.

### 33.2 Data

- Dataset IDs.
- Dataset hashes.
- Provider.
- Licence state.
- Universe.
- Instruments.
- Venue.
- Resolution.
- Timezone.
- Timestamp convention.
- Coverage.
- Missing intervals.
- Quality warnings.
- Adjustments.
- FX source.
- Feature source and publication-time policy.

### 33.3 Protocol

- Hypothesis.
- Rationale.
- Baseline.
- Feature set.
- Search budget.
- Random seed.
- Objective.
- Constraints.
- Train period.
- Validation period.
- OOS period.
- Embargo.
- Final holdout policy.
- Stop condition.
- Statistical family.

### 33.4 Simulation

- Initial capital.
- Cash.
- Positions.
- Fills.
- Unfilled quantity.
- Fees.
- Taxes.
- Slippage.
- Impact.
- Turnover.
- Participation.
- Market exposure.
- Gross and net returns.
- Drawdown.
- Risk metrics.
- Accounting reconciliation.

### 33.5 Search

- Candidate count.
- Failed count.
- Duplicate count.
- Generation count.
- Runtime.
- Fitness distribution.
- Best candidate.
- Median candidate.
- Worst candidate.
- Diversity.
- Parent and child lineage.
- Pareto front where relevant.
- Stopping reason.

### 33.6 Validation

- TRAIN metrics.
- VALIDATION metrics.
- OOS metrics.
- Final holdout state.
- Candidate digest.
- Policy version.
- Statistical diagnostics.
- Robustness checks.
- Missing evidence.
- Classification.

### 33.7 Environment

- OS.
- Python.
- Dependencies.
- CPU.
- RAM.
- GPU.
- Driver.
- CUDA.
- Backend.
- Precision.
- Worker count.
- Resource usage.

### 33.8 Conclusion

The conclusion must state:

- What was tested.
- What was not tested.
- What passed.
- What failed.
- What remains unknown.
- Which assumptions affected the result.
- Whether the result can be reproduced.
- Whether the result needs independent confirmation.

The conclusion must not imply that a positive backtest guarantees future profit.

## 34. Final audit addendum

This expanded report records the source-level test inventory and a more detailed requirement map.

The API comparison route is present. It supports two to ten unique experiment IDs and keeps comparisons within one market. The full visual comparison suite remains incomplete.

The focused test inventory contains 159 test function definitions across twelve research-platform files. This is a source count. The number of runtime cases can differ when parametrisation is used.

The main software foundation is present. The main research evidence gaps remain.

The immediate engineering order is unchanged:

1. Approve the OOS policy.
2. Isolate the final holdout.
3. Establish approved point-in-time data.
4. Complete financial accounting and execution.
5. Validate statistical methods.
6. Complete mixed-genome evolution.
7. Test the target GPU.
8. Add job recovery and full monitoring.
9. Run the four research tracks.
10. Publish complete, reproducible reports.

The current implementation is not complete under the v2 definition of completion in GOAL.md.

The current implementation does not establish a profitable strategy.

The current implementation does not establish live trading readiness.

**Audit result: PARTIAL. Further engineering, independent review, and market-data validation are required.**
