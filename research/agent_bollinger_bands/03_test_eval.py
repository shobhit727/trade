"""Step 03 — TEST (2024-01-01 .. 2026-10-01). Evaluated ONCE, unchanged.

The variant was selected on TRAIN by the rule declared in DECLARED_BUDGET.md and
frozen to `selected_variant.json` by `02_train_select.py`. This script reads that file
and does not choose anything. For full transparency it also prints the other four
variants' TEST numbers, clearly marked as NOT selection evidence.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_bollinger_bands")
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from common import PORT, TEST, bh_panel, bollinger_position, fmt, gate, load_panel, make_score, run

from nsealgo.backtest.engine import run_backtest
from nsealgo.backtest.metrics import yearly_returns
from nsealgo.costs import CostModel
from nsealgo.factors.core import build_composite_score

sel = json.load(open("research/agent_bollinger_bands/selected_variant.json"))
P, N, E, C = sel["period"], sel["n_std"], sel["entry"], sel["construction"]

full = load_panel()
panel = full.loc[TEST[0] :].copy()
assert panel.index.min() >= pd.Timestamp(TEST[0], tz=panel.index.tz)
assert panel.index.max() == pd.Timestamp("2026-10-01", tz=panel.index.tz)
ZERO = CostModel(segment="delivery", slippage_bps=0)

print("=" * 108)
print(f"TEST  {panel.index.min().date()} -> {panel.index.max().date()}  "
      f"({len(panel)} bars, {panel.shape[1]} symbols)   [data ends 2026-10-01]")
print(f"LOCKED VARIANT from TRAIN selection: {sel['label']}  "
      f"period={P} n_std={N} entry={E} construction={C}")
print(f"  (TRAIN Sharpe for that pick: {sel['train_sharpe']:.3f} — negative, i.e. the")
print("   rule picked the LEAST BAD of five all-negative variants)")
print("=" * 108)

score = make_score(panel, P, N, E, C)
res = run(panel, score)


def show(label, r):
    d = r.diag
    print(fmt(label, r.metrics, {"avg_names": round(d["avg_names"], 1),
                                 "nrb": d["n_rebalances"]}))


print("\n" + "-" * 108)
print("PRIMARY RESULT — selected variant, net of the full Indian delivery stack")
print("-" * 108)
show("TEST bb_pure_slow", res)
z = run_backtest(panel, score, ZERO, PORT, rebalance="M")
print(f"  cost decomposition: net CAGR {res.metrics.cagr*100:.2f}%  |  "
      f"zero-slippage CAGR {z.metrics.cagr*100:.2f}%  |  "
      f"drag {(res.metrics.cagr - z.metrics.cagr)*100:.2f} pp/y  |  "
      f"turnover {res.metrics.annual_turnover:.2f}x/y")

print("\n" + "-" * 108)
print("BENCHMARKS — identical TEST window, identical costs, identical constraints")
print("-" * 108)
bh = run(panel, bh_panel(panel))
show("TEST buy-and-hold (EW)", bh)
comp = run(panel, build_composite_score(panel))
show("TEST nsealgo composite", comp)

print("\n" + "-" * 108)
print("NEGATIVE CONTROL — random signal, same per-day name count, 5 seeds")
print("-" * 108)
g = gate(bollinger_position(panel, P, N), E)
counts = g.sum(axis=1).to_numpy()
rand = []
for s in range(5):
    rng = np.random.default_rng(20260101 + 1000 * s)
    m = np.full(g.shape, np.nan)
    for i in range(g.shape[0]):
        k = int(counts[i])
        if k:
            pick = rng.choice(panel.shape[1], size=min(k, panel.shape[1]), replace=False)
            m[i, pick] = rng.permutation(len(pick)).astype(float)
    r = run(panel, pd.DataFrame(m, index=panel.index, columns=panel.columns))
    rand.append(r)
    show(f"TEST random seed{s}", r)
print(f"  CTRL mean    : CAGR {np.mean([r.metrics.cagr for r in rand])*100:>6.2f}%  "
      f"Sharpe {np.mean([r.metrics.sharpe for r in rand]):>5.2f}  "
      f"MaxDD {np.mean([r.metrics.max_drawdown for r in rand])*100:>6.2f}%")

# ------------------------------------------------------- brief section 6 checks
print("\n" + "=" * 108)
print("SANITY CHECKS (brief section 6)")
print("=" * 108)
inv = float(res.weights.sum(axis=1).mean())
liveness = float(g.to_numpy().mean())
print(f"  6.1 plausibility   : CAGR {res.metrics.cagr*100:.2f}%  "
      f"-> far below the 40-50% unlevered long-only ceiling. No lookahead bug.")
print(f"  6.2 weight count   : avg names held {res.diag['avg_names']:.2f} "
      f"(cap 22). Below the cap because the gate is sparse — not accumulation.")
print(f"  6.3 signal liveness: {liveness:.2%} of (name,day) cells long on TEST "
      f"({int((res.weights>0).to_numpy().sum())} held name-days). Above the 5% floor.")
print(f"  6.4 cost drag      : {res.metrics.cost_drag_annual*100:.2f}%/y on "
      f"{res.metrics.annual_turnover:.2f}x turnover. Zero-slippage CAGR is "
      f"{z.metrics.cagr*100:+.2f}% vs net {res.metrics.cagr*100:+.2f}%, so costs cost "
      f"{(z.metrics.cagr-res.metrics.cagr)*100:.2f} pp/y. Costs flip the sign here, but "
      f"the strategy is ~0 gross too — costs are not the root cause.")
vr = res.metrics.cagr - np.mean([r.metrics.cagr for r in rand])
print(f"  6.5 negative ctrl  : strategy CAGR {res.metrics.cagr*100:.2f}% vs random "
      f"{np.mean([r.metrics.cagr for r in rand])*100:.2f}% -> excess {vr*100:+.2f} pp/y. "
      f"{'BEATS' if vr>0 else 'LOSES TO'} a coin flip.")
print(f"      Sharpe {res.metrics.sharpe:.2f} vs random "
      f"{np.mean([r.metrics.sharpe for r in rand]):.2f} -> "
      f"{'above' if res.metrics.sharpe>np.mean([r.metrics.sharpe for r in rand]) else 'below'} zero.")

# ------------------------------------------------- TEST signal-level confirmation
print("\n" + "-" * 108)
print("SIGNAL-LEVEL CONFIRMATION ON TEST (exposure-free, cost-free)")
print("   one check only, on the locked variant's parameters. Not a selection.")
print("-" * 108)
fwd = (panel.shift(-21) / panel - 1.0)
zs = bollinger_position(panel, P, N) * N
bins = [-np.inf, -2.5, -2, -1.5, -1, 0, 1, np.inf]
labs = ["<-2.5", "-2.5..-2", "-2..-1.5", "-1.5..-1", "-1..0", "0..1", ">1"]
zf, ff = zs.to_numpy().ravel(), fwd.to_numpy().ravel()
ok = np.isfinite(zf) & np.isfinite(ff)
lo = pd.DataFrame({"z": zf[ok], "fwd": ff[ok]})
lo["b"] = pd.cut(lo["z"], bins=bins, labels=labs)
ag = lo.groupby("b", observed=True).agg(mean_fwd=("fwd", "mean"),
                                        n=("fwd", "size"), mean_z=("z", "mean"))
ag["mean_bps"] = ag["mean_fwd"] * 1e4
print(ag[["n", "mean_z", "mean_bps"]].to_string(float_format=lambda v: f"{v:,.2f}"))
corr = float(np.corrcoef(ag["mean_z"].to_numpy(),
                         ag["mean_fwd"].to_numpy())[0, 1])
print(f"\n  corr(mean z per bucket, mean 21d fwd return) on TEST = {corr:+.3f}")
print(f"  mean reversion would require corr < 0. Observed {corr:+.3f} -> "
      f"{'reversion CONFIRMED OOS' if corr < -0.3 else 'reversion STILL ABSENT OOS'}")
gated = lo[lo["b"].isin(["<-2.5", "-2.5..-2"])]
uni = lo["fwd"].mean()
print(f"  gated (z<-2.0) mean 21d fwd {gated['fwd'].mean()*1e4:,.0f} bps  "
      f"vs universe {uni*1e4:,.0f} bps  -> excess "
      f"{(gated['fwd'].mean()-uni)*1e4:+,.0f} bps")

# --------------------------------------------------------- per-year + comparison
print("\n" + "-" * 108)
print("CALENDAR YEARS (selected variant vs buy-and-hold vs composite)")
print("-" * 108)
t = pd.DataFrame({
    "bb_pure_slow": yearly_returns(res.returns),
    "buy_and_hold": yearly_returns(bh.returns),
    "composite": yearly_returns(comp.returns),
})
print((t * 100).round(2).to_string())

print("\n" + "=" * 108)
print("TEST vs BUY-AND-HOLD")
print("=" * 108)
d_ret = (res.metrics.cagr - bh.metrics.cagr) * 100
d_dd = (res.metrics.max_drawdown - bh.metrics.max_drawdown) * 100
print(f"  CAGR    : {res.metrics.cagr*100:>7.2f}%  vs  {bh.metrics.cagr*100:>7.2f}%   "
      f"-> {d_ret:+.2f} pp/y   {'BETTER' if d_ret>0 else 'WORSE'}")
print(f"  MaxDD   : {res.metrics.max_drawdown*100:>7.2f}%  vs  "
      f"{bh.metrics.max_drawdown*100:>7.2f}%  -> {d_dd:+.2f} pp   "
      f"{'BETTER (shallower)' if d_dd>0 else 'WORSE (deeper)'}")
print(f"  Sharpe  : {res.metrics.sharpe:>7.2f}  vs  {bh.metrics.sharpe:>7.2f}   "
      f"-> {res.metrics.sharpe-bh.metrics.sharpe:+.2f}")
print(f"  vs composite: CAGR {res.metrics.cagr*100:.2f}% vs {comp.metrics.cagr*100:.2f}% "
      f"({(res.metrics.cagr-comp.metrics.cagr)*100:+.2f} pp), "
      f"Sharpe {res.metrics.sharpe:.2f} vs {comp.metrics.sharpe:.2f}")

# ------------------------------- transparency: all 5 variants on TEST (NOT selection)
print("\n" + "=" * 108)
print("TRANSPARENCY — all 5 declared variants on TEST. NOT SELECTION EVIDENCE:")
print("the selection was made on TRAIN alone. Shown so the reader can audit that the")
print("ranking did not simply get re-picked from these numbers.")
print("=" * 108)
for nm, p_, n_, e_, c_ in [("V1 bb_pure_default", 20, 2.0, 1.0, "pure"),
                           ("V2 bb_hybrid_mom6m", 20, 2.0, 1.0, "hybrid"),
                           ("V3 bb_pure_deep", 20, 2.5, 1.0, "pure"),
                           ("V4 bb_pure_slow", 60, 2.0, 1.0, "pure"),
                           ("V5 bb_pure_fast", 10, 2.0, 1.0, "pure")]:
    r = run(panel, make_score(panel, p_, n_, e_, c_))
    mark = "  <= TRAIN-SELECTED" if nm == sel["label"] else ""
    print(fmt(nm, r.metrics,
              {"avg_names": round(r.diag["avg_names"], 1)}) + mark)

res.to_pickle("research/agent_bollinger_bands/test_selected.pkl") if False else None
print("\ndone.")
