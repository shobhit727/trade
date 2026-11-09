"""Step 0 — data check, cost basis, ROC-library parity, engine provenance."""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    CFG,
    COST,
    ENGINE_SHA,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    load,
    roc_panel,
    roc_signal,
)


def main() -> None:
    print("=" * 78)
    print("ENGINE PROVENANCE")
    print("=" * 78)
    from nsealgo.backtest.engine import REF_POSITION_NOTIONAL, _d

    rt = COST.round_trip_bps(_d(REF_POSITION_NOTIONAL))
    ait = COST.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL))
    print(f"engine_sha            = {ENGINE_SHA}")
    print(f"round_trip_bps(1e5)   = {rt}   (statutory only)")
    print(f"all_in_rt_bps(1e5)    = {ait}   (what run_backtest charges)")
    print(f"PortfolioConfig       = {CFG}")
    print()

    print("=" * 78)
    print("DATA")
    print("=" * 78)
    panel, symbols, report = load()
    print(report.describe() if hasattr(report, "describe") else report.summary())
    print(f"symbols               = {len(symbols)}")
    print(f"panel rows            = {len(panel)}")
    print(f"span                  = {panel.index[0].date()} -> {panel.index[-1].date()}")
    n_tr = len(panel.loc[TRAIN_START:TRAIN_END])
    n_te = len(panel.loc[TEST_START:TEST_END])
    print(f"TRAIN bars            = {n_tr}  ({TRAIN_START.date()} -> {TRAIN_END.date()})")
    print(f"TEST bars             = {n_te}  ({TEST_START.date()} -> {TEST_END.date()})")
    print()

    # ---- parity with the catalog library's roc() ------------------------------
    # The library consumes a *contiguous* close list, so parity must be checked on a
    # NaN-free per-symbol series — comparing it against the union-calendar panel
    # would compare different bar indices.
    from cryptobot.strategies.indicators import roc as roc_lib

    probes = 0
    max_err = 0.0
    for sym in list(panel.columns)[:12]:
        c = panel[sym].dropna()
        for p in (10, 20):
            vp = roc_panel(c.to_frame(), p)[sym]
            for end in (250, 600, 1200, 2000):
                if end >= len(c):
                    continue
                got = roc_lib(list(c.to_numpy()[:end]), p)
                want = vp.iloc[end - 1]
                if np.isnan(got):
                    continue
                max_err = max(max_err, abs(got - want))
                probes += 1
    print(f"roc() parity          : {probes} probes, max_abs_err = {max_err:.3e}")
    print(f"panel NaN cells       : {int(panel.isna().sum().sum())} of {panel.size}")
    print()

    # ---- liveness -------------------------------------------------------------
    for p, thr in ((10, 0.01), (20, 0.01), (10, 0.0)):
        sig = roc_signal(panel, p, thr)
        print(
            f"ROC({p}) > {thr:<5} fires on {float(sig.mean().mean()) * 100:6.2f}% of all "
            f"bar/symbol cells (TRAIN {float(sig.loc[TRAIN_START:TRAIN_END].mean().mean()) * 100:6.2f}%)"
        )
    sig = roc_signal(panel, 10, 0.01)
    flags = sig.sum(axis=1)
    print(
        f"flagged names per bar : mean {flags.mean():.1f}  median {flags.median():.1f}  "
        f"min {flags.min():.0f}  max {flags.max():.0f}"
    )
    print(f"bars with >=1 flag    : {float((flags > 0).mean()) * 100:.2f}%")
    print()

    # ---- ROC distribution -----------------------------------------------------
    r10 = roc_panel(panel, 10)
    r20 = roc_panel(panel, 20)
    flat = pd.DataFrame({"roc10": r10.stack(), "roc20": r20.stack()}).dropna()
    print("ROC distribution (all cells, 2008-2026):")
    for col in flat.columns:
        q = flat[col].quantile([0.01, 0.25, 0.5, 0.75, 0.99])
        print(f"  {col}: mean {flat[col].mean() * 100:+.2f}%  sd {flat[col].std() * 100:.2f}%")
        print(f"     p01 {q[0.01] * 100:+.2f}%  p25 {q[0.25] * 100:+.2f}%  "
              f"p50 {q[0.5] * 100:+.2f}%  p75 {q[0.75] * 100:+.2f}%  p99 {q[0.99] * 100:+.2f}%")
    print(f"  corr(roc10, roc20) = {flat['roc10'].corr(flat['roc20']):.4f}")
    mom126 = (panel / panel.shift(126) - 1.0).stack()
    print(f"  corr(roc10, mom126) = {r10.stack().corr(mom126):.4f}")
    print()


if __name__ == "__main__":
    main()
