#!/usr/bin/env bash
# Run Optuna parameter optimization for a strategy
# Usage: ./scripts/optimize.sh [strategy_name] [n_trials]

set -euo pipefail

STRATEGY="${1:-mean_reversion}"
N_TRIALS="${2:-100}"

echo "Optimizing $STRATEGY with $N_TRIALS trials..."
python3 -c "
from cryptobot.cli.optimize import run_optimization
results = run_optimization(strategy='$STRATEGY', n_trials=$N_TRIALS)
print(f'Best params: {results.best_params}')
print(f'Best Sharpe: {results.best_value:.2f}')
"