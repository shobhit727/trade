"""STEP 2 — THE SINGLE TEST EVALUATION.

The variant chosen on TRAIN (`selected_variant.txt`, written by step 1) is run
**unchanged** on TEST. No parameter is adjusted here. This script also produces the
mandatory comparisons: buy-and-hold, random-signal control, nsealgo composite, and
the section-6 sanity checks.

TEST is touched here and only here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    VARIANTS,
    build_composite_score,
    buy_and_hold,
    cost_drag_split,
    cost_model,
    liveness,
    load,
    portfolio_config,
    random_control_score,
    run_backtest,
    strategy_score,
    window,
    yearly_returns,
)

OUT = Path(__file__).resolve().parent
N_SEEDS = 60


def main() -> None:
    panel, symbols, _ = load()
    selected = (OUT / "selected_variant.txt").read_text().strip()
    variant = next(v for v in VARIANTS if v.name == selected)
    print("=" * 92)
    print(f"OUT-OF-SAMPLE (TEST) — {TEST_START.date()} -> {TEST_END.date()}")
    print(f"Variant carried over UNCHANGED from TRAIN: {variant.name} "
          f"(period={variant.period}, threshold={variant.threshold})")
    print("=" * 92)

    te = window(panel, TEST_START, TEST_END)
    print(f"TEST bars: {len(te)} ({te.index[0].date()} -> {te.index[-1].date()})  "
          f"symbols: {len(symbols)}\n")

    cost = cost_model()
    cfg = portfolio_config()
    score = strategy_score(panel, variant.period, variant.threshold).reindex(te.index)

    # ---- the strategy -----------------------------------------------------
    res = run_backtest(te, score, cost, cfg, rebalance="M")
    m = res.metrics
    live = liveness(panel, variant.period, variant.threshold, TEST_START, TEST_END)

    print("--- 1. STRATEGY (TEST, net of full Indian delivery stack) ---")
    print(res.summary())
    print(f"avg names held      : {res.diag['avg_names']:.1f}   "
          f"rebalances: {res.diag['n_rebalances']}")
    print(f"max names held      : {int((res.weights > 0).sum(axis=1).max())}  "
          f"(engine cap max_names={cfg.max_names})")
    print(f"max single weight   : {res.weights.max().max() * 100:.2f}%  (cap 12%)")
    print(f"signal liveness     : {live['long_frac'] * 100:.1f}% of (name,bar) cells long; "
          f"avg {live['avg_flagged_names']:.1f} names eligible/day")
    print(f"days with <22 eligible names: {live['days_with_fewer_than_n_positions'] * 100:.1f}%")
    print(f"costs paid (Rs)     : {res.costs_paid:,.0f}")
    yr = yearly_returns(res.returns)
    print(f"years positive     : {(yr > 0).mean() * 100:.0f}%  -> "
          + ", ".join(f"{y}:{v * 100:+.1f}%" for y, v in yr.items()))

    # ---- 2. cost drag split ------------------------------------------------
    net, gross = cost_drag_split(panel, strategy_score(panel, variant.period,
                                                       variant.threshold),
                                 TEST_START, TEST_END)
    print("\n--- 2. COST DRAG (TEST) ---")
    print(f"  gross (zero cost) : CAGR {gross.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {gross.metrics.sharpe:>5.2f}  Ret {gross.metrics.total_return * 100:>7.1f}%")
    print(f"  net   (base cost) : CAGR {net.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {net.metrics.sharpe:>5.2f}  Ret {net.metrics.total_return * 100:>7.1f}%")
    print(f"  drag              : {(gross.metrics.cagr - net.metrics.cagr) * 100:.2f} pp/yr  "
          f"(annualised cost drag {net.metrics.cost_drag_annual * 100:.2f}%/y)")
    print(f"  VIABLE?           : "
          f"{'yes — net positive' if net.metrics.cagr > 0 else 'NO — net negative'}")

    # ---- 3. buy-and-hold ---------------------------------------------------
    bh = buy_and_hold(panel, cost, TEST_START, TEST_END)
    bm = bh["metrics"]
    print("\n--- 3. BUY-AND-HOLD, identical TEST window, same costs ---")
    print(f"  CAGR {bm.cagr * 100:>7.2f}%  Sharpe {bm.sharpe:>6.2f}  "
          f"MaxDD {bm.max_drawdown * 100:>7.2f}%  Calmar {bm.calmar:>6.2f}  "
          f"Ret {bm.total_return * 100:>7.1f}%  cost Rs {bh['costs_paid']:,.0f}")
    print("\n--- 4. HEAD TO HEAD (TEST) ---")
    d_ret = (m.total_return - bm.total_return) * 100
    d_cagr = (m.cagr - bm.cagr) * 100
    print(f"  return  : strategy {m.total_return * 100:+.1f}%  vs  B&H "
          f"{bm.total_return * 100:+.1f}%   -> {d_ret:+.1f} pp  "
          f"({'BETTER' if d_ret > 0 else 'WORSE'})")
    print(f"  CAGR    : {m.cagr * 100:+.2f}% vs {bm.cagr * 100:+.2f}%  -> {d_cagr:+.2f} pp")
    print(f"  drawdown: strategy {m.max_drawdown * 100:+.2f}%  vs  B&H "
          f"{bm.max_drawdown * 100:+.2f}%  -> "
          f"{(m.max_drawdown - bm.max_drawdown) * 100:+.2f} pp  "
          f"({'BETTER' if m.max_drawdown > bm.max_drawdown else 'WORSE'})")

    # ---- 5. random control -------------------------------------------------
    print(f"\n--- 5. RANDOM-SIGNAL CONTROL (TEST, {N_SEEDS} seeds) ---")
    print("  random names, random rank, matched daily eligible count")
    ctrl = []
    for s in range(N_SEEDS):
        sc, _ = random_control_score(panel, variant.period, variant.threshold, s)
        r = run_backtest(te, sc.reindex(te.index), cost, cfg, rebalance="M")
        ctrl.append((r.metrics.cagr, r.metrics.sharpe, r.metrics.max_drawdown,
                     r.metrics.total_return))
    cdf = pd.DataFrame(ctrl, columns=["cagr", "sharpe", "maxdd", "total_ret"])
    print(f"  random  CAGR  mean {cdf.cagr.mean() * 100:>6.2f}%  "
          f"p05 {cdf.cagr.quantile(.05) * 100:>6.2f}%  p95 {cdf.cagr.quantile(.95) * 100:>6.2f}%")
    print(f"  random Sharpe mean {cdf.sharpe.mean():>6.2f}  "
          f"p05 {cdf.sharpe.quantile(.05):>6.2f}  p95 {cdf.sharpe.quantile(.95):>6.2f}")
    pct = float((cdf.sharpe < m.sharpe).mean())
    print(f"  strategy Sharpe {m.sharpe:.2f} beats {pct * 100:.0f}% of random draws "
          f"-> {'PASS' if pct >= 0.95 else 'FAIL'} the coin-flip bar")

    # ---- 6. composite ------------------------------------------------------
    comp = run_backtest(te, build_composite_score(panel).reindex(te.index),
                        cost, cfg, rebalance="M")
    cm = comp.metrics
    print("\n--- 6. nsealgo COMPOSITE (TEST, same panel/costs) ---")
    print(f"  CAGR {cm.cagr * 100:>7.2f}%  Sharpe {cm.sharpe:>6.2f}  "
          f"MaxDD {cm.max_drawdown * 100:>7.2f}%  Calmar {cm.calmar:>6.2f}  "
          f"Turn {cm.annual_turnover:>5.2f}x/y")
    print(f"  strategy vs composite: Sharpe {m.sharpe:.2f} vs {cm.sharpe:.2f}  "
          f"-> {'BEATS' if m.sharpe > cm.sharpe else 'LOSES TO'} it "
          f"({m.sharpe - cm.sharpe:+.2f})")

    # ---- 7. sanity --------------------------------------------------------
    print("\n--- 7. SANITY CHECKS (brief section 6) ---")
    print(f"  [1] plausibility : CAGR {m.cagr * 100:.2f}% "
          f"-> {'OK (unlevered long-only NIFTY-50)' if m.cagr < 0.5 else 'SUSPICIOUS'}")
    print(f"  [2] weight count : avg {res.diag['avg_names']:.1f} names "
          f"(target 22, hard cap 30) -> {'OK' if res.diag['avg_names'] <= 30 else 'BUG'}")
    print(f"  [3] liveness     : {live['long_frac'] * 100:.1f}% long "
          f"-> {'OK (live signal)' if live['long_frac'] >= 0.05 else 'DEAD (always flat)'}")
    print(f"  [4] cost drag    : {(gross.metrics.cagr - net.metrics.cagr) * 100:+.2f} pp/yr; "
          f"gross {'+' if gross.metrics.cagr > 0 else ''}"
          f"{gross.metrics.cagr * 100:.1f}% -> net {net.metrics.cagr * 100:+.1f}%")

    # ---- 8. persistence: full-history, for context only --------------------
    full = run_backtest(panel, score if score.index.equals(panel.index) else
                        strategy_score(panel, variant.period, variant.threshold),
                        cost, cfg, rebalance="M")
    fm = full.metrics
    print("\n--- 8. CONTEXT (not a selection criterion): full 2008-2026 history ---")
    print(f"  CAGR {fm.cagr * 100:.2f}%  Sharpe {fm.sharpe:.2f}  "
          f"MaxDD {fm.max_drawdown * 100:.2f}%  -> the strategy's edge is "
          f"{'regime-dependent' if m.sharpe < fm.sharpe - 0.2 or m.sharpe > fm.sharpe + 0.2 else 'stable'}")

    pd.DataFrame({
        "strategy": [m.cagr, m.sharpe, m.max_drawdown, m.calmar, m.total_return,
                     m.annual_turnover, m.cost_drag_annual, m.volatility],
        "buy_hold": [bm.cagr, bm.sharpe, bm.max_drawdown, bm.calmar, bm.total_return,
                     bm.annual_turnover, bm.cost_drag_annual, bm.volatility],
        "composite": [cm.cagr, cm.sharpe, cm.max_drawdown, cm.calmar, cm.total_return,
                      cm.annual_turnover, cm.cost_drag_annual, cm.volatility],
    }, index=["cagr", "sharpe", "maxdd", "calmar", "total_ret", "turnover_yr",
              "cost_drag_yr", "vol"]).to_csv(OUT / "test_summary.csv")
    cdf.to_csv(OUT / "test_random_control.csv", index=False)
    print(f"\nwrote {OUT / 'test_summary.csv'}")


if __name__ == "__main__":
    main()
