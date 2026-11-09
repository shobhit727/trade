"""Mandatory first step: load the universe and print the audit report."""
import sys

sys.path.insert(0, "src")
from nsealgo.data.loader import load_universe  # noqa: E402

panel, symbols, report = load_universe("data/nse")
print(report.describe())
print()
print("panel shape :", panel.shape)
print("symbols     :", len(symbols))
print("index       :", panel.index.min(), "->", panel.index.max(), "| tz:", panel.index.tz)
print("dtype       :", panel.dtypes.unique())
print("NaNs        :", int(panel.isna().sum().sum()))
print("non-positive:", int((panel <= 0).sum().sum()))
