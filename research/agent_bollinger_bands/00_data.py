"""Step 00 — mandatory data load + universe sanity (brief section 2)."""

import sys

sys.path.insert(0, "src")

import pandas as pd

from nsealgo.data.loader import load_universe

panel, symbols, report = load_universe("data/nse")
print(report.describe())
print("panel", panel.shape, panel.index.min().date(), panel.index.max().date())
print("symbols", len(symbols), "tz", panel.index.tz)

assert panel.index.is_monotonic_increasing
assert not panel.index.has_duplicates

TRAIN = (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"), pd.Timestamp("2023-12-31", tz="Asia/Kolkata"))
TEST = (pd.Timestamp("2024-01-01", tz="Asia/Kolkata"), pd.Timestamp("2026-10-01", tz="Asia/Kolkata"))

tr = panel.loc[: TRAIN[1]]
te = panel.loc[TEST[0] :]
print(f"\nTRAIN bars {len(tr)}  {tr.index.min().date()} -> {tr.index.max().date()}")
print(f"TEST  bars {len(te)}  {te.index.min().date()} -> {te.index.max().date()}")

# --- missing-data audit. load_universe does NOT forward-fill; NaN close -> NaN in
# every rolling factor -> name is simply not scoreable that day. That is the safe
# behaviour (no synthetic prices). Quantify it so it is not a hidden drag.
nan_frac_tr = tr.isna().mean()
nan_frac_te = te.isna().mean()
print("\nNaN close fraction per symbol (TRAIN), worst 8:")
print(nan_frac_tr.sort_values(ascending=False).head(8).round(4).to_string())
print("\nNaN close fraction per symbol (TEST), worst 8:")
print(nan_frac_te.sort_values(ascending=False).head(8).round(4).to_string())
print(f"\nsymbols ever NaN in TRAIN: {int((nan_frac_tr>0).sum())} / {len(symbols)}")
print(f"symbols ever NaN in TEST : {int((nan_frac_te>0).sum())} / {len(symbols)}")
print(f"fully clean in both      : {int(((nan_frac_tr==0)&(nan_frac_te==0)).sum())} / {len(symbols)}")

# Symbols whose first bar falls inside TRAIN/TEST (late listings)
first_seen = panel.apply(lambda s: s.first_valid_index())
print("\nlate listings (first valid bar after 2016):")
print(first_seen[first_seen > TRAIN[0]].sort_values().to_string())

mkt = panel.pct_change(fill_method=None).mean(axis=1)
for nm, (a, b) in (("TRAIN", TRAIN), ("TEST", TEST)):
    s = mkt.loc[a:b]
    eq = (1 + s.fillna(0.0)).cumprod()
    yrs = len(s) / 244
    print(f"\n{nm} equal-weight universe: CAGR {(eq.iloc[-1]**(1/yrs)-1)*100:.2f}%  "
          f"total {(eq.iloc[-1]-1)*100:.2f}%")

panel.to_pickle("research/agent_bollinger_bands/panel.pkl")
with open("research/agent_bollinger_bands/symbols.txt", "w") as fh:
    fh.write("\n".join(symbols))
print("\nsaved panel.pkl")
