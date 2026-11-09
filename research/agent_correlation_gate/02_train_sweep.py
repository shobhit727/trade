"""TRAIN-ONLY sweep. TEST is not touched here.

DECLARED PARAMETER BUDGET (written before any run -- brief section 4):

  score construction : FIXED for all variants.
                       score = cross-sectional pct-rank of the strategy's own
                       ROC(period) taken only over names flagged +1.
                       Names flagged 0/-1 -> NaN -> excluded (long-only).
  rebalance          : monthly (engine default, matches nsealgo's evidence note)
  portfolio          : PortfolioConfig() defaults (22 names, 12%/25%/10%)
  costs              : CostModel(segment="delivery", slippage_bps=5)

  the 5 variants (the ONLY 5 parameter variants that will ever be run):
    V1  period=20  threshold=0.010   <- catalog default
    V2  period=10  threshold=0.010
    V3  period=40  threshold=0.010
    V4  period=20  threshold=0.000
    V5  period=20  threshold=0.030

  selection rule (declared up front): highest TRAIN Sharpe; tie -> lower TRAIN MaxDD.
"""
import pandas as pd
from common import (
    TRAIN_END,
    TRAIN_START,
    backtest,
    fmt_metrics,
    live_frac,
    load,
    score_from_signal,
    signal_panel,
)

VARIANTS = [(20, 0.010), (10, 0.010), (40, 0.010), (20, 0.000), (20, 0.030)]

panel, symbols, _ = load()
rows = []
print("=" * 130)
print("TRAIN 2016-01-01 -> 2023-12-31   (TEST window deliberately not loaded here)")
print("=" * 130)
for i, (p, t) in enumerate(VARIANTS, 1):
    sig = signal_panel(panel, p, t)
    sc = score_from_signal(sig, panel, p)
    tr = sig.loc[TRAIN_START:TRAIN_END]
    res = backtest(panel, sc, TRAIN_START, TRAIN_END)
    tagged = "  <- catalog default" if (p, t) == VARIANTS[0] else ""
    print(fmt_metrics(
        f"V{i} p={p:<3} thr={t:<6}", res.metrics,
        extra=f"live={live_frac(tr) * 100:5.1f}%  names={res.diag['avg_names']:4.1f}"
              f"  nflag_med={tr.gt(0).sum(axis=1).median():4.0f}{tagged}"))
    rows.append(dict(variant=f"V{i}", period=p, thr=t, sharpe=res.metrics.sharpe,
                     cagr=res.metrics.cagr, maxdd=res.metrics.max_drawdown,
                     calmar=res.metrics.calmar, live=live_frac(tr),
                     names=res.diag["avg_names"]))

df = pd.DataFrame(rows).sort_values(["sharpe", "maxdd"], ascending=[False, True])
print("\nTRAIN ranking (selection = best TRAIN Sharpe):")
print(df.assign(sharpe=df.sharpe.round(2), cagr=(df.cagr * 100).round(2),
                maxdd=(df.maxdd * 100).round(2), live=(df.live * 100).round(1),
                names=df.names.round(1)).to_string(index=False))
CHAMPION = df.iloc[0]
print(f"\nCHAMPION -> {CHAMPION.variant} period={CHAMPION.period} threshold={CHAMPION.thr}")
df.to_csv("research/agent_correlation_gate/train_sweep.csv", index=False)
