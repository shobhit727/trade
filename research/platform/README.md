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
  resolution, objective and chronological-window provenance.
- Chronological split definitions and an access lifecycle that separates optimisation,
  model selection, OOS evaluation and one-time final-holdout access.
- SQLite experiment/event/candidate persistence with append-only event and candidate
  records, including evolutionary lineage JSON.
- Optional CuPy batch linear-population evaluation with NumPy CPU fallback.

## Additional research capabilities

- Local adapters for the legacy NSE splitter and exchange-scoped crypto CSV/Parquet files.
  They do not download market data. Imported datasets remain licence-review-required.
- A long-only multi-asset cash simulator which decides on close t and executes on open t+1,
  with participation limits, adverse slippage, square-root impact and declared per-side fees.
- Random search, capped grid search, differential evolution and a clearly labelled
  Parzen-style heuristic. The latter is not canonical Optuna TPE or a Bayesian result.
- Bounded numerical genetic programming with a closed AST interpreter; generated Python
  is never executed.
- A compact dense-network evolution strategy and declarative strategy-composition search.
- Pareto non-dominated sorting / NSGA-II crowding selection.
- Benjamini-Hochberg FDR, moving-block bootstrap and a CSCV PBO diagnostic.
- Batched long/flat population fitness in NumPy or optional CuPy.
- A loopback WSGI API and actual experiment-record dashboard. API creation persists a
  record and explicitly does not start a research worker.

## Explicit limitations

This increment is not yet a complete point-in-time historical universe, live data-acquisition
system, full NSE tax/corporate-action portfolio simulator, crypto derivatives/margin/
liquidation engine, exchange arbitrage simulator, production job scheduler, secured
distributed holdout service, or complete dashboard for job start/stop and GPU telemetry.
The crypto adapter reads local files only. The market ledger and portfolio simulator are
long-only INR cash models. There is no live brokerage connection or order placement.

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

The crypto cash ledger in this increment requires fills and marks denominated in INR.
A future FX adapter must attach timestamped FX provenance before normalising non-INR
quotes. Futures, perpetual swaps, short selling, margin and liquidation accounting require
separate instrument-specific ledgers before those products can be simulated credibly.

Run the focused tests from the repository root:

```bash
# Test the foundational ledger, provenance and split/holdout logic.
python -m pytest tests/unit/test_research_platform.py -q

# Test the search, evolutionary, Pareto, statistics, adapter and portfolio increment.
python -m pytest tests/unit/test_research_platform_search.py -q

# Test the experiment API and dashboard routes.
python -m pytest tests/unit/test_research_platform_api.py -q

# Launch the local dashboard/API (default bind is loopback only).
python -m research.platform.app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. The dashboard shows persisted records only; an experiment
created through the form is recorded as `created_not_started`.
