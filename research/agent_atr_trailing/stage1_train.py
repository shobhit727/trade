"""STAGE 1 — TRAIN ONLY (2016-01-01 .. 2023-12-31).

Selects among the 5 declared parameter variants. Nothing in this script touches the
TEST window, and nothing here is ever re-run after stage 2.

DECLARED PARAMETER BUDGET (5 variants, fixed before any run):
    V1  period=14  multiplier=2.0   (catalog default)
    V2  period=14  multiplier=1.5
    V3  period=20  multiplier=2.5
    V4  period=55  multiplier=2.0
    V5  period=10  multiplier=3.0

Fixed for every variant: score = cross-sectional rank of 126-day momentum restricted
to names flagged +1; 22 names; 12%/25%/10% caps; 35% turnover budget; monthly
rebalance; full Indian delivery cost stack. Only (period, multiplier) varies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from common import (
    TRAIN_END,
    TRAIN_START,
    atr_trailing_signal,
    buy_and_hold,
    fmt_row,
    load_ohlc,
    momentum_score,
    run,
    summarise,
)

from nsealgo.backtest.metrics import yearly_returns

HERE = Path(__file__).resolve().parent

VARIANTS = [
    ("V1_period14_mult2.0", 14, 2.0),
    ("V2_period14_mult1.5", 14, 1.5),
    ("V3_period20_mult2.5", 20, 2.5),
    ("V4_period55_mult2.0", 55, 2.0),
    ("V5_period10_mult3.0", 10, 3.0),
]


def main() -> None:
    close, high, low = load_ohlc()

    rows, series, chosen, best = [], {}, None, float("-inf")
    for name, period, mult in VARIANTS:
        sig = atr_trailing_signal(close, high, low, period, mult)
        score = momentum_score(close, sig)

        # liveness: fraction of (bar, symbol) pairs flagged +1, plus how many names
        # are eligible on a typical day (book capacity is 22).
        elig = (sig > 0).sum(axis=1)
        elig_nz = elig[elig > 0]
        live_frac = float((sig > 0).to_numpy().mean())

        res = run(close, score, TRAIN_START, TRAIN_END)
        row = summarise(res, close, name)
        row.update({
            "period": period,
            "multiplier": mult,
            "live_frac": live_frac,
            "median_eligible": float(elig_nz.median()) if len(elig_nz) else 0.0,
            "min_eligible": int(elig_nz.min()) if len(elig_nz) else 0,
        })
        rows.append(row)
        series[name] = res.returns
        print(fmt_row(row))
        print(f"{'':<28} period={period:<3} mult={mult:<4} "
              f"live={live_frac * 100:5.1f}%  median_eligible={row['median_eligible']:.0f}"
              f"  min_eligible={row['min_eligible']}")

        if row["sharpe"] > best:
            best, chosen = row["sharpe"], name

    print("\n" + "=" * 118)
    print("TRAIN WINDOW 2016-01-01 .. 2023-12-31 — all costs net (5 bps slippage)")
    print("=" * 118)
    tbl = pd.DataFrame(rows).set_index("label")
    print(tbl[["period", "multiplier", "cagr", "sharpe", "max_drawdown", "calmar",
               "turnover", "cost_drag", "gross_cagr", "avg_names",
               "median_eligible", "live_frac"]].to_string(
        float_format=lambda v: f"{v:.4f}"))

    bench = buy_and_hold(close, TRAIN_START, TRAIN_END)
    print(f"\nTRAIN buy & hold (equal weight, one round trip charged): "
          f"CAGR {bench['cagr'] * 100:.2f}%  Sharpe {bench['sharpe']:.2f}  "
          f"MaxDD {bench['max_drawdown'] * 100:.2f}%")

    y = pd.DataFrame({k: yearly_returns(v) for k, v in series.items()})
    y["EQUAL_WEIGHT"] = yearly_returns(bench["returns"])
    print("\nTRAIN yearly returns (net of costs):")
    print(y.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))

    print(f"\nTRAIN-selected variant: {chosen} (highest TRAIN Sharpe {best:.3f})")

    (HERE / "stage1_train.json").write_text(
        json.dumps({"rows": rows, "selected": chosen, "train_bench": bench},
                   indent=2, default=str)
    )
    print(f"wrote {HERE / 'stage1_train.json'}")


if __name__ == "__main__":
    main()
