# Hybrid evolutionary research platform — architecture increment 1

## Integration strategy

The existing repository already contains three useful execution and research domains:

- `research/optimize/` discovers the 84-strategy catalogue, derives typed parameter
  spaces, performs resumable per-stock optimisation and isolates its historical TEST
  slice structurally.
- `src/nsealgo/` contains NSE portfolio research, an Indian delivery cost model,
  a walk-forward engine and source/data provenance fingerprints.
- `src/cryptobot/` plus the Rust workspace contain crypto market-data, event-driven
  simulation, funding and order-book code, ML models, Grafana dashboard generation,
  and Rust statistical components including PBO and Deflated Sharpe implementations.

The new `research/platform/` package is an additive orchestration and metadata layer.
It does not replace or silently alter those existing components.

## Market and track boundaries

`Market` and `ResearchTrack` provide explicit identifiers. `TRACK_MARKET` rejects a track
paired with the wrong market. `MARKET_SPECS` gives each market its own INR 2,100,000
simulated seed allocation. `MarketLedger` instances are market-bound; a fill from the other
market is rejected before ledger mutation. There is no transfer or combined-return API.

The initial ledger handles long-only cash positions only. NSE delivery and crypto spot
can use it after their fills have been normalised into INR with explicit cost and FX
provenance. Futures, perpetuals, margin, liquidation, shorts and multi-currency cash
require dedicated accounting models; they must not be routed through this spot ledger.

## Data provenance

`DatasetManifest` captures provider, source, instrument, exchange, category, resolution,
coverage, timezone, timestamp convention, acquisition time, update frequency, licence
review, origin type, quality score, known gaps, adjustment and processing history. The
catalogue reports counts of manifests by market/exchange/resolution. Such counts are not
claims that the full exchange universe or time range has been acquired.

## Experiment reproducibility

`ExperimentSpec` binds a run to one market and track and records dataset identifiers,
resolution, algorithm family, random seed, git commit, code version, four chronological
partitions, market-specific cost and execution model identifiers, objectives and
parameters. Its canonical SHA-256 fingerprint can be stored with every experiment.

`ExperimentStore` uses a separate SQLite database and append-only experiment events and
candidate rows. Candidate lineage is stored with each candidate so parent, mutation,
crossover and selection metadata can be reconstructed. The experiment definition is
immutable; event and candidate tables reject update/delete operations.

## Candidate classification

The platform labels outcomes as failed, inconclusive, overfit, training-only, validation success,
historical OOS success, robust research candidate or requires independent confirmation. The
classifier consumes explicit evidence flags. It defines no return, Sharpe, drawdown or trade-count
thresholds; those belong in an approved, versioned v2 research protocol. Unknown OOS gate status
is inconclusive and cannot unlock final-holdout access. A robust research candidate is not a
real-money suitability label.

## Validation access policy

The `ValidationLifecycle` can persist its one-way state transitions in the append-only
experiment event store, keyed by experiment and job ID. Each transition is serialized under
a SQLite write transaction, so a restarted process cannot repeat the same job's OOS start or
final-holdout access. This records lifecycle authorization; it does not restrict filesystem
access or replace a separate worker process/service.

The `ValidationLifecycle` permits:

| Role | Data access |
|---|---|
| Optimizer | TRAIN only |
| Model selector | TRAIN and VALIDATION |
| OOS evaluator | OOS only, after candidate freeze |
| Final auditor | FINAL_HOLDOUT only, after a passing recorded OOS evaluation |

The final holdout can be opened once per persisted job lifecycle. Registered workers now
persist candidate freeze and OOS evaluation state; because no explicit OOS acceptance gate
is configured, their OOS result is recorded as unknown and cannot unlock the final holdout.
The current workers do not load final-holdout rows. A separate service/process boundary with
restrictive file permissions is still required before claiming secure holdout separation.

The old NSE protocol (TRAIN 2016–2023; TEST 2024–2026) is historical and exposed. It must
not be relabelled as a new, untouched final holdout. New validation/OOS/holdout dates must
be assigned only when genuinely new, independently controlled data exists.

## Compute backend

`ComputeEngine` uses NumPy by default and probes CuPy plus a real CUDA device only when
requested/auto-detected. It supports a batch linear-population calculation, returns
results to host memory, and exposes local runtime metadata. It does not claim GPU speedup;
benchmark results must be measured on the actual host with representative data, including
transfer overhead. The host's exact NVIDIA model, driver, CUDA compatibility and VRAM
remain machine-side facts to be recorded before choosing production dependencies.

