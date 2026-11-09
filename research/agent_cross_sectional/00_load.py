"""Step 00 — mandatory data audit for the cross_sectional agent."""

import sys

sys.path.insert(0, "src")
import pandas as pd  # noqa: E402

from nsealgo.data.loader import load_universe  # noqa: E402

panel, symbols, report = load_universe("data/nse")
print(report.describe())
print("symbols:", len(symbols))
print("panel shape:", panel.shape)
print("index tz:", panel.index.tz, "| first", panel.index[0], "| last", panel.index[-1])
print("dtypes:", panel.dtypes.unique())
print("NaN total:", int(panel.isna().sum().sum()))
print()
print("=== head ===")
print(panel.iloc[:3, :5])
print("=== tail ===")
print(panel.iloc[-3:, :5])
print()
# Per-symbol history coverage (survivorship-bias disclosure input)
cov = pd.DataFrame(
    {
        "first": panel.apply(lambda c: c.first_valid_index()),
        "last": panel.apply(lambda c: c.last_valid_index()),
        "n": panel.notna().sum(),
    }
).sort_values("n")
print("=== symbols with shortest history ===")
print(cov.head(8).to_string())
print("=== symbols with longest history ===")
print(cov.tail(8).to_string())
print()
print("bars per year (all symbols):")
print(panel.groupby(panel.index.year).size().to_string())
