"""Pull real data for funding-carry backtest: spot 1h, perp 8h, funding history.

All public Binance endpoints (no auth). Writes CSVs in the format expected by
``tools/run_carry_real.py``:
    spot    : /tmp/opencode/spot_BTCUSDT_1h.csv   (timestamp, open, high, low, close, volume, symbol)
    perp    : /tmp/opencode/perp_BTCUSDT_8h.csv   (timestamp, open, high, low, close, volume, symbol)
    funding : /tmp/opencode/funding_BTCUSDT.csv   (funding_time, funding_rate)
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("/tmp/opencode")


def _fetch(base, params: dict) -> list:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{base}?{qs}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def klines(base: str, symbol: str, interval: str, start_ms: int, end_ms: int):
    out = []
    cursor = end_ms
    while cursor > start_ms:
        batch = _fetch(
            base,
            {
                "symbol": symbol,
                "interval": interval,
                "limit": 1000,
                "endTime": cursor,
            },
        )
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
        cursor = next_ts - (28_800_000 if interval == "8h" else 3_600_000)
        time.sleep(0.05)
    out.sort(key=lambda r: r["ts"])
    return out


def write_ohlcv(path: Path, rows: list[dict], symbol: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume", "symbol"])
        for r in rows:
            w.writerow([r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"], symbol])


def write_funding(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["funding_time", "funding_rate"])
        for r in rows:
            w.writerow([r["fundingTime"], r["fundingRate"]])
    print(f"funding rows: {len(rows)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - args.days * 86_400_000

    spot = klines("https://api.binance.com/api/v3/klines", args.symbol, "1h", start_ms, now_ms)
    write_ohlcv(OUT / f"spot_{args.symbol}_1h.csv", spot, args.symbol)
    print(f"spot {args.symbol} 1h: {len(spot)}")

    perp = klines("https://fapi.binance.com/fapi/v1/klines", args.symbol, "8h", start_ms, now_ms)
    write_ohlcv(OUT / f"perp_{args.symbol}_8h.csv", perp, args.symbol)
    print(f"perp {args.symbol} 8h: {len(perp)}")

    funding = _fetch(
        "https://fapi.binance.com/fapi/v1/fundingRate",
        {
            "symbol": args.symbol,
            "limit": 1000,
            "startTime": start_ms,
        },
    )
    all_funding = list(funding)
    while funding and int(funding[-1]["fundingTime"]) < now_ms - 28_800_000:
        batch = _fetch(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            {
                "symbol": args.symbol,
                "limit": 1000,
                "startTime": int(funding[-1]["fundingTime"]) + 1,
            },
        )
        if not batch or batch == funding:
            break
        funding = batch
        all_funding.extend(batch)
        time.sleep(0.05)
    write_funding(OUT / f"funding_{args.symbol}.csv", all_funding)


if __name__ == "__main__":
    main()
