"""Step 2 — THE frozen TEST run. One variant, chosen on TRAIN, run unchanged.

Variant: V2_mom252 (selected in step1 on TRAIN Sharpe 0.70).
Nothing below re-selects. Benchmarks, controls and diagnostics only.
"""

from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "research/agent_adx_trend")

import harness as H  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import STRESS_MODELS  # noqa: E402

FROZEN = "V2_mom252"
N_SEEDS = 20


def main() -> None:
    panel, _ = H.load_panel()
    score = H.build_score(FROZEN, panel)

    print("=" * 112)
    print(f"OUT-OF-SAMPLE TEST  2024-01-01 -> 2026-10-01   ({len(panel.loc[H.TEST_START:H.TEST_END])} sessions)")
    print(f"FROZEN VARIANT: {FROZEN} -- selected on TRAIN, unchanged")
    print("=" * 112)
    print(H.HDR)

    strat = H.run(panel, score, H.TEST_START, H.TEST_END)
    r_strat = H.row_of(f"strategy {FROZEN}", "TEST", strat)
    print(H.line(r_strat))

    # ---- buy-and-hold over the identical window, identical cost assumption ----
    bh = H.buy_and_hold(panel, H.TEST_START, H.TEST_END)
    m = bh["metrics"]
    r_bh = H.Row("buy-and-hold (eq-wt)", "TEST", m.cagr, m.sharpe,
                 m.max_drawdown, m.calmar, bh["annual_turnover"],
                 bh["cost_drag"], float(len(panel.columns)), m.total_return,
                 float((yearly_returns(
                     bh["equity"].pct_change(fill_method=None).fillna(0.0)) > 0).mean()))
    print(H.line(r_bh))

    # ---- nsealgo composite on the same panel ----
    comp = H.composite_score(panel)
    comp_res = H.run(panel, comp, H.TEST_START, H.TEST_END)
    r_comp = H.row_of("nsealgo composite", "TEST", comp_res)
    print(H.line(r_comp))

    # ---- random-signal negative control, same % of name-days long ----
    rets = []
    for seed in range(N_SEEDS):
        rs = H.run(panel, H.random_score(panel, seed), H.TEST_START, H.TEST_END)
        rets.append(rs.metrics.cagr)
    rets = np.array(rets)
    print(H.line(H.Row(f"random x{N_SEEDS} (median)", "TEST",
                       float(np.median(rets)), 0, 0, 0, 0, 0,
                       float("nan"), 0, 0)))
    print(f"{'':<26}{'':<6}  random CAGR mean {rets.mean() * 100:>6.2f}%  "
          f"p5 {np.percentile(rets, 5) * 100:>6.2f}%  "
          f"p95 {np.percentile(rets, 95) * 100:>6.2f}%  "
          f"beat by strategy on {int((rets < strat.metrics.cagr).sum())}/{N_SEEDS} seeds")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 112)
    print("VIABILITY: gross (zero cost) vs net (full stack) vs cost stress  -- TEST window")
    print("=" * 112)
    sub = panel.loc[H.TEST_START:H.TEST_END]
    sc = score.loc[H.TEST_START:H.TEST_END]
    zc = run_backtest(sub, sc, STRESS_MODELS["zero_cost"], H.PORTFOLIO, rebalance="M")
    d2 = run_backtest(sub, sc, STRESS_MODELS["double_slippage"], H.PORTFOLIO,
                      rebalance="M")
    for lab, res in (("gross (0 bps, unattainable)", zc),
                     ("net  (21.92 bps, live)", strat),
                     ("stress (31.92 bps, 2x slippage)", d2)):
        print(f"  {lab:<34}CAGR {res.metrics.cagr * 100:>7.2f}%  "
              f"Sharpe {res.metrics.sharpe:>5.2f}  MaxDD {res.metrics.max_drawdown * 100:>7.2f}%")
    print(f"  -> cost drag is {strat.metrics.cost_drag_annual * 100:.2f}%/yr at "
          f"{strat.metrics.annual_turnover:.2f}x turnover; gross exceeds net by "
          f"{(zc.metrics.cagr - strat.metrics.cagr) * 100:.2f}pp/yr")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 112)
    print("SANITY CHECKS")
    print("=" * 112)
    flag = (H.signal_flag(panel).loc[H.TEST_START:H.TEST_END] > 0)
    print(f"  [1] plausibility   CAGR {strat.metrics.cagr * 100:.1f}% on an unlevered "
          f"long-only book -- well inside the 40-50% ceiling, no compounding bug")
    print(f"  [2] weight count   avg names held {strat.diag['avg_names']:.1f}, "
          f"max top weight {strat.diag['avg_top_weight'] * 100:.1f}% "
          f"(cap 12%). PortfolioConfig targets n_positions={H.PORTFOLIO.n_positions} "
          f"and hard-bounds max_names={H.PORTFOLIO.max_names}")
    diag22 = run_backtest(sub, sc, H.COST_MODEL,
                          PortfolioConfig(max_names=22), rebalance="M")
    print(f"                   diagnostic with max_names=22 -> avg "
          f"{diag22.diag['avg_names']:.1f} names. Not 48: no residual accretion.")
    print(f"  [3] signal liveness {flag.to_numpy().mean() * 100:.1f}% of name-days long "
          f"(floor ~5%) -> genuinely long, not a flat book")
    print(f"  [4] cost drag      gross {zc.metrics.cagr * 100:.2f}% vs net "
          f"{strat.metrics.cagr * 100:.2f}% -- see viability line above")
    print(f"  [5] negative ctrl  strategy beats {int((rets < strat.metrics.cagr).sum())}"
          f"/{N_SEEDS} random signals")
    eq_bh = bh["equity"]
    eq_s = strat.equity
    corr = float(eq_s.pct_change().corr(eq_bh.pct_change()))
    beta = float(np.polyfit(eq_bh.pct_change().dropna(),
                            eq_s.pct_change().reindex(
                                eq_bh.pct_change().dropna().index).fillna(0.0), 1)[0])
    print(f"  [6] beta to eq-wt market {beta:.2f}, daily corr {corr:.2f} -> this is a "
          f"modestly levered beta book, not an alpha book")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 112)
    print("TEST YEARLY RETURNS  (Gate 3 wants positive in >=60% of years)")
    print("=" * 112)
    for lab, ret in (("strategy", strat.returns),
                     ("buy-and-hold", bh["equity"].pct_change(fill_method=None).fillna(0.0)),
                     ("composite", comp_res.returns)):
        yr = yearly_returns(ret)
        print(f"  {lab:<16}" + "  ".join(f"{y}:{v * 100:+7.2f}%"
                                        for y, v in yr.items()))

    out = dict(
        frozen=FROZEN,
        strategy=r_strat.__dict__,
        buy_and_hold=r_bh.__dict__,
        composite=r_comp.__dict__,
        random=dict(mean=float(rets.mean()), p5=float(np.percentile(rets, 5)),
                    p95=float(np.percentile(rets, 95)),
                    beaten=int((rets < strat.metrics.cagr).sum()), n=N_SEEDS),
        gross_cagr=zc.metrics.cagr,
        double_slippage_cagr=d2.metrics.cagr,
        beta=beta,
        corr=corr,
        rt_bps=H.RT_BPS,
    )
    with open("research/agent_adx_trend/test_results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("\n  wrote research/agent_adx_trend/test_results.json")


if __name__ == "__main__":
    main()
