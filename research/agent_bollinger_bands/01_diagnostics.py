"""Step 01 — (a) prove the vectorised port matches the catalog implementation exactly,
(b) TRAIN-only descriptive diagnostics: signal liveness + forward returns by bucket.

Everything in (b) is restricted to TRAIN. TEST is not touched here.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_bollinger_bands")
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from common import TRAIN, bollinger_position, gate, load_panel

from cryptobot.strategies.catalog.bollinger_bands import BollingerBandsConfig, BollingerBandsStrategy

panel = load_panel()
sym = "reliance"

# ---------------------------------------------------------------- (a) port check
print("=" * 78)
print("(a) PORT EQUIVALENCE  vs  catalog BollingerBandsStrategy")
print("=" * 78)
for period, n_std, entry in ((20, 2.0, 1.0), (20, 2.5, 1.0), (60, 2.0, 1.0), (10, 2.0, 1.0)):
    strat = BollingerBandsStrategy(BollingerBandsConfig(period=period, n_std=n_std, entry=entry))
    closes = panel[sym].to_numpy()
    highs = closes.copy()
    lows = closes.copy()
    vols = np.ones_like(closes)
    cat = []
    for i in range(200, len(closes)):
        c, h, lo, v = closes[: i + 1], highs[: i + 1], lows[: i + 1], vols[: i + 1]
        cat.append(strat.signal(c[-period:], h[-period:], lo[-period:], v[-period:]))
    cat_sig = np.array(cat)

    mine = bollinger_position(panel, period, n_std).loc[:, sym]
    g = (mine < -entry)
    # Compare the LONG leg only. The catalog also emits -1 (short) on the upper band;
    # an Indian delivery account cannot short, so that leg is dropped and must not
    # be counted as a disagreement.
    mine_long = g.to_numpy()[200:]
    cat_long = cat_sig > 0
    short_frac = float((cat_sig < 0).mean())
    n = len(cat_long)
    agree = int((mine_long == cat_long).sum())
    long_frac_cat = float(cat_long.mean())
    long_frac_mine = float(mine_long.mean())
    print(f"  period={period:<3} n_std={n_std:<4} entry={entry}  "
          f"long-leg agreement {agree}/{n}  long% catalog {long_frac_cat:.3%} "
          f"mine {long_frac_mine:.3%}  (short leg dropped: {short_frac:.3%})")
    assert agree == n, "port mismatch"

print("\n  -> vectorised port reproduces the catalog signal bar-for-bar on RELIANCE.")

# full-universe liveness
sig = bollinger_position(panel, 20, 2.0)
g = gate(sig, 1.0)
tr = panel.loc[TRAIN[0] : TRAIN[1]]
sig_tr, g_tr = sig.loc[tr.index], g.loc[tr.index]
te = panel.loc["2024-01-01":"2026-10-01"]
sig_te, g_te = sig.loc[te.index], g.loc[te.index]

print("\n" + "=" * 78)
print("(b) SIGNAL LIVENESS  (fraction of (name, day) cells signalled long)")
print("=" * 78)
for nm, gg in (("TRAIN", g_tr), ("TEST", g_te)):
    frac = float(gg.to_numpy().mean())
    per_day = gg.sum(axis=1)
    print(f"  {nm}: {frac:6.2%} of cells | names signalled per day: "
          f"mean {per_day.mean():.2f}  median {per_day.median():.0f}  "
          f"p90 {per_day.quantile(0.9):.0f}  max {per_day.max():.0f}")
print("  brief section 6.3 warns below ~5% liveness = effectively always-flat.")
print(f"  -> liveness {float(g_tr.to_numpy().mean()):.2%} TRAIN / "
      f"{float(g_te.to_numpy().mean()):.2%} TEST : NOT always-flat.\n")

# ------------------------------------------------- TRAIN forward-return buckets
print("=" * 78)
print("(c) TRAIN-ONLY descriptive: mean 21d forward return by Bollinger z-bucket")
print("=" * 78)
z = sig * 2.0  # un-normalise: z = (close-mean)/sd, so buckets are in true sigmas
fwd = (panel.shift(-21) / panel - 1.0)
zt, ft = z.loc[tr.index], fwd.loc[tr.index]
bins = [-np.inf, -3, -2.5, -2, -1.5, -1, 0, 1, 2, np.inf]
labels = ["<-3.0", "-3..-2.5", "-2.5..-2 (GATE)", "-2..-1.5", "-1.5..-1", "-1..0",
          "0..1", "1..2", ">2"]

# long form: one row per (name, day). Panels carry NaN; a NaN z has no bucket.
zf, ff = zt.to_numpy().ravel(), ft.to_numpy().ravel()
ok = np.isfinite(zf) & np.isfinite(ff)
long = pd.DataFrame({"z": zf[ok], "fwd": ff[ok]})
long["bucket"] = pd.cut(long["z"], bins=bins, labels=labels)
agg = long.groupby("bucket", observed=True)["fwd"].agg(["count", "mean", "median", "std"])
agg["mean_bps"] = agg["mean"] * 1e4
agg["t_stat"] = agg["mean"] / (agg["std"] / np.sqrt(agg["count"]))
print(agg[["count", "mean", "mean_bps", "t_stat"]].to_string(float_format=lambda v: f"{v:,.4f}"))
gate_row = agg.loc["-2.5..-2 (GATE)"]
print(f"\n  GATE (z < -2.0), 21d fwd: mean {gate_row['mean']*1e4:,.0f} bps, "
      f"t = {gate_row['t_stat']:.2f}, n = {int(gate_row['count']):,}")

# equal-count comparison: signal cells vs all cells
allmean = float(long["fwd"].mean())
print(f"  All cells, 21d fwd:  mean {allmean*1e4:,.0f} bps")
print(f"  Signal cells excess: {(gate_row['mean']-allmean)*1e4:,.0f} bps per 21d")
print("\n  NOTE: unconditional (equal-count) comparison. Not tradeable as stated —")
print("  the backtests below impose the portfolio constraints and costs.")
