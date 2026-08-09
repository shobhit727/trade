"""Pull historical Binance klines into JSON with pagination (no auth).

Pulls up to `days` of data at `interval` for spot `symbol`, paging backwards
from `end_ms` using the API's 1000-bar limit per call.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "8h": 28_800_000,
}


def fetch(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    base = "https://api.binance.com/api/v3/klines"
    out: list[dict] = []
    cursor = end_ms
    while cursor > start_ms:
        params = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": interval,
                "limit": 1000,
                "endTime": cursor,
            }
        )
        req = urllib.request.Request(f"{base}?{params}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        for k in batch:
            out.append(
                {
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
            )
        next_ts = int(batch[0][0])
        if next_ts >= cursor:
            cursor -= INTERVAL_MS[interval] * 1000
        else:
            cursor = next_ts - INTERVAL_MS[interval] * 1000
        time.sleep(0.05)
    out.sort(key=lambda k: k["ts"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - args.days * 86_400_000
    data = fetch(args.symbol, args.interval, start_ms, now_ms)
    out = args.out or f"/tmp/opencode/{args.symbol}_{args.interval}_{args.days}d.json"
    Path(out).write_text(json.dumps(data))
    first = data[0]["ts"] if data else 0
    import datetime as _dt

    print(
        f"pulled {len(data)} {args.symbol} {args.interval} bars "
        f"({_dt.datetime.fromtimestamp(first / 1000, tz=_dt.UTC).date()} -> now) -> {out}"
    )


if __name__ == "__main__":
    main()
