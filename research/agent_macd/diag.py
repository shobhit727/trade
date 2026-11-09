"""TRAIN+TEST diagnostics for the MACD run. Does not re-select anything."""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_macd")

import macd_lib as M  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

TEST = ("2024-01-01", "2026-10-01")
TRAIN = ("2016-01-01", "2023-12-31")
BEST = (5, 20, 9)
DEFAULT = (12, 26, 9)
MOM_DAYS = 126
COST = CostModel(segment="delivery", slippage_bps=5)

panel, symbols, _ = load_universe("data/nse")
px = panel.loc[TEST[0] : TEST[1]]
out = {}

st = M.signal_state(panel, *BEST)
score = M.score_from_signal(panel, st, MOM_DAYS).loc[px.index]

# --- why 28.8 names, not 22? how many names are scoreable each day? ---
n_valid = score.notna().sum(axis=1)
out["test_scoreable_names"] = {
    "mean": round(float(n_valid.mean()), 2),
    "median": float(n_valid.median()),
    "p05": int(n_valid.quantile(0.05)),
    "min": int(n_valid.min()),
    "max": int(n_valid.max()),
    "frac_days_lt_22": round(float((n_valid < 22).mean()), 3),
}
print("TEST scoreable names per day:", out["test_scoreable_names"])

stt = st.loc[px.index]
n_long = (stt > 0).sum(axis=1)
out["test_names_long"] = {
    "mean": round(float(n_long.mean()), 2),
    "median": float(n_long.median()),
    "min": int(n_long.min()),
    "max": int(n_long.max()),
}
print("TEST names long per day:", out["test_names_long"])

# --- weights over TEST ---
res = run_backtest(px, score, COST, PortfolioConfig())
held = res.weights
cnt = (held > 0).sum(axis=1)
out["test_held_names"] = {
    "mean": round(float(cnt.mean()), 1),
    "median": float(cnt.median()),
    "first_bar": int(cnt.iloc[0]),
    "min_after_bar1": int(cnt.iloc[1:].min()),
    "max": int(cnt.max()),
    "p95": int(cnt.quantile(0.95)),
}
print("TEST held names:", out["test_held_names"])
print("  weight at bar0 sum:", round(float(held.iloc[0].sum()), 4))
print("  weight at bar1 sum:", round(float(held.iloc[1].sum()), 4))

# --- cash actually held (1 - sum(w)) ---
inv = held.sum(axis=1)
out["test_gross_exposure"] = {
    "mean": round(float(inv.mean()), 4),
    "min": round(float(inv.min()), 4),
    "max": round(float(inv.max()), 4),
}
print("TEST gross exposure (mean/min/max):", out["test_gross_exposure"])

# --- random control: full Sharpe distribution ---
lf = float((stt > 0).to_numpy().mean())
rng_rows = []
for s in range(50):
    r = np.random.default_rng(s)
    mask = r.random(panel.shape) < lf
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    sc = mom.where(pd.DataFrame(mask, index=panel.index, columns=panel.columns)).rank(
        axis=1, pct=True
    )
    m = run_backtest(panel.loc[px.index], sc.loc[px.index], COST, PortfolioConfig()).metrics
    rng_rows.append((round(m.cagr * 100, 2), round(m.sharpe, 2), round(m.max_drawdown * 100, 2)))

r = pd.DataFrame(rng_rows, columns=["cagr", "sharpe", "maxdd"])
for lbl, params in (("selected_V3_5_20_9", BEST), ("catalog_V1_12_26_9", DEFAULT)):
    m = run_backtest(
        panel.loc[px.index],
        M.score_from_signal(panel, M.signal_state(panel, *params), MOM_DAYS).loc[px.index],
        COST,
        PortfolioConfig(),
    ).metrics
    out[lbl] = {
        "cagr": round(m.cagr * 100, 2),
        "sharpe": round(m.sharpe, 2),
        "maxdd": round(m.max_drawdown * 100, 2),
        "pct_rank_cagr_vs_random": round(float((r["cagr"] < m.cagr * 100).mean()), 3),
        "pct_rank_sharpe_vs_random": round(float((r["sharpe"] < m.sharpe).mean()), 3),
        "pct_rank_maxdd_vs_random": round(float((r["maxdd"] > m.max_drawdown * 100).mean()), 3),
    }
out["random_n"] = 50
out["random_cagr"] = {"median": float(r.cagr.median()), "p10": float(r.cagr.quantile(0.1)),
                      "p90": float(r.cagr.quantile(0.9)), "mean": round(float(r.cagr.mean()), 2)}
out["random_sharpe"] = {"median": float(r.sharpe.median()), "p10": float(r.sharpe.quantile(0.1)),
                        "p90": float(r.sharpe.quantile(0.9)), "mean": round(float(r.sharpe.mean()), 2)}
out["random_maxdd"] = {"median": float(r.maxdd.median()), "p10": float(r.maxdd.quantile(0.1)),
                       "p90": float(r.maxdd.quantile(0.9))}
print("\nrandom control (50 seeds) CAGR:", out["random_cagr"])
print("random control (50 seeds) Sharpe:", out["random_sharpe"])
print("random control (50 seeds) MaxDD:", out["random_maxdd"])
print("selected V3 vs random:", out["selected_V3_5_20_9"])
print("catalog V1 vs random:", out["catalog_V1_12_26_9"])

# --- TRAIN liveness + scoreable, for the same table ---
pxt = panel.loc[TRAIN[0] : TRAIN[1]]
stt_tr = st.loc[pxt.index]
out["train_live_frac"] = round(float((stt_tr > 0).to_numpy().mean()), 4)
out["train_scoreable_names_mean"] = round(
    float(M.score_from_signal(panel, st, MOM_DAYS).loc[pxt.index].notna().sum(axis=1).mean()), 2
)
out["train_names_long_mean"] = round(float((stt_tr > 0).sum(axis=1).mean()), 2)
print(
    f"\nTRAIN live frac {out['train_live_frac']:.3f} | names long "
    f"{out['train_names_long_mean']} | scoreable {out['train_scoreable_names_mean']}"
)

with open("research/agent_macd/diag.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("\nwrote research/agent_macd/diag.json")
