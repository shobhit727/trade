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

## Validation access policy

The `ValidationLifecycle` permits:

| Role | Data access |
|---|---|
| Optimizer | TRAIN only |
| Model selector | TRAIN and VALIDATION |
| OOS evaluator | OOS only, after candidate freeze |
| Final auditor | FINAL_HOLDOUT only, after a passing recorded OOS evaluation |

The final holdout can be opened once per lifecycle instance. Production use must persist
lifecycle transitions in the experiment event store and place holdout data behind a
separate service/process boundary; Python object checks alone are not a security boundary.

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
| Existing data adapters | `NSELegacyAdapter`, `CryptoLocalAdapter` | Local historical files only; licence review remains required |
| Existing strategy discovery | `ExistingStrategyCatalogueAdapter` | Catalogue discovery only; full optimizer integration still required |
| Cash portfolio simulation | `PortfolioSimulator` | Long-only, INR cash; no derivative margin/liquidation or corporate-action ledger |
| Execution assumptions | Next-open, participation cap, slippage, square-root impact, proportional fee bps | NSE statutory cost calculator and historical schedules need a fee-model adapter |
| Optimisation baselines | Random, capped grid, differential evolution, Parzen-style heuristic | Parzen method is explicitly not canonical Optuna TPE |
| Genetic programming | Bounded numerical AST interpreter and evolution | No Boolean/control-flow grammar yet |
| Neuroevolution | Dense one-hidden-layer network + mirrored-noise ES | CPU implementation; topology evolution / GPU path not yet integrated |
| Strategy composition | Declarative component-genome evolution | Requires adapters to actual strategy component implementations |
| Multi-objective optimisation | Non-dominated sorting and crowding selection | No full experiment scheduler integration yet |
| Statistical diagnostics | BH FDR, moving-block bootstrap, CSCV PBO diagnostic | Requires independent statistical review and broader tests |
| Population compute | Batched long/flat fitness, NumPy / optional CuPy | CuPy path and target GPU remain unverified |
| API and dashboard | Local WSGI API, create/list/detail records, HTML dashboard | Creates metadata only; worker start/stop, logs, telemetry and comparisons are incomplete |

## Execution and accounting limitations

The portfolio engine uses target weights selected at close (t), calculates desired positions from information available at that close, and attempts execution at open (t+1). It caps participation using next-bar volume and records adverse slippage and a square-root participation impact estimate. The engine must be tested against market-specific historical execution assumptions before its results are treated as realistic.

The generic simulator currently uses a proportional per-side fee schedule. A dedicated adapter to `src/nsealgo/costs.py` is still required to apply the complete statutory delivery cost stack, including fixed DP charges and itemised taxes. Crypto venue-specific maker/taker/funding/borrow schedules also remain to be integrated. Current portfolio accounting is long-only INR cash. It is not a futures/perpetual, margin, short-selling, liquidation or cross-currency engine. It does not yet apply Indian capital-gains tax or corporate actions to portfolio lots.

The local crypto adapter imports CSV/Parquet and records source-file hashes, but intentionally sets licence status to `REVIEW_REQUIRED`. The NSE adapter reuses the repository's audited splitter. Existing NSE `open` data defects mean the strict OHLCV validation may reject data that has not been corrected or independently checked. No source is scraped or downloaded and no market coverage is claimed.

## API / dashboard operating model

Run `python -m research.platform.app --host 127.0.0.1 --port 8765`. The server binds to loopback by default and refuses a non-loopback host unless `--allow-remote` is supplied. Remote access must not be enabled without adding authentication and transport security. The dashboard uses persisted SQLite experiment records; creating an experiment does not launch a worker. Data providers, worker scheduling, cancellation and job logs are not yet exposed through the API.

## Validation and statistical interpretation

The Python lifecycle state machine prevents accidental stage transitions in one process, but it is not an OS/process security boundary. Final holdout data must be isolated in a separate process/service and access transitions must be persisted. The historical NSE 2024–2026 TEST is exposed and remains unsuitable as a new pristine holdout.

The included BH, moving-block bootstrap and CSCV functions are diagnostics whose assumptions and outputs must be independently reviewed, especially for dependence structure and the actual trial family. They do not by themselves correct universe survivorship, data-quality, publication-time, cost or execution bias.

## Remaining implementation priorities

1. Integrate statutory NSE and venue-specific crypto cost calculators with the new portfolio simulator.
2. Add portfolio tax lots, corporate actions, dividends, funding, borrow, margin and liquidation models where reliable data exists.
3. Connect data adapters to persistent manifests, availability coverage, quality reports and point-in-time feature joins.
4. Add a common interface over existing strategy catalogue, NSE factors and crypto signals, and compare shipped defaults to search results.
5. Integrate the evolutionary/optimisation families with the experiment store, candidate lineage and budget-equal orchestration.
6. Add type-safe conditional GP nodes, topology evolution, multi-population hybrid selection and lineage validation.
7. Add multi-asset GPU simulation and CPU/GPU parity tests on the actual target NVIDIA hardware.
8. Audit statistical implementations against independent published fixtures and lock down the complete holdout protocol.
9. Implement a bounded worker/job manager, cancellation, logs, resource limits, worker persistence and real dashboard monitoring/comparisons.
10. Run all four tracks on actual, licence-cleared historical datasets and publish negative as well as positive results.

A successful build is not a strategy result. A profitable historical simulation is not evidence of a deployable edge.