"""TRAIN-side controls, run BEFORE the single TEST read.

Three controls, all computed on TRAIN only:

  1. RANDOM-SIGNAL control. Same fraction of bars flagged as the real strategy, but the
     names are chosen at random. Minimum bar per brief section 6.5.

  2. SIGNAL-SCRAMBLED control (the one the assignment demands). The cross-sectional
     score is PERMUTED ACROSS SYMBOLS within each rebalance date. This preserves
     turnover, exposure, position count and the score distribution exactly -- only the
     mapping from score to symbol is destroyed. If the real strategy and this control
     score the same, the ranking carries no information.

  3. nsealgo COMPOSITE, the production benchmark (brief section 7.6).

Plus the zero-cost run of the selected variant, to separate "signal is dead" from
"signal is alive but costs eat it".
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    COSTS_ZERO,
    HDR,
    avg_names,
    full_panel,
    invested_frac,
    row,
    run,
    tmr_score,
    train_slice,
)

from nsealgo.factors.core import build_composite_score

sel = json.load(open("selected_variant.json"))
SLOW, ENTRY = sel["slow"], sel["entry"]
print(f"Using TRAIN-selected variant {sel['variant']} (slow={SLOW}, entry={ENTRY})\n")

panel = full_panel()
tr_panel = train_slice(panel)
score = train_slice(tmr_score(panel, SLOW, ENTRY))

# --------------------------------------------------------------------------- #
# 1. Real strategy (TRAIN reference)
# --------------------------------------------------------------------------- #
real = run(tr_panel, score, label="TRAIN real")
print(HDR)
print(row("TRAIN real strategy", real.metrics, f"names {avg_names(real):.1f}"))

# --------------------------------------------------------------------------- #
# 2. Zero-cost control — 11.92 bps statutory only, no slippage
# --------------------------------------------------------------------------- #
real_zero = run(tr_panel, score, costs=COSTS_ZERO, label="TRAIN real @0 slippage")
print(row("TRAIN real @ 0 slippage (11.92bps)", real_zero.metrics, "cost-drag A/B"))

# --------------------------------------------------------------------------- #
# 3. Random-signal control — same live fraction, random names
# --------------------------------------------------------------------------- #
n_flagged = score.notna().sum(axis=1)
live_frac = float(score.notna().to_numpy().sum()) / float(score.notna().size)
print(f"\nrandom control: live fraction {live_frac * 100:.2f}%")

rng_master = np.random.default_rng(20261011)
rand_rows = []
for seed in range(20):
    rng = np.random.default_rng(20261011 + seed)
    fake = pd.DataFrame(np.nan, index=score.index, columns=score.columns)
    arr = np.full(fake.shape, np.nan)
    for i in range(len(score)):
        k = int(n_flagged.iloc[i])
        if k == 0:
            continue
        cols = rng.choice(arr.shape[1], size=k, replace=False)
        arr[i, cols] = rng.permutation(np.arange(1, k + 1) / k)
    r = run(tr_panel, pd.DataFrame(arr, index=score.index, columns=score.columns),
            label=f"random seed {seed}")
    rand_rows.append(
        {
            "seed": seed,
            "cagr": float(r.metrics.cagr),
            "sharpe": float(r.metrics.sharpe),
            "max_drawdown": float(r.metrics.max_drawdown),
        }
    )
    print(row(f"TRAIN random seed {seed:02d}", r.metrics, ""))

rc = np.array([x["cagr"] for x in rand_rows])
rs = np.array([x["sharpe"] for x in rand_rows])
print(
    f"\nRANDOM CONTROL: CAGR mean {rc.mean() * 100:.2f}% "
    f"[p10 {np.percentile(rc, 10) * 100:.2f}%, p90 {np.percentile(rc, 90) * 100:.2f}%]  "
    f"Sharpe mean {rs.mean():.2f}"
)
print(
    f"  real CAGR {real.metrics.cagr * 100:.2f}% -> percentile "
    f"{(rc < real.metrics.cagr).mean() * 100:.0f}th"
)
print(
    f"  real Sharpe {real.metrics.sharpe:.2f} -> percentile "
    f"{(rs < real.metrics.sharpe).mean() * 100:.0f}th"
)

# --------------------------------------------------------------------------- #
# 4. Signal-scrambled control — permute scores across symbols, keep everything else
# --------------------------------------------------------------------------- #
print("\nSCRAMBLED CONTROL — permuting score across symbols within each date")
scr_rows = []
for seed in range(20):
    rng = np.random.default_rng(777000 + seed)
    arr = score.to_numpy().copy()
    for i in range(arr.shape[0]):
        rowv = arr[i]
        valid = ~np.isnan(rowv)
        if valid.sum() > 1:
            vals = rowv[valid].copy()
            rng.shuffle(vals)
            rowv[valid] = vals
            arr[i] = rowv
    r = run(tr_panel, pd.DataFrame(arr, index=score.index, columns=score.columns),
            label=f"scramble {seed}")
    scr_rows.append(
        {
            "seed": seed,
            "cagr": float(r.metrics.cagr),
            "sharpe": float(r.metrics.sharpe),
            "max_drawdown": float(r.metrics.max_drawdown),
        }
    )

sc = np.array([x["cagr"] for x in scr_rows])
ss = np.array([x["sharpe"] for x in scr_rows])
print(
    f"SCRAMBLED: CAGR mean {sc.mean() * 100:.2f}% "
    f"[p10 {np.percentile(sc, 10) * 100:.2f}%, p90 {np.percentile(sc, 90) * 100:.2f}%]  "
    f"Sharpe mean {ss.mean():.2f}"
)
print(
    f"  real CAGR {real.metrics.cagr * 100:.2f}% -> percentile "
    f"{(sc < real.metrics.cagr).mean() * 100:.0f}th"
)
print(
    f"  real Sharpe {real.metrics.sharpe:.2f} -> percentile "
    f"{(ss < real.metrics.sharpe).mean() * 100:.0f}th"
)

# --------------------------------------------------------------------------- #
# 5. nsealgo composite benchmark
# --------------------------------------------------------------------------- #
comp = build_composite_score(tr_panel)
comp_res = run(tr_panel, comp, label="TRAIN composite")
print()
print(row("TRAIN nsealgo composite", comp_res.metrics, f"names {avg_names(comp_res):.1f}"))

out = {
    "variant": sel["variant"],
    "slow": SLOW,
    "entry": ENTRY,
    "engine_sha": real.engine_sha,
    "real": {
        "cagr": float(real.metrics.cagr),
        "sharpe": float(real.metrics.sharpe),
        "calmar": float(real.metrics.calmar),
        "max_drawdown": float(real.metrics.max_drawdown),
        "total_return": float(real.metrics.total_return),
        "annual_turnover": float(real.metrics.annual_turnover),
        "cost_drag_annual": float(real.metrics.cost_drag_annual),
        "avg_names": avg_names(real),
        "invested": invested_frac(real),
    },
    "real_zero_cost": {
        "cagr": float(real_zero.metrics.cagr),
        "sharpe": float(real_zero.metrics.sharpe),
        "max_drawdown": float(real_zero.metrics.max_drawdown),
        "cost_drag_annual": float(real_zero.metrics.cost_drag_annual),
    },
    "random": {
        "seeds": rand_rows,
        "cagr_mean": float(rc.mean()),
        "sharpe_mean": float(rs.mean()),
        "cagr_p10": float(np.percentile(rc, 10)),
        "cagr_p90": float(np.percentile(rc, 90)),
        "real_cagr_percentile": float((rc < real.metrics.cagr).mean()),
        "real_sharpe_percentile": float((rs < real.metrics.sharpe).mean()),
    },
    "scrambled": {
        "seeds": scr_rows,
        "cagr_mean": float(sc.mean()),
        "sharpe_mean": float(ss.mean()),
        "cagr_p10": float(np.percentile(sc, 10)),
        "cagr_p90": float(np.percentile(sc, 90)),
        "real_cagr_percentile": float((sc < real.metrics.cagr).mean()),
        "real_sharpe_percentile": float((ss < real.metrics.sharpe).mean()),
    },
    "composite": {
        "cagr": float(comp_res.metrics.cagr),
        "sharpe": float(comp_res.metrics.sharpe),
        "max_drawdown": float(comp_res.metrics.max_drawdown),
        "cost_drag_annual": float(comp_res.metrics.cost_drag_annual),
    },
}
with open("train_controls.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("\nwrote train_controls.json")
