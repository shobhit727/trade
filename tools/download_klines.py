"""Download Binance klines for the HFT matrix sweep (public REST, no key).

Usage: python3 tools/download_klines.py [--quote USDT]
Downloads: BTCUSDT, ETHUSDT x [1m, 5m, 15m, 1h, 4h, 1d]
Lookback caps keep sizes sane: 1m=120d, 5m=240d, 15m=400d, rest=max.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

BASE = "https://api.binance.com/api/v3/klines"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = {"1m": 120, "5m": 240, "15m": 400, "1h": 800, "4h": 1200, "1d": 2000}
LIMIT = 1000


async def fetch_interval(session: aiohttp.ClientSession, symbol: str,
                         interval: str, days: int, out_dir: Path) -> str:
    out = out_dir / f"{symbol.lower()}_{interval}.csv"
    end_ms = int(datetime.now(UTC).timestamp() * 1000)
    start_ms = end_ms - days * 86_400_000
    rows: list[list] = []
    cur = start_ms
    while cur < end_ms:
        params = {"symbol": symbol, "interval": interval,
                  "startTime": cur, "limit": LIMIT}
        for attempt in range(5):
            try:
                async with session.get(BASE, params=params,
                                       timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 418 or r.status == 429:
                        await asyncio.sleep(2 ** attempt * 2)
                        continue
                    r.raise_for_status()
                    batch = await r.json()
                    break
            except Exception:
                if attempt == 4:
                    return f"{symbol} {interval}: network failure"
                await asyncio.sleep(1 + attempt)
        if not batch:
            break
        rows.extend(batch)
        cur = batch[-1][6] + 1  # close_time + 1ms
        if len(batch) < LIMIT:
            break
        await asyncio.sleep(0.15)  # weight-friendly

    seen, dedup = set(), []
    for k in rows:
        ts = k[0]
        if ts in seen:
            continue
        seen.add(ts)
        # k[0]=open_time ms, 1=open 2=high 3=low 4=close 5=volume
        dedup.append((ts, k[1], k[2], k[3], k[4], k[5]))
    dedup.sort(key=lambda x: x[0])
    tmp = out.with_suffix(".tmp")
    tmp.write_text(
        "ts,open,high,low,close,vol\n" +
        "\n".join(",".join(str(x) for x in row) for row in dedup) + "\n",
        encoding="utf-8")
    tmp.replace(out)
    return f"{symbol} {interval}: {len(dedup)} bars -> {out.name}"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for sym in SYMBOLS:
        for iv, days in INTERVALS.items():
            jobs.append((sym, iv, days))

    from tqdm import tqdm

    async with aiohttp.ClientSession() as session:
        # sequential per job but many jobs: keep rate-limit friendly
        for sym, iv, days in tqdm(jobs, unit="dl", ncols=80, desc="klines"):
            msg = await fetch_interval(session, sym, iv, days, out_dir)
            print(msg, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
