"""Port validation + TRAIN-only variant selection.

Step 1 validates the vectorised signal against the catalog's scalar loop (random
symbol/date draws, both legs) so we know the port is faithful before trusting any number.
Step 2 runs the 5 DECLARED variants on TRAIN only and applies the pre-declared
selection rule (highest TRAIN Sharpe, ties -> lower TRAIN MaxDD).

TEST is not touched in this file.
"""

from __future__ import annotations

import random
import sys

sys.path.insert(0, "research/agent_trendvol")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    COST,
    PORT,
    SCRATCH,
    TEST,
    TRAIN,
    VARIANTS,
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
)  # noqa: E402


def validate_port(close: pd.DataFrame, vol: pd.DataFrame, n_draw: int = 4000) -> dict:
    """Compare the vectorised signal to the catalog's scalar loop, bar by bar.

    The catalog computes on a growing prefix; we reproduce exactly that (closes[:i+1],
    volumes[:i+1]) so the comparison is apples-to-apples, not a shortcut.
    """
    rng = random.Random(20261011)
    cols = list(close.columns)
    mismatches = []
    n_tested = 0
    for _ in range(n_draw):
        c = rng.choice(cols)
        p = rng.choice([20, 60, 120])
        vr = rng.choice([1.0, 1.2])
        i = rng.randrange(400, len(close))
        d = close.index[i]
        cs = close[c].iloc[: i + 1].to_numpy()
        vs = vol[c].iloc[: i + 1].to_numpy()
        if np.isnan(cs[-1]) or np.isnan(vs[-1]) or len(vs) < p:
            continue
        # --- catalog scalar semantics, transcribed verbatim ---
        t = float(np.mean(cs[-p:])) if len(cs) >= p else float("nan")
        if t != t or len(vs) < p:
            expected = 0
        else:
            avg = float(np.sum(vs[-p:]) / p)
            if cs[-1] > t and vs[-1] > avg * vr:
                expected = 1
            elif cs[-1] < t and vs[-1] > avg * vr:
                expected = -1
            else:
                expected = 0
        sig = trend_volume_signal(close[[c]], vol[[c]], p, vr)[c].iloc[i]
        n_tested += 1
        if int(sig) != expected:
            mismatches.append((c, str(d.date()), p, vr, int(sig), expected))
    return {"n_tested": n_tested, "n_mismatch": len(mismatches),
            "examples": mismatches[:5]}


def main() -> None:
    panel = load_panel()
    vol = load_vol()
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")

    # ---------------- Step 1: port validation ----------------
    port = validate_port(panel, vol)
    print("\n=== PORT VALIDATION (vectorised vs catalog scalar loop) ===")
    print(f"tested {port['n_tested']} random symbol/date/param draws, "
          f"mismatches = {port['n_mismatch']}")
    if port["n_mismatch"]:
        for e in port["examples"]:
            print("  MISMATCH", e)
        raise SystemExit("FATAL: vectorised port does not match the catalog source")
    print("  OK - port is faithful")

    # ---------------- Step 2: TRAIN selection ----------------
    tr_panel = slice_window(panel, TRAIN)
    rows, live, sig_cache = [], {}, {}

    print("\n=== SIGNAL LIVENESS (full history and both windows) ===")
    print(f"{'variant':<14}{'sym-day LONG':>14}{'avg names/day':>15}"
          f"{'median':>9}{'% days 0 sig':>15}{'% days <5 sig':>15}")
    for vid, cfg in VARIANTS.items():
        sig = trend_volume_signal(panel, vol, cfg["period"], cfg["vol_ratio"])
        sig_cache[vid] = sig
        lf = signal_liveness(sig, TRAIN)
        live[vid] = {
            "TRAIN": lf,
            "TEST": signal_liveness(sig, TEST),
            "FULL": signal_liveness(sig, (str(panel.index[0].date()), str(panel.index[-1].date()))),
        }
        print(f"{vid:<14}{lf['sym_day_long_frac'] * 100:>13.2f}%"
              f"{lf['avg_names_signalled_per_day']:>15.2f}"
              f"{lf['median_names_signalled_per_day']:>9.1f}"
              f"{lf['pct_days_with_zero_signals'] * 100:>14.2f}%"
              f"{lf['pct_days_under_5_signals'] * 100:>14.2f}%")

    print("\n=== TRAIN (2016-01-01 -> 2023-12-31), net of 21.92 bps ===")
    for vid, cfg in VARIANTS.items():
        sig = sig_cache[vid]
        score = gated_momentum_score(panel, sig)
        score_tr = score.reindex(tr_panel.index)
        res = run_backtest(tr_panel, score_tr, COST, PORT)
        r = metrics_row(res, vid)
        r["period"] = cfg["period"]
        r["vol_ratio"] = cfg["vol_ratio"]
        rows.append(r)

    print(fmt_table(rows, ["cagr", "sharpe", "max_dd", "calmar",
                           "annual_turnover", "cost_drag_annual", "avg_names"]))
    print("\n(all costs as decimals of annual equity: cagr 0.15 = 15%/yr, "
          "cost_drag 0.01 = 1%/yr)")

    # Pre-declared selection rule: highest Sharpe, ties -> lower MaxDD.
    best = sorted(rows, key=lambda r: (-r["sharpe"], r["max_dd"]))[0]
    print(f"\nSELECTED ON TRAIN (rule: max Sharpe, tie->min |MaxDD|): {best['label']}")

    save_json({"rows": rows, "selected": best["label"], "liveness": live,
               "port_validation": port,
               "selection_rule": "max TRAIN Sharpe, tie -> min TRAIN |MaxDD|"},
              f"{SCRATCH}/results_train.json")
    print(f"wrote {SCRATCH}/results_train.json")
    print("\nTEST remains untouched. Next: 02_test_eval.py runs ONLY the selected variant.")


if __name__ == "__main__":
    main()
