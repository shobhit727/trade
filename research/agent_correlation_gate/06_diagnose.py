"""POST-HOC diagnostics on TEST. No re-tuning -- the champion is already scored.

Purpose: explain WHY the champion lost, so the "next thing to try" is evidence-based.
Everything here runs on data already seen; it cannot change the result above.
"""
import benchmarks as B
import numpy as np
from common import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    load,
    score_from_signal,
    signal_panel,
)

panel, _, _ = load()
P, T = 10, 0.01
sig = signal_panel(panel, P, T)
sc = score_from_signal(sig, panel, P)

res = backtest(panel, sc, TEST_START, TEST_END)
bhc = B.bh_constrained(panel, TEST_START, TEST_END)
bh_r, bh_e, bh_m = B.bh_gross(panel, TEST_START, TEST_END)

print("TEST calendar-year returns (net of the delivery cost stack)")
def yearly(r, eq):
    y = eq.resample("YE").last().pct_change()
    y.iloc[0] = eq.resample("YE").last().iloc[0] - 1.0
    return y
ys = yearly(res.returns, res.equity)
yb = yearly(bh_r, bh_e)
for d in ys.index:
    print(f"  {d.year}   strategy {ys[d] * 100:7.2f}%   B&H equal-weight {yb[d] * 100:7.2f}%")

print(f"\nfull window  strategy CAGR {res.metrics.cagr * 100:6.2f}%  vs  "
      f"B&H {bh_m.cagr * 100:6.2f}%  ->  shortfall {(res.metrics.cagr - bh_m.cagr) * 100:+.2f} pp/yr")
print(f"             Indian 6m T-bill proxy ~6.50% -> strategy is "
      f"{(res.metrics.cagr - 0.065) * 100:+.2f} pp/yr vs cash")

# --- how much of the gap is exposure vs selection?
print("\nattribution (TEST):")
r = panel.loc[TEST_START:TEST_END].pct_change(fill_method=None).fillna(0.0)
w = res.weights
inv = (w.shift(1).fillna(0.0) * r).sum(axis=1)
bench = r.mean(axis=1)
print(f"  strategy daily gross beta to the equal-weight universe: "
      f"{np.cov(inv, bench)[0, 1] / np.var(bench, ddof=1):.3f}")
print(f"  strategy avg exposure {w.sum(axis=1).mean() * 100:.1f}%  vs  B&H 22-name "
      f"{bhc.weights.sum(axis=1).mean() * 100:.1f}%")
print(f"  -> the book runs {(w.sum(axis=1).mean() - bhc.weights.sum(axis=1).mean()) * 100:.0f} pp less invested, "
      f"so it captures only {np.cov(inv, bench)[0, 1] / np.var(bench, ddof=1) * 100:.0f}% of the market move")
print(f"  strategy turnover {res.metrics.annual_turnover:.2f}x/y vs B&H {bhc.metrics.annual_turnover:.2f}x/y "
      f"-> {res.metrics.annual_turnover / bhc.metrics.annual_turnover:.1f}x the trading")
print(f"  cost drag {res.metrics.cost_drag_annual * 100:.2f}%/y vs B&H {bhc.metrics.cost_drag_annual * 100:.2f}%/y "
      f"-> extra drag {(res.metrics.cost_drag_annual - bhc.metrics.cost_drag_annual) * 100:.2f} pp/yr")

# --- is the signal itself informative on TEST? (excess return of held names)
held = w > 1e-6
sym_ex = (r * held).sum().sum() / held.to_numpy().sum() * 244
sym_un = (r * (~held)).sum().sum() / (~held).to_numpy().sum() * 244
print(f"\n  annualised return of FLAGGED (held) names      : {sym_ex * 100:6.2f}%")
print(f"  annualised return of NON-flagged (avoided) names : {sym_un * 100:6.2f}%")
print(f"  raw selection spread (flagged - avoided)        : {(sym_ex - sym_un) * 100:+6.2f} pp/yr")

# --- same spread on TRAIN, for contrast
res_tr = backtest(panel, sc, TRAIN_START, TRAIN_END)
r_tr = panel.loc[TRAIN_START:TRAIN_END].pct_change(fill_method=None).fillna(0.0)
w_tr = res_tr.weights
h = w_tr > 1e-6
ex = (r_tr * h).sum().sum() / h.to_numpy().sum() * 244
un = (r_tr * (~h)).sum().sum() / (~h).to_numpy().sum() * 244
print(f"  [TRAIN for contrast] selection spread: {(ex - un) * 100:+6.2f} pp/yr "
      f"(flagged {ex * 100:.2f}% vs avoided {un * 100:.2f}%)")
