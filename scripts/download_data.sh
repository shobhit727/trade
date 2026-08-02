#!/usr/bin/env bash
# Download historical OHLCV data from Binance
# Usage: ./scripts/download_data.sh [symbol] [timeframe] [days]

set -euo pipefail

SYMBOL="${1:-BTCUSDT}"
TIMEFRAME="${2:-1h}"
DAYS="${3:-365}"

echo "Downloading $DAYS days of $SYMBOL $TIMEFRAME data..."
python3 -c "
from datetime import datetime, timedelta
from cryptobot.data.ingestion import BinanceDataIngestion
import asyncio

async def main():
    end = datetime.utcnow()
    start = end - timedelta(days=$DAYS)
    ingestion = BinanceDataIngestion()
    bars = await ingestion.fetch_ohlcv('$SYMBOL', '$TIMEFRAME', start, end)
    print(f'Downloaded {len(bars)} bars')
    out = f'data/{$SYMBOL}_{$TIMEFRAME}.csv'
    with open(out, 'w') as f:
        f.write('timestamp,open,high,low,close,volume\n')
        for bar in bars:
            f.write(f'{bar.timestamp.isoformat()},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}\n')
    print(f'Saved to {out}')

asyncio.run(main())
"