"""TRAIN sweep — all 5 declared variants, plus liveness. TEST is not touched here."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_multifactor")


from harness import (  # noqa: E402
    CM,
    PANEL,
    RATE,
    TEST,
    TRAIN,
    PortfolioConfig,
    buy_and_hold,
    fmt_row,
    long_mask,
    pct_live,
    run_backtest,
    score_variant,
    window_metrics,
)

from nsealgo.backtest.metrics import yearly_returns  # noqa: E402

# Declared in REPORT.md before any run. Order is the declared order.
VARIANTS = {
    "V1 period20 rsip14 rank126": dict(period=20, rsip=14, rank_days=126, fill=False),
    "V2 period20 rsip14 rank21": dict(period=20, rsip=14, rank_days=21, fill=False),
    "V3 period50 rsip14 rank126": dict(period=50, rsip=14, rank_days=126, fill=False),
    "V4 period20 rsip14 rank126 fill": dict(period=20, rsip=14, rank_days=126, fill=True),
    "V5 period20 rsip21 rank126": dict(period=20, rsip=21, rank_days=126, fill=False),
}

print(f"cost rate applied by run_backtest: {RATE*10000:.2f} bps all-in round trip\n")
print(f"panel {PANEL.shape}  {PANEL.index.min().date()} -> {PANEL.index.max().date()}\n")

# ---- signal liveness, full history and TRAIN ------------------------------ #
print("SIGNAL LIVENESS (fraction of (name, bar) obs the strategy is long)")
for label, kw in VARIANTS.items():
    frac = pct_live(PANEL, kw["period"], kw["rsip"], PANEL.index.min(), PANEL.index.max())
    tr = pct_live(PANEL, kw["period"], kw["rsip"], *TRAIN)
    print(f"  {label:<32} full {frac*100:>5.1f}%   TRAIN {tr*100:>5.1f}%")

# ---- how many names are flagged per day (book starvation check) ---------- #
print("\nFLAGGED NAMES PER DAY (TRAIN)")
for label, kw in VARIANTS.items():
    m = long_mask(PANEL.loc[TRAIN[0]:TRAIN[1]], kw["period"], kw["rsip"])
    n = m.sum(axis=1)
    print(
        f"  {label:<32} mean {n.mean():>5.1f}  p10 {n.quantile(.10):>5.0f}  "
        f"p50 {n.quantile(.50):>5.0f}  min {n.min():>4.0f}  <22 on {(n<22).mean()*100:>5.1f}% of days"
    )

# ---- TRAIN sweep --------------------------------------------------------- #
print(f"\n{'='*118}\nTRAIN {TRAIN[0].date()} -> {TRAIN[1].date()}\n{'='*118}")
rows = {}
for label, kw in VARIANTS.items():
    sc = score_variant(PANEL, **kw)
    res = run_backtest(PANEL, sc, CM, PortfolioConfig(), rebalance="M")
    m = window_metrics(res, *TRAIN)
    rows[label] = m
    print(fmt_row(label, m))

bh = buy_and_hold(PANEL, *TRAIN)
print(fmt_row("  [control] B&H eod", bh["eod"]))
print(fmt_row("  [control] B&H monthly-eq", bh["mly"]))

# ---- write a machine-readable TRAIN record ------------------------------- #
out = {k: {kk: float(vv) for kk, vv in v.items()} for k, v in rows.items()}
with open("research/agent_multifactor/train_results.json", "w") as f:
    json.dump(out, f, indent=2)

# ---- yearly returns for the declared baseline ----------------------------- #
best = max(rows.items(), key=lambda kv: kv[1]["sharpe"])
print(f"\nbest TRAIN Sharpe: {best[0]}  (Sharpe {best[1]['sharpe']:.2f})")
sc = score_variant(PANEL, **VARIANTS["V1 period20 rsip14 rank126"])
res = run_backtest(PANEL, sc, CM, PortfolioConfig(), rebalance="M")
yr = yearly_returns(res.returns.loc[TRAIN[0]:TRAIN[1]])
print("\nV1 TRAIN yearly returns:\n" + yr.map(lambda x: f"{x*100:>7.2f}%").to_string())
print(f"\nTEST window (declared, NOT evaluated in this script): {TEST[0].date()} -> {TEST[1].date()}")

