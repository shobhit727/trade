"""Addendum: gross-vs-net cost drag for the two TRAIN-selected variants.

Brief §6.4: "If gross return is positive but net is negative, the strategy is
unviable and that is the finding." This reports exactly that decomposition on
the TEST window, plus the cost model rate actually used by the engine.

Run: .venv/bin/python research/agent_inapplicable/cost_drag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.costs import CostModel

DATA = Path("data/nse")
TEST = ("2024-01-01", "2026-10-01")
cfg = PortfolioConfig()
cost = CostModel(segment="delivery", slippage_bps=5)

print(f"CostModel: round_trip_bps={cost.round_trip_bps(100_000):.2f}  "
      f"all_in_round_trip_bps={cost.all_in_round_trip_bps(100_000):.2f}")
print("run_backtest charges rate = all_in_round_trip_bps/1e4 and applies "
      "2 x one_way_turnover x equity x rate on every rebalance.\n")


def load_panel():
    frames = {}
    for f in sorted(DATA.glob("*_1d.csv")):
        sym = f.stem.replace("_1d", "")
        df = pd.read_csv(f, index_col="ts")
        df.index = pd.to_datetime(df.index, unit="ms", utc=True).tz_convert("Asia/Kolkata")
        frames[sym] = df["close"]
    panel = pd.DataFrame(frames).sort_index()
    return panel.loc["2008-01-01":]


panel = load_panel()


def score_for(kind, period, threshold):
    if kind == "basket":
        roc = panel / panel.shift(period) - 1.0
        sig = pd.DataFrame(
            np.where(roc.abs() > threshold, np.sign(roc), np.nan),
            index=panel.index, columns=panel.columns)
    else:
        ma = panel.rolling(period).mean()
        sig = pd.DataFrame(np.where(panel > ma, 1.0, -1.0),
                           index=panel.index, columns=panel.columns)
    mom = panel / panel.shift(126) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


for kind, period, th, label in [
    ("basket", 120, 0.015, "basket p120 t0.015 (TRAIN-selected)"),
    ("meta", 100, None, "meta p100 (TRAIN-selected)"),
]:
    score = score_for(kind, period, 0.0 if th is None else th)
    idx = panel.index.intersection(score.index)
    idx = idx[(idx >= pd.Timestamp(TEST[0], tz=idx.tz)) & (idx <= pd.Timestamp(TEST[1], tz=idx.tz))]

    net = run_backtest(panel.loc[idx], score.loc[idx], cost, cfg)
    # Rebuild the same book with a zero-cost model to isolate the cost drag.
    zero = CostModel(segment="delivery", slippage_bps=0.0)
    gross = run_backtest(panel.loc[idx], score.loc[idx], zero, cfg)

    print(f"--- {label} on TEST {TEST[0]} -> {TEST[1]} ---")
    print(f"  net   (21.92bps): CAGR={net.metrics.cagr:7.2%}  Sharpe={net.metrics.sharpe:6.2f}  "
          f"MaxDD={net.metrics.max_drawdown:7.2%}")
    print(f"  gross ( 0.00bps): CAGR={gross.metrics.cagr:7.2%}  "
          f"Sharpe={gross.metrics.sharpe:6.2f}  MaxDD={gross.metrics.max_drawdown:7.2%}")
    drag = gross.metrics.cagr - net.metrics.cagr
    print(f"  cost drag       : {drag:7.2%} per year "
          f"(engine cost_drag_annual={net.metrics.cost_drag_annual:.2%}/y, "
          f"turnover={net.metrics.annual_turnover:.2f}x/y)")
    print(f"  signal liveness : {(net.weights > 0).sum(axis=1).mean():.1f} names avg held; "
          f"long fraction {(score.loc[idx].notna().sum(axis=1) / len(score.columns)).mean():.1%}")
    if gross.metrics.cagr <= 0:
        verdict = "gross negative too -> no edge before costs"
    elif net.metrics.cagr <= 0:
        verdict = "gross positive, NET NEGATIVE -> unviable (costs kill it)"
    else:
        verdict = ("both positive but negligible; Sharpe is computed vs rf=6.5%, "
                   "so negative Sharpe = did not clear the risk-free hurdle")
    print(f"  VERDICT         : {verdict}")
    print()

bh = compute_metrics(panel.pct_change().mean(axis=1).loc[TEST[0]:TEST[1]])
print(f"buy-and-hold TEST: CAGR={bh.cagr:.2%} Sharpe={bh.sharpe:.2f} "
      f"MaxDD={bh.max_drawdown:.2%}  (gross of any strategy cost)")
