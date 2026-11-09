from nsealgo.data.loader import load_universe

panel, symbols, report = load_universe("data/nse")
print(report.describe())
print("symbols:", len(symbols))
print("panel shape:", panel.shape)
print("index tz:", panel.index.tz, "| first", panel.index[0], "| last", panel.index[-1])
print("dtypes:", panel.dtypes.unique())
print(panel.iloc[:3, :5])
print(panel.iloc[-3:, :5])
print("NaN count total:", int(panel.isna().sum().sum()))
