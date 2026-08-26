#!/usr/bin/env python3
"""Round 2 (fixed): sweeps with EXACTLY the round-1 semantics.

Convention (matches round 1):
- condition evaluated on ALL bars strictly before `enter`
- entry = close of first bar at/after `enter` (that's the 15-min bar itself)
- exit  = close of the LAST bar with mod >= exit_min
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict
from pathlib import Path

import pandas as pd

DATA = Path("data/nse")
OUT_MD = Path("PROJECT_MEMORY/43_NSE_Intraday_Research.md")
COST_RT = 6.0 / 10_000
IST = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")


def load_frames() -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(DATA.glob("*_15m.csv")):
        sym = f.stem.split("_")[0].upper()
        df = pd.read_csv(f)
        df["dt"] = pd.to_datetime(df.ts, unit="ms", utc=True).dt.tz_convert(IST)
        df["date"] = df.dt.dt.date
        df["mod"] = df.dt.dt.hour * 60 + df.dt.dt.minute
        ret = df.close.pct_change()
        df = df[~(ret.abs() > 0.5)]
        if len(df) > 200:
            out[sym] = df
    return out


def trade(frames, enter, exit_, cond, label):
    trades, stock_counts, months = [], defaultdict(int), defaultdict(list)
    days = sorted({d for df in frames.values() for d in df.date.unique()})
    by_day = defaultdict(dict)
    for s, df in frames.items():
        for d, g in df.groupby("date"):
            by_day[d][s] = g
    for d in days:
        for s, g in by_day[d].items():
            g = g.sort_values("mod")
            hist = g[g["mod"] < enter]
            entry_bars = g[(g["mod"] >= enter) & (g["mod"] < enter + 15)]
            post = g[g["mod"] >= exit_]
            if len(hist) < 8 or len(entry_bars) < 1 or post.empty:
                continue
            if not cond(hist, entry_bars):
                continue
            entry = float(entry_bars.close.iloc[-1])
            px_out = float(post.close.iloc[-1])
            tt = px_out / entry - 1 - COST_RT
            trades.append(tt)
            stock_counts[s] += 1
            months[str(d)[:7]].append(tt)

    def vw_rising(hist, _entry):
        tp = (hist.high + hist.low + hist.close) / 3
        vwap = (tp * hist.vol).sum() / max(hist.vol.sum(), 1)
        c = float(hist.close.iloc[-1])
        recent_n = min(5, len(hist))
        tail_tp = (tp * hist.vol).iloc[-recent_n:]
        vwap_recent = tail_tp.sum() / max(hist.vol.iloc[-recent_n:].sum(), 1)
        return c > vwap and vwap >= vwap_recent

    def always(_h, _e):
        return True

    def first_bar_up_full(g_hist, _e):
        first = g_hist.iloc[0]
        return float(first.close) > float(first.open)

    conds = {
        "vw>0&rising": vw_rising,
        "always": always,
        "day1up": first_bar_up_full,
    }
    del conds  # conditions passed in by caller below


def run_sweep(frames) -> list[dict]:
    def make_cond(kind):
        if kind == "vwap":
            def c(hist, _e):
                tp = (hist.high + hist.low + hist.close) / 3
                vwap = (tp * hist.vol).sum() / max(hist.vol.sum(), 1)
                c_last = float(hist.close.iloc[-1])
                n = min(5, len(hist))
                tail_tp = (tp * hist.vol).iloc[-n:]
                vw_recent = tail_tp.sum() / max(hist.vol.iloc[-n:].sum(), 1)
                return c_last > vwap and vwap >= vw_recent
            return c
        if kind == "day1up":
            def c(hist, _e):
                if hist.empty:
                    return False
                f = hist.iloc[0]
                return float(f.close) > float(f.open)
            return c
        return lambda h, e: True

    out = []
    specs = [
        ("H1 13:45->15:15", 13*60+45, 15*60+15, "vwap"),
        ("H1 14:00->15:15", 14*60, 15*60+15, "vwap"),
        ("H1 14:00->last", 14*60, 15*60, "vwap"),
        ("H1 14:15->15:15", 14*60+15, 15*60+15, "vwap"),
        ("H5 09:30->12:00 day1up", 9*60+30, 12*60, "day1up"),
        ("H5 09:30->14:00 day1up", 9*60+30, 14*60, "day1up"),
        ("H6 15:00->15:15 always", 15*60, 15*60+15, "always"),
        ("H6 14:45->15:15 always", 14*60+45, 15*60+15, "always"),
    ]
    min_hist = {"vwap": 8, "always": 0, "day1up": 1}
    for label, enter, exit_, kind in specs:
        mh = min_hist[kind]
        trades, stock_counts, months = [], defaultdict(int), defaultdict(list)
        days = sorted({d for df in frames.values() for d in df.date.unique()})
        by_day = defaultdict(dict)
        for s, df in frames.items():
            for d, g in df.groupby("date"):
                by_day[d][s] = g
        cond = make_cond(kind)
        for d in days:
            for s, g in by_day[d].items():
                g = g.sort_values("mod")
                hist = g[g["mod"] < enter]
                entry_bars = g[(g["mod"] >= enter) & (g["mod"] < enter + 15)]
                post = g[g["mod"] >= exit_]
                if len(hist) < mh or entry_bars.empty or post.empty:
                    continue
                if not cond(hist, entry_bars):
                    continue
                entry = float(entry_bars.close.iloc[-1])
                px_out = float(post.close.iloc[-1])
                tt = px_out / entry - 1 - COST_RT
                trades.append(tt)
                stock_counts[s] += 1
                months[str(d)[:7]].append(tt)
        r = {"label": label, "n": len(trades),
             "win%": sum(1 for x in trades if x > 0)/len(trades)*100 if trades else 0,
             "mean": st.mean(trades) if trades else 0,
             "median": st.median(trades) if trades else 0,
             "top": max(stock_counts.values())/len(trades) if trades else 0,
             "mp": sum(1 for v in months.values() if st.mean(v) > 0),
             "mt": len(months)}
        out.append(r)
    return out


def main() -> None:
    frames = load_frames()
    rows = run_sweep(frames)
    lines = ["", "## Round 2 (fixed semantics) — sweeps & new hypotheses", "",
             "| variant | trades | win% | mean | median | top-stock % | pos months |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['label']} | {r['n']} | {r['win%']:.1f}% "
                     f"| {r['mean']:+.4%} | {r['median']:+.4%} "
                     f"| {r['top']:.0%} | {r['mp']}/{r['mt']} |")
    with OUT_MD.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for r in rows:
        print(f"{r['label']}: n={r['n']} win={r['win%']:.1f}% "
              f"mean={r['mean']:+.4%} med={r['median']:+.4%} "
              f"top={r['top']:.0%} months={r['mp']}/{r['mt']}")


if __name__ == "__main__":
    main()
