"""Stage 2: the single TEST evaluation. V5 is frozen from the TRAIN selection.

Nothing is tuned here. This script runs V5 once, plus the mandated benchmarks and
the random-signal negative control, all on the identical TEST window.
"""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "research/agent_momvol")

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    assert_atr_tautology,
    buy_hold_score,
    composite_score,
    get_panel,
    metrics_from_returns,
    out,
    random_score,
    run,
    signal_panel,
    test_parts,
)

from nsealgo.backtest.metrics import yearly_returns  # noqa: E402

FROZEN_MOMPERIOD = 5
FROZEN_THRESHOLD = 0.005
FROZEN_ID = "V5"
N_RANDOM_SEEDS = 20


def main() -> None:
    panel, _ = get_panel()
    print("=" * 78)
    print("TEST WINDOW -- touched once. V5 frozen from the TRAIN selection.")
    print(f"  {TEST_START.date()} -> {TEST_END.date()}")
    print("=" * 78)

    n_atr = assert_atr_tautology(TEST_START, TEST_END, "TEST")
    print(f"ATR-predicate guard: {n_atr} gating endpoints in TEST\n")

    p, sc = test_parts(panel, FROZEN_MOMPERIOD, FROZEN_THRESHOLD)
    print(f"TEST panel {p.shape}  {p.index[0].date()} -> {p.index[-1].date()}")

    sig = signal_panel(panel, FROZEN_MOMPERIOD, FROZEN_THRESHOLD)
    long_frac = float(sig.loc[p.index].notna().to_numpy().mean())
    print(f"Signal liveness: {long_frac*100:.1f}% of bars long "
          f"(brief's red flag is <5%)\n")

    results = {}

    # ---- the strategy, frozen -------------------------------------------- #
    strat = run(p, sc, "STRATEGY_V5", long_frac=long_frac)
    results["strategy"] = strat.row()

    # ---- buy-and-hold, identical constraints + identical costs ---------- #
    bh = run(p, buy_hold_score(p), "BUY_HOLD")
    results["buy_hold_constrained"] = bh.row()

    # ---- buy-and-hold, the brief's literal literal form ----------------- #
    eqw = p.pct_change(fill_method=None).mean(axis=1).dropna()
    results["buy_hold_equal_weight_raw"] = metrics_from_returns(eqw, "BUY_HOLD_EW_RAW")

    # ---- nsealgo composite ---------------------------------------------- #
    comp = run(p, composite_score(p), "COMPOSITE")
    results["composite"] = comp.row()

    # ---- random-signal negative control --------------------------------- #
    rnd = []
    for seed in range(N_RANDOM_SEEDS):
        rs = random_score(p, long_frac, seed)
        rr = run(p, rs, f"RANDOM_{seed}", long_frac=long_frac)
        rnd.append(rr.row())
    rdf = pd.DataFrame(rnd)
    results["random_control"] = {
        "n_seeds": N_RANDOM_SEEDS,
        "mean_cagr": float(rdf["cagr"].mean()),
        "std_cagr": float(rdf["cagr"].std()),
        "median_cagr": float(rdf["cagr"].median()),
        "mean_sharpe": float(rdf["sharpe"].mean()),
        "std_sharpe": float(rdf["sharpe"].std()),
        "mean_maxdd": float(rdf["maxdd"].mean()),
        "best_cagr": float(rdf["cagr"].max()),
        "worst_cagr": float(rdf["cagr"].min()),
        "strategy_cagr": results["strategy"]["cagr"],
        "strategy_sharpe": results["strategy"]["sharpe"],
        "strategy_pctile_vs_random": float(
            (rdf["cagr"] < results["strategy"]["cagr"]).mean()
        ),
    }

    # ---- cost decomposition -------------------------------------------- #
    results["cost_analysis"] = {
        "strategy_net_cagr": strat.metrics.cagr,
        "strategy_gross_cagr": strat.gross_cagr(),
        "cost_drag_annual": strat.metrics.cost_drag_annual,
        "round_trip_bps_charged": strat.result.diag["round_trip_bps"],
    }

    # ---- plausibility ---------------------------------------------------- #
    results["sanity"] = {
        "avg_names_held": strat.result.diag["avg_names"],
        "avg_top_weight": strat.result.diag["avg_top_weight"],
        "n_rebalances": strat.result.diag["n_rebalances"],
        "gross_weight_sum_max": float(strat.result.weights.sum(axis=1).max()),
        "gross_weight_sum_min": float(strat.result.weights.sum(axis=1).min()),
        "final_equity": float(strat.result.equity.iloc[-1]),
        "max_equity": float(strat.result.equity.max()),
        "plausible_cagr": bool(strat.metrics.cagr < 0.50),
        "weight_count_ok": bool(20 <= strat.result.diag["avg_names"] <= 30),
        "signal_liveness_ok": bool(long_frac >= 0.05),
        "no_negative_weights": bool((strat.result.weights.values >= 0).all()),
        "weights_sum_le_1": bool(strat.result.weights.sum(axis=1).max() <= 1.0 + 1e-9),
    }

    # ---- yearly breakdown ----------------------------------------------- #
    yr = yearly_returns(strat.result.returns)
    results["yearly"] = {str(k): float(v) for k, v in yr.items()}

    out("stage2_test.json", results)
    out("stage2_equity.csv", strat.result.equity.rename("equity"))

    # ---------------------------------------------------------------- print #
    def line(tag, d):
        print(f"  {tag:<28} CAGR {d['cagr']*100:>6.2f}%  Sharpe {d['sharpe']:>5.2f}  "
              f"MaxDD {d['maxdd']*100:>6.2f}%  Calmar {d['calmar']:>5.2f}  "
              f"turn {d['turnover']:>4.2f}x  names {d['avg_names']:>4.1f}")

    print("\nTEST RESULTS (net of 21.92 bps):")
    line("STRATEGY (V5, frozen)", results["strategy"])
    line("buy-and-hold (22-name book)", results["buy_hold_constrained"])
    line("nsealgo composite", results["composite"])
    d = results["buy_hold_equal_weight_raw"]
    print(f"  {'buy-and-hold (raw EW)':<28} CAGR {d['cagr']*100:>6.2f}%  "
          f"Sharpe {d['sharpe']:>5.2f}  MaxDD {d['maxdd']*100:>6.2f}%")

    rc = results["random_control"]
    print(f"\nRANDOM-SIGNAL CONTROL ({N_RANDOM_SEEDS} seeds, same % long):")
    print(f"  mean CAGR  {rc['mean_cagr']*100:>6.2f}% +/- {rc['std_cagr']*100:.2f}  "
          f"[best {rc['best_cagr']*100:.2f}%, worst {rc['worst_cagr']*100:.2f}%]")
    print(f"  mean Sharpe {rc['mean_sharpe']:>6.2f} +/- {rc['std_sharpe']:.2f}")
    print(f"  strategy sits at the {rc['strategy_pctile_vs_random']*100:.0f}th "
          f"percentile of random on CAGR")

    ca = results["cost_analysis"]
    print("\nCOST DECOMPOSITION:")
    print(f"  gross CAGR {ca['strategy_gross_cagr']*100:>6.2f}%  ->  "
          f"net CAGR {ca['strategy_net_cagr']*100:>6.2f}%   "
          f"(drag {ca['cost_drag_annual']*100:.2f}%/y @ {ca['round_trip_bps_charged']:.2f} bps)")

    print("\nSANITY:")
    for k, v in results["sanity"].items():
        print(f"  {k:<24} {v}")

    print("\nYEARLY (strategy):")
    for k, v in results["yearly"].items():
        print(f"  {k}  {v*100:>6.2f}%")


if __name__ == "__main__":
    main()
