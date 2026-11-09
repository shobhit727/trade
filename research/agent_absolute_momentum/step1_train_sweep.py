"""STEP 1 — TRAIN-only sweep of the 5 DECLARED variants.

No TEST data is touched here. Selection is by TRAIN Sharpe, tie-broken on Calmar.
Writes research/agent_absolute_momentum/train_sweep.csv and prints the table.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (  # noqa: E402
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    build_composite_score,
    cost_model,
    liveness,
    load,
    portfolio_config,
    run_backtest,
    strategy_score,
    window,
    yearly_returns,
)

OUT = Path(__file__).resolve().parent


def main() -> None:
    panel, symbols, _ = load()
    tr = window(panel, TRAIN_START, TRAIN_END)
    print(f"TRAIN window: {tr.index[0].date()} -> {tr.index[-1].date()} "
          f"({len(tr)} bars, {len(symbols)} symbols)\n")
    print("DECLARED PARAMETER BUDGET (5 variants, fixed before any run):")
    for v in VARIANTS:
        print(f"  {v.name:<14} period={v.period:<4} threshold={v.threshold}")
    print()

    cost = cost_model()
    cfg = portfolio_config()
    rows = []
    for v in VARIANTS:
        score = strategy_score(panel, v.period, v.threshold)
        live = liveness(panel, v.period, v.threshold, TRAIN_START, TRAIN_END)
        r = run_backtest(tr, score.reindex(tr.index), cost, cfg, rebalance="M")
        m = r.metrics
        yr = yearly_returns(r.returns)
        rows.append({
            "variant": v.name, "period": v.period, "threshold": v.threshold,
            "cagr": m.cagr, "sharpe": m.sharpe, "sortino": m.sortino,
            "maxdd": m.max_drawdown, "calmar": m.calmar,
            "total_ret": m.total_return, "vol": m.volatility,
            "turnover_yr": m.annual_turnover, "cost_drag_yr": m.cost_drag_annual,
            "avg_names": r.diag["avg_names"],
            "long_frac": live["long_frac"],
            "avg_flagged": live["avg_flagged_names"],
            "pct_years_pos": float((yr > 0).mean()),
        })
        print(f"{v.name:<14} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
              f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
              f"Turn {m.annual_turnover:>5.2f}x  Cost {m.cost_drag_annual * 100:>5.2f}%/y  "
              f"names {r.diag['avg_names']:>4.1f}  long {live['long_frac'] * 100:>5.1f}%")

    # Composite reference on TRAIN (the thing to beat)
    comp = run_backtest(tr, build_composite_score(panel).reindex(tr.index),
                        cost, cfg, rebalance="M")
    cm = comp.metrics
    print(f"\n{'COMPOSITE (ref)':<14} CAGR {cm.cagr * 100:>7.2f}%  "
          f"Sharpe {cm.sharpe:>6.2f}  MaxDD {cm.max_drawdown * 100:>7.2f}%  "
          f"Calmar {cm.calmar:>6.2f}")
    rows.append({
        "variant": "COMPOSITE_ref", "period": -1, "threshold": -1.0,
        "cagr": cm.cagr, "sharpe": cm.sharpe, "sortino": cm.sortino,
        "maxdd": cm.max_drawdown, "calmar": cm.calmar,
        "total_ret": cm.total_return, "vol": cm.volatility,
        "turnover_yr": cm.annual_turnover, "cost_drag_yr": cm.cost_drag_annual,
        "avg_names": comp.diag["avg_names"], "long_frac": 1.0,
        "avg_flagged": float(len(symbols)), "pct_years_pos": float(
            (yearly_returns(comp.returns) > 0).mean()),
    })

    df = pd.DataFrame(rows).set_index("variant")
    df.to_csv(OUT / "train_sweep.csv")

    strat = df.drop(index="COMPOSITE_ref")
    best = strat.sort_values(["sharpe", "calmar"], ascending=False).index[0]
    print(f"\n>>> TRAIN-selected variant: {best}  "
          f"(Sharpe {strat.loc[best, 'sharpe']:.2f}, Calmar {strat.loc[best, 'calmar']:.2f})")
    print(f">>> TRAIN composite Sharpe: {cm.sharpe:.2f}  -> "
          f"{'BEATS' if strat.loc[best, 'sharpe'] > cm.sharpe else 'LOSES TO'} composite in-sample")
    (OUT / "selected_variant.txt").write_text(best + "\n")


if __name__ == "__main__":
    main()
