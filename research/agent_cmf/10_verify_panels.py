"""Step 10 — INDEPENDENT VERIFICATION of the interrupted run's panels.

Does not trust `_*.pkl`. Rebuilds from `data/nse` via the brief's mandatory entry
point (`load_universe`) plus per-symbol OHLCV, then compares against the pickles the
interrupted run left behind. Also proves CMF parity against the catalog indicator.

Nothing here reads TEST for tuning. TEST is only touched for its date range label.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.data.loader import EXCLUDE_SYMBOLS, DataIntegrityError, load_symbol, load_universe

DATA = "data/nse"
D = "research/agent_cmf"


def cmf_panel(closes, highs, lows, vols, period):
    rng = (highs - lows).replace(0.0, np.nan)
    mfm = ((closes - lows) - (highs - closes)) / rng
    num = (mfm * vols).rolling(period, min_periods=period).sum()
    den = vols.rolling(period, min_periods=period).sum()
    return num / den.replace(0.0, np.nan)


def main() -> None:
    # ---------- A. the brief's mandatory first step ----------
    panel, symbols, report = load_universe(DATA)
    print("=" * 78)
    print("A. load_universe (brief mandatory first step)")
    print("=" * 78)
    print(report.describe())
    print(f"symbols kept        : {len(symbols)}")
    print(f"panel shape         : {panel.shape}")
    print(f"index               : {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"TRAIN 2016-01-01->2023-12-31 bars: {int(((panel.index >= '2016-01-01') & (panel.index <= '2023-12-31')).sum())}")
    print(f"TEST  2024-01-01->2026-10-01 bars: {int(((panel.index >= '2024-01-01') & (panel.index <= '2026-10-01')).sum())}")

    # ---------- B. rebuild OHLCV the way the interrupted run did ----------
    frames = {}
    for fname in sorted(os.listdir(DATA)):
        if not fname.endswith("_1d.csv"):
            continue
        sym = fname[: -len("_1d.csv")]
        if sym in EXCLUDE_SYMBOLS:
            continue
        try:
            df = load_symbol(os.path.join(DATA, fname), sym)
        except DataIntegrityError:
            continue
        if len(df) < 1000:
            continue
        frames[sym] = df

    syms = sorted(frames)
    idx = None
    for s in syms:
        idx = frames[s].index if idx is None else idx.union(frames[s].index)
    idx = idx.sort_values()

    closes = pd.DataFrame({s: frames[s]["close"] for s in syms}).reindex(idx)
    highs = pd.DataFrame({s: frames[s]["high"] for s in syms}).reindex(idx)
    lows = pd.DataFrame({s: frames[s]["low"] for s in syms}).reindex(idx)
    vols = pd.DataFrame({s: frames[s]["vol"] for s in syms}).reindex(idx)

    print()
    print("=" * 78)
    print("B. rebuilt panels")
    print("=" * 78)
    print(f"symbols {len(syms)}  index {len(idx)} ({idx[0].date()} -> {idx[-1].date()})")
    for nm, p in [("close", closes), ("high", highs), ("low", lows), ("vol", vols)]:
        print(f"  {nm:6s} NaN {int(p.isna().sum().sum()):>8,}  symbols w/NaN "
              f"{int((p.isna().sum() > 0).sum()):>3}  "
              f"min {float(p.min().min()):>14.4g}  max {float(p.max().max()):>14.4g}")

    # OHLC coherence: is high >= low >= close-ish?  cheap structural check.
    bad_hl = int((highs < lows).sum().sum())
    bad_hc = int((highs < closes).sum().sum())
    bad_lc = int((lows > closes).sum().sum())
    print(f"  coherence violations: high<low {bad_hl}  high<close {bad_hc}  low>close {bad_lc}")

    # ---------- C. do the interrupted run's pickles match a fresh rebuild? ----------
    print()
    print("=" * 78)
    print("C. compare against the interrupted run's pickles")
    print("=" * 78)
    for nm, fresh in [("_closes", closes), ("_highs", highs), ("_lows", lows), ("_vols", vols)]:
        path = os.path.join(D, nm + ".pkl")
        if not os.path.exists(path):
            print(f"  {nm:8s} MISSING")
            continue
        old = pd.read_pickle(path)
        same_idx = old.index.equals(fresh.index)
        same_cols = list(old.columns) == list(fresh.columns)
        if same_idx and same_cols:
            a = old.to_numpy(dtype=float)
            b = fresh.to_numpy(dtype=float)
            both_nan = np.isnan(a) & np.isnan(b)
            nan_mismatch = int((np.isnan(a) ^ np.isnan(b)).sum())
            d = np.abs(np.where(both_nan, 0.0, a - b))
            mx = float(np.nanmax(d)) if d.size else 0.0
            print(f"  {nm:8s} shape {old.shape} == {fresh.shape}: "
                  f"{old.shape == fresh.shape}  max|diff| {mx:.6e}  nan-mismatch {nan_mismatch}")
        else:
            print(f"  {nm:8s} INDEX/COLS DIFFER "
                  f"(idx {same_idx} cols {same_cols}) "
                  f"old {old.shape} new {fresh.shape}")

    # ---------- D. CMF parity vs the catalog indicator ----------
    print()
    print("=" * 78)
    print("D. CMF parity vs cryptobot.strategies.indicators.chaikin_mf")
    print("=" * 78)
    from cryptobot.strategies.indicators import chaikin_mf

    for s in (syms[0], syms[len(syms) // 2]):
        c = closes[s].dropna()
        h = highs[s].reindex(c.index)
        lo = lows[s].reindex(c.index)
        v = vols[s].reindex(c.index)
        ca, ha, la, va = (x.to_numpy(dtype=float) for x in (c, h, lo, v))
        for period in (10, 20, 60):
            mine = cmf_panel(closes[[s]], highs[[s]], lows[[s]], vols[[s]], period)[s]
            mine = mine.reindex(c.index)
            ref = pd.Series(
                [chaikin_mf(ca[:i], ha[:i], la[:i], va[:i], period)
                 for i in range(period, len(ca) + 1)],
                index=c.index[period - 1:],
            )
            both = pd.concat([mine.rename("mine"), ref.rename("ref")], axis=1).dropna()
            mx = float((both["mine"] - both["ref"]).abs().max())
            flag = "OK " if mx < 1e-9 else "MISMATCH"
            print(f"  {flag} {s:12s} period={period:>2}  max|diff| {mx:.3e}  n={len(both)}")
            print(f"       mine range [{mine.min():+.4f},{mine.max():+.4f}]  "
                  f"ref range [{ref.min():+.4f},{ref.max():+.4f}]")

    # ---------- E. save the verified panels (overwrite the untrusted ones) ----------
    closes.to_pickle(os.path.join(D, "v_closes.pkl"))
    highs.to_pickle(os.path.join(D, "v_highs.pkl"))
    lows.to_pickle(os.path.join(D, "v_lows.pkl"))
    vols.to_pickle(os.path.join(D, "v_vols.pkl"))
    print("\nsaved VERIFIED panels as _v_*.pkl")


if __name__ == "__main__":
    main()
