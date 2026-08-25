#!/usr/bin/env python3
"""Download NSE (Nifty50) OHLCV via yfinance into the repo's CSV schema.

Same bar schema as the crypto pipeline: ts,open,high,low,close,vol with
ts = epoch milliseconds. Symbols get the .NS suffix for Yahoo Finance.

yfinance interval limits (enforced here):
  1m -> last 7d | 2m,5m,15m,30m -> last 60d | 60m,1h -> last 730d | 1d -> max

Usage:
  python3 tools/download_nse.py --out data/nse --interval 1d
  python3 tools/download_nse.py --out data/nse --interval 15m --symbols RELIANCE,TCS
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import UTC, datetime
from pathlib import Path

LIST_CSV = "tmp/nifty50.csv"  # fetched from archives.nseindia.com; see nifty50_symbols()

INTERVAL_LIMITS = {
    "1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60,
    "60m": 730, "1h": 730, "1d": None, "1wk": None,
}


def nifty50_symbols(list_csv: str = LIST_CSV) -> list[str]:
    """Parse the official NSE constituents CSV (col: Symbol)."""
    syms: list[str] = []
    with open(list_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = (row.get("Symbol") or "").strip()
            if s:
                syms.append(s)
    return syms


def fetch_one(symbol: str, interval: str, out_dir: Path) -> str:
    import pandas as pd

    ticker = f"{symbol}.NS"
    days = INTERVAL_LIMITS.get(interval)
    end = datetime.now(UTC)
    start = end - pd.Timedelta(days=days) if days else "2000-01-01"

    df = yf_download(ticker, start, interval)
    if df is None or df.empty:
        return f"{symbol} {interval}: EMPTY"

    out = out_dir / f"{symbol.lower()}_{interval}.csv"
    tmp = out.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "vol"])
        for idx, r in df.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1000)
            w.writerow([ts, r["Open"], r["High"], r["Low"], r["Close"], r["Volume"]])
    tmp.replace(out)
    return f"{symbol} {interval}: {len(df)} bars -> {out.name}"


def yf_download(ticker: str, start, interval: str):
    import pandas as pd
    import yfinance as yf

    # auto_adjust=True: split/bonus-adjusted OHLC — mandatory for honest
    # backtests (raw prices show splits as -50/80% cliffs, #58).
    df = yf.download(ticker, start=start, interval=interval,
                     auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):  # yfinance >=0.2 multi-ticker shape
        df.columns = [c[0] for c in df.columns]
    return df.dropna(subset=["Open", "High", "Low", "Close"])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/nse")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--symbols", default=None,
                    help="comma list of NSE symbols (default: full Nifty50)")
    ap.add_argument("--list-csv", default=LIST_CSV)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols = (args.symbols.split(",") if args.symbols else nifty50_symbols(args.list_csv))
    print(f"{len(symbols)} symbols @ {args.interval}", flush=True)

    from tqdm import tqdm

    loop = asyncio.get_running_loop()
    for sym in tqdm(symbols, unit="dl", ncols=80, desc="nse"):
        msg = await loop.run_in_executor(None, fetch_one, sym, args.interval, out_dir)
        print(msg, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
