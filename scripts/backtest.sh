#!/usr/bin/env bash
# Run a backtest with default settings
# Usage: ./scripts/backtest.sh [strategy] [data_source] [symbol] [timeframe]

set -euo pipefail

STRATEGY="${1:-mean_reversion}"
DATA_SOURCE="${2:-synthetic}"
SYMBOL="${3:-BTCUSDT}"
TIMEFRAME="${4:-1h}"

echo "Running backtest:"
echo "  Strategy: $STRATEGY"
echo "  Data: $DATA_SOURCE"
echo "  Symbol: $SYMBOL"
echo "  Timeframe: $TIMEFRAME"

python3 -m cryptobot.cli.main validate \
    --source "$DATA_SOURCE" \
    --symbol "$SYMBOL" \
    --timeframe "$TIMEFRAME" \
    --strategy "$STRATEGY"