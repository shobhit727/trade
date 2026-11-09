"""Step 2 — TEST. Evaluates ONLY the variant frozen in `frozen.txt`, once.

Nothing is selected here. The parameters come from the frozen file written by
step1_train.py; this script never looks at TEST to choose anything.
"""

from __future__ import annotations

import ast

from harness import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    bh_row,
    build_score,
    print_table,
    run_on,
    yearly_returns,
)


def load_frozen() -> tuple[str, dict]:
    with open("frozen.txt") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    label = lines[0]
    params = ast.literal_eval(lines[1])
    return label, params


def main() -> None:
    label, params = load_frozen()
    print("=" * 92)
    print("STEP 2 — TEST (2024-01-01 -> 2026-10-01), frozen variant, evaluated ONCE")
    print("=" * 92)
    print(f"FROZEN LABEL : {label}")
    print(f"FROZEN PARAMS: {params}")

    score = build_score(**params)
    rows = [
        run_on(label, "TEST", score, TEST_START, TEST_END),
        run_on(label, "TRAIN", score, TRAIN_START, TRAIN_END),
        bh_row("TEST_buy_and_hold", "TEST", TEST_START, TEST_END),
        bh_row("TRAIN_buy_and_hold", "TRAIN", TRAIN_START, TRAIN_END),
    ]
    print()
    print_table(rows)

    r = rows[0]
    bh = rows[2]
    # `run_on` returns an equity curve that begins at WARMUP, so its yearly returns
    # span pre-TEST years. Clip to TEST before reporting year-by-year, otherwise a
    # "TEST" table shows 2015-2023 numbers it has no right to show.
    yr_r = yearly_returns(r.returns.loc[TEST_START:])
    yr_b = yearly_returns(bh.returns)
    print("\n--- calendar-year returns, TEST only ---")
    print("  strategy :", {int(k): round(v * 100, 2) for k, v in yr_r.items()})
    print("  buy&hold :", {int(k): round(v * 100, 2) for k, v in yr_b.items()})

    print("\n--- headline comparison, TEST ---")
    print(f"  CAGR     {r.cagr * 100:7.2f}%  vs buy&hold {bh.cagr * 100:7.2f}%   "
          f"-> {(r.cagr - bh.cagr) * 100:+.2f} pp/yr")
    print(f"  Sharpe   {r.sharpe:7.2f}   vs buy&hold {bh.sharpe:7.2f}   -> {r.sharpe - bh.sharpe:+.2f}")
    print(f"  MaxDD    {r.maxdd * 100:7.2f}%  vs buy&hold {bh.maxdd * 100:7.2f}%  "
          f"-> {'shallower' if r.maxdd > bh.maxdd else 'DEEPER'} by {abs(r.maxdd - bh.maxdd) * 100:.2f} pp")
    print(f"  Calmar   {r.calmar:7.2f}   vs buy&hold {bh.calmar:7.2f}")
    print(f"  cost/y   {r.cost_drag * 100:7.2f}%  vs buy&hold {bh.cost_drag * 100:7.2f}%")
    print(f"  names    {r.avg_names:7.1f}   vs buy&hold {bh.avg_names:7.1f}")
    print(f"  engine_sha {r.engine_sha}")

    # Gross vs net on the SAME eval window, using the same warmup-then-slice path.
    print("\n--- cost drag: gross (zero-cost) vs net (21.92bps), TEST window ---")
    from harness import COST_MODEL

    g = run_on(label + "_GROSS", "TEST", score, TEST_START, TEST_END,
               config=None, cost_model=COST_MODEL.__class__(segment="delivery", slippage_bps=0))
    n = rows[0]
    print(f"  gross CAGR {g.cagr * 100:6.2f}%   net CAGR {n.cagr * 100:6.2f}%   "
          f"drag {(g.cagr - n.cagr) * 100:.2f} pp/yr")
    print(f"  gross Sharpe {g.sharpe:.2f}  net Sharpe {n.sharpe:.2f}")
    print(f"  gross MaxDD {g.maxdd * 100:.2f}%  net MaxDD {n.maxdd * 100:.2f}%")
    print(f"  gross cost/y {g.cost_drag * 100:.2f}%  net cost/y {n.cost_drag * 100:.2f}%")

    print("\n--- engine diagnostics ---")
    for k in ("turnover_reconciles_with_engine", "engine_annual_turnover_full_span",
              "recon_annual_turnover_full_span", "round_trip_bps", "n_rebalances",
              "avg_names", "avg_top_weight"):
        print(f"  {k:<34} {n.diag.get(k)}")


if __name__ == "__main__":
    main()
