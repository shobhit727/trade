#!/usr/bin/env bash
# Clean and validate OHLCV data
# Usage: ./scripts/clean_data.sh <input.csv> [output.csv]

set -euo pipefail

INPUT="${1:-data/btc_1h.csv}"
OUTPUT="${2:-${INPUT%.csv}_clean.csv}"

echo "Cleaning data: $INPUT -> $OUTPUT"
python3 -c "
from cryptobot.data.cleaning import DataCleaner
import pandas as pd

df = pd.read_csv('$INPUT')
cleaner = DataCleaner()
df_clean = cleaner.clean_ohlcv(df)
df_clean.to_csv('$OUTPUT', index=False)
print(f'Cleaned {len(df)} -> {len(df_clean)} rows')
"