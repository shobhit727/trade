"""Pull real Binance klines (public, no auth)."""

import json
import urllib.request
from datetime import UTC, datetime

url = "https://api.binance.com/api/v3/klines"
symbol = "BTCUSDT"
interval = "1h"
n = 1000  # ~83 days of 1h bars

req = urllib.request.Request(f"{url}?symbol={symbol}&interval={interval}&limit={n}")
data = json.loads(urllib.request.urlopen(req, timeout=10).read())
print(f"pulled {len(data)} {symbol} {interval} bars")
print("first:", data[0][0], datetime.fromtimestamp(data[0][0] / 1000, tz=UTC).isoformat())
print("last:", data[-1][0], datetime.fromtimestamp(data[-1][0] / 1000, tz=UTC).isoformat())
# Save
out = []
for k in data:
    out.append(
        {
            "ts": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
    )
with open("/tmp/t/btcusdt_1h.json", "w") as f:
    json.dump(out, f)
print("saved", len(out), "bars")
