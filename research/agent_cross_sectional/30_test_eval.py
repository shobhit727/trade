"""Step 30 — the ONE evaluation of TEST (2024-01-01 .. 2026-10-01).

V1 was selected on TRAIN in step 20 and is evaluated here **unchanged**. No
parameter is touched after seeing TEST. Controls: buy-and-hold, a random-signal
control matched on cross-sectional selectivity, and the nsealgo composite.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_cross_sectional")

import numpy as np  # noqa: E402
from common import (  # noqa: E402
    COST,
    PORTFOLIO,
    TEST_END,
    TEST_START,
    VARIANTS,
    build_score,
    buy_and_hold,
    diagnostics,
    liveness,
    metrics_table,
    random_control,
    run_backtest,
    yearly,
    yearly_returns_safe,
)

from nsealgo.backtest.engine import _rebalance_dates  # noqa: E402
from nsealgo.costs import STRESS_MODELS  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

with open("research/agent_cross_sectional/20_train.json") as fh:
    train_pick = json.load(fh)
SEL = train_pick["selected"]
variant = next(v for v in VARIANTS if v.tag == SEL)

print("=" * 78)
print(f"TEST EVALUATION — variant {SEL} selected on TRAIN, evaluated UNCHANGED")
print("=" * 78)
print(f"  {variant}")
print(f"  TRAIN selection detail: {variant.note}")
print(f"  TEST window: {TEST_START.date()} .. {TEST_END.date()}")
print(f"  cost model: {COST.segment}, slippage {COST.slippage_bps} bps/side")
print()

panel, symbols, _ = load_universe("data/nse")
test = panel.loc[(panel.index >= TEST_START) & (panel.index <= TEST_END)]
assert test.index.min() >= TEST_START and test.index.max() <= TEST_END
print(f"TEST panel: {test.shape}  {test.index[0].date()} .. {test.index[-1].date()}")
print(f"years: {len(test) / 244:.2f}\n")

# --------------------------------------------------------------------------- #
# 1. The strategy
# --------------------------------------------------------------------------- #
score, sig = build_score(test, variant.period, variant.threshold, variant.rank_days)
res = run_backtest(test, score, COST, PORTFOLIO, variant.rebalance)

print("--- STRATEGY (net of full Indian delivery stack) ---")
print(res.summary())
print(diagnostics(res))
print(liveness(sig, "signal liveness"))
rb = _rebalance_dates(test.index, variant.rebalance)
elig = sig.loc[rb].gt(0).sum(axis=1)
n_held = (res.weights > 0).sum(axis=1)
print(f"    eligible/rebalance  : mean {elig.mean():.1f} min {int(elig.min())} "
      f"max {int(elig.max())}")
print(f"    names held          : mean {n_held.mean():.2f} "
      f"MAX {int(n_held.max())} (engine hard limit max_names={PORTFOLIO.max_names})")
print(f"    drawdown check      : min equity {res.equity.min():.4f} "
      f"final {res.equity.iloc[-1]:.4f}")
print(f"    yearly              : {yearly(res.returns)}")
print(f"    costs paid (nominal): Rs {res.costs_paid:,.0f} on Rs 21,00,000 book")
print()

# --------------------------------------------------------------------------- #
# 2. Buy-and-hold benchmark, identical window
# --------------------------------------------------------------------------- #
bh = buy_and_hold(test, COST)
print("--- BUY-AND-HOLD, same window, same costs ---")
print(bh.summary())
print(f"    yearly              : {yearly(bh.returns)}")
print()

# --------------------------------------------------------------------------- #
# 3. Random-signal control, matched on selectivity
# --------------------------------------------------------------------------- #
elig_series = elig
rand = [random_control(test, elig_series, seed=s, config=PORTFOLIO,
                       rebalance=variant.rebalance) for s in (1, 2, 3, 4, 5)]
print("--- RANDOM-SIGNAL CONTROL (same eligible count each rebalance, no signal) ---")
for i, r in enumerate(rand, 1):
    print(f"  seed {i}: {r.summary().splitlines()[0]}")
print(f"  mean CAGR {np.mean([r.metrics.cagr for r in rand]) * 100:6.2f}%  "
      f"mean Sharpe {np.mean([r.metrics.sharpe for r in rand]):5.2f}  "
      f"mean MaxDD {np.mean([r.metrics.max_drawdown for r in rand]) * 100:7.2f}%")
print()

# --------------------------------------------------------------------------- #
# 4. nsealgo composite
# --------------------------------------------------------------------------- #
comp = run_backtest(test, build_composite_score(test), COST, PORTFOLIO, "M")
print("--- NSEALGO COMPOSITE (same window, same costs) ---")
print(comp.summary())
print()

# --------------------------------------------------------------------------- #
# 5. Cost stress + gross diagnostic (NOT a result — a diagnostic)
# --------------------------------------------------------------------------- #
print("--- COST SENSITIVITY / GROSS DIAGNOSTIC (diagnostic, not a result) ---")
print(f"  zero cost (gross of all frictions) : "
      f"{run_backtest(test, score, STRESS_MODELS['zero_cost'], PORTFOLIO, variant.rebalance).metrics.cagr * 100:6.2f}% CAGR")
for nm in ("base", "double_slippage", "triple_slippage"):
    m = run_backtest(test, score, STRESS_MODELS[nm], PORTFOLIO, variant.rebalance).metrics
    print(f"  {nm:<20} : CAGR {m.cagr * 100:6.2f}%  Sharpe {m.sharpe:5.2f}  "
          f"CostDrag {m.cost_drag_annual * 100:.2f}%/y")
print()

# --------------------------------------------------------------------------- #
# 6. Headline table
# --------------------------------------------------------------------------- #
print("=" * 78)
print("TEST (2024-01-01 .. 2026-10-01) — NET OF COSTS")
print("=" * 78)
print(metrics_table([
    (f"STRATEGY {SEL}", res.metrics),
    ("buy-and-hold", bh.metrics),
    ("random mean", type("M", (), {
        "cagr": np.mean([r.metrics.cagr for r in rand]),
        "sharpe": np.mean([r.metrics.sharpe for r in rand]),
        "max_drawdown": np.mean([r.metrics.max_drawdown for r in rand]),
        "calmar": np.mean([r.metrics.calmar for r in rand]),
        "sortino": np.mean([r.metrics.sortino for r in rand]),
        "volatility": np.mean([r.metrics.volatility for r in rand]),
        "total_return": np.mean([r.metrics.total_return for r in rand]),
        "annual_turnover": np.mean([r.metrics.annual_turnover for r in rand]),
        "cost_drag_annual": np.mean([r.metrics.cost_drag_annual for r in rand]),
        "trades_per_year": np.mean([r.metrics.trades_per_year for r in rand]),
        "win_rate": np.mean([r.metrics.win_rate for r in rand]),
    })()),
    ("nsealgo composite", comp.metrics),
]))
print()

d_ret = (res.metrics.cagr - bh.metrics.cagr) * 100
d_dd = (res.metrics.max_drawdown - bh.metrics.max_drawdown) * 100
d_rnd = (res.metrics.cagr - np.mean([r.metrics.cagr for r in rand])) * 100
d_cmp = (res.metrics.cagr - comp.metrics.cagr) * 100
print(f"  vs buy-and-hold  : CAGR {d_ret:+.2f} pp   "
      f"MaxDD {d_dd:+.2f} pp  ({'shallower' if d_dd > 0 else 'DEEPER'})")
print(f"  vs random control: CAGR {d_rnd:+.2f} pp   "
      f"Sharpe {res.metrics.sharpe - np.mean([r.metrics.sharpe for r in rand]):+.2f}")
print(f"  vs composite     : CAGR {d_cmp:+.2f} pp   "
      f"Sharpe {res.metrics.sharpe - comp.metrics.sharpe:+.2f}")
print()

out = {
    "selected": SEL,
    "variant": {"period": variant.period, "threshold": variant.threshold,
                "rank_days": variant.rank_days, "rebalance": variant.rebalance},
    "test_start": str(TEST_START.date()), "test_end": str(TEST_END.date()),
    "strategy": res.metrics.as_dict(),
    "buy_hold": bh.metrics.as_dict(),
    "random_mean": {
        k: float(np.mean([getattr(r.metrics, k) for r in rand]))
        for k in ("cagr", "sharpe", "max_drawdown", "calmar", "sortino",
                  "volatility", "total_return", "annual_turnover",
                  "cost_drag_annual", "trades_per_year", "win_rate")
    },
    "random_seeds": [
        {"cagr": r.metrics.cagr, "sharpe": r.metrics.sharpe,
         "max_drawdown": r.metrics.max_drawdown} for r in rand
    ],
    "composite": comp.metrics.as_dict(),
    "diag": {k: float(v) for k, v in res.diag.items()},
    "strategy_yearly": {str(k): float(v) for k, v in
                        yearly_returns_safe(res.returns).items()},
    "bh_yearly": {str(k): float(v) for k, v in
                  yearly_returns_safe(bh.returns).items()},
}
with open("research/agent_cross_sectional/30_test.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("wrote research/agent_cross_sectional/30_test.json")
print(f"equity curve -> research/agent_cross_sectional/test_equity_{SEL}.csv")
res.equity.to_csv(f"research/agent_cross_sectional/test_equity_{SEL}.csv")
bh.equity.to_csv("research/agent_cross_sectional/test_equity_bh.csv")
