#!/usr/bin/env bash
# Run a single strategy backtest with custom params
# Usage: ./scripts/run_strategy.sh <strategy_name> [params_json]

set -euo pipefail

STRATEGY="${1:-mean_reversion}"
PARAMS="${2:-{}}"

echo "Running strategy: $STRATEGY"
python3 -c "
from cryptobot.backtest.runner import run_backtest, make_strategy, generate_synthetic_ohlcv
from datetime import datetime

strategy = make_strategy('$STRATEGY')
bars = generate_synthetic_ohlcv(datetime(2024, 1, 1), n_bars=500)
result = run_backtest(strategy, bars, initial_equity=10000.0)
print(f'Return: {result.total_return:.2%}')
print(f'Sharpe: {result.metrics.sharpe_ratio:.2f}')
print(f'Max DD: {result.metrics.max_drawdown:.2%}')
"