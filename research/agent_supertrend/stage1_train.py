"""Stage 1 — TRAIN sweep over the 5 declared variants. TEST is NOT touched.

Selection rule, fixed in advance (REPORT.md §0.5): highest TRAIN Sharpe, net of costs.
Ties broken by TRAIN Calmar. Costs are charged by `run_backtest` at
`all_in_round_trip_bps(100_000)` = 21.92 bps; nothing here is gross.

This script never reads, slices or prints any TEST-window price. The price panel it
loads is sliced to TRAIN *before* the backtest call, and every figure printed is TRAIN.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TRAIN_END,
    TRAIN_START,
    as_shipped_signal,
    buy_and_hold,
    fmt_row,
    load_ohlc,
    momentum_score,
    run,
    summarise,
    supertrend_signal,
    window,
)

HERE = Path(__file__).resolve().parent

#: The declared budget. Exactly five entries; REPORT.md §0.5 is the pre-registration.
VARIANTS = [
    ("V0", "as_shipped", None, None),
    ("V1", "st_p10_m3.0", 10, 3.0),
    ("V2", "st_p14_m3.0", 14, 3.0),
    ("V3", "st_p10_m2.0", 10, 2.0),
    ("V4", "st_p20_m3.0", 20, 3.0),
]


def build_signal(close, high, low, period, mult):
    if period is None:
        return as_shipped_signal(close)
    return supertrend_signal(close, high, low, period, mult)


def main():
    close, high, low = load_ohlc()
    print("=" * 96)
    print("STAGE 1 — TRAIN ONLY  (2016-01-01 .. 2023-12-31)")
    print("TEST window 2024-01-01 .. 2026-10-01 is NOT read by this script.")
    print("=" * 96)

    rows = []
    for vid, name, period, mult in VARIANTS:
        sig = build_signal(close, high, low, period, mult)
        # Score is built on FULL history then sliced, so TRAIN does not open with a
        # synthetic 126-day warm-up hole (see common.run docstring).
        score = momentum_score(close, sig)
        res = run(close, score, TRAIN_START, TRAIN_END)
        row = summarise(res, close, name)
        row.update(variant=vid, period=period, multiplier=mult)

        # Liveness + eligibility measured on TRAIN only.
        s_tr = window(sig, TRAIN_START, TRAIN_END)
        row["live_frac_train"] = float((s_tr > 0).to_numpy().mean())
        elig = s_tr.where(s_tr > 0).notna().sum(axis=1)
        row["avg_eligible_train"] = float(elig.mean())
        row["max_weight_breach"] = float(res.weights.max().max())

        rows.append(row)
        print(f"  [{vid}] " + fmt_row(row)
              + f"  live={row['live_frac_train'] * 100:.1f}%"
              + f"  elig={row['avg_eligible_train']:.1f}")

    bench = buy_and_hold(close, TRAIN_START, TRAIN_END)
    bench.pop("returns", None)
    print("  [B/H] " + fmt_row(bench))

    # ---- selection: best TRAIN Sharpe, tie-break Calmar
    ranked = sorted(rows, key=lambda r: (-r["sharpe"], -r["calmar"]))
    winner = ranked[0]
    print("\n" + "-" * 96)
    print("TRAIN ranking (by Sharpe):")
    for r in ranked:
        print(f"  {r['variant']} {r['label']:<16} Sharpe {r['sharpe']:>6.3f}  "
              f"CAGR {r['cagr'] * 100:>7.2f}%  MaxDD {r['max_drawdown'] * 100:>7.2f}%")
    print(f"\nSELECTED (TRAIN): {winner['variant']} {winner['label']}")

    # ---- brief §6 sanity checks on the selected variant
    print("\n" + "-" * 96)
    print("SANITY CHECKS on selected variant (brief §6):")
    print(f"  §6.1 plausibility  CAGR {winner['cagr'] * 100:.2f}%  "
          f"(unlevered long-only NIFTY-50 should be << 100%)")
    print(f"  §6.2 weight count  avg names {winner['avg_names']:.1f}  "
          f"max names {winner['max_names']}  avg invested {winner['avg_invested']:.3f}")
    print(f"  §6.3 liveness      {winner['live_frac_train'] * 100:.1f}% of bars long "
          f"(floor is 5%)")
    print(f"  §6.4 cost drag     gross CAGR {winner['gross_cagr'] * 100:.2f}% -> net "
          f"{winner['cagr'] * 100:.2f}%  ({winner['cost_drag'] * 100:.2f}%/yr)")
    print(f"  caps               max single weight {winner['max_weight_breach']:.4f} "
          f"(cap 0.12)")
    print(f"  round-trip charged {winner['round_trip_bps']:.2f} bps (all-in)")

    out = {
        "window": [str(TRAIN_START.date()), str(TRAIN_END.date())],
        "variants": rows,
        "buy_and_hold": bench,
        "selected": winner,
        "selection_rule": "max TRAIN Sharpe, tie-break TRAIN Calmar",
        "n_variants": len(rows),
    }
    (HERE / "stage1_train.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {HERE / 'stage1_train.json'}")


if __name__ == "__main__":
    main()
