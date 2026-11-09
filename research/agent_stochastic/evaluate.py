"""Full evaluation for stochastic_strategy.

Stage 1 (TRAIN only): sweep the 5 declared variants x 2 score constructions,
  plus buy-and-hold and the nsealgo composite as baselines.
  Writes train_results.json and picks the winner by TRAIN Sharpe.

Stage 2 (TEST, run once): takes the winner chosen in stage 1, unchanged, and
  evaluates it on TEST alongside buy-and-hold, the composite, and a random-signal
  control matched on % of bars long.

Stages are separate functions and stage 2 takes the winner as an ARGUMENT, so the
TEST numbers cannot leak back into selection.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import (  # noqa: E402
    ENGINE_SHA,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import build_score, signal_panel, stoch_k_panel  # noqa: E402

OUT = Path(__file__).resolve().parent

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

VARIANTS = {
    "V1": dict(period=14, lower=20.0, upper=80.0),
    "V2": dict(period=5, lower=20.0, upper=80.0),
    "V3": dict(period=21, lower=20.0, upper=80.0),
    "V4": dict(period=14, lower=10.0, upper=80.0),
    "V5": dict(period=14, lower=30.0, upper=70.0),
}
CONSTRUCTIONS = ("depth", "momentum")


# --------------------------------------------------------------------------- #


def load_all():
    panel, symbols, report = load_universe("data/nse")
    highs, lows = {}, {}
    for s in symbols:
        df = load_symbol(f"data/nse/{s}_1d.csv", s)
        highs[s] = df["high"].rename(s)
        lows[s] = df["low"].rename(s)
    high = pd.DataFrame(highs).reindex(index=panel.index, columns=panel.columns)
    low = pd.DataFrame(lows).reindex(index=panel.index, columns=panel.columns)
    return panel, symbols, high, low, report


def buy_and_hold(panel: pd.DataFrame, start: str, end: str,
                 cm: CostModel) -> tuple[pd.Series, pd.Series]:
    """Equal-weight buy-and-hold, net of the SAME all-in cost the engine charges.

    The brief specifies `panel.pct_change().mean(axis=1)`. Costed honestly: a single
    entry and a single exit is a full rotation, sum|dW| = 2.0, one-way turnover 1.0,
    so the engine's own formula charges `2 * 1.0 * eq * rate`. That is applied once,
    at the start of the window, as a level shift on equity (and on the daily return
    that produces it), so the benchmark is net of exactly what the strategy pays.
    """
    p = panel.loc[start:end]
    r = p.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    daily = r.copy()
    # Charge the round trip ONCE, on the first bar only. Subtracting it from every day
    # would be a ~0.44%/day (≈108%/yr) phantom drag.
    if len(daily):
        daily.iloc[0] = daily.iloc[0] - 2.0 * 1.0 * rate
    equity = (1.0 + daily).cumprod()
    return daily, equity


def m(d: dict) -> dict:
    out = d.as_dict()
    out["yearly"] = {}
    return out


def row(name: str, res, extra: dict | None = None) -> dict:
    mt = res.metrics
    d = {
        "name": name,
        "cagr": mt.cagr,
        "sharpe": mt.sharpe,
        "sortino": mt.sortino,
        "maxdd": mt.max_drawdown,
        "maxdd_days": mt.max_drawdown_days,
        "calmar": mt.calmar,
        "volatility": mt.volatility,
        "total_return": mt.total_return,
        "turnover": mt.annual_turnover,
        "cost_drag": mt.cost_drag_annual,
        "trades_per_year": mt.trades_per_year,
        "win_rate": mt.win_rate,
        "avg_names": res.diag.get("avg_names"),
        "engine_sha": res.engine_sha,
    }
    if extra:
        d.update(extra)
    return d


def score_for(panel, high, low, sig, ctor):
    if ctor == "depth":
        return None  # handled by caller (needs lower)
    raise NotImplementedError


def stage_train() -> None:
    panel, symbols, high, low, report = load_all()
    print(f"[engine_sha] {ENGINE_SHA}")
    print(report.describe())
    cm = CostModel(segment="delivery", slippage_bps=5)
    cfg = PortfolioConfig()
    s, e = TRAIN
    tr = panel.loc[s:e]

    results = {}
    for name, p in VARIANTS.items():
        k = stoch_k_panel(high, low, panel, int(p["period"]))
        sig = signal_panel(k, p["lower"], p["upper"])
        live = float((sig.loc[s:e] > 0).sum(axis=1).mean() / len(symbols))
        for ctor in CONSTRUCTIONS:
            if ctor == "depth":
                raw = (p["lower"] - k).where(sig > 0)
            else:
                raw = (panel / panel.shift(126) - 1.0).where(sig > 0)
            score = build_score(raw)
            res = run_backtest(tr, score.loc[tr.index], cm, cfg, rebalance="M")
            rec = row(f"{name}:{ctor}", res,
                      {"signal_liveness_train": live,
                       "long_names_mean": float((sig.loc[s:e] > 0).sum(axis=1).mean())})
            results[f"{name}:{ctor}"] = rec
            print(f"TRAIN {name} {ctor:9s} CAGR {rec['cagr']*100:7.2f}%  "
                  f"Sh {rec['sharpe']:6.2f}  DD {rec['maxdd']*100:7.2f}%  "
                  f"Cal {rec['calmar']:6.2f}  TO {rec['turnover']:4.2f}  "
                  f"names {rec['avg_names']:4.1f}  live {live*100:4.1f}%")

    # baselines on TRAIN
    r_bh, eq_bh = buy_and_hold(panel, s, e, cm)
    mbh = compute_metrics(r_bh, eq_bh)
    results["BH"] = {"name": "buy_and_hold", "cagr": mbh.cagr, "sharpe": mbh.sharpe,
                     "maxdd": mbh.max_drawdown, "calmar": mbh.calmar,
                     "volatility": mbh.volatility, "total_return": mbh.total_return}
    print(f"TRAIN {'BH':10s} CAGR {mbh.cagr*100:7.2f}%  Sh {mbh.sharpe:6.2f}  "
          f"DD {mbh.max_drawdown*100:7.2f}%")

    comp = build_composite_score(tr)
    rc = run_backtest(tr, comp.loc[tr.index], cm, cfg, rebalance="M")
    results["COMPOSITE"] = row("composite", rc)
    print(f"TRAIN {'COMPOSITE':10s} CAGR {rc.metrics.cagr*100:7.2f}%  "
          f"Sh {rc.metrics.sharpe:6.2f}  DD {rc.metrics.max_drawdown*100:7.2f}%")

    # selection: max TRAIN Sharpe over the 5 parameter variants (both constructions
    # reported; the variant choice is the 5-way parameter decision)
    best = max((k for k in results if k not in ("BH", "COMPOSITE")),
               key=lambda k: results[k]["sharpe"])
    results["_selected"] = best
    print(f"\nSELECTED (max TRAIN Sharpe): {best}  "
          f"sharpe={results[best]['sharpe']:.4f}")
    (OUT / "train_results.json").write_text(json.dumps(results, indent=2, default=str))


def stage_test(winner: str) -> None:
    panel, symbols, high, low, report = load_all()
    cm = CostModel(segment="delivery", slippage_bps=5)
    cfg = PortfolioConfig()
    s, e = TEST
    te = panel.loc[s:e]
    vname, ctor = winner.split(":")
    p = VARIANTS[vname]

    print(f"[engine_sha] {ENGINE_SHA}")
    print(f"TEST window {te.index[0].date()} -> {te.index[-1].date()}  bars={len(te)}")
    print(f"WINNER (chosen on TRAIN): {winner}")

    k = stoch_k_panel(high, low, panel, int(p["period"]))
    sig = signal_panel(k, p["lower"], p["upper"])
    if ctor == "depth":
        raw = (p["lower"] - k).where(sig > 0)
    else:
        raw = (panel / panel.shift(126) - 1.0).where(sig > 0)
    score = build_score(raw)
    live = float((sig.loc[s:e] > 0).sum(axis=1).mean() / len(symbols))
    res = run_backtest(te, score.loc[te.index], cm, cfg, rebalance="M")
    strat = row("strategy", res, {"signal_liveness_test": live,
                                  "long_names_mean": float(
                                      (sig.loc[s:e] > 0).sum(axis=1).mean())})
    yr = yearly_returns(res.returns)
    strat["yearly"] = {int(k2): float(v) for k2, v in yr.items()}
    print(f"\nTEST strategy  CAGR {strat['cagr']*100:7.2f}%  Sh {strat['sharpe']:6.2f}  "
          f"DD {strat['maxdd']*100:7.2f}%  Cal {strat['calmar']:6.2f}  "
          f"TO {strat['turnover']:4.2f}  drag {strat['cost_drag']*100:5.2f}%  "
          f"names {strat['avg_names']:4.1f}  live {live*100:4.1f}%")

    # ---- buy and hold, identical window, same costs
    r_bh, eq_bh = buy_and_hold(panel, s, e, cm)
    mbh = compute_metrics(r_bh, eq_bh)
    ybh = yearly_returns(r_bh)
    bh = {"name": "buy_and_hold", "cagr": mbh.cagr, "sharpe": mbh.sharpe,
          "maxdd": mbh.max_drawdown, "calmar": mbh.calmar,
          "volatility": mbh.volatility, "total_return": mbh.total_return,
          "yearly": {int(a): float(b) for a, b in ybh.items()}}
    print(f"TEST {'buy&hold':9s} CAGR {mbh.cagr*100:7.2f}%  Sh {mbh.sharpe:6.2f}  "
          f"DD {mbh.max_drawdown*100:7.2f}%  Cal {mbh.calmar:6.2f}")

    # ---- composite
    comp = build_composite_score(te)
    rc = run_backtest(te, comp.loc[te.index], cm, cfg, rebalance="M")
    cmp_ = row("composite", rc)
    print(f"TEST {'composite':9s} CAGR {cmp_['cagr']*100:7.2f}%  Sh {cmp_['sharpe']:6.2f}  "
          f"DD {cmp_['maxdd']*100:7.2f}%  Cal {cmp_['calmar']:6.2f}")

    # ---- random control: same % of bars long, matched per (symbol, day)
    rng_ctrl = {}
    n_seeds = 5
    for seed in range(n_seeds):
        rs = np.random.default_rng(1000 + seed)
        # match the strategy's marginal long rate on the TEST window
        target_rate = float((sig.loc[s:e] > 0).sum(axis=1).mean() / len(symbols))
        rmask = rs.random((len(te), len(symbols))) < target_rate
        rsig = pd.DataFrame(np.where(rmask, 1.0, 0.0), index=te.index, columns=te.columns)
        rraw = (panel / panel.shift(126) - 1.0).where(rsig > 0)
        rscore = build_score(rraw)
        rres = run_backtest(te, rscore.loc[te.index], cm, cfg, rebalance="M")
        rng_ctrl[f"seed{seed}"] = {"cagr": rres.metrics.cagr,
                                   "sharpe": rres.metrics.sharpe,
                                   "maxdd": rres.metrics.max_drawdown}
        print(f"TEST random seed{seed} CAGR {rres.metrics.cagr*100:7.2f}%  "
              f"Sh {rres.metrics.sharpe:6.2f}")
    rng_mean_cagr = float(np.mean([v["cagr"] for v in rng_ctrl.values()]))
    rng_mean_sh = float(np.mean([v["sharpe"] for v in rng_ctrl.values()]))
    print(f"TEST random MEAN CAGR {rng_mean_cagr*100:7.2f}%  Sh {rng_mean_sh:6.2f}")

    out = {"strategy": strat, "buy_and_hold": bh, "composite": cmp_,
           "random": {"seeds": rng_ctrl, "mean_cagr": rng_mean_cagr,
                      "mean_sharpe": rng_mean_sh,
                      "matched_long_rate": float(
                          (sig.loc[s:e] > 0).sum(axis=1).mean() / len(symbols))},
           "winner": winner, "params": p,
           "engine_sha": ENGINE_SHA, "window": TEST,
           "n_symbols": len(symbols),
           "bars": len(te)}
    (OUT / "test_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT/'test_results.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["train", "test"])
    ap.add_argument("--winner", default=None)
    a = ap.parse_args()
    if a.stage == "train":
        stage_train()
    else:
        assert a.winner, "--winner required"
        stage_test(a.winner)
