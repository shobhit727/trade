#!/usr/bin/env python3
"""NSE intraday research — four conditional hypotheses, one harness.

Prior sweeps killed ALWAYS-ON bar algos. These hypotheses are conditional:
they trade only specific windows / regimes / cross-sections, which is where
documented intraday effects live.

All on 15m bars, ~49 stocks, MIS costs (2bps fee + 1bp slip per side),
long-only and long-short variants where applicable. Flat by 15:25 IST.

H1 power_hour   : long stocks above rising session-VWAP entering 14:00,
                  exit at close.
H2 xsec_mom     : at 11:00 rank stocks by morning return; hold top-N till
                  close (long-only N best; plus LS variant).
H3 cond_orb     : ORB only when opening-range width > k*ATR14(daily proxy
                  via rolling) AND first-hour volume > v*median.
H4 tod_scan     : descriptive — mean 15m-bucket return conditioned on the
                  stock's 10:30 vs open direction (where does drift live?).

Writes PROJECT_MEMORY/43_NSE_Intraday_Research.md.
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data/nse")
OUT_MD = Path("PROJECT_MEMORY/43_NSE_Intraday_Research.md")
FEE_BPS, SLIP_BPS = 2.0, 1.0
COST_RT = (FEE_BPS + SLIP_BPS) * 2 / 10_000     # round-trip fraction

IST = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")


def load_frames() -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(DATA.glob("*_15m.csv")):
        sym = f.stem.split("_")[0].upper()
        df = pd.read_csv(f)
        df["dt"] = pd.to_datetime(df.ts, unit="ms", utc=True).dt.tz_convert(IST)
        df["date"] = df.dt.dt.date
        df["mod"] = df.dt.dt.hour * 60 + df.dt.dt.minute
        # outlier scrub
        ret = df.close.pct_change()
        df = df[~(ret.abs() > 0.5)]
        if len(df) > 200:
            out[sym] = df
    return out


def _cost(notional: float) -> float:
    return notional * COST_RT


# --------------------------------------------------------------- H1 power hour

def h1_power_hour(frames: dict[str, pd.DataFrame], enter_min=14*60,
                  exit_min=15*60+15) -> dict:
    """Long stocks whose close > session VWAP and VWAP slope > 0 at enter_min;
    exit at exit_min. Returns per-trade returns."""
    trades: list[float] = []
    days = sorted({d for df in frames.values() for d in df.date.unique()})
    by_day: dict[date, dict[str, pd.DataFrame]] = defaultdict(dict)
    for s, df in frames.items():
        for d, g in df.groupby("date"):
            by_day[d][s] = g
    for d in days:
        picks = []
        for s, g in by_day[d].items():
            pre = g[g["mod"] < enter_min]
            if len(pre) < 8:
                continue
            tp = (pre["high"] + pre["low"] + pre["close"]) / 3
            vwap = (tp * pre["vol"]).sum() / max(pre["vol"].sum(), 1)
            c = pre["close"].iloc[-1]
            vwap_prev = ((tp * pre["vol"]).iloc[:-6:-1].sum()
                         / max(pre["vol"].iloc[:-6:-1].sum(), 1))
            if c > vwap and vwap >= vwap_prev:
                picks.append((s, c))
        for s, entry in picks:
            g = by_day[d][s]
            ex = g[(g["mod"] >= exit_min)]
            if ex.empty:
                continue
            px_out = float(ex.close.iloc[-1])
            trades.append(px_out / entry - 1 - COST_RT)
    win = sum(1 for t in trades if t > 0)
    return {"name": "H1 power_hour(long-only)", "trades": len(trades),
            "win%": win / len(trades) * 100 if trades else 0,
            "mean": st.mean(trades) if trades else 0,
            "median": st.median(trades) if trades else 0}


# ------------------------------------------------------- H2 cross-sectional mom

def h2_xsec_momentum(frames: dict[str, pd.DataFrame], pick_min=11*60,
                     top_n: int = 5, long_short=False) -> dict:
    """At pick_min rank by morning return; hold leaders (and optionally short
    laggards) till close."""
    longs, shorts = [], []
    days = sorted({d for df in frames.values() for d in df.date.unique()})
    by_day: dict[date, dict[str, pd.DataFrame]] = defaultdict(dict)
    for s, df in frames.items():
        for d, g in df.groupby("date"):
            by_day[d][s] = g
    for d in days:
        mret = {}
        close_px = {}
        for s, g in by_day[d].items():
            pre = g[g["mod"] < pick_min]
            post = g[g["mod"] >= 15 * 60 + 15]
            if len(pre) < 6 or post.empty:
                continue
            o = float(pre["open"].iloc[0])
            c = float(pre["close"].iloc[-1])
            if o <= 0:
                continue
            mret[s] = c / o - 1
            close_px[s] = float(post["close"].iloc[-1])
        if len(mret) < top_n * 2:
            continue
        ranked = sorted(mret, key=mret.get, reverse=True)
        # buy at pick-time close, sell at final close
        for s in ranked[:top_n]:
            entry = None
            g = by_day[d][s]
            row = g[g["mod"] < pick_min]
            entry = float(row.close.iloc[-1])
            longs.append(close_px[s] / entry - 1 - COST_RT)
        if long_short:
            for s in ranked[-top_n:]:
                g = by_day[d][s]
                row = g[g["mod"] < pick_min]
                entry = float(row.close.iloc[-1])
                shorts.append(entry / close_px[s] - 1 - COST_RT)
    def agg(xs):
        return {"trades": len(xs),
                "win%": sum(1 for x in xs if x > 0) / len(xs) * 100 if xs else 0,
                "mean": st.mean(xs) if xs else 0,
                "median": st.median(xs) if xs else 0}
    res = {"name": f"H2 xsec_mom(top{top_n} long)", **agg(longs)}
    if long_short:
        ls = [a + b for a, b in zip(longs, shorts)] if len(longs) == len(shorts) else []
        res["ls_mean"] = st.mean(ls) if ls else 0
        res["ls_trades"] = len(ls)
    return res


# ---------------------------------------------------------------- H3 cond ORB

def h3_conditional_orb(frames: dict[str, pd.DataFrame],
                       k_atr: float = 1.5, v_mult: float = 1.5) -> dict:
    """ORB only when opening 2-bar range >= k*rolling ATR(14 days) AND
    first-30min volume >= v_mult of the stock's median first-half volume."""
    trades = []
    stats_vol: dict[str, list[float]] = defaultdict(list)
    atr_state: dict[str, float] = {}
    days = sorted({d for df in frames.values() for d in df.date.unique()})
    by_day: dict[date, dict[str, pd.DataFrame]] = defaultdict(dict)
    for s, df in frames.items():
        for d, g in df.groupby("date"):
            by_day[d][s] = g
    for d in days:
        for s, g in by_day[d].items():
            g = g.sort_values("mod")
            rng_bars = g[g["mod"] <= 9*60+45]
            if len(rng_bars) < 2:
                continue
            hi, lo = rng_bars["high"].max(), rng_bars["low"].min()
            atr = atr_state.get(s)
            vol30 = rng_bars["vol"].sum()
            med_v = st.median(stats_vol[s][-20:]) if len(stats_vol[s]) >= 20 else None
            stats_vol[s].append(vol30)
            # update ATR proxy at day end
            tr = g["high"].max() - g["low"].min()
            atr_state[s] = tr if atr is None else 0.94 * atr + 0.06 * tr
            if atr is None or med_v is None or atr <= 0 or med_v <= 0:
                continue
            if (hi - lo) < k_atr * atr or vol30 < v_mult * med_v:
                continue
            # breakout: close above hi after the window -> long till close
            post = g[g["mod"] > 9*60+45]
            sig = post[(post["close"] > hi)]
            if sig.empty:
                continue
            entry = float(sig["close"].iloc[0])
            px_out = float(post["close"].iloc[-1])
            trades.append(px_out / entry - 1 - COST_RT)
    return {"name": f"H3 cond_orb(k={k_atr},v={v_mult})", "trades": len(trades),
            "win%": sum(1 for t in trades if t > 0)/len(trades)*100 if trades else 0,
            "mean": st.mean(trades) if trades else 0,
            "median": st.median(trades) if trades else 0}