## Implemented increment — branch `feature/hybrid-evolution-research`

The feature branch now contains the following additive modules:

| Capability | Implementation | Limitation |
|---|---|---|
| Existing data adapters | `NSELegacyAdapter`, `CryptoLocalAdapter`; OHLCV open-range/price/volume checks, manifest quality JSON and a pre-materialised non-holdout partition reader | Local historical files only; licence review remains required; production partition mode is strict by default and OS/process isolation remains open |
| Existing strategy discovery | `ExistingStrategyRegistry`, `ExistingStrategySignalAdapter` | Original classes stream bar by bar; only long/flat signals are adapted so far |
| Cash portfolio simulation | `PortfolioSimulator` | Long-only, INR cash; no derivative margin/liquidation or corporate-action ledger |
| Execution assumptions | Next-open, prior-completed-bar participation cap, slippage, square-root impact, injected market fee calculators | NSE uses existing itemised delivery cost model; crypto uses explicit venue maker/taker bps; historical fee schedules and intraday changes need sourcing |
| Optimisation baselines | Random, capped grid, differential evolution, seeded Optuna TPE; hybrid ensemble combines multiple methods under equal per-method budgets | Separate Parzen-style approximation remains a heuristic baseline; hybrid does not yet mix GP/neural/component genome types |
| Genetic programming | Bounded numerical AST interpreter, full candidate archive and TRAIN/VALIDATION/OOS worker | Numeric-only grammar; no Boolean/control-flow nodes yet |
| Neuroevolution | Dense one-hidden-layer network, mirrored-noise candidate archive, persisted TRAIN/VALIDATION/OOS descendants and batched NumPy/CuPy inference | Topology evolution is not integrated; portfolio fitness uses the CPU cash simulator; CUDA device and throughput remain unverified |
| Strategy composition | Closed causal component registry and TRAIN/VALIDATION/OOS evolution worker | Current entries/exits/filters are simple numerical rules; not yet adapters to all production strategy modules |
| Multi-objective optimisation | NSGA-II worker over existing-strategy parameters; TRAIN Pareto front, VALIDATION re-ranking and frozen OOS run | Does not yet evolve a mixed population spanning GP/neural/component genomes |
| Statistical diagnostics | TRAIN return-vector PSR-derived p-values, full-family BH FDR/DSR and bounded CSCV/PBO in optimiser, GP, neural, composition and Pareto workers; moving-block bootstrap and label-interval purging | DSR uses an independent-Gaussian trial-family approximation; CSCV uses at most 128 evenly spaced candidates; all diagnostics require independent methodological review and never drive selection |
| Population compute | Batched linear, long/flat and dense-neural inference, NumPy / optional CuPy, runtime fallback and scalar/batch parity tests | CuPy path has not been exercised on the target GPU; simulator/ledger fitness remains CPU and end-to-end GPU acceleration is not claimed |
| API and dashboard | Local WSGI API, experiment/data catalogue, strategy explorer, queue/inspect/cancel controls for existing-strategy, search, GP, neural, composition and Pareto workers | GPU telemetry, experiment comparison and full evolution monitoring remain incomplete |
| Job lifecycle | Bounded local thread pool, SQLite status/events/results, cooperative cancellation and interrupted-job recovery | Jobs are not durable across process death; interrupted work is marked failed and must be resubmitted |

## Execution and accounting limitations

The portfolio engine uses target weights selected at close (t), calculates desired positions from information available at that close, and attempts execution at open (t+1). Participation and square-root impact use the previous completed bar's volume, not the current bar's final volume. It records adverse slippage and fee charges from the selected market calculator. This remains an OHLCV approximation: it does not replay order-book events, queue priority, partial trade prints, auction mechanics or measured latency.

The simulator accepts market-specific fee calculators. NSE delivery fees delegate to the existing `src/nsealgo/costs.py` model, including itemised delivery charges and DP fee assumptions. The adapter currently applies the repository's configured schedule uniformly; historical rate changes, broker-specific differences and date-effective statutory transitions still need versioned schedules. Crypto spot uses an explicit venue maker/taker bps schedule, but the current market-order execution path uses taker fees. Funding, borrow and liquidation remain unimplemented. Current accounting is long-only INR cash, not a futures/perpetual, margin or short-selling engine. Indian capital-gains tax lots, corporate actions, dividends and delisting cash settlement are still unimplemented.

