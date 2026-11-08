# Research platform foundation

This package is the first additive layer for the hybrid evolutionary research platform.
It deliberately does not replace `research/optimize`, `src/nsealgo`, `src/cryptobot`, or
any existing backtest engine.

## Included in this increment

- Explicit `Market` and four `ResearchTrack` domain types.
- Independent ₹21,00,000 simulated budgets for NSE and crypto.
- Market-bound long-only INR cash ledgers with duplicate-fill, oversell, cash and
  cross-market checks. Crypto derivatives/margin accounting is **not** implemented here.
- Immutable dataset provenance manifests and a data availability catalogue.
- Experiment specifications with code, dataset, cost-model, execution-model, seed,
  resolution, objective, embargo and chronological-window provenance.
- Chronological split definitions, label-interval-aware purging, explicit embargo handling,
  and an access lifecycle that separates optimisation, model selection, OOS evaluation
  and one-time final-holdout access.
- SQLite experiment/event/candidate persistence with append-only event and candidate
  records, including evolutionary lineage JSON.
- Optional CuPy batch linear-population, dense-neural inference and long/flat fitness
  kernels with NumPy CPU fallback. Dense neural inference is checked against the scalar
  NumPy implementation; the portfolio simulator remains the execution/fee fitness engine.
  GPU availability and performance depend on the machine running the worker.

## Additional research capabilities

- Local adapters for the legacy NSE splitter and exchange-scoped crypto CSV/Parquet files.
  They do not download market data. Imported datasets remain licence-review-required.
  Ingest rejects non-positive prices, negative volume, open values outside [low, high] and
  inconsistent high/low bounds. NSE daily imports default to a strict absolute close-return
  threshold below 20%; crypto does not inherit that NSE-specific limit. Quality checks are
  recorded as canonical JSON in manifest metadata; a full gap/universe quality grade is not
  inferred from these checks.
- Explicit quote-currency to INR conversion using backward-only FX alignment, maximum staleness
  limits and source provenance. Future or stale FX rates are rejected.
- A causal trailing price/volume feature engine plus separately timestamped forward labels.
  Feature outputs never use negative shifts or future rows.
- A long-only multi-asset cash simulator which decides on close t and executes on open t+1,
  with participation limits, adverse slippage, square-root impact and declared per-side fees.
- Random search, capped grid search, differential evolution and seeded Optuna TPE.
  A hybrid ensemble can run multiple methods with separate fixed seeds and equal per-method
  budgets, merge their candidate traces and select from one shared VALIDATION shortlist.
  The separate Parzen-style approximation remains available as a heuristic baseline.
- Bounded numerical genetic programming with a closed AST interpreter; generated Python
  is never executed. The worker evolves only on TRAIN, selects from the final population
  on VALIDATION, and evaluates one frozen expression on OOS.
- A compact dense-network neuroevolution worker using mirrored-noise ES, candidate weight
  vectors and generation ancestry.
- Declarative strategy-composition evolution over a fixed causal component registry:
  momentum/trend entries and exits, volatility/volume filters, regime and risk gates.
- NSGA-II multi-objective search over existing strategy parameters, including persisted
  candidate ancestry, TRAIN Pareto fronts, VALIDATION selection and frozen OOS evaluation.
- Market-specific fee calculators: the existing itemised NSE delivery cost model and a
  separately configured crypto maker/taker fee schedule.
- TRAIN-only candidate-family diagnostics across optimiser, GP, neuroevolution, composition
  and Pareto workers: PSR-derived one-sided p-values, Benjamini-Hochberg FDR, DSR and CSCV/PBO.
  FDR/DSR use the full successful candidate family; CSCV uses a deterministic, evenly spaced
  subset capped at 128 candidates. These reports do not influence model selection and are
  diagnostic, not evidence of profitability.
- Batched long/flat population fitness and dense-neural inference in NumPy or optional CuPy.
  Neural inference uses bounded candidate chunks; auto mode falls back to NumPy after a
  runtime CUDA error, while explicit CuPy mode fails rather than silently changing backend.
- A loopback WSGI API and dashboard backed by SQLite manifests, experiments, jobs and
  candidate lineage. The dashboard can queue, inspect and cooperatively cancel the
  allow-listed existing-strategy, parameter-search, hybrid search ensemble, GP,
  neuroevolution, composition and Pareto workers.

## Explicit limitations

This increment is not yet a complete point-in-time historical universe, live data-acquisition
system, full NSE tax-lot/corporate-action portfolio simulator, crypto derivatives/margin/
liquidation engine, exchange arbitrage simulator, durable distributed worker cluster,
secured process-isolated holdout service, or full dashboard telemetry/comparison suite.
The job manager uses local threads and marks in-flight jobs interrupted after process
restart; interrupted jobs must be resubmitted. GP, neural and composition policies are
currently long/flat cash models over price/volume features; they do not yet use point-in-time
fundamentals, macro, news, or order-book execution. NSGA-II presently evolves existing
strategy parameters, not a unified mixed population of GP, neural and component genomes. The crypto adapter reads local files only. The market ledger and
portfolio simulator are long-only INR cash models. There is no live brokerage connection
or order placement.

The statistical helpers are diagnostic implementations and require independent
methodological validation before being used as confirmatory evidence. No result from this
package is evidence of a profitable or deployable strategy.

## Basic usage

```python
# Keep the market account objects separate; there is no combined portfolio API.
from research.platform.domain import Market
from research.platform.market import MarketLedger

nse_ledger = MarketLedger(Market.NSE)
crypto_ledger = MarketLedger(Market.CRYPTO)

# Compute backend probes CuPy/CUDA at runtime and otherwise uses NumPy.
from research.platform.compute import ComputeEngine
compute = ComputeEngine(backend="auto")
print(compute.info())
```

The crypto cash ledger and portfolio simulator require bars, fills and marks denominated in INR.
Use `CryptoLocalAdapter.load_inr(...)` with an explicit `FXRateSeries` for non-INR quote data.
The FX converter uses only a prior observation and rejects stale/missing rates. Futures,
perpetual swaps, short selling, margin and liquidation accounting require separate
instrument-specific ledgers before those products can be simulated credibly.

Run the focused tests from the repository root:

```bash
# Test the foundational ledger, provenance and split/holdout logic.
python -m pytest tests/unit/test_research_platform.py -q

# Test the search, evolutionary, Pareto, statistics, adapter and portfolio increment.
python -m pytest tests/unit/test_research_platform_search.py -q

# Test the experiment API and dashboard routes.
python -m pytest tests/unit/test_research_platform_api.py -q

# Run all focused platform tests, including API, jobs, data loaders and evaluation.
python -m pytest tests/unit/test_research_platform*.py -q

# Launch the local dashboard/API and its allow-listed worker (default bind is loopback only).
python -m research.platform.app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. The dashboard shows persisted records only; an experiment
created through the form is recorded as `created_not_started`.
