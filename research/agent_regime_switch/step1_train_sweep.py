"""STEP 1 — TRAIN-only selection. Declared budget: the 5 variants in harness.VARIANTS.

Selection rule, fixed in advance: highest TRAIN Sharpe; ties broken on Calmar.
Nothing here reads TEST.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    build_composite_score,
    buy_and_hold,
    cost_model,
    liveness,
    load,
    portfolio_config,
    run_backtest,
    strategy_score,
    window,
)


def main() -> None:
    panel, symbols, _ = load()
    px = window(panel, TRAIN_START, TRAIN_END)
    print(f"TRAIN window {px.index[0].date()} -> {px.index[-1].date()}  "
          f"({len(px)} bars, {px.shape[1]} symbols)\n")

    cm = cost_model()
    cfg = portfolio_config()

    # ---- reference points on TRAIN -------------------------------------- #
    bh = buy_and_hold(panel, cm, TRAIN_START, TRAIN_END)
    comp = run_backtest(
        px, build_composite_score(px).reindex(px.index), cm, cfg, rebalance="M"
    )
    print("--- TRAIN references ---")
    print(f"{'buy-and-hold (EW)':<28} CAGR {bh['metrics'].cagr * 100:>7.2f}%  "
          f"Sharpe {bh['metrics'].sharpe:>6.2f}  "
          f"MaxDD {bh['metrics'].max_drawdown * 100:>7.2f}%")
    print(f"{'nsealgo composite':<28} CAGR {comp.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {comp.metrics.sharpe:>6.2f}  "
          f"MaxDD {comp.metrics.max_drawdown * 100:>7.2f}%\n")

    # ---- the 5 declared variants ---------------------------------------- #
    rows = []
    for v in VARIANTS:
        sc = strategy_score(panel, v.period)
        res = run_backtest(px, sc.reindex(px.index), cm, cfg, rebalance="M")
        live = liveness(panel, v.period, TRAIN_START, TRAIN_END)
        m = res.metrics
        rows.append(
            {
                "variant": v.name,
                "period": v.period,
                "cagr": m.cagr,
                "sharpe": m.sharpe,
                "max_dd": m.max_drawdown,
                "calmar": m.calmar,
                "turnover": m.annual_turnover,
                "cost_drag": m.cost_drag_annual,
                "avg_names": res.diag["avg_names"],
                "long_frac": live["long_frac_cells"],
                "avg_long_names": live["avg_long_names"],
                "days_below_22": live["days_below_n_positions"],
            }
        )
        print(
            f"{v.name:<28} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
            f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
            f"Turn {m.annual_turnover:>5.2f}x/y  "
            f"Cost {m.cost_drag_annual * 100:>5.2f}%/y  "
            f"names {res.diag['avg_names']:>4.1f}  "
            f"long {live['long_frac_cells'] * 100:>5.1f}%  "
            f"({live['avg_long_names']:>4.1f} names/day)"
        )

    df = pd.DataFrame(rows).sort_values(["sharpe", "calmar"], ascending=False)
    df.to_csv(HERE / "train_sweep.csv", index=False)

    sel = df.iloc[0]
    (HERE / "selected_variant.txt").write_text(f"{sel['variant']}\n")
    print(f"\nSELECTED ON TRAIN (Sharpe, tie-broken on Calmar): {sel['variant']}  "
          f"period={int(sel['period'])}  Sharpe {sel['sharpe']:.2f}")
    print("TEST has not been touched.")


if __name__ == "__main__":
    main()
