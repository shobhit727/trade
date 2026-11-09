"""ONE-SHOT TEST evaluation. Run once. Nothing is tuned here.

Champion was selected on TRAIN (Sharpe 0.83) and is applied UNCHANGED to
2024-01-01 -> 2026-10-01. All five declared variants are also reported on TEST
for transparency; only V2 was used for selection.
"""
from decimal import Decimal

import benchmarks as B
import numpy as np
import pandas as pd
from common import PCFG, TEST_END, TEST_START, fmt_metrics, live_frac, load, score_from_signal, signal_panel

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import CostModel

VARIANTS = [(20, 0.010), (10, 0.010), (40, 0.010), (20, 0.000), (20, 0.030)]
CHAMPION = (10, 0.010)

panel, symbols, _ = load()
out = {}

print("#" * 132)
print("# TEST 2024-01-01 -> 2026-10-01   (out-of-sample; champion chosen on TRAIN only)")
print("#" * 132)

# ---- the five declared variants on TEST -------------------------------------
rows = []
for i, (p, t) in enumerate(VARIANTS, 1):
    sig = signal_panel(panel, p, t)
    sc = score_from_signal(sig, panel, p)
    from common import backtest
    res = backtest(panel, sc, TEST_START, TEST_END)
    te = sig.loc[TEST_START:TEST_END]
    star = "  <= CHAMPION (selected on TRAIN)" if (p, t) == CHAMPION else ""
    print(fmt_metrics(f"V{i} p={p:<3} thr={t:<6}", res.metrics,
                      extra=f"live={live_frac(te) * 100:5.1f}%  names={res.diag['avg_names']:4.1f}{star}"))
    rows.append(dict(variant=f"V{i}", period=p, thr=t, **{k: getattr(res.metrics, k)
                     for k in ("cagr", "sharpe", "max_drawdown", "calmar",
                               "annual_turnover", "cost_drag_annual")},
                     names=res.diag["avg_names"], live=live_frac(te),
                     **{f"{n}_{y}": v for y in ("train", "test") for n, v in []}))
    if (p, t) == CHAMPION:
        out["champ"] = (sig, res)
pd.DataFrame(rows).to_csv("research/agent_correlation_gate/test_variants.csv", index=False)

# ---- champion full diagnostics ---------------------------------------------
sig, res = out["champ"]
w = res.weights
nc = (w > 0).sum(axis=1)
gross = w.sum(axis=1)
te = sig.loc[TEST_START:TEST_END]
print("\nchampion structural diagnostics (TEST)")
print(f"  days={len(res.returns)}  avg names={nc.mean():.2f} (cap {PCFG.max_names}) "
      f"max={nc.max()}  min={nc.min()}")
print(f"  avg gross exposure {gross.mean() * 100:.1f}%  cash {(1 - gross.mean()) * 100:.1f}%  "
      f"max single weight {w.max().max() * 100:.2f}%")
print(f"  signal liveness: long {live_frac(te) * 100:.1f}%  "
      f"short {float((te < 0).to_numpy().mean()) * 100:.1f}%  "
      f"flat {float((te == 0).to_numpy().mean()) * 100:.1f}%")
print(f"  flagged names/day: median {te.gt(0).sum(axis=1).median():.0f} "
      f"p10 {te.gt(0).sum(axis=1).quantile(.1):.0f} p90 {te.gt(0).sum(axis=1).quantile(.9):.0f}")
print(f"  round-trip cost used: {res.diag['round_trip_bps']:.2f} bps")
free = run_backtest(panel.loc[TEST_START:TEST_END], score_from_signal(sig, panel, 10).loc[TEST_START:TEST_END],
                    CostModel(segment="delivery", slippage_bps=Decimal("0"),
                              brokerage_per_order=Decimal("0")), PCFG)
print(f"  NET {res.metrics.cagr * 100:.2f}%  vs  zero-cost diagnostic {free.metrics.cagr * 100:.2f}% "
      f"-> costs cost {(free.metrics.cagr - res.metrics.cagr) * 100:.2f} pp/yr")
ye = res.equity.resample("YE").last()
yr = ye.pct_change()
yr.iloc[0] = ye.iloc[0] - 1.0
print("  test-year CAGR (net): " + "  ".join(f"{d.year}:{v * 100:6.2f}%" for d, v in yr.items()))

# ---- benchmarks and controls on TEST ---------------------------------------
print("\n" + "-" * 132)
bh_r, bh_e, bh_g = B.bh_gross(panel, TEST_START, TEST_END)
bhc = B.bh_constrained(panel, TEST_START, TEST_END)
comp = B.composite(panel, TEST_START, TEST_END)
print(fmt_metrics("B&H equal-weight (gross, brief)", bh_g))
print(fmt_metrics("B&H 22-name constrained (net)", bhc.metrics, f"names={bhc.diag['avg_names']:.1f}"))
print(fmt_metrics("nsealgo composite (net)", comp.metrics, f"names={comp.diag['avg_names']:.1f}"))

lf = live_frac(te)
ctl = B.random_control(panel, lf, TEST_START, TEST_END, seed=7, n=5)
for i, m in enumerate(ctl, 1):
    print(fmt_metrics(f"random control #{i} (live={lf * 100:.0f}%)", m))
a = np.array([m.sharpe for m in ctl])
ac = np.array([m.cagr for m in ctl])
print(f"\n  control Sharpe mean {a.mean():.2f} sd {a.std(ddof=1):.2f} | "
      f"control CAGR mean {ac.mean() * 100:.2f}%")
print(f"  strategy Sharpe {res.metrics.sharpe:.2f} -> beats {int((a < res.metrics.sharpe).sum())}/{len(a)} controls")
print(f"  strategy CAGR   {res.metrics.cagr * 100:.2f}% -> beats {int((ac < res.metrics.cagr).sum())}/{len(ac)} controls")

# ---- head to head ----------------------------------------------------------
print("\n" + "#" * 132)
print("# HEAD TO HEAD (TEST, all net of the same delivery cost stack unless marked gross)")
print("#" * 132)
tbl = pd.DataFrame([
    dict(what="correlation_gate (champion V2)", cagr=res.metrics.cagr * 100, sharpe=res.metrics.sharpe,
         maxdd=res.metrics.max_drawdown * 100, calmar=res.metrics.calmar,
         turnover=res.metrics.annual_turnover, drag=res.metrics.cost_drag_annual * 100,
         names=res.diag["avg_names"]),
    dict(what="B&H equal-weight (GROSS)", cagr=bh_g.cagr * 100, sharpe=bh_g.sharpe,
         maxdd=bh_g.max_drawdown * 100, calmar=bh_g.calmar, turnover=2.0, drag=0.0, names=48),
    dict(what="B&H 22-name constrained", cagr=bhc.metrics.cagr * 100, sharpe=bhc.metrics.sharpe,
         maxdd=bhc.metrics.max_drawdown * 100, calmar=bhc.metrics.calmar,
         turnover=bhc.metrics.annual_turnover, drag=bhc.metrics.cost_drag_annual * 100,
         names=bhc.diag["avg_names"]),
    dict(what="nsealgo composite", cagr=comp.metrics.cagr * 100, sharpe=comp.metrics.sharpe,
         maxdd=comp.metrics.max_drawdown * 100, calmar=comp.metrics.calmar,
         turnover=comp.metrics.annual_turnover, drag=comp.metrics.cost_drag_annual * 100,
         names=comp.diag["avg_names"]),
    dict(what="random-signal control (mean of 5)", cagr=ac.mean() * 100, sharpe=a.mean(),
         maxdd=float(np.mean([m.max_drawdown for m in ctl])) * 100,
         calmar=float(np.mean([m.calmar for m in ctl])),
         turnover=float(np.mean([m.annual_turnover for m in ctl])),
         drag=float(np.mean([m.cost_drag_annual for m in ctl])) * 100, names=np.nan),
]).round(2)
print(tbl.to_string(index=False))
tbl.to_csv("research/agent_correlation_gate/test_headline.csv", index=False)
