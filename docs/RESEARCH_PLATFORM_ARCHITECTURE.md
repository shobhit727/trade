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

## Next software increments

1. Adapter interfaces for existing NSE and crypto data readers, with point-in-time
   availability and corporate-action/funding metadata.
2. Shared strategy and execution protocols that wrap existing catalogue implementations
   without changing their semantics.
3. Portfolio simulation and market-specific accounting, while keeping the existing
   single-stock engine as a compatibility baseline.
4. Conventional optimiser adapters and budget-matched experiment scheduling.
5. Typed genetic-programming expression trees and bounded evaluation.
6. Neuroevolution and strategy-composition genomes, compared to simple baselines.
7. Multi-objective selection and statistically controlled candidate accounting.
8. GPU batch kernels for measured bottlenecks, with CPU/GPU differential tests.
9. Real experiment API and dashboard views backed by stored records.

Each increment must add tests and preserve negative findings. A successful build is not a
strategy result; a profitable historical simulation is not evidence of a deployable edge.
