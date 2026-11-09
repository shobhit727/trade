"""Second diagnostic: exposure decay, cash days, turnover concentration. TEST only."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_macd")

import macd_lib as M  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

TEST = ("2024-01-01", "2026-10-01")
BEST = (5, 20, 9)
DEFAULT = (12, 26, 9)
COST = CostModel(segment="delivery", slippage_bps=5)

panel, _, _ = load_universe("data/nse")
px = panel.loc[TEST[0] : TEST[1]]
out = {}

for lbl, params in (("V3_5_20_9", BEST), ("V1_12_26_9", DEFAULT)):
    sc = M.score_from_signal(panel, M.signal_state(panel, *params), 126).loc[px.index]
    res = run_backtest(px, sc, COST, PortfolioConfig())
    inv = res.weights.sum(axis=1)
    st = M.signal_state(panel, *params).loc[px.index]
    n_long = (st > 0).sum(axis=1)
    out[lbl] = {
        "gross_exposure_mean": round(float(inv.mean()), 4),
        "days_below_25pct_exposure_pct": round(float((inv < 0.25).mean() * 100), 1),
        "days_below_5pct_exposure_pct": round(float((inv < 0.05).mean() * 100), 1),
        "days_zero_names_long_pct": round(float((n_long == 0).mean() * 100), 1),
        "days_lt_5_names_long_pct": round(float((n_long < 5).mean() * 100), 1),
        "final_gross_exposure": round(float(inv.iloc[-1]), 4),
        "annual_turnover_x": round(res.metrics.annual_turnover, 2),
        "cost_drag_pct_y": round(res.metrics.cost_drag_annual * 100, 2),
        "cagr_pct": round(res.metrics.cagr * 100, 2),
    }
    print(f"--- {lbl} ---")
    for k, v in out[lbl].items():
        print(f"  {k:38s} {v}")

# what does the market do? context for the TEST window
mkt = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
eq = (1 + mkt).cumprod()
out["market_test"] = {
    "total_ret_pct": round(float((eq.iloc[-1] - 1) * 100), 2),
    "cagr_pct": round(float((eq.iloc[-1] ** (244 / len(eq)) - 1) * 100), 2),
    "maxdd_pct": round(float((eq / eq.cummax() - 1).min() * 100), 2),
    "frac_days_up": round(float((mkt > 0).mean() * 100), 1),
}
print("\nmarket (equal-weight universe, gross, TEST):", out["market_test"])

# how concentrated is the result in a couple of names?
w = res.weights
contrib = (w.shift(1) * px.pct_change(fill_method=None).fillna(0.0)).sum()
tot = contrib.sum()
top = contrib.nlargest(5)
out["pnl_concentration_top5"] = round(float(top.sum() / tot), 3) if tot else None
out["pnl_top5_names"] = {k: round(float(v / tot), 3) for k, v in top.items()}
print("V1 pnl concentration: top-5 names =", out["pnl_concentration_top5"], out["pnl_top5_names"])

with open("research/agent_macd/diag2.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("\nwrote research/agent_macd/diag2.json")
