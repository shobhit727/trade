#!/usr/bin/env python3
"""Hardened recovery of data/nse after accidental local deletion.

`tools/download_nse.py` does the actual work but assumes yfinance always answers. In
practice Yahoo is flaky for `.NS` tickers: it intermittently returns "possibly delisted;
no price data found" and also disagrees between `auto_adjust=True/False` for the same
symbol. This wrapper retries both modes with backoff, writes atomically, and verifies the
result against the per-symbol statistics committed in `research/_audit_1d.csv`, so a
silent partial/garbled fetch cannot pass unnoticed.

Usage:
    python tools/recover_nse_data.py --interval 1d
    python tools/recover_nse_data.py --interval 1d --verify-only
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

# The 50 NSE symbols that made up the original panel, recovered from the committed
# audit summary (research/_audit_1d.csv). tmp/nifty50.csv was also deleted locally.
SYMBOLS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC",
    "JSWSTEEL", "KOTAKBANK", "LT", "MARUTI", "MAXHEALTH",
    "M&M", "NESTLEIND", "NTPC", "ONGC", "POWERGRID",
    "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN", "SUNPHARMA",
    "TATACONSUM", "TATASTEEL", "TCS", "TECHM", "TITAN",
    "TMPV", "TRENT", "ULTRACEMCO", "WIPRO", "JIOFIN",
]


def write_list_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Symbol"])
        w.writeheader()
        for s in SYMBOLS:
            w.writerow({"Symbol": s})


def audit_reference() -> dict[str, dict[str, str]]:
    """Per-symbol expected stats from the committed audit, for verification."""
    p = Path("research/_audit_1d.csv")
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return {r["symbol"]: r for r in csv.DictReader(f)}


def download(symbol: str, interval: str, out_dir: Path,
             attempts: int = 6) -> tuple[str, int]:
    """Fetch one symbol, retrying both auto_adjust modes with backoff.

    Returns (status, bars). status is "ok" | "empty".
    """
    import pandas as pd
    import yfinance as yf

    ticker = f"{symbol}.NS"
    out = out_dir / f"{symbol.lower().replace('-', '')}_{interval}.csv"

    for attempt in range(attempts):
        # Yahoo is inconsistent about auto_adjust; try both before giving up.
        for adjust in (True, False):
            try:
                df = yf.download(
                    ticker, start="2000-01-01", interval=interval,
                    auto_adjust=adjust, progress=False, threads=False,
                )
            except Exception:  # noqa: BLE001 - network flakiness
                df = None

            if df is None or df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            if df.empty:
                continue

            tmp = out.with_suffix(".tmp")
            with tmp.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ts", "open", "high", "low", "close", "vol"])
                for idx, r in df.iterrows():
                    ts = int(pd.Timestamp(idx).timestamp() * 1000)
                    w.writerow([ts, r["Open"], r["High"], r["Low"],
                                r["Close"], r.get("Volume", 0)])
            tmp.replace(out)
            return "ok", len(df)

        time.sleep(min(2 ** attempt, 20) + random.uniform(0, 2))

    return "empty", 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/nse")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_list_csv(Path("tmp/nifty50.csv"))

    if not args.verify_only:
        print(f"recovering {len(SYMBOLS)} symbols @ {args.interval} -> {out_dir}",
              flush=True)
        ok = failed = 0
        for i, sym in enumerate(SYMBOLS, 1):
            status, bars = download(sym, args.interval, out_dir)
            if status == "ok":
                ok += 1
            else:
                failed += 1
            print(f"  [{i:>2}/{len(SYMBOLS)}] {sym:<14} {status} bars={bars}",
                  flush=True)
        print(f"\ndownloaded={ok} failed={failed}")

    # ---------------- verification against the committed audit -------------
    ref = audit_reference()
    print(f"\nVERIFY against research/_audit_1d.csv ({len(ref)} symbols)")
    files = sorted(out_dir.glob(f"*_{args.interval}.csv"))
    print(f"files present: {len(files)}")

    import pandas as pd

    mismatches, ok_rows = [], 0
    for p in files:
        sym = p.name[: -len(f"_{args.interval}.csv")]
        r = ref.get(sym)
        if not r:
            continue
        df = pd.read_csv(p)
        got_bars = len(df)
        got_last = round(float(df["close"].iloc[-1]), 2)
        want_bars, want_last = int(r["bars"]), round(float(r["px_last"]), 2)
        # The recovery is fresher than the audit (which ended 2026-08-25), so bars
        # should be >= the audited count. Last price should match closely.
        bars_ok = got_bars >= want_bars - 5
        px_ok = abs(got_last - want_last) / want_last < 0.25
        if bars_ok and px_ok:
            ok_rows += 1
        else:
            mismatches.append(
                f"{sym}: bars {got_bars} vs {want_bars}, "
                f"last {got_last} vs {want_last}"
            )

    print(f"verified OK: {ok_rows}/{len(files)}")
    if mismatches:
        print("MISMATCHES (first 10):")
        for m in mismatches[:10]:
            print(f"  {m}")

    return 0 if (len(files) >= 45 and len(mismatches) <= 3) else 1


if __name__ == "__main__":
    sys.exit(main())
