"""Fill the two gaps in run.py's output: buy-and-hold calendar years, and when the
book is empty (a warm-up artefact or a real cash episode)."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_macd")

import macd_lib as M  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

COST = CostModel(segment="delivery", slippage_bps=5)
TEST = ("2024-01-01", "2026-10-01")
BEST = (5, 20, 9)
panel, _, _ = load_universe("data/nse")
px = panel.loc[TEST[0] : TEST[1]]
out = {}

# --- buy-and-hold calendar years, computed correctly ---
r = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
rate = float(COST.all_in_round_trip_bps(100000)) / 10_000.0
r.iloc[0] = r.iloc[0] - rate
bh_yearly = (yearly_returns(r) * 100).round(2)
out["bh_yearly"] = {str(k): float(v) for k, v in bh_yearly.items()}
print("buy-and-hold TEST calendar years (%):", out["bh_yearly"])

# --- when is the book empty? ---
sc = M.score_from_signal(panel, M.signal_state(panel, *BEST), 126).loc[px.index]
res = run_backtest(px, sc, COST, PortfolioConfig())
cnt = (res.weights > 0).sum(axis=1)
zero = cnt[cnt == 0]
out["zero_name_days"] = {
    "n": int(len(zero)),
    "dates": [str(d.date()) for d in zero.index[:10]],
    "first_nonempty": str(cnt[ cnt > 0].index[0].date()) if (cnt > 0).any() else None,
}
print("zero-name days:", out["zero_name_days"])

# --- how long is the vol warm-up that starves the first rebalance? ---
rets = px.pct_change(fill_method=None).fillna(0.0)
vol = rets.rolling(60, min_periods=20).std()
out["vol_warmup"] = {
    "first_bar_with_any_vol": str(vol.notna().any(axis=1).idxmax().date()),
    "first_bar_with_22_valid_vol": None,
}
ok22 = vol.notna().sum(axis=1) >= 22
out["vol_warmup"]["first_bar_with_22_valid_vol"] = (
    str(ok22[ok22].index[0].date()) if ok22.any() else None
)
print("vol warm-up:", out["vol_warmup"])

# --- full TEST window growth, both sides ---
out["macd_total_ret_pct"] = round(float(res.equity.iloc[-1] - 1) * 100, 2)
out["bh_total_ret_pct"] = round(float((1 + r).cumprod().iloc[-1] - 1) * 100, 2)
print("total return TEST: macd", out["macd_total_ret_pct"], "bh", out["bh_total_ret_pct"])

# --- TRAIN total for the selected variant, and its TRAIN calendar years ---
tr = panel.loc["2016-01-01" : "2023-12-31"]
sctr = M.score_from_signal(panel, M.signal_state(panel, *BEST), 126).loc[tr.index]
rtr = run_backtest(tr, sctr, COST, PortfolioConfig())
out["train_yearly"] = {str(k): round(float(v) * 100, 2)
                       for k, v in yearly_returns(rtr.returns).items()}
print("TRAIN calendar years (%):", out["train_yearly"])

with open("research/agent_macd/diag3.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("\nwrote research/agent_macd/diag3.json")
