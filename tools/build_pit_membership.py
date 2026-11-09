#!/usr/bin/env python3
"""Stitch the point-in-time NIFTY-50 membership matrix.

Combines three sources into one long-format table:
  1. vishalvx/nifty-indices-datasets  (MIT) monthly reconstruction, 2008-01..2025-08
  2. archive.org snapshots of the live NSE constituent file (ground truth)
  3. the live NSE file downloaded now

Output: data/nse_membership/nifty50_monthly_membership.csv
        (long format: date, symbol, in_index  -- easy to diff and to audit)
"""

from __future__ import annotations

import json
import os

import pandas as pd

OUT = "data/nse_membership"
SRC = "tem/datagap"


def norm(v: str) -> str:
    """NSE symbol hygiene. NiftyIndices/Yahoo disagree on '-' and '&'."""
    return str(v).strip().upper().replace("-", "").replace("&", "").replace(" ", "")


def read_list(path: str) -> set[str] | None:
    if not os.path.exists(path):
        return None
    d = pd.read_csv(path)
    c = next((x for x in d.columns if x.strip().lower() == "symbol"), None)
    return None if c is None else {norm(x) for x in d[c].dropna()}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    frames = []

    # ---- 1. reconstructed monthly matrix
    m = pd.read_csv(f"{SRC}/nifty50_weights.csv")
    m["DATE"] = pd.to_datetime(m["DATE"])
    long = m.melt(id_vars="DATE", var_name="symbol", value_name="in_index")
    long = long[long.in_index == 1.0].copy()
    long["symbol"] = long["symbol"].map(norm)
    long["source"] = "reconstructed_github"
    long = long.rename(columns={"DATE": "date"})[["date", "symbol", "source"]]
    frames.append(long)

    # ---- 2. archive.org ground-truth snapshots (verified against the matrix)
    wb = os.path.join(SRC, "wayback")
    for fn in sorted(os.listdir(wb)):
        if not fn.startswith("nifty50_") or not fn.endswith(".csv"):
            continue
        ts = fn[len("nifty50_"):-len(".csv")]
        syms = read_list(os.path.join(wb, fn))
        if not syms:
            continue
        d = pd.Timestamp(f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}") + pd.offsets.MonthEnd(0)
        frames.append(pd.DataFrame(
            {"date": d, "symbol": sorted(syms), "source": f"wayback_{ts}"}))

    # ---- 3. live list
    live = read_list(f"{SRC}/nse_live_nifty50.csv")
    if live:
        frames.append(pd.DataFrame({
            "date": pd.Timestamp("2026-10-31"),
            "symbol": sorted(live),
            "source": "nse_live",
        }))

    out = (pd.concat(frames, ignore_index=True)
             .drop_duplicates(["date", "symbol"])
             .sort_values(["date", "symbol"])
             .reset_index(drop=True))
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    path = os.path.join(OUT, "nifty50_monthly_membership.csv")
    out.to_csv(path, index=False)

    n_dates = out.date.nunique()
    per = out.groupby("date").size()
    print(f"wrote {path}")
    print(f"  {len(out):,} rows | {n_dates} month-ends "
          f"({out.date.min()} .. {out.date.max()}) | "
          f"{out.symbol.nunique()} distinct symbols")
    print(f"  membership per month: min={per.min()} max={per.max()} "
          f"median={per.median():.0f}")
    print(f"  file size: {os.path.getsize(path)/1024:.1f} KiB")
    print("\n  coverage by source:")
    print(out.groupby("source").size().to_string())

    missing = sorted(set(pd.date_range(
        pd.Timestamp(out.date.min()), pd.Timestamp(out.date.max()), freq="ME")
        .strftime("%Y-%m-%d")) - set(out.date))
    print(f"\n  month-ends with NO membership recorded: {len(missing)}")
    print(f"    {missing[:14]}{' ...' if len(missing) > 14 else ''}")

    meta = {
        "rows": len(out), "month_ends": n_dates,
        "date_min": out.date.min(), "date_max": out.date.max(),
        "distinct_symbols": int(out.symbol.nunique()),
        "months_missing": len(missing), "missing": missing,
        "bytes": os.path.getsize(path),
    }
    with open(os.path.join(OUT, "membership_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
