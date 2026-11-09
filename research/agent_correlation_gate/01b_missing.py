import pandas as pd
from common import TEST_START, TRAIN_START, load

panel, symbols, _ = load()
rows=[]
for s in symbols:
    v = panel[s].dropna()
    gaps = panel[s].isna().sum()
    rows.append(dict(sym=s, first=v.index[0].date(), last=v.index[-1].date(), n=len(v), missing=int(gaps),
                     in_train=int(((v.index>=TRAIN_START)&(v.index<=pd.Timestamp("2023-12-31",tz="Asia/Kolkata"))).sum()),
                     in_test=int((v.index>=TEST_START).sum())))
df=pd.DataFrame(rows).set_index("sym")
print(df.sort_values("missing",ascending=False).head(10).to_string())
print("\nTEST-window coverage: min bars =", df.in_test.min(), "| symbols with <200 test bars:", df[df.in_test<200].index.tolist())
print("TRAIN coverage: min bars =", df.in_train.min(), "| symbols with <1000 train bars:", df[df.in_train<1000].index.tolist())
