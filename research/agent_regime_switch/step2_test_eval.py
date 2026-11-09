"""STEP 2 — the single TEST evaluation of the TRAIN-selected variant, plus every
comparison the brief mandates (buy-and-hold, composite, cost split, random control,
beta/alpha, yearly returns, sanity checks).

The variant is read from `selected_variant.txt`, written by step 1. Nothing here can
change a parameter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    beta_alpha,
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

SEEDS = list(range(60))


def main() -> None:
    panel, symbols, _ = load()
    sel_name = (HERE / "selected_variant.txt").read_text().strip()
    period = int("".join(ch for ch in sel_name.split("_p")[1] if ch.isdigit()))
    print(f"TEST evaluation of the TRAIN-selected variant: {sel_name} "
          f"(period={period}), unchanged\n")

    px = window(panel, TEST_START, TEST_END)
    cm = cost_model()
    cfg = portfolio_config()

    sc = strategy_score(panel, period)

    # ---- the book -------------------------------------------------------- #
    res = run_backtest(px, sc.reindex(px.index), cm, cfg, rebalance="M")
    net, gross = cost_drag_split(panel, sc, TEST_START, TEST_END)
    bh = buy_and_hold(panel, cm, TEST_START, TEST_END)
    comp = run_backtest(
        px, build_composite_score(px).reindex(px.index), cm, cfg, rebalance="M"
    )

    m = res.metrics
    beta, alpha, corr = beta_alpha(res.returns, panel, TEST_START, TEST_END)
    bh_beta, bh_alpha, _ = beta_alpha(bh["returns"], panel, TEST_START, TEST_END)
    live = liveness(panel, period, TEST_START, TEST_END)

    print(f"--- TEST {px.index[0].date()} -> {px.index[-1].date()} "
          f"({len(px)} bars) ---")
    hdr = f"{'book':<24}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}{'Calmar':>8}" \
          f"{'Total':>9}{'Turn':>8}{'Cost':>8}{'Names':>8}{'Beta':>7}{'Alpha/y':>9}"
    print(hdr)
    for lab, mm, extra in (
        ("regime_switch (TEST)", m, f"{res.diag['avg_names']:.1f} {beta:.2f} {alpha*100:+.2f}"),
        ("buy-and-hold (TEST)", bh["metrics"], f"48.0 {bh_beta:.2f} {bh_alpha*100:+.2f}"),
        ("nsealgo composite", comp.metrics, f"{comp.diag['avg_names']:.1f}"),
        ("GROSS (zero cost)", gross.metrics, ""),
    ):
        print(f"{lab:<24}{mm.cagr * 100:>8.2f}%{mm.sharpe:>9.2f}"
              f"{mm.max_drawdown * 100:>8.2f}%{mm.calmar:>8.2f}"
              f"{mm.total_return * 100:>8.2f}%{mm.annual_turnover:>7.2f}x"
              f"{mm.cost_drag_annual * 100:>7.2f}%{extra:>8}")

    print("\nYearly: " + "  ".join(
        f"{y} {v * 100:+.1f}%" for y, v in yearly_returns(res.returns).items()
    ))
    yrs = yearly_returns(res.returns)
    print(f"positive years: {(yrs > 0).mean() * 100:.0f}%")

    print("\n--- sanity checks (brief section 6) ---")
    print(f"[1] plausibility   CAGR {m.cagr * 100:.2f}%  (long-only ceiling ~40-50%)  "
          f"{'OK' if m.cagr < 0.5 else 'SUSPECT'}")
    print(f"[2] weight count   avg {res.diag['avg_names']:.1f} names "
          f"(target 22, cap 30)  max single weight "
          f"{float(res.weights.max().max()) * 100:.2f}% (cap 12%)")
    print(f"[3] liveness       {live['long_frac_cells'] * 100:.1f}% of (name,bar) cells "
          f"long; {live['avg_long_names']:.1f} names/day; "
          f"{live['days_below_n_positions'] * 100:.0f}% of days < 22 eligible")
    print(f"[4] cost drag      {m.cost_drag_annual * 100:.2f}%/y  "
          f"(gross CAGR {gross.metrics.cagr * 100:.2f}% -> net {m.cagr * 100:.2f}%)")
    print(f"    beta {beta:.2f}  alpha {alpha * 100:+.2f}%/y  corr to EW market {corr:.2f}")
    print(f"    rebalances {res.diag['n_rebalances']}  "
          f"round-trip charged {res.diag['round_trip_bps']:.2f} bps")

    # ---- random control -------------------------------------------------- #
    print("\n--- negative control: random names, same % of bars long ---")
    rows = []
    for seed in SEEDS:
        rc = random_control_score(panel, period, seed)
        r = run_backtest(px, rc.reindex(px.index), cm, cfg, rebalance="M")
        rows.append({"seed": seed, "cagr": r.metrics.cagr, "sharpe": r.metrics.sharpe,
                     "max_dd": r.metrics.max_drawdown})
    rnd = pd.DataFrame(rows)
    rnd.to_csv(HERE / "test_random_control.csv", index=False)
    beat_cagr = (rnd["cagr"] < m.cagr).mean()
    beat_sh = (rnd["sharpe"] < m.sharpe).mean()
    print(f"random over {len(SEEDS)} seeds:  CAGR {rnd.cagr.mean() * 100:.2f}% "
          f"(p05 {rnd.cagr.quantile(.05) * 100:.2f}, p95 {rnd.cagr.quantile(.95) * 100:.2f})"
          f"   Sharpe {rnd.sharpe.mean():.2f}")
    print(f"strategy beats {beat_cagr * 100:.0f}% of random on CAGR, "
          f"{beat_sh * 100:.0f}% on Sharpe")
    print("VERDICT vs coin flip: " + ("PASS" if beat_sh >= 0.90 else "FAIL"))

    summary = pd.DataFrame(
        [
            {"book": "regime_switch", "cagr": m.cagr, "sharpe": m.sharpe,
             "max_dd": m.max_drawdown, "calmar": m.calmar,
             "total_return": m.total_return, "turnover": m.annual_turnover,
             "cost_drag": m.cost_drag_annual, "avg_names": res.diag["avg_names"],
             "beta": beta, "alpha": alpha},
            {"book": "buy_and_hold", "cagr": bh["metrics"].cagr,
             "sharpe": bh["metrics"].sharpe, "max_dd": bh["metrics"].max_drawdown,
             "calmar": bh["metrics"].calmar,
             "total_return": bh["metrics"].total_return,
             "turnover": bh["metrics"].annual_turnover,
             "cost_drag": bh["metrics"].cost_drag_annual, "avg_names": 48.0,
             "beta": bh_beta, "alpha": bh_alpha},
            {"book": "nsealgo_composite", "cagr": comp.metrics.cagr,
             "sharpe": comp.metrics.sharpe, "max_dd": comp.metrics.max_drawdown,
             "calmar": comp.metrics.calmar, "total_return": comp.metrics.total_return,
             "turnover": comp.metrics.annual_turnover,
             "cost_drag": comp.metrics.cost_drag_annual,
             "avg_names": comp.diag["avg_names"], "beta": float("nan"),
             "alpha": float("nan")},
        ]
    )
    summary.to_csv(HERE / "test_summary.csv", index=False)
    print(f"\nTEST result written. Selected variant was {sel_name}; unchanged.")


if __name__ == "__main__":
    main()
