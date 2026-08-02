#!/usr/bin/env bash
# Run walk-forward + Monte Carlo validation
# Usage: ./scripts/validate.sh [data_source] [symbol] [timeframe]

set -euo pipefail

DATA_SOURCE="${1:-synthetic}"
SYMBOL="${2:-BTCUSDT}"
TIMEFRAME="${3:-1h}"

echo "Running validation:"
echo "  Data: $DATA_SOURCE"
echo "  Symbol: $SYMBOL"
echo "  Timeframe: $TIMEFRAME"

python3 -m cryptobot.backtest.validation \
    --source "$DATA_SOURCE" \
    --symbol "$SYMBOL" \
    --timeframe "$TIMEFRAME" \
    --n-splits 5 \
    --n-permutations 200