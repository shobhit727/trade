"""Deep audit of local NSE data: coverage, ranges, quality, survivorship bias.

Run:  docker compose run --rm research  OR  python research/audit_data.py
"""

from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

DATA = os.environ.get("NSE_DATA", "data/nse")
DAY = 86_400_000.0


def ms_to_date(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, unit="ms", utc=True).dt.tz_convert("Asia/Kolkata")


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if "ts" not in df.columns:
        # some files may already be datetimes
        df["ts"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def audit_timeframe(tf: str) -> pd.DataFrame:
    files = sorted(glob.glob(f"{DATA}/*_{tf}.csv"))
    rows = []
    for path in files:
        sym = os.path.basename(path).replace(f"_{tf}.csv", "")
        try:
            df = load(path)
        except Exception as exc:  # noqa: BLE001
            rows.append({"symbol": sym, "error": str(exc)})
            continue

        ts = df["ts"].astype("int64")
        dts = ms_to_date(ts)
        ohlc = df[["open", "high", "low", "close"]].astype(float)
        vol = df["vol"].astype(float) if "vol" in df.columns else pd.Series(dtype=float)

        # ---- gaps in *trading* terms (ignore weekends + known holidays roughly)
        deltas = ts.diff().dropna()
        gaps = deltas / DAY
        if tf == "1d":
            expected = 1.0
            gaps = gaps[(gaps > 1) & (gaps < 400)]
        else:
            expected = {"1m": 1 / 1440, "5m": 5 / 1440, "15m": 15 / 1440,
                        "30m": 30 / 1440, "1h": 1 / 24, "4h": 4 / 24}[tf]
            gaps = gaps[(gaps > expected * 1.5) & (gaps < 30)]

        # ---- OHLC integrity
        bad_ohlc = int(
            (
                (ohlc["high"] < ohlc["low"])
                | (ohlc["high"] < ohlc["open"] - 1e-6)
                | (ohlc["high"] < ohlc["close"] - 1e-6)
                | (ohlc["low"] > ohlc["open"] + 1e-6)
                | (ohlc["low"] > ohlc["close"] + 1e-6)
            ).sum()
        )
        zero_price = int((ohlc[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
        dup_ts = int(ts.duplicated().sum())
        nonpos_vol = int((vol <= 0).sum()) if len(vol) else 0

        # ---- suspicious flatlines (synthetic / stale print)
        ret = ohlc["close"].pct_change()
        flat = float((ret.abs() < 1e-9).mean())

        rows.append({
            "symbol": sym,
            "tf": tf,
            "bars": len(df),
            "start": str(dts.min().date()),
            "end": str(dts.max().date()),
            "span_days": (dts.max() - dts.min()).days,
            "px_first": float(ohlc["close"].iloc[0]),
            "px_last": float(ohlc["close"].iloc[-1]),
            "gaps": len(gaps),
            "max_gap_days": float(gaps.max()) if len(gaps) else 0.0,
            "bad_ohlc": bad_ohlc,
            "zero_price": zero_price,
            "dup_ts": dup_ts,
            "nonpos_vol": nonpos_vol,
            "flat_frac": round(flat, 4),
            "median_vol": float(vol.median()) if len(vol) else np.nan,
        })
    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 100)
    print("NSE DATA AUDIT")
    print("=" * 100)

    for tf in ["1d", "1h", "4h", "30m", "15m", "5m", "1m"]:
        files = glob.glob(f"{DATA}/*_{tf}.csv")
        if not files:
            continue
        rep = audit_timeframe(tf)
        print(f"\n### TIMEFRAME {tf}  ({len(rep)} symbols)")
        if "error" in rep.columns and rep["error"].notna().any():
            print("  ERRORS:", rep.loc[rep["error"].notna(), ["symbol", "error"]].to_dict("records"))
            rep = rep[rep["error"].isna()]
        cols = ["bars", "start", "end", "px_first", "px_last", "gaps",
                "max_gap_days", "bad_ohlc", "zero_price", "dup_ts", "nonpos_vol", "flat_frac"]
        print(rep[cols].describe().loc[["count", "mean", "min", "50%", "max"]].to_string())
        bad = rep[(rep["bad_ohlc"] > 0) | (rep["zero_price"] > 0) | (rep["dup_ts"] > 0)]
        if len(bad):
            print("  !! DATA QUALITY ISSUES:")
            print(bad[["symbol", "bad_ohlc", "zero_price", "dup_ts", "nonpos_vol"]].to_string(index=False))
        rep.to_csv(f"research/_audit_{tf}.csv", index=False)

    # ---------------------------------------------------------------- universe
    print("\n" + "=" * 100)
    print("UNIVERSE / SURVIVORSHIP CHECK (daily)")
    print("=" * 100)
    d1 = audit_timeframe("1d")
    d1 = d1[d1["bars"] > 200]
    print(f"symbols with >200 daily bars: {len(d1)}")
    # IPO age proxy -> index membership survivorship indicator
    d1["first_seen"] = pd.to_datetime(d1["start"])
    d1 = d1.sort_values("first_seen")
    print(d1[["symbol", "first_seen", "bars", "px_last"]].to_string(index=False))

    # ---------------------------------------------------------------- what is usable
    print("\n" + "=" * 100)
    print("USABLE FOR BACKTEST")
    print("=" * 100)
    for tf in ["1d", "1h", "4h", "1m"]:
        f = glob.glob(f"{DATA}/*_{tf}.csv")
        if not f:
            continue
        r = pd.DataFrame([{"bars": len(load(p))} for p in f])
        print(f"{tf:>4}: bars min={r['bars'].min():<7} median={int(r['bars'].median()):<7} max={r['bars'].max()}")


if __name__ == "__main__":
    main()
