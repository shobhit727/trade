"""Step 02 — TRAIN selection. Runs the 5 declared variants and picks one.

TEST is not touched here. Selection rule was fixed in REPORT.md §3 before this ran:
highest TRAIN Sharpe among variants at least 5% live; ties -> Calmar -> ID order.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from common import (
    COSTS,
    ENGINE_SHA,
    HDR,
    buy_and_hold,
    fmt_yearly,
    liveness,
    load_panel,
    mean_names_flagged,
    row,
    run,
    train_panel,
    zscore_score,
)

HERE = Path(__file__).resolve().parent

# Declared budget, REPORT.md §3. Do not add a sixth.
VARIANTS = [
    ("V1", 20, 0.8, "config defaults as advertised"),
    ("V2", 60, 0.8, "one quarter lookback"),
    ("V3", 300, 0.8, "lookback as executed on crypto"),
    ("V4", 60, 1.2, "deeper threshold"),
    ("V5", 60, 0.5, "shallower threshold"),
]

MIN_LIVE = 0.05


def main() -> None:
    panel = load_panel()[0]
    tr = train_panel()
    print(f"engine_sha = {ENGINE_SHA}")
    print(f"TRAIN      = {tr.index[0].date()} .. {tr.index[-1].date()}  ({len(tr):,} bars)")
    print(f"costs      = all_in {COSTS.all_in_round_trip_bps(__import__('decimal').Decimal('100000'))} bps\n")

    rows, records = [], []
    for vid, L, entry, note in VARIANTS:
        score = zscore_score(panel, L, entry)
        res = run(tr, score.loc[tr.index])
        live = liveness(tr, L, entry)
        m = res.metrics
        rows.append(row(vid, m, f"avg_names={res.diag['avg_names']:.1f} live={live * 100:.1f}%"))
        records.append(
            {
                "id": vid, "L": L, "entry": entry, "note": note,
                "sharpe": m.sharpe, "calmar": m.calmar, "cagr": m.cagr,
                "maxdd": m.max_drawdown, "total": m.total_return,
                "live": live, "avg_names": res.diag["avg_names"],
                "turnover": m.annual_turnover, "cost_drag": m.cost_drag_annual,
                "mean_flagged": mean_names_flagged(tr, L, entry),
            }
        )
        print(f"ran {vid}  L={L:>3} entry={entry}  sharpe={m.sharpe:>6.2f} "
              f"cagr={m.cagr * 100:>6.2f}%  maxdd={m.max_drawdown * 100:>6.2f}%  "
              f"avg_names={res.diag['avg_names']:.1f}  live={live * 100:.1f}%")

    print("\n" + HDR)
    for r in rows:
        print(r)

    bh = buy_and_hold(tr, "buy_and_hold TRAIN")
    print("\n" + HDR)
    print(row("BH-TRAIN", bh["metrics"], "equal-weight, 48 names, net"))

    print("\nTRAIN yearly returns (selected-eligible variants):")
    for vid, L, entry, _ in VARIANTS:
        sc = zscore_score(panel, L, entry)
        r = run(tr, sc.loc[tr.index]).returns
        yr = pd.Series((1.0 + r).cumprod().groupby(r.index.year).last().pct_change())
        print(f"  {vid}: {fmt_yearly(yr[1:])}")
    yr_bh = bh["yearly"]
    print(f"  BH : {fmt_yearly(yr_bh[1:])}")

    # ---- selection (rule fixed in advance) ----
    live_ok = [r for r in records if r["live"] >= MIN_LIVE]
    pool = live_ok if live_ok else records
    best = max(pool, key=lambda r: (round(r["sharpe"], 6), round(r["calmar"], 6),))
    tie = [r for r in pool if abs(r["sharpe"] - best["sharpe"]) < 1e-9]
    if len(tie) > 1:
        best = max(tie, key=lambda r: (round(r["calmar"], 6), -int(r["id"][1:])))

    print("\n" + "=" * 78)
    print(f"SELECTED: {best['id']}  L={best['L']} entry={best['entry']}  "
          f"({best['note']})")
    print(f"  rule: highest TRAIN Sharpe with >= {MIN_LIVE:.0%} liveness; "
          f"ties -> Calmar -> ID order")
    print(f"  TRAIN sharpe {best['sharpe']:.2f}  calmar {best['calmar']:.2f}  "
          f"cagr {best['cagr'] * 100:.2f}%  maxdd {best['maxdd'] * 100:.2f}%")
    print("=" * 78)

    (HERE / "selected_variant.json").write_text(
        json.dumps({**best, "engine_sha": ENGINE_SHA, "min_live": MIN_LIVE}, indent=2)
    )
    (HERE / "train_results.json").write_text(json.dumps(records, indent=2))
    print("wrote selected_variant.json, train_results.json")


if __name__ == "__main__":
    main()
