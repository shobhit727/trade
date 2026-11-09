"""TEST evaluation — the selected variant ONLY, run exactly once.

Runs, all on TEST (2024-01-01 -> 2026-10-01):
  * the TRAIN-selected variant `tv_p20_r10`, net of 21.92 bps   (headline)
  * the same variant with slippage set to 0 (11.92 bps)        (cost decomposition)
  * buy-and-hold over the identical window                      (market bar)
  * 20 random-signal controls matched on TRAIN %-long           (coin-flip bar)
  * nsealgo `build_composite_score` on the same panel            (repo bar)

The random controls take their %-long rate from TRAIN and apply that fixed rate to
TEST, so TEST never informs the controls' own calibration.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_trendvol")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    COST,
    COST_ZERO_SLIP,
    PORT,
    SCRATCH,
    TEST,
    TRAIN,
    VARIANTS,
    buy_and_hold,
    fmt_table,
    gated_momentum_score,
    load_panel,
    load_vol,
    metrics_row,
    run_backtest,
    save_json,
    signal_liveness,
    slice_window,
    trend_volume_signal,
    yearly_str,
)

N_RANDOM = 20


def random_signal_like(sig: pd.DataFrame, p_long: float, seed: int) -> pd.DataFrame:
    """A random panel with the SAME unconditional fraction of bars long as `sig`.

    Drawn i.i.d. Bernoulli(p_long) per symbol-day. Deliberately NOT momentum-correlated:
    if the strategy's value comes from the gate's interaction with momentum ranking, a
    pure coin will miss it. That is exactly the question brief section 6.5 asks.
    """
    rng = np.random.default_rng(seed)
    draw = rng.random(sig.shape) < p_long
    out = pd.DataFrame(0, index=sig.index, columns=sig.columns, dtype=int)
    out[draw] = 1
    return out


def main() -> None:
    panel = load_panel()
    vol = load_vol()
    te_panel = slice_window(panel, TEST)
    te_idx = te_panel.index

    with open(f"{SCRATCH}/results_train.json") as fh:
        train = json.load(fh)
    selected = train["selected"]
    cfg = VARIANTS[selected]
    print(f"TRAIN-selected variant: {selected}  {cfg}")
    print(f"TEST window: {TEST[0]} -> {TEST[1]}  ({len(te_idx)} bars)\n")

    sig = trend_volume_signal(panel, vol, cfg["period"], cfg["vol_ratio"])
    score_full = gated_momentum_score(panel, sig)
    score_te = score_full.reindex(te_idx)

    results = {}

    # ---------------- headline ----------------
    res = run_backtest(te_panel, score_te, COST, PORT)
    head = metrics_row(res, selected)
    head["avg_names_live"] = signal_liveness(sig, TEST)["avg_names_signalled_per_day"]
    head["sym_day_long_frac_TEST"] = signal_liveness(sig, TEST)["sym_day_long_frac"]
    results["strategy"] = head
    print("=== TEST: strategy, net of 21.92 bps ===")
    print(res.summary())
    print(f"  avg names held     : {head['avg_names']:.2f} (of 48 in panel, 22 target)")
    print(f"  signalled per day  : {head['avg_names_live']:.2f}")
    print(f"  sym-day LONG frac  : {head['sym_day_long_frac_TEST'] * 100:.2f}%")
    print(f"  cost drag          : {head['cost_drag_annual'] * 100:.2f}%/yr "
          f"({head['costs_paid']:,.0f} Rs on 21,00,000)")
    print(f"  yearly             : {yearly_str(res.returns)}")

    # ---------------- zero-slippage control ----------------
    res0 = run_backtest(te_panel, score_te, COST_ZERO_SLIP, PORT)
    zero = metrics_row(res0, f"{selected}@zero_slippage")
    results["strategy_zero_slippage"] = zero
    print("\n=== COST DECOMPOSITION ===")
    print(f"  slippage 5bps/side (21.92 bps) : CAGR {head['cagr'] * 100:+.2f}%  "
          f"Sharpe {head['sharpe']:+.2f}  MaxDD {head['max_dd'] * 100:+.2f}%")
    print(f"  slippage 0      (11.92 bps)   : CAGR {zero['cagr'] * 100:+.2f}%  "
          f"Sharpe {zero['sharpe']:+.2f}  MaxDD {zero['max_dd'] * 100:+.2f}%")
    print(f"  => slippage alone costs {(head['cagr'] - zero['cagr']) * 100:+.2f} pct-pts/yr")

    # ---------------- buy and hold ----------------
    bh = buy_and_hold(panel, TEST, COST)
    bh0 = buy_and_hold(panel, TEST, COST_ZERO_SLIP)
    bh["avg_names_live"] = bh["avg_names"]
    results["buy_and_hold"] = bh
    results["buy_and_hold_zero_slippage"] = bh0
    print("\n=== TEST: buy-and-hold (equal weight, 48 names), net of 21.92 bps ===")
    print(f"  CAGR {bh['cagr'] * 100:+.2f}%  Sharpe {bh['sharpe']:+.2f}  "
          f"MaxDD {bh['max_dd'] * 100:+.2f}%  Calmar {bh['calmar']:.2f}")
    print(f"  (at zero slippage: CAGR {bh0['cagr'] * 100:+.2f}%)")

    # ---------------- random controls ----------------
    p_train = signal_liveness(sig, TRAIN)["sym_day_long_frac"]
    rnd_rows = []
    for s in range(N_RANDOM):
        rsig = random_signal_like(sig, p_train, seed=1000 + s)
        rscore = gated_momentum_score(panel, rsig).reindex(te_idx)
        rr = run_backtest(te_panel, rscore, COST, PORT)
        r = metrics_row(rr, f"rand_{s:02d}")
        rnd_rows.append(r)
    results["random_controls"] = rnd_rows
    rc = pd.DataFrame(rnd_rows)
    print(f"\n=== RANDOM-SIGNAL CONTROL (n={N_RANDOM}, %-long={p_train * 100:.2f}% from TRAIN) ===")
    print(f"  strategy CAGR {head['cagr'] * 100:+.2f}%  Sharpe {head['sharpe']:+.2f}")
    print(f"  random   CAGR mean {rc['cagr'].mean() * 100:+.2f}%  "
          f"median {rc['cagr'].median() * 100:+.2f}%  "
          f"[{rc['cagr'].min() * 100:+.2f}%, {rc['cagr'].max() * 100:+.2f}%]")
    print(f"  random   Sharpe mean {rc['sharpe'].mean():+.2f}  "
          f"[{rc['sharpe'].min():+.2f}, {rc['sharpe'].max():+.2f}]")
    beat = int((rc["cagr"] < head["cagr"]).sum())
    beat_s = int((rc["sharpe"] < head["sharpe"]).sum())
    results["random_summary"] = {
        "p_long_from_train": p_train, "n": N_RANDOM,
        "strategy_cagr": head["cagr"], "strategy_sharpe": head["sharpe"],
        "rand_cagr_mean": float(rc["cagr"].mean()),
        "rand_cagr_median": float(rc["cagr"].median()),
        "rand_cagr_min": float(rc["cagr"].min()),
        "rand_cagr_max": float(rc["cagr"].max()),
        "rand_sharpe_mean": float(rc["sharpe"].mean()),
        "n_random_beaten_on_cagr": beat, "n_random_beaten_on_sharpe": beat_s,
        "pct_random_beaten_on_cagr": beat / N_RANDOM,
        "pct_random_beaten_on_sharpe": beat_s / N_RANDOM,
    }
    print(f"  strategy beat {beat}/{N_RANDOM} random controls on CAGR, "
          f"{beat_s}/{N_RANDOM} on Sharpe")

    # ---------------- nsealgo composite ----------------
    from nsealgo.factors.core import build_composite_score

    comp = build_composite_score(te_panel).reindex(te_idx)
    rc_res = run_backtest(te_panel, comp, COST, PORT)
    comp_row = metrics_row(rc_res, "nsealgo_composite")
    results["nsealgo_composite"] = comp_row
    print("\n=== TEST: nsealgo build_composite_score, same panel/costs ===")
    print(f"  CAGR {comp_row['cagr'] * 100:+.2f}%  Sharpe {comp_row['sharpe']:+.2f}  "
          f"MaxDD {comp_row['max_dd'] * 100:+.2f}%  Calmar {comp_row['calmar']:.2f}")

    save_json(results, f"{SCRATCH}/results_test.json")

    print("\n=== HEADLINE TEST TABLE (net of 21.92 bps) ===")
    rows = [head, bh, comp_row]
    print(fmt_table(rows, ["cagr", "sharpe", "max_dd", "calmar", "vol",
                           "annual_turnover", "cost_drag_annual", "avg_names"]))
    print(f"\nwrote {SCRATCH}/results_test.json")


if __name__ == "__main__":
    main()
