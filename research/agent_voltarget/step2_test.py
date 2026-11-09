"""Step 2 — TEST, run ONCE on the frozen variant.

Reads `frozen.txt` (written by step1_train.py from TRAIN Sharpe alone) and reports
TEST metrics against buy-and-hold over the identical window and the nsealgo
composite. No parameter is chosen here.
"""

from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "research/agent_voltarget")

from harness import (  # noqa: E402
    HDR,
    TEST_END,
    TEST_START,
    VARIANTS,
    assert_engine_pinned,
    bh_row,
    build_score,
    buy_and_hold,
    composite_score,
    line,
    load_panel,
    row_of,
    run,
    source_flag,
    vol_regime,
)


def main() -> None:
    assert_engine_pinned()
    with open("research/agent_voltarget/frozen.txt") as f:
        frozen = f.read().strip()
    assert frozen in VARIANTS, f"frozen variant {frozen!r} not in declared budget"

    panel, _ = load_panel()
    print("=" * 92)
    print(f"STEP 2 — TEST (2024-01-01 -> 2026-10-01). Frozen variant: {frozen}")
    print("This is the first and only time TEST is read for performance.")
    print("=" * 92)
    n = len(panel.loc[TEST_START:TEST_END])
    print(f"bars in TEST: {n}  (~{n / 244:.2f} years)")
    print()

    score = build_score(frozen, panel)
    res = run(panel, score, TEST_START, TEST_END)
    strat = row_of(frozen, "TEST", res)
    print(line(strat))
    print(line(bh_row("TEST buy-and-hold", "TEST", panel, TEST_START, TEST_END)))
    comp = run(panel, composite_score(panel), TEST_START, TEST_END)
    print(line(row_of("nsealgo composite", "TEST", comp)))
    print()
    print(HDR)
    print()

    b = bh_row("TEST buy-and-hold", "TEST", panel, TEST_START, TEST_END)
    print(f"vs buy-and-hold  return {strat.cagr * 100 - b.cagr * 100:+.2f}pp/yr   "
          f"drawdown {strat.maxdd * 100 - b.maxdd * 100:+.2f}pp   "
          f"Sharpe {strat.sharpe - b.sharpe:+.2f}")
    c = row_of("nsealgo composite", "TEST", comp)
    print(f"vs composite     return {strat.cagr * 100 - c.cagr * 100:+.2f}pp/yr   "
          f"drawdown {strat.maxdd * 100 - c.maxdd * 100:+.2f}pp   "
          f"Sharpe {strat.sharpe - c.sharpe:+.2f}")
    print()

    # yearly
    from nsealgo.backtest.metrics import yearly_returns

    ys = yearly_returns(res.returns)
    bhe = buy_and_hold(panel, TEST_START, TEST_END)["equity"]
    ybh = yearly_returns(bhe.pct_change(fill_method=None).fillna(0.0))
    ycomp = yearly_returns(comp.returns)
    print("year-by-year (2026 partial, through 2026-10-01):")
    print(f"  {'year':<8}{'strategy':>12}{'buy-hold':>12}{'composite':>12}")
    for y in sorted(set(ys.index)):
        print(f"  {y:<8}{ys.get(y, np.nan) * 100:>11.2f}%{ybh.get(y, np.nan) * 100:>11.2f}%"
              f"{ycomp.get(y, np.nan) * 100:>11.2f}%")
    print()

    print(f"avg names held {strat.avg_names:.1f}   max top weight "
          f"{res.diag['avg_top_weight'] * 100:.2f}% (cap 12%)")
    print(f"rebalances {res.diag['n_rebalances']:.0f}")

    # Liveness must describe the FROZEN variant's own eligibility mask, not the
    # default two-part flag -- V4 drops the direction half and uses a 2% threshold,
    # so reporting `source_flag` here would misdescribe what the book actually held.
    if frozen.startswith("V5"):
        elig = source_flag(panel, thresh=0.03)
    elif frozen.startswith("V4"):
        elig = vol_regime(panel, 0.02)
    else:
        elig = source_flag(panel)
    elig = elig.loc[TEST_START:TEST_END]
    print(f"signal liveness ({frozen} eligibility mask): active on "
          f"{np.nanmean(elig.to_numpy()) * 100:.2f}% of name-days; "
          f"median eligible names/bar {elig.sum(axis=1).median():.0f}")
    cnt = elig.sum(axis=1)
    print(f"  bars with >=22 eligible: {(cnt >= 22).mean() * 100:.1f}%  "
          f"bars with 0 eligible: {(cnt == 0).mean() * 100:.1f}%")

    out = dict(
        frozen=frozen,
        test_bars=n,
        strategy=dict(
            cagr=strat.cagr, sharpe=strat.sharpe, maxdd=strat.maxdd,
            calmar=strat.calmar, turnover=strat.turnover,
            cost_drag=strat.cost_drag, avg_names=strat.avg_names,
            total=strat.total,
        ),
        buyhold=dict(
            cagr=b.cagr, sharpe=b.sharpe, maxdd=b.maxdd, total=b.total,
        ),
        composite=dict(cagr=c.cagr, sharpe=c.sharpe, maxdd=c.maxdd),
        yearly={str(y): float(ys.get(y, np.nan)) for y in ys.index},
        yearly_bh={str(y): float(ybh.get(y, np.nan)) for y in ybh.index},
        yearly_comp={str(y): float(ycomp.get(y, np.nan)) for y in ycomp.index},
    )
    with open("research/agent_voltarget/test_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote test_results.json")


if __name__ == "__main__":
    main()
