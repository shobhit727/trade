#!/usr/bin/env bash
# Generate HTML tearsheet report from backtest results
# Usage: ./scripts/report.sh <backtest_output.json> [output_html]

set -euo pipefail

INPUT_JSON="${1:-}"
OUTPUT_HTML="${2:-tearsheet.html}"

if [ -z "$INPUT_JSON" ]; then
    echo "Usage: $0 <backtest_output.json> [output_html]"
    exit 1
fi

if [ ! -f "$INPUT_JSON" ]; then
    echo "Error: Input file '$INPUT_JSON' not found"
    exit 1
fi

echo "Generating report:"
echo "  Input: $INPUT_JSON"
echo "  Output: $OUTPUT_HTML"

python3 -c "
import json
from cryptobot.backtest.reporting import generate_html_tearsheet

with open('$INPUT_JSON') as f:
    data = json.load(f)

html = generate_html_tearsheet(data)
with open('$OUTPUT_HTML', 'w') as f:
    f.write(html)
print('Report generated: $OUTPUT_HTML')
"