# ------------------------------------------------------------------- H4 tod scan

def h4_tod_scan(frames: dict[str, pd.DataFrame]) -> dict:
    """Mean 15m-bucket return conditioned on stock up/down at 12:00."""
    buckets_up = defaultdict(list)
    buckets_dn = defaultdict(list)
    for s, df in frames.items():
        for d, g in df.groupby("date"):
            g = g.sort_values("mod")
            noon = g[g["mod"] <= 12*60]
            if len(noon) < 10:
                continue
            up = noon.close.iloc[-1] >= noon.open.iloc[0]
            for i in range(1, len(g)):
                b_mod = int(g["mod"].iloc[i])
                r = g["close"].iloc[i] / g["close"].iloc[i-1] - 1
                (buckets_up if up else buckets_dn)[b_mod].append(r)
    rows = []
    for mod in sorted(buckets_up):
        u = buckets_up[mod]
        dn = buckets_dn[mod]
        rows.append((mod, st.mean(u), st.mean(dn)))
    drift = [(m, u - dn) for m, u, dn in rows]
    strongest = max(drift, key=lambda x: x[1])
    weakest = min(drift, key=lambda x: x[1])
    return {"strongest_bucket": f"{strongest[0]//60:02d}:{strongest[0]%60:02d}",
            "up_minus_down_drift": strongest[1],
            "weakest_bucket": f"{weakest[0]//60:02d}:{weakest[0]%60:02d}",
            "rows": rows}


def main() -> None:
    frames = load_frames()
    print(f"{len(frames)} stocks loaded", flush=True)

    results = [
        h1_power_hour(frames),
        h2_xsec_momentum(frames, top_n=5),
        h2_xsec_momentum(frames, top_n=10),
        h3_conditional_orb(frames),
        h3_conditional_orb(frames, k_atr=2.0, v_mult=2.0),
        h4_tod_scan(frames),
    ]

    lines = ["# NSE intraday research — conditional hypotheses",
             "",
             f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} · "
             f"{len(frames)} stocks · 15m bars · MIS 2+1bps/side · flat by 15:25",
             "",
             "## Results",
             "",
             "| hypothesis | trades | win% | mean/trade | median |",
             "|---|---|---|---|---|"]
    for r in results:
        if "trades" in r and "mean" in r:
            lines.append(f"| {r['name']} | {r['trades']} | {r['win%']:.1f}% "
                         f"| {r['mean']:+.4%} | {r['median']:+.4%} |")
    tod = next(r for r in results if "strongest_bucket" in r)
    lines += ["", "## H4 time-of-day drift map",
              "",
              f"- Strongest 15m bucket for morning-up stocks: **{tod['strongest_bucket']}"
              f"** (drift {tod['up_minus_down_drift']:+.4%}/bar vs morning-down)",
              f"- Weakest: {tod['weakest_bucket']}",
              "", "| bucket | mean ret if morning-up | mean ret if morning-down |",
              "|---|---|---|"]
    for mod, u, dn in tod["rows"]:
        lines.append(f"| {mod//60:02d}:{mod%60:02d} | {u:+.4%} | {dn:+.4%} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")
    for r in results[:5]:
        print(r)


if __name__ == "__main__":
    main()