The local crypto adapter imports CSV/Parquet and records source-file hashes, but intentionally sets licence status to `REVIEW_REQUIRED`. Numeric timestamp units and candle timestamp positions must be declared. Non-INR crypto prices require a separately registered, approved FX dataset and backward-only as-of conversion. The NSE adapter reuses the repository's audited splitter and fingerprints the source CSV. Existing NSE `open` data defects mean strict OHLCV validation may reject data that has not been corrected or independently checked. No source is scraped or downloaded and no market coverage is claimed.

## API / dashboard operating model

Run `python -m research.platform.app --host 127.0.0.1 --port 8765`. The server binds to loopback by default and refuses a non-loopback host unless `--allow-remote` is supplied. Do not enable remote binding without adding authentication and transport security. The dashboard can create experiment records and queue the allow-listed existing-strategy evaluator,
parameter-search/hybrid, genetic-programming, neuroevolution, strategy-composition and Pareto
workers, then list, inspect and cooperatively cancel jobs. Job state and logs persist in SQLite; worker execution itself is a local thread pool and interrupted jobs are marked failed after restart.

## Validation and statistical interpretation

Experiment specifications persist an embargo in seconds and reject adjacent windows that do not leave the declared gap. `purged_walk_forward_split` uses each sample's label start/end interval to remove training examples overlapping validation plus embargo. These helpers are not yet integrated into every optimiser or model trainer, so callers must explicitly use them.

The runner requires NSE OOS to start after 1 October 2026 because the previous TRAIN/TEST research history is exposed through that date. A trusted ingestion step can now write a physical non-holdout copy with materialize_non_holdout_partition; a manifest with that path makes workers load only the safe copy and verify its SHA-256. Set RESEARCH_PARTITION_DATA_ROOT to the partition store. An unset RESEARCH_REQUIRE_PARTITIONED_DATA
is strict mode; setting it to 0 is an explicit exploratory compatibility override that may parse
combined source files before row clipping. A local process may still access other files on the same filesystem; a future isolated worker/holdout service with OS-level file permissions remains necessary. The remaining post-2026 sample is currently very short and cannot support a robust strategy claim.

The workers now attach TRAIN-only PSR/FDR/DSR/CSCV diagnostics to the full successful candidate family. FDR and DSR use all successful candidates; CSCV/PBO uses a deterministic evenly spaced subset capped at 128 candidates. DSR explicitly assumes independent Gaussian trial Sharpe estimates; this is not a realistic model for correlated strategy populations and requires sensitivity analysis. P-values are PSR-derived against a zero per-period Sharpe benchmark. None of these diagnostics affects candidate selection or corrects universe survivorship, publication-time leakage, data-quality, cost or execution bias.

## Remaining implementation priorities

1. Integrate the other optimiser/evolution families with the persistent job manager, candidate storage and budget-equal orchestration. The default manager now registers parameter-search/hybrid, GP, neuroevolution,
  strategy-composition and Pareto runners; a unified mixed-genome population spanning those
  families remains open.
2. Add storage-level holdout isolation and streaming reads which do not parse protected future rows into worker memory.
3. Add portfolio tax lots, corporate actions, dividends, crypto funding, borrow, margin and liquidation models.
4. Add date-effective cost schedules, broker/venue fee tiers and execution calibration from tick/order-book data.
5. Extend causal feature joins to publication-time fundamentals, news, macroeconomic and crypto on-chain sources.
6. Add Boolean/control-flow genetic programming, topology evolution, and a hybrid mixed-genome search that combines existing strategies, GP, neural and component candidates.
7. Add multi-asset GPU simulation and CPU/GPU parity/throughput benchmarks on the actual target NVIDIA hardware.
8. Audit DSR/PBO/FDR implementations against independent published fixtures and test dependence assumptions under candidate correlation.
9. Add dashboard experiment comparisons, GPU/CPU telemetry, population monitoring and job-level artefacts.
10. Run all four tracks only when sufficient licence-cleared post-exposed-boundary data is available; publish negative as well as positive results.

A successful build is not a strategy result. A profitable historical simulation is not evidence of a deployable edge.