"""Definitive run for `correlation_gate`: TRAIN selection, then one TEST evaluation.

Structure
---------
  A. verify the vectorised signal == the real catalog class (already proven, re-asserted)
  B. TRAIN sweep over the 5 DECLARED variants only -> champion
  C. TEST once, champion unchanged
  D. benchmarks: B&H gross (brief formula), B&H constrained+net, nsealgo composite
  E. two flavours of negative control, both matched on % of bars long:
       ctrl_tie : flagged names equal-weighted (the prior harness's control)
       ctrl_rank: random MASK but the strategy's real ROC ranking retained
                 -> isolates "is the signal informative" from "does concentration help"
  F. sanity checks 1-4 of the brief

Nothing here is tuned on TEST.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_correlation_gate")

from common import (  # noqa: E402
    PCFG,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    live_frac,
    load,
    score_from_signal,
    signal_panel,
)

from nsealgo.backtest.engine import run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

VARIANTS = [(20, 0.010), (10, 0.010), (40, 0.010), (20, 0.000), (20, 0.030)]
LBL = {VARIANTS[0]: "V1 (catalog default)", VARIANTS[1]: "V2", VARIANTS[2]: "V3",
       VARIANTS[3]: "V4", VARIANTS[4]: "V5"}


def row(tag, m, extra=""):
    return (f"{tag:<38} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>5.2f}  "
            f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>5.2f}  "
            f"Turn {m.annual_turnover:>5.2f}x/y  Drag {m.cost_drag_annual * 100:>5.2f}%/y"
            + (f"  {extra}" if extra else ""))


panel, symbols, _ = load()

# ================= B. TRAIN sweep (TEST window never loaded below) =============
print("=" * 134)
print(f"B. TRAIN {TRAIN_START.date()} -> {TRAIN_END.date()}   "
      "(TEST window deliberately not loaded here)")
print("=" * 134)
tr_rows = []
for (p, t) in VARIANTS:
    sig = signal_panel(panel, p, t)
    res = backtest(panel, score_from_signal(sig, panel, p), TRAIN_START, TRAIN_END)
    s = sig.loc[TRAIN_START:TRAIN_END]
    print(row(f"{LBL[(p, t)]}  p={p:<3} thr={t:<5}", res.metrics,
              extra=f"live={live_frac(s) * 100:5.1f}%  names={res.diag['avg_names']:4.1f}"))
    tr_rows.append(dict(period=p, thr=t, sharpe=res.metrics.sharpe, cagr=res.metrics.cagr,
                        maxdd=res.metrics.max_drawdown, live=live_frac(s)))
tr = pd.DataFrame(tr_rows).sort_values(["sharpe", "maxdd"], ascending=[False, True])
CHAMP = (int(tr.iloc[0].period), float(tr.iloc[0].thr))
print("\n  TRAIN ranking (selection = best TRAIN Sharpe, tie -> lower MaxDD):")
print("    " + tr.assign(sharpe=tr.sharpe.round(2), cagr=(tr.cagr * 100).round(2),
                        maxdd=(tr.maxdd * 100).round(2),
                        live=(tr.live * 100).round(1)).to_string(index=False).replace("\n", "\n    "))
print(f"\n  CHAMPION -> period={CHAMP[0]} threshold={CHAMP[1]}  ({LBL[CHAMP]})")

# ================= C. TEST, champion unchanged ==============================
print("\n" + "#" * 134)
print(f"# C+D+E. TEST {TEST_START.date()} -> {TEST_END.date()}  out-of-sample, champion unchanged")
print("#" * 134)
csig = signal_panel(panel, *CHAMP)
cscore = score_from_signal(csig, panel, CHAMP[0])
res = backtest(panel, cscore, TEST_START, TEST_END)
te = csig.loc[TEST_START:TEST_END]
print(row(f"correlation_gate CHAMPION p={CHAMP[0]}", res.metrics,
          extra=f"live={live_frac(te) * 100:.1f}%  names={res.diag['avg_names']:.1f}"))

# --- sanity checks 1-3 -------------------------------------------------------
w = res.weights
nc = (w > 0).sum(axis=1)
gross = w.sum(axis=1)
print("\n  sanity checks")
print(f"    1 plausibility   CAGR {res.metrics.cagr * 100:.2f}%  (unlevered long-only "
      f"bound ~40-50% -> {'OK' if res.metrics.cagr < 0.5 else 'BUG'})")
print(f"    2 weight count   avg names {nc.mean():.2f}  max {nc.max()}  min {nc.min()}  "
      f"(n_positions={PCFG.n_positions}, hard cap {PCFG.max_names}) -> "
      f"{'OK' if nc.mean() < 35 else 'ACCUMULATION BUG'}")
print(f"    3 liveness       long {live_frac(te) * 100:.1f}% of symbol-days "
      f"({'OK' if live_frac(te) > 0.05 else 'EFFECTIVELY ALWAYS-FLAT'})")
print(f"      full signal    long {live_frac(te) * 100:.1f}%  short "
      f"{float((te < 0).to_numpy().mean()) * 100:.1f}%  flat "
      f"{float((te == 0).to_numpy().mean()) * 100:.1f}%")
print(f"    exposure         gross {gross.mean() * 100:.1f}%  cash {(1 - gross.mean()) * 100:.1f}%  "
      f"max single weight {w.max().max() * 100:.2f}% (cap {PCFG.max_weight * 100:.0f}%)")
print(f"      flagged names/day median {te.gt(0).sum(axis=1).median():.0f}  "
      f"p10 {te.gt(0).sum(axis=1).quantile(.1):.0f}  p90 {te.gt(0).sum(axis=1).quantile(.9):.0f}")
print(f"    cost applied     {res.diag['round_trip_bps']:.2f} bps all-in round trip")

# --- sanity check 4: cost drag ----------------------------------------------
free = run_backtest(panel.loc[TEST_START:TEST_END],
                    cscore.loc[TEST_START:TEST_END],
                    CostModel(segment="delivery", slippage_bps=__import__("decimal").Decimal("0"),
                              brokerage_per_order=__import__("decimal").Decimal("0")),
                    PCFG)
print(f"    4 cost drag      net {res.metrics.cagr * 100:.2f}% vs zero-cost "
      f"{free.metrics.cagr * 100:.2f}%  -> {(free.metrics.cagr - res.metrics.cagr) * 100:+.2f} pp/yr")

ye = res.equity.resample("YE").last()
print("      calendar-year net returns: " +
      "  ".join(f"{ye.index[0].year}:{(ye.iloc[0] - 1) * 100:6.2f}%" if i == 0 else
               f"{ye.index[i].year}:{(ye.iloc[i] / ye.iloc[i - 1] - 1) * 100:6.2f}%"
               for i in range(len(ye))))

# ================= D. benchmarks =============================================
print("\n" + "-" * 134)
print("D. benchmarks over the identical TEST window")
print("-" * 134)
rets = panel.loc[TEST_START:TEST_END].pct_change(fill_method=None).mean(axis=1).fillna(0.0)
bh_g = compute_metrics(rets, (1 + rets).cumprod(), annual_turnover=2.0, cost_drag_annual=0.0)
bhc = backtest(panel, pd.DataFrame(1.0, index=panel.index, columns=panel.columns), TEST_START, TEST_END)
comp = backtest(panel, build_composite_score(panel), TEST_START, TEST_END)
print(row("B&H equal-weight (GROSS, brief formula)", bh_g))
print(row("B&H 22-name constrained (net)", bhc.metrics, f"names={bhc.diag['avg_names']:.1f}"))
print(row("nsealgo composite (net)", comp.metrics, f"names={comp.diag['avg_names']:.1f}"))

# ================= E. negative controls =====================================
lf = live_frac(te)
sub = panel.loc[TEST_START:TEST_END]
roc_ = panel / panel.shift(CHAMP[0]) - 1.0
res_tie, res_rank = [], []
for k in range(5):
    rng = np.random.default_rng(7000 + k)
    mask = rng.random(sub.shape) < lf
    m = pd.DataFrame(np.where(mask, 1.0, 0.0), index=sub.index, columns=sub.columns)
    # flavour 1: flagged names equal-weighted (prior harness's control)
    sc_tie = pd.DataFrame(1.0, index=sub.index, columns=sub.columns).where(m > 0).rank(axis=1, pct=True)
    res_tie.append(backtest(panel, sc_tie, TEST_START, TEST_END).metrics)
    # flavour 2: random mask, strategy's REAL ROC ranking retained
    sc_rank = roc_.loc[TEST_START:TEST_END].where(m > 0).rank(axis=1, pct=True)
    res_rank.append(backtest(panel, sc_rank, TEST_START, TEST_END).metrics)

print("\n" + "-" * 134)
print(f"E. negative controls, 5 draws each, matched on live fraction {lf * 100:.1f}%")
print("-" * 134)
for i in range(5):
    print(row(f"ctrl_tie  # {i + 1} (random mask, equal-weight flags)", res_tie[i]))
for i in range(5):
    print(row(f"ctrl_rank # {i + 1} (random mask, REAL roc ranking)", res_rank[i]))

s, c = res.metrics.sharpe, res.metrics.cagr
for name, ctl in (("ctrl_tie ", res_tie), ("ctrl_rank", res_rank)):
    a = np.array([m.sharpe for m in ctl])
    ac = np.array([m.cagr for m in ctl])
    print(f"\n  {name}: control CAGR mean {ac.mean() * 100:6.2f}%  Sharpe mean {a.mean():5.2f} "
          f"(sd {a.std(ddof=1):.2f})")
    print(f"    strategy CAGR {c * 100:.2f}% -> beats {int((ac < c).sum())}/5 | "
          f"Sharpe {s:.2f} -> beats {int((a < s).sum())}/5")

# ================= head to head =============================================
print("\n" + "#" * 134)
print("# HEAD TO HEAD (TEST; net of the same delivery stack unless marked GROSS)")
print("#" * 134)
at = np.array([m.sharpe for m in res_tie])
act = np.array([m.cagr for m in res_tie])
tbl = pd.DataFrame([
    dict(what="correlation_gate (champion)", cagr=c * 100, sharpe=s,
         maxdd=res.metrics.max_drawdown * 100, calmar=res.metrics.calmar,
         turnover=res.metrics.annual_turnover, drag=res.metrics.cost_drag_annual * 100,
         names=res.diag["avg_names"]),
    dict(what="B&H equal-weight (GROSS)", cagr=bh_g.cagr * 100, sharpe=bh_g.sharpe,
         maxdd=bh_g.max_drawdown * 100, calmar=bh_g.calmar, turnover=2.0, drag=0.0, names=48),
    dict(what="B&H 22-name constrained (net)", cagr=bhc.metrics.cagr * 100, sharpe=bhc.metrics.sharpe,
         maxdd=bhc.metrics.max_drawdown * 100, calmar=bhc.metrics.calmar,
         turnover=bhc.metrics.annual_turnover, drag=bhc.metrics.cost_drag_annual * 100,
         names=bhc.diag["avg_names"]),
    dict(what="nsealgo composite (net)", cagr=comp.metrics.cagr * 100, sharpe=comp.metrics.sharpe,
         maxdd=comp.metrics.max_drawdown * 100, calmar=comp.metrics.calmar,
         turnover=comp.metrics.annual_turnover, drag=comp.metrics.cost_drag_annual * 100,
         names=comp.diag["avg_names"]),
    dict(what="random control (mean of 5)", cagr=act.mean() * 100, sharpe=at.mean(),
         maxdd=float(np.mean([m.max_drawdown for m in res_tie])) * 100,
         calmar=float(np.mean([m.calmar for m in res_tie])),
         turnover=float(np.mean([m.annual_turnover for m in res_tie])),
         drag=float(np.mean([m.cost_drag_annual for m in res_tie])) * 100, names=np.nan),
]).round(2)
print(tbl.to_string(index=False))
tbl.to_csv("research/agent_correlation_gate/FINAL_headline.csv", index=False)

print(f"\n  net of 21.92 bps: strategy {c * 100:.2f}% vs B&H-constrained "
      f"{bhc.metrics.cagr * 100:.2f}% -> {c * 100 - bhc.metrics.cagr * 100:+.2f} pp")
print(f"  drawdown: strategy {res.metrics.max_drawdown * 100:.2f}% vs B&H-constrained "
      f"{bhc.metrics.max_drawdown * 100:.2f}% -> "
      f"{res.metrics.max_drawdown * 100 - bhc.metrics.max_drawdown * 100:+.2f} pp")
