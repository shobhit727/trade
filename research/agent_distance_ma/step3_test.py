"""Step 3: the single TEST evaluation. Selection was made on TRAIN in step 2.

`SELECTED` below is fixed by the rule in DECLARED_BUDGET.md (highest TRAIN Sharpe net
of costs). It is hard-coded here so the TEST run cannot silently re-select.

The other four variants appear on TEST too, but only as a disclosure of the
already-declared budget -- they were registered before any number existed, and the
headline TEST number is the TRAIN-selected one.
"""

from __future__ import annotations

from decimal import Decimal

from common import (
    BUILDERS,
    COST,
    PORTFOLIO,
    STRESS_MODELS,
    TEST_END,
    TEST_START,
    build_composite_score,
    buy_and_hold_result,
    compute_metrics,
    deviation_panel,
    load_panel,
    random_signal_result,
    run_backtest,
    table,
    yearly_returns,
)
from step1_signal_diag import VARIANTS

# Frozen by the TRAIN selection rule. Do not change without declaring a new run.
SELECTED = "V3 dev_depth p50 t0.05"


def main() -> None:
    panel, symbols, _ = load_panel()
    test = panel.loc[(panel.index >= TEST_START) & (panel.index <= TEST_END)]
    train = panel.loc[(panel.index < TEST_START)]
    print(f"TEST  {TEST_START.date()} .. {TEST_END.date()}   bars={len(test)}")
    print(f"costs: {COST.all_in_round_trip_bps(Decimal('100000'))} bps all-in RT\n")

    results = {}
    for label, con, period, thr in VARIANTS:
        results[label] = run_backtest(test, BUILDERS[con](test, period, thr),
                                      COST, PORTFOLIO, rebalance="M")

    # ---- headline: TRAIN-selected variant, unchanged -----------------------
    r = results[SELECTED]
    m = r.metrics
    held = r.weights
    print(f"===== HEADLINE TEST RESULT: {SELECTED} =====")
    print(m.fmt())
    print(f"  avg names held    : {r.diag['avg_names']:.1f}")
    print(f"  avg invested      : {float(held.sum(axis=1).mean()):.1%} "
          "(rest is the 10% cash buffer + uninvestable cash)")
    print(f"  rebalances        : {r.diag['n_rebalances']:.0f}")
    print(f"  costs paid (Rs)   : {r.costs_paid:,.0f} on a Rs 21,00,000 book")

    # gross vs net, to size the cost drag honestly
    rets = test.pct_change(fill_method=None).fillna(0.0)
    gross = (held.shift(1).fillna(0.0) * rets).sum(axis=1)
    ge = (1 + gross).cumprod()
    gm = compute_metrics(gross, ge)
    print(f"\n  GROSS (costs removed): CAGR {gm.cagr * 100:>6.2f}%  "
          f"Sharpe {gm.sharpe:>5.2f}  -> NET {m.cagr * 100:.2f}% / {m.sharpe:.2f}")
    print(f"  cost drag          : {m.cost_drag_annual * 100:.2f}%/yr "
          f"on {m.annual_turnover:.2f}x turnover")

    print("\n  calendar-year returns:")
    for y, v in yearly_returns(r.returns).items():
        print(f"    {y}: {v * 100:>7.2f}%")

    # ---- all 5 declared variants on TEST ----------------------------------
    print("\n===== ALL 5 DECLARED VARIANTS, TEST =====")
    print(table([(k, v.metrics) for k, v in results.items()]))

    # ---- benchmark: buy-and-hold, identical window ------------------------
    bh48 = buy_and_hold_result(test, None, "buy_and_hold (EW 48)")
    bh22 = buy_and_hold_result(test, sorted(symbols)[:22], "buy_and_hold (EW 22)")
    comp = run_backtest(test, build_composite_score(test), COST, PORTFOLIO, rebalance="M")

    print("\n===== TEST BENCHMARKS =====")
    print(table([(SELECTED, m), (bh22["name"], bh22["metrics"]),
                 (bh48["name"], bh48["metrics"]),
                 ("nsealgo_composite", comp.metrics)]))

    # ---- head-to-head -----------------------------------------------------
    bm = bh22["metrics"]
    print("\n===== HEAD TO HEAD vs buy-and-hold (EW 22) =====")
    print(f"  return    : strategy {m.cagr * 100:>7.2f}%  vs  B&H {bm.cagr * 100:>7.2f}%"
          f"   ->  {(m.cagr - bm.cagr) * 100:>+7.2f} pp/yr")
    print(f"  total     : strategy {m.total_return * 100:>8.2f}%  vs  "
          f"B&H {bm.total_return * 100:>8.2f}%  ->  "
          f"{(m.total_return - bm.total_return) * 100:>+8.2f} pp")
    print(f"  drawdown  : strategy {m.max_drawdown * 100:>7.2f}%  vs  "
          f"B&H {bm.max_drawdown * 100:>7.2f}%  ->  "
          f"{'better' if m.max_drawdown > bm.max_drawdown else 'WORSE'} by "
          f"{abs(m.max_drawdown - bm.max_drawdown) * 100:.2f} pp")
    print(f"  Sharpe    : strategy {m.sharpe:>7.2f}  vs  B&H {bm.sharpe:>7.2f}")
    print(f"  vs composite: strategy {m.cagr * 100:.2f}% / {m.sharpe:.2f}  vs  "
          f"composite {comp.metrics.cagr * 100:.2f}% / {comp.metrics.sharpe:.2f}")

    # ---- negative control: random signal, same liveness -------------------
    dev = deviation_panel(test, 50)
    live = float((dev < -0.05).values.mean())
    print(f"\n===== NEGATIVE CONTROL: random signal, same {live:.2%} of name-days long =====")
    rnd = random_signal_result(test, live, seeds=(1, 2, 3))
    print(table([(f"random(seed={s})", v.metrics) for s, v in rnd.items()]))
    print(f"  mean random Sharpe: "
          f"{sum(v.metrics.sharpe for v in rnd.values()) / len(rnd):.2f}"
          f"   vs strategy {m.sharpe:.2f}")

    # ---- literature negative control: reversal_20d ------------------------
    from nsealgo.factors.core import NEGATIVE_CONTROL_WEIGHTS

    rev = run_backtest(test, build_composite_score(test, NEGATIVE_CONTROL_WEIGHTS),
                       COST, PORTFOLIO, rebalance="M")
    print(f"\n  reversal composite (literature negative control): "
          f"CAGR {rev.metrics.cagr * 100:.2f}%  Sharpe {rev.metrics.sharpe:.2f}")

    # ---- cost stress (GOAL.md Gate 4) ------------------------------------
    print("\n===== COST STRESS (selected variant, TEST) =====")
    for nm, cm in STRESS_MODELS.items():
        rr = run_backtest(test, BUILDERS["dev_depth"](test, 50, 0.05), cm, PORTFOLIO,
                          rebalance="M")
        print(f"  {nm:<18} CAGR {rr.metrics.cagr * 100:>7.2f}%  "
              f"Sharpe {rr.metrics.sharpe:>6.2f}  "
              f"drag {rr.metrics.cost_drag_annual * 100:>5.2f}%/y")

    # ---- per-name attribution on TEST ------------------------------------
    print("\n===== WHERE THE TEST P&L CAME FROM (selected variant) =====")
    pos = (test > test.shift(1)).mean(axis=1)
    print(f"  fraction of TEST bars where the mean held name rose: {pos.mean():.1%}")
    sel = dev < -0.05
    fut5 = (test.shift(-5) / test - 1.0)[sel].stack()
    fut21 = (test.shift(-21) / test - 1.0)[sel].stack()
    print(f"  after a long signal, mean 5d forward return : {fut5.mean():+.3%}")
    print(f"  after a long signal, mean 21d forward ret  : {fut21.mean():+.3%}")
    print(f"  whole-universe mean 5d forward return      : "
          f"{(test.shift(-5)/test - 1.0).stack().mean():+.3%}")
    print(f"  whole-universe mean 21d forward return     : "
          f"{(test.shift(-21)/test - 1.0).stack().mean():+.3%}")

    # ---- is TEST just a bad market for this rule? TRAIN vs TEST forward ----
    print("\n===== TRAIN vs TEST, same signal, 21d forward return =====")
    for tag, sub in (("TRAIN", train), ("TEST ", test)):
        d2 = deviation_panel(sub, 50)
        s = d2 < -0.05
        f = (sub.shift(-21) / sub - 1.0)[s].stack()
        a = (sub.shift(-21) / sub - 1.0).stack()
        print(f"  {tag}: signalled {f.mean():+.3%}  universe {a.mean():+.3%}  "
              f"excess {f.mean() - a.mean():+.3%}  (n={len(f):,})")


if __name__ == "__main__":
    main()
