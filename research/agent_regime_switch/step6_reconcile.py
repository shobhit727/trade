"""Final reconciliation: recompute every headline number quoted in REPORT.md from
scratch and print it, so the report can be checked against reality rather than
against my memory of the run."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    build_composite_score,
    buy_and_hold,
    cost_model,
    load,
    portfolio_config,
    run_backtest,
    strategy_score,
    window,
    yearly_returns,
)


def main() -> None:
    panel, _, _ = load()
    cm, cfg = cost_model(), portfolio_config()
    sel = (HERE / "selected_variant.txt").read_text().strip()
    period = int("".join(c for c in sel.split("_p")[1] if c.isdigit()))
    print(f"selected variant: {sel}  period={period}\n")

    tr = window(panel, TRAIN_START, TRAIN_END)
    te = window(panel, TEST_START, TEST_END)
    sc = strategy_score(panel, period)

    tr_res = run_backtest(tr, sc.reindex(tr.index), cm, cfg, rebalance="M")
    te_res = run_backtest(te, sc.reindex(te.index), cm, cfg, rebalance="M")
    tr_comp = run_backtest(tr, build_composite_score(tr).reindex(tr.index), cm, cfg, "M")
    te_comp = run_backtest(te, build_composite_score(te).reindex(te.index), cm, cfg, "M")
    tr_bh = buy_and_hold(panel, cm, TRAIN_START, TRAIN_END)
    te_bh = buy_and_hold(panel, cm, TEST_START, TEST_END)

    def line(tag, r, bh=None):
        m = r["metrics"] if isinstance(r, dict) else getattr(r, "metrics", r)
        nm = r.diag["avg_names"] if hasattr(r, "diag") else 48.0
        rs = r["costs_paid"] if isinstance(r, dict) else getattr(r, "costs_paid", float("nan"))
        print(f"{tag:<26} CAGR {m.cagr * 100:>7.2f}%  Sh {m.sharpe:>6.2f}  "
              f"DD {m.max_drawdown * 100:>7.2f}%  Cal {m.calmar:>5.2f}  "
              f"Tot {m.total_return * 100:>7.2f}%  Turn {m.annual_turnover:>5.2f}x  "
              f"Cost {m.cost_drag_annual * 100:>5.2f}%/y  Names {nm:>4.1f}  "
              f"RsCost {rs:>12,.0f}")
        return m

    print("TRAIN")
    line("regime_switch", tr_res)
    line("nsealgo composite", tr_comp)
    line("buy-and-hold", tr_bh)
    print("\nTEST")
    t = line("regime_switch", te_res)
    line("nsealgo composite", te_comp)
    b = line("buy-and-hold", te_bh)

    print(f"\nTEST total-return gap vs B&H: "
          f"{(b.total_return - t.total_return) * 100:+.2f}pp "
          f"= Rs {(b.total_return - t.total_return) * 2_100_000:+,.0f} on 21,00,000")
    print(f"TEST CAGR gap vs B&H:          "
          f"{(b.cagr - t.cagr) * 100:+.2f}pp/yr")
    print(f"TEST MaxDD improvement vs B&H: "
          f"{(t.max_drawdown - b.max_drawdown) * 100:+.2f}pp")

    yr = yearly_returns(te_res.returns)
    print("\nTEST yearly: " + "  ".join(f"{y} {v * 100:+.1f}%" for y, v in yr.items()))
    print(f"positive years: {(yr > 0).mean() * 100:.0f}%")
    print(f"\ncost-drag multiple vs composite (TEST): "
          f"{t.cost_drag_annual / te_comp.metrics.cost_drag_annual:.2f}x "
          f"(strategy {t.cost_drag_annual * 100:.2f}%/y vs "
          f"composite {te_comp.metrics.cost_drag_annual * 100:.2f}%/y)")
    print(f"cost-drag multiple vs composite (TRAIN): "
          f"{tr_res.metrics.cost_drag_annual / tr_comp.metrics.cost_drag_annual:.2f}x "
          f"({tr_res.metrics.cost_drag_annual * 100:.2f}%/y vs "
          f"{tr_comp.metrics.cost_drag_annual * 100:.2f}%/y)")
    print(f"\nTEST costs paid in rupees (21,00,000 book): Rs {te_res.costs_paid:,.0f}")
    print(f"max single weight: {float(te_res.weights.max().max()) * 100:.2f}%  "
          f"(cap 12%)   rebalances: {te_res.diag['n_rebalances']}  "
          f"rt_bps charged: {te_res.diag['round_trip_bps']:.2f}")


if __name__ == "__main__":
    main()
