"""Step 2 — TEST. Touched exactly once.

Contains the winner (fixed on TRAIN), buy-and-hold, the random-signal control, the
nsealgo composite benchmark, and every sanity check from the brief §6.
Nothing in this file was used to choose parameters.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/agent_gaussian")

from harness import (  # noqa: E402
    TEST,
    build_score,
    buy_and_hold,
    cost_model,
    fmt_rows,
    held_basket,
    row,
    run_window,
    signal_panel,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

# Fixed on TRAIN by the declared selection rule. Do not change.
WINNER = ("V5", 30, 0.8, "equalw")
N_RANDOM = 20


class ZeroCost:
    """Cost stub for the gross-of-cost decomposition only. Not a result."""

    def all_in_round_trip_bps(self, _notional) -> float:
        return 0.0

    def round_trip_bps(self, _notional) -> float:
        return 0.0


def random_signal_panel(panel, k_daily, seed):
    """Same daily breadth as the strategy, names chosen uniformly at random."""
    r = np.random.default_rng(seed)
    keep = (
        r.random((len(panel), len(panel.columns)))
        < (k_daily / len(panel.columns))[:, None]
    )
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns).where(keep)


def show_year(y, series):
    v = series.get(y, np.nan)
    return f"{v * 100:>9.2f}%" if pd.notna(v) else "        -"


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    cm = cost_model()
    cfg = PortfolioConfig()

    vid, per, ent, con = WINNER
    score = build_score(panel, per, ent, con)
    res = run_window(panel, score, TEST, cfg)
    strat = row(res, vid)
    m = res.metrics
    px = panel.loc[TEST[0] : TEST[1]]

    print(f"=== {vid} on TEST {TEST[0]} -> {TEST[1]}  (net of 21.92 bps) ===")
    print(m.fmt())
    print()
    print(f"  rt_bps charged   : {res.diag['round_trip_bps']:.2f}")
    print(f"  avg names held   : {res.diag['avg_names']:.2f}   (max_names=30)")
    print(f"  avg top weight   : {res.diag['avg_top_weight']:.4f}  (cap 0.12)")
    print(f"  n rebalances     : {res.diag['n_rebalances']}")
    print()

    # ---------------- gross-of-cost decomposition --------------------------
    zero = run_backtest(panel, score.loc[TEST[0] : TEST[1]], ZeroCost(), cfg, rebalance="M")
    print("=== cost drag decomposition (identical signals) ===")
    print(
        f"  gross of cost : CAGR {zero.metrics.cagr * 100:>7.2f}%  "
        f"Sharpe {zero.metrics.sharpe:>5.2f}  MaxDD {zero.metrics.max_drawdown * 100:>7.2f}%"
    )
    print(
        f"  net of cost   : CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>5.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%"
    )
    print(
        f"  => drag       : {(zero.metrics.cagr - m.cagr) * 100:>7.2f} pp/yr "
        f"(engine cost_drag {m.cost_drag_annual * 100:.2f}%/y)"
    )
    print()

    # ---------------- buy-and-hold ------------------------------------------
    bh_m, bh_eq = buy_and_hold(panel, TEST, cm)
    print("=== buy-and-hold (equal-weight universe), same window, same costs ===")
    print(bh_m.fmt())
    hb = held_basket(panel, TEST)
    print(f"  true held-basket (no rebalancing) CAGR: {hb * 100:>7.2f}%")
    print()

    # ---------------- nsealgo composite -------------------------------------
    comp = run_backtest(
        panel, build_composite_score(panel).loc[TEST[0] : TEST[1]], cm, cfg, rebalance="M"
    )
    comp_row = row(comp, "composite")
    print("=== nsealgo composite (build_composite_score), same window ===")
    print(comp.metrics.fmt())
    print()

    # ---------------- random-signal control --------------------------------
    print(f"=== random-signal control ({N_RANDOM} seeds, same daily breadth) ===")
    sig = signal_panel(panel, per, ent)
    k = sig.sum(axis=1).to_numpy()
    print(f"  signalled names/day: mean {k.mean():.1f}  min {k.min()}  max {k.max()}")
    rand_rows, rand_yr = [], []
    for i in range(N_RANDOM):
        rs = random_signal_panel(panel, k, 1000 + i)
        rr = run_backtest(panel, rs.loc[TEST[0] : TEST[1]], cm, cfg, rebalance="M")
        rand_rows.append(row(rr, f"rand{i}"))
        rand_yr.append(yearly_returns(rr.returns))
    rdf = pd.DataFrame(rand_rows)
    y_rd = pd.concat(rand_yr, axis=1).median(axis=1)
    print(
        f"  random CAGR  : median {rdf['cagr'].median() * 100:6.2f}%  "
        f"[{rdf['cagr'].min() * 100:.2f}, {rdf['cagr'].max() * 100:.2f}]"
    )
    print(
        f"  random Sharpe: median {rdf['sharpe'].median():6.2f}  "
        f"[{rdf['sharpe'].min():.2f}, {rdf['sharpe'].max():.2f}]"
    )
    print(f"  random MaxDD : median {rdf['maxdd'].median() * 100:6.2f}%")
    print(f"  {vid} beats {int((rdf['cagr'] < m.cagr).sum())}/{N_RANDOM} random on CAGR")
    print()

    # ---------------- summary ------------------------------------------------
    rows = [strat, comp_row]
    rows.append(
        {
            "id": "buy&hold",
            "cagr": bh_m.cagr,
            "sharpe": bh_m.sharpe,
            "sortino": bh_m.sortino,
            "maxdd": bh_m.max_drawdown,
            "calmar": bh_m.calmar,
            "vol": bh_m.volatility,
            "turnover": 1.0,
            "cost_drag": 0.0,
            "names": float(len(symbols)),
        }
    )
    rows.append(
        {
            "id": "random(med)",
            "cagr": float(rdf["cagr"].median()),
            "sharpe": float(rdf["sharpe"].median()),
            "sortino": float(rdf["sortino"].median()),
            "maxdd": float(rdf["maxdd"].median()),
            "calmar": float(rdf["calmar"].median()),
            "vol": float(rdf["vol"].median()),
            "turnover": float(rdf["turnover"].median()),
            "cost_drag": float(rdf["cost_drag"].median()),
            "names": float(rdf["names"].median()),
        }
    )
    print("=== TEST SUMMARY ===")
    print(fmt_rows(rows))
    print()

    # ---------------- calendar years -----------------------------------------
    print("=== calendar-year returns on TEST ===")
    y_str = yearly_returns(res.returns)
    y_bh = yearly_returns(bh_eq.pct_change(fill_method=None).fillna(0.0))
    y_co = yearly_returns(comp.returns)
    yrs = sorted(set(y_str.index) | set(y_bh.index) | set(y_co.index))
    print(f"{'year':<6} {vid:>9} {'buy&hold':>10} {'composite':>10} {'random(med)':>12}")
    for y in yrs:
        print(
            f"{y:<6} {show_year(y, y_str)} {show_year(y, y_bh)} "
            f"{show_year(y, y_co)} {show_year(y, y_rd)}"
        )
    print()

    # ---------------- attribution --------------------------------------------
    print("=== signal attribution on TEST ===")
    r_un = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    beta = float(np.polyfit(r_un, res.returns, 1)[0])
    resid = res.returns - beta * r_un
    print(f"  universe mean daily return : {r_un.mean() * 244 * 100:>8.2f}%/yr")
    print(f"  {vid} CAGR (net)            : {m.cagr * 100:>8.2f}%/yr")
    print(f"  {vid} vol                  : {m.volatility * 100:>8.2f}%")
    print(f"  bars signalled             : {sig.loc[TEST[0]:TEST[1]].to_numpy().mean() * 100:>8.2f}%")
    print(f"  corr(daily, universe)      : {float(res.returns.corr(r_un)):>8.3f}")
    print(f"  beta to universe           : {beta:>8.3f}")
    print(f"  alpha vs universe          : {resid.mean() * 244 * 100:>8.3f}%/yr")
    print()

    pd.DataFrame([strat, comp_row]).to_csv("research/agent_gaussian/test_results.csv")
    rdf.to_csv("research/agent_gaussian/test_random_control.csv", index=False)


if __name__ == "__main__":
    main()
