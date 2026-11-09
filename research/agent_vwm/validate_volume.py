"""Validate the NSE `volume` column BEFORE trusting any volume-weighted result.

The audit flagged ~485 pooled zero-volume bars and frozen-price runs. This script
quantifies, on the ACTUAL cleaned panel this study uses:

  1. how much volume data survives C1-C9 cleaning, per timeframe
  2. zero/negative volume bar counts, per symbol and pooled
  3. whether volume is constant / frozen (a real volume-weighted factor needs
     cross-sectional dispersion at each date; a constant volume column would make
     any "volume weighting" a no-op)
  4. cross-sectional dispersion of volume: is there signal, or is it all noise?
  5. the critical question for THIS strategy: on how many (date, symbol) cells does
     the `vw > 0` gate actually bind? If ~never, the strategy is not volume-weighted.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    avg_volume_panel,
    load_panels,
    roc_panel,
)


def main() -> None:
    px, vol, symbols = load_panels()
    print(f"panel close: {px.shape}  vol: {vol.shape}  symbols: {len(symbols)}")
    print(f"date span  : {px.index.min().date()} -> {px.index.max().date()}")

    # ---- 1. raw file level: zero volume BEFORE cleaning (for the audit caveat)
    import glob

    raw_zero = raw_total = 0
    for f in sorted(glob.glob("data/nse/*_1d.csv")):
        d = pd.read_csv(f)
        raw_zero += int((d["vol"] <= 0).sum())
        raw_total += len(d)
    print(
        f"\n[RAW disk]  vol<=0 : {raw_zero:,} / {raw_total:,} "
        f"= {raw_zero / raw_total:.4%}  (all timeframes)"
    )

    # ---- 2. cleaned panel: zero / negative volume
    flat = vol.stack()
    zero = int((flat <= 0).sum())
    print(
        f"[CLEAN 1d] vol<=0 : {zero:,} / {len(flat):,} = {zero / len(flat):.4%}  "
        f"(post C1-C9)"
    )
    per = (vol <= 0).sum()
    top = per[per > 0].sort_values(ascending=False).head(10)
    print("  worst symbols (post-clean zero-vol bars):")
    for s, n in top.items():
        print(f"    {s:<12} {n:>5}")

    # ---- 3. frozen volume: constant runs (>=5 identical consecutive volume values)
    frozen_cells = 0
    for col in vol.columns:
        v = vol[col].dropna().to_numpy()
        if v.size < 5:
            continue
        new_run = np.empty(v.size, dtype=bool)
        new_run[0] = True
        np.not_equal(v[1:], v[:-1], out=new_run[1:])
        run_id = np.cumsum(new_run) - 1
        run_len = np.bincount(run_id)
        frozen_cells += int(run_len[run_id].max()) if (run_len >= 5).any() else 0
    print(f"[CLEAN 1d] symbols with a frozen vol run >=5 : "
          f"{sum(1 for c in vol.columns if (vol[c].diff() == 0).rolling(5).sum().max() >= 4)}")

    # ---- 4. cross-sectional dispersion: does volume vary across names each day?
    # A usable volume factor needs names to differ. Report mean CV across dates.
    cv = (vol.std(axis=1) / vol.mean(axis=1)).replace([np.inf, -np.inf], np.nan)
    print(f"\n[DISPERSION] cross-sectional vol CV: mean={cv.mean():.4f} "
          f"p10={cv.quantile(0.10):.4f} median={cv.median():.4f}")
    # how correlated is volume with |return| and with close? (sanity: volume should
    # spike on big moves if it's real)
    ret = px.pct_change(fill_method=None)
    logv = np.log1p(vol.where(vol > 0))
    corr_absret = logv.corrwith(ret.abs(), axis=1).mean()
    corr_px = logv.corrwith(px, axis=1).mean()
    print(f"[SANITY] mean corr(logvol, |ret|) per day = {corr_absret:.4f}")
    print(f"[SANITY] mean corr(logvol, close)  per day = {corr_px:.4f}")

    # ---- 5. THE decisive test for this strategy: does the vw>0 gate bind?
    print("\n[STRATEGY GATE] fraction of cells where vw>0 is FALSE "
          "(avg volume window == 0):")
    for period in (20, 63, 126, 252):
        avg = avg_volume_panel(vol, period)
        dead = avg <= 0
        m = roc_panel(px, period)
        gate_blocks = int((dead & m.notna()).to_numpy().sum())
        live_cells = int(m.notna().to_numpy().sum())
        frac = gate_blocks / max(live_cells, 1)
        print(
            f"  period={period:>3}: gate blocks {gate_blocks:>7,} / "
            f"{live_cells:>9,} live cells = {frac:.6%}"
        )

    # Also: what does the volume CONDITION (vol[-1]>=avg -> 1.0 else 0.5) do?
    # It scales vw by 0.5 or 1.0. Since the strategy only tests vw>0, the
    # condition is literally a no-op. Prove it.
    for period in (20, 126):
        avg = avg_volume_panel(vol, period)
        above = (vol >= avg)
        vw = avg * np.where(above, 1.0, 0.5)
        # vw>0 iff avg>0 regardless of the 0.5/1.0 factor
        same = bool(((vw > 0) == (avg > 0)).all().all())
        print(f"  period={period}: (vw>0)==(avg>0) everywhere? {same}  "
              f"(factor 0.5/1.0 cannot change a >0 test on a non-negative avg)")

    # ---- 6. splits
    for name, (s, e) in {
        "TRAIN": (TRAIN_START, TRAIN_END),
        "TEST": (TEST_START, TEST_END),
    }.items():
        v = vol.loc[(vol.index >= s) & (vol.index <= e)]
        p = px.loc[(px.index >= s) & (px.index <= e)]
        z = int((v <= 0).sum().sum())
        tot = int(v.notna().sum().sum())
        print(f"\n[{name}] {p.index[0].date()}->{p.index[-1].date()} "
              f"bars={len(p)} zero-vol={z:,}/{tot:,}={z/max(tot,1):.4%}")


if __name__ == "__main__":
    main()
