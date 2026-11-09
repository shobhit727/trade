"""Controls for the MFI run: random signals, cash-matched control, cost stress, lookahead.

The single most important question is §6.5: did the MFI signal beat a *random* selection
with the same number of long names? A book holding 1-12 of 48 names is mostly cash, so it
will "beat" buy-and-hold on drawdown for free. The cash-matched control isolates that.
"""

from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_mfi")

from data_prep import TEST_END, TEST_START, TRAIN_END, TRAIN_START, load_all  # noqa: E402
from mfi_lib import mfi_panel, signal_panel  # noqa: E402
from run_variants import (  # noqa: E402
    BASE_COST,
    VARIANTS,
    ZERO_COST,
    build_random_score,
    build_score,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402

N_RANDOM = 50


def run(panel, index, score, cost=BASE_COST):
    res = run_backtest(panel.loc[index], score, cost, config=PortfolioConfig(),
                       rebalance="M")
    if res.diag["n_rebalances"] == 0:
        raise RuntimeError("zero rebalances")
    return res


def main() -> None:
    panel, syms, rep, close, high, low, vol, _ = load_all()
    windows = {
        "TRAIN": panel.loc[TRAIN_START:TRAIN_END].index,
        "TEST": panel.loc[TEST_START:TEST_END].index,
    }
    mfi = {p: mfi_panel(high, low, close, vol, p)
           for p in sorted({p for p, _ in VARIANTS.values()})}

    out: dict = {"random": {}, "cashmatch": {}, "coststress": {}}

    for wname, index in windows.items():
        # ---------- 1. random-signal control ----------
        rand: dict[str, dict] = {}
        for vname, (p, lo) in VARIANTS.items():
            sig = signal_panel(mfi[p], lo)
            real = run(panel, index, build_score(panel, sig))
            cagrs, sharpes = [], []
            for s in range(N_RANDOM):
                sc = build_random_score(panel.loc[index], sig.loc[index],
                                        seed=1000 * s + 7)
                r = run(panel, index, sc)
                cagrs.append(r.metrics.cagr)
                sharpes.append(r.metrics.sharpe)
            cagrs = np.array(cagrs)
            sharpes = np.array(sharpes)
            rand[vname] = {
                "real_cagr": real.metrics.cagr,
                "real_sharpe": real.metrics.sharpe,
                "rand_cagr_mean": float(cagrs.mean()),
                "rand_cagr_sd": float(cagrs.std(ddof=1)),
                "rand_cagr_median": float(np.median(cagrs)),
                "rand_sharpe_mean": float(sharpes.mean()),
                "rand_sharpe_sd": float(sharpes.std(ddof=1)),
                "pct_beaten_cagr": float((cagrs < real.metrics.cagr).mean() * 100),
                "pct_beaten_sharpe": float((sharpes < real.metrics.sharpe).mean() * 100),
                "n_random": N_RANDOM,
            }
        out["random"][wname] = rand

        # ---------- 2. cash-matched control ----------
        # What does the MARKET do with exactly the same invested exposure on exactly the
        # same days? Removes "held cash during drawdowns" as an explanation.
        cm: dict[str, dict] = {}
        for vname, (p, lo) in VARIANTS.items():
            sig = signal_panel(mfi[p], lo)
            sc = build_score(panel, sig)
            res = run(panel, index, sc)
            held = res.weights
            invested = held.sum(axis=1)
            daily_inv = invested.shift(1).fillna(0.0)
            # Market return on those days, scaled by the book's actual exposure.
            mkt = panel.loc[index].pct_change(fill_method=None).fillna(0.0).mean(axis=1)
            strat_gross = (held.shift(1).fillna(0.0)
                           * panel.loc[index].pct_change(fill_method=None).fillna(0.0)
                           ).sum(axis=1)
            strat_net = res.returns
            bm = daily_inv * mkt
            years = len(strat_net) / 244.0
            cm[vname] = {
                "mean_invested": float(invested.mean()),
                "median_invested": float(invested.median()),
                "strategy_net_cagr": res.metrics.cagr,
                "strategy_net_sharpe": res.metrics.sharpe,
                "cashmatched_cagr": float((1.0 + bm).cumprod().iloc[-1] ** (1 / years) - 1),
                "strategy_gross_cagr": float(
                    (1.0 + strat_gross).cumprod().iloc[-1] ** (1 / years) - 1),
                "bh_cagr": float((1.0 + mkt).cumprod().iloc[-1] ** (1 / years) - 1),
            }
        out["cashmatch"][wname] = cm

        # ---------- 3. cost stress (incl. zero-cost control) ----------
        cs: dict[str, dict] = {}
        for vname, (p, lo) in VARIANTS.items():
            sig = signal_panel(mfi[p], lo)
            sc = build_score(panel, sig)
            row = {}
            for label, cmodel in (
                ("zero", ZERO_COST),
                ("base5", BASE_COST),
                ("dbl10", CostModel(segment="delivery", slippage_bps=10)),
                ("triple15", CostModel(segment="delivery", slippage_bps=15)),
            ):
                r = run(panel, index, sc, cost=cmodel)
                row[label] = {
                    "cagr": r.metrics.cagr,
                    "sharpe": r.metrics.sharpe,
                    "cost_drag": r.metrics.cost_drag_annual,
                    "rt_bps": r.diag["round_trip_bps"],
                }
            cs[vname] = row
        out["coststress"][wname] = cs

    with open("research/agent_mfi/results_controls.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    for wname in ("TRAIN", "TEST"):
        print(f"\n===== {wname}: RANDOM CONTROL =====")
        print(f"{'variant':18s} {'realShp':>8s} {'rndShp':>8s} {'beat%Shp':>9s} "
              f"{'realCAGR':>9s} {'rndCAGR':>9s} {'beat%CAGR':>9s}")
        for v, r in out["random"][wname].items():
            print(f"{v:18s} {r['real_sharpe']:8.2f} {r['rand_sharpe_mean']:8.2f} "
                  f"{r['pct_beaten_sharpe']:8.0f}% {r['real_cagr']*100:8.2f}% "
                  f"{r['rand_cagr_mean']*100:8.2f}% {r['pct_beaten_cagr']:8.0f}%")

        print(f"\n----- {wname}: CASH-MATCHED -----")
        print(f"{'variant':18s} {'invested%':>10s} {'netCAGR%':>9s} {'grossCAGR%':>10s} "
              f"{'cashmatch%':>11s} {'BH%':>7s}")
        for v, r in out["cashmatch"][wname].items():
            print(f"{v:18s} {r['mean_invested']*100:10.1f} "
                  f"{r['strategy_net_cagr']*100:9.2f} {r['strategy_gross_cagr']*100:10.2f} "
                  f"{r['cashmatched_cagr']*100:11.2f} {r['bh_cagr']*100:7.2f}")

        print(f"\n----- {wname}: COST STRESS (CAGR%) -----")
        print(f"{'variant':18s} {'zero':>8s} {'base5':>8s} {'dbl10':>8s} {'triple15':>9s}")
        for v, r in out["coststress"][wname].items():
            print(f"{v:18s} {r['zero']['cagr']*100:8.2f} {r['base5']['cagr']*100:8.2f} "
                  f"{r['dbl10']['cagr']*100:8.2f} {r['triple15']['cagr']*100:9.2f}")


if __name__ == "__main__":
    main()
