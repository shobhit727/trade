"""Step 03 — TRAIN-only run of the 5 declared variants.

Selection happens entirely inside TRAIN. TEST is not read by this script.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import yearly_returns
from nsealgo.costs import CostModel
from nsealgo.factors.core import build_composite_score, rank_cross_sectional

TRAIN = (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"),
         pd.Timestamp("2023-12-31", tz="Asia/Kolkata"))
MOM_LOOKBACK = 126
COST = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()


def cmf_panel(closes, highs, lows, vols, period):
    rng = (highs - lows).replace(0.0, np.nan)
    mfm = ((closes - lows) - (highs - closes)) / rng
    num = (mfm * vols).rolling(period, min_periods=period).sum()
    den = vols.rolling(period, min_periods=period).sum()
    return num / den.replace(0.0, np.nan)


def momentum_score(panel: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """Brief §5 construction: 126d momentum, ranked, but only among flagged names."""
    mom = panel / panel.shift(MOM_LOOKBACK) - 1.0
    return mom.where(mask).rank(axis=1, pct=True)


def build_score(panel, cmf, spec):
    kind, period, thr, direction, construction = spec
    if construction == "mom_rank":
        m = (cmf > thr) if direction == "literal" else (cmf < -thr)
        return momentum_score(panel, m), m
    if construction == "cmf_rank":
        return rank_cross_sectional(-cmf if direction == "flipped" else cmf), cmf.notna()
    raise ValueError(construction)


def slice_(df, lo=None, hi=None):
    return df if lo is None else df.loc[lo:hi]


def run_on(df: pd.DataFrame, score: pd.DataFrame, lo, hi, rebalance="M"):
    p = df.loc[lo:hi]
    s = score.loc[lo:hi]
    return run_backtest(p, s, COST, CFG, rebalance=rebalance)


def row(name, res, extra=None):
    m = res.metrics
    d = {
        "variant": name,
        "cagr": round(m.cagr * 100, 3),
        "sharpe": round(m.sharpe, 3),
        "maxdd": round(m.max_drawdown * 100, 2),
        "calmar": round(m.calmar, 3),
        "vol": round(m.volatility * 100, 2),
        "turnover_y": round(m.annual_turnover, 3),
        "cost_drag_y": round(m.cost_drag_annual * 100, 3),
        "avg_names": round(res.diag["avg_names"], 2),
        "trades_y": round(m.trades_per_year, 1),
        "rt_bps": res.diag["round_trip_bps"],
    }
    if extra:
        d.update(extra)
    return d


def main() -> None:
    lo, hi = TRAIN
    closes = pd.read_pickle("research/agent_cmf/_closes.pkl")
    highs = pd.read_pickle("research/agent_cmf/_highs.pkl")
    lows = pd.read_pickle("research/agent_cmf/_lows.pkl")
    vols = pd.read_pickle("research/agent_cmf/_vols.pkl")

    SPECS = [
        ("V1_p20_t10_literal", "cmf", 20, 0.10, "literal", "mom_rank"),
        ("V2_p20_t10_flipped", "cmf", 20, 0.10, "flipped", "mom_rank"),
        ("V3_p10_t10_flipped", "cmf", 10, 0.10, "flipped", "mom_rank"),
        ("V4_p60_t10_flipped", "cmf", 60, 0.10, "flipped", "mom_rank"),
        ("V5_p20_continuous_flip", "cmf", 20, 0.0, "flipped", "cmf_rank"),
    ]

    rows, keep = [], {}
    for name, _k, period, thr, direction, construction in SPECS:
        cmf = cmf_panel(closes, highs, lows, vols, period)
        score, mask = build_score(closes, cmf, (name, period, thr, direction, construction))
        res = run_on(closes, score, lo, hi)
        frac = float((mask.loc[lo:hi] > 0).sum().sum() / mask.loc[lo:hi].notna().sum().sum())
        rows.append(row(name, res, {"frac_bars_long": round(frac, 4)}))
        keep[name] = (score, mask)
        yr = yearly_returns(res.returns)
        pos = float((yr > 0).mean())
        print(f"{name:24s} CAGR {res.metrics.cagr * 100:7.2f}%  "
              f"Sh {res.metrics.sharpe:6.2f}  MaxDD {res.metrics.max_drawdown * 100:7.2f}%  "
              f"Cal {res.metrics.calmar:6.2f}  names {res.diag['avg_names']:5.1f}  "
              f"drag {res.metrics.cost_drag_annual * 100:5.2f}%/y  posyrs {pos:.2f}")

    # ---- TRAIN benchmark: nsealgo composite
    comp = build_composite_score(closes)
    rc = run_on(closes, comp, lo, hi)
    rows.append(row("BENCH_nsealgo_composite", rc))
    print(f"{'BENCH_nsealgo_composite':24s} CAGR {rc.metrics.cagr * 100:7.2f}%  "
          f"Sh {rc.metrics.sharpe:6.2f}  MaxDD {rc.metrics.max_drawdown * 100:7.2f}%  "
          f"Cal {rc.metrics.calmar:6.2f}  names {rc.diag['avg_names']:5.1f}  "
          f"drag {rc.metrics.cost_drag_annual * 100:5.2f}%/y")

    df = pd.DataFrame(rows)
    print("\n=== TRAIN results (all 5 declared variants + benchmark) ===")
    print(df.to_string(index=False))

    # ---- selection: highest TRAIN Sharpe among the 5 variants only
    cands = df[~df.variant.str.startswith("BENCH")].sort_values(
        ["sharpe", "calmar"], ascending=[False, False])
    winner = cands.iloc[0]["variant"]
    print(f"\nSELECTED ON TRAIN (max Sharpe): {winner}")

    with open("research/agent_cmf/train_results.json", "w") as f:
        json.dump({"rows": rows, "winner": winner}, f, indent=2)
    print("wrote research/agent_cmf/train_results.json")


if __name__ == "__main__":
    main()
