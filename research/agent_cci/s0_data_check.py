"""Step 0 — data audit + proof that the vectorised CCI == the catalog CCI."""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    cci_panel,
    header,
    load_panels,
    signal_panel,
    typical_price,
    validate_cci_matches_catalog,
)

p = load_panels()

print(header("DATA AUDIT (loader cleaning rules C1-C6 applied)"))
print(p.report.describe())
print(f"symbols        : {len(p.symbols)}")
print(f"panel rows     : {len(p.close)}")
print(f"span           : {p.close.index.min().date()} -> {p.close.index.max().date()}")
print(f"train bars     : {len(p.close.loc[TRAIN_START:TRAIN_END])}")
print(f"test bars      : {len(p.close.loc[TEST_START:TEST_END])}")
print(f"max names/day  : {p.close.shape[1]}")

print(header("VECTORISED CCI vs CATALOG INDICATOR"))
for period in (10, 14, 20):
    v = validate_cci_matches_catalog(p, period=period, n_probe=120)
    print(
        f"period={period:>3}  probes={v['n_checked']:>4}  "
        f"max_abs_error={v['max_abs_error']:.3e}  identical={v['identical']}"
    )

print(header("CCI DISTRIBUTION (full sample, all symbols)"))
tp = typical_price(p)
for period in (10, 20):
    c = cci_panel(tp, period)
    v = c.to_numpy(dtype=float).ravel()
    v = v[np.isfinite(v)]
    print(
        f"period={period:>3}  n={v.size:>9,}  mean={v.mean():>7.2f}  "
        f"sd={v.std():>7.2f}  min={v.min():>8.2f}  max={v.max():>8.2f}"
    )
    for thr in (100.0, 150.0):
        print(
            f"          entry={thr:>5.0f}  frac CCI<-entry = "
            f"{float((v < -thr).mean()):.4f}   frac CCI>+entry = "
            f"{float((v > thr).mean()):.4f}"
        )

print(header("SIGNAL LIVENESS (per rebalance date, TRAIN window)"))
c20 = cci_panel(tp, 20)
for entry in (100.0, 150.0):
    sig = signal_panel(c20, entry)
    tr = sig.loc[TRAIN_START:TRAIN_END]
    keys = tr.index.tz_localize(None).to_period("M")
    rb = [g.index[0] for _, g in tr.groupby(keys)]
    counts = [int((tr.loc[d] > 0).sum()) for d in rb]
    counts = np.array(counts)
    print(
        f"entry={entry:>5.0f}  rebalances={len(counts):>4}  "
        f"flagged names/date: mean {counts.mean():>5.2f}  median {np.median(counts):>5.1f}  "
        f"min {counts.min():>3}  max {counts.max():>3}  "
        f"dates with 0 flagged: {int((counts == 0).sum())}  "
        f"dates with <22 flagged: {int((counts < 22).sum())}"
    )
    # NaN / warmup leakage check
    warm = tr.loc[: tr.index[0] + pd.Timedelta(days=25)]
    print(f"          warmup-window flagged count (must be 0): {int((warm > 0).sum().sum())}")
