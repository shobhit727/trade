# DECLARED PARAMETER BUDGET — written BEFORE any variant was run.
"""
`research/AGENT_BRIEF.md` §4: at most 5 distinct parameter variants, chosen on
TRAIN only. This list is the whole budget. Nothing else gets evaluated.

| # | name  | period | entry | rebalance | rank_by   | note                                |
|---|-------|--------|-------|-----------|-----------|-------------------------------------|
| V1 | base  | 20     | 100   | M         | mom126    | catalog defaults, brief's construction|
| V2 | tight | 20     | 150   | M         | mom126    | stricter oversold filter            |
| V3 | week  | 20     | 100   | W         | mom126    | rebalance matched to signal horizon |
| V4 | fast  | 10     | 100   | M         | mom126    | shorter CCI window                  |
| V5 | deep  | 20     | 100   | M         | deepest   | buy most-oversold, not strongest     |

Selection rule, fixed in advance: highest TRAIN Sharpe, ties broken by higher
TRAIN Calmar. The winner is frozen and evaluated on TEST unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    TRAIN_END,
    TRAIN_START,
    build_score,
    cci_panel,
    equal_weight_score,
    header,
    load_panels,
    run_variant,
    signal_panel,
    typical_price,
)

VARIANTS = [
    # name,  period, entry, rebalance, rank_by
    ("V1_base", 20, 100.0, "M", "mom126"),
    ("V2_tight", 20, 150.0, "M", "mom126"),
    ("V3_week", 20, 100.0, "W", "mom126"),
    ("V4_fast", 10, 100.0, "M", "mom126"),
    ("V5_deep", 20, 100.0, "M", "deepest"),
]

p = load_panels()
close = p.close.loc[TRAIN_START:TRAIN_END]
tp = typical_price(p).loc[TRAIN_START:TRAIN_END]

print(header("TRAIN WINDOW 2016-01-01 -> 2023-12-31  (selection window only)"))
print(f"bars={len(close)}  symbols={close.shape[1]}\n")

cci_cache: dict[int, pd.DataFrame] = {}
rows, results = [], {}

for name, period, entry, reb, rank_by in VARIANTS:
    if period not in cci_cache:
        cci_cache[period] = cci_panel(tp, period)
    cci = cci_cache[period]

    # Bar-level long fraction on TRAIN only (brief §6.3 liveness check).
    sig = signal_panel(cci, entry)
    long_frac = float((sig > 0).sum().sum()) / float((~np.isnan(cci)).sum().sum())

    score = build_score(close, cci, entry, rank_by=rank_by)
    r = run_variant(name, close, score, rebalance=reb, long_frac=long_frac)
    results[name] = r
    m = r.metrics
    rows.append(
        {
            "variant": name, "period": period, "entry": entry, "rebal": reb,
            "rank_by": rank_by, "bar_long_frac": long_frac,
            "cagr": m.cagr, "sharpe": m.sharpe, "sortino": m.sortino,
            "calmar": m.calmar, "maxdd": m.max_drawdown,
            "turnover": m.annual_turnover, "cost_drag": m.cost_drag_annual,
            "trades_y": m.trades_per_year, "avg_names": r.avg_names,
            "invested": float(r.returns.shape[0] and np.nan),
        }
    )
    print(
        f"{name:<10} p={period:>3} entry={entry:>5.0f} {reb} {rank_by:<7} "
        f"CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x  Cost {m.cost_drag_annual * 100:>5.2f}%/y  "
        f"Names {r.avg_names:>5.1f}  LongFrac {long_frac * 100:>5.2f}%"
    )

# ---- TRAIN reference points (not variants — comparators) ----
print(header("TRAIN REFERENCE POINTS (comparators, not tuned variants)"))
ew = run_variant("equal_weight_book", close, equal_weight_score(close))
print(
    f"{'equal_weight_book':<10} {'':<28} "
    f"CAGR {ew.metrics.cagr * 100:>7.2f}%  Sharpe {ew.metrics.sharpe:>6.2f}  "
    f"MaxDD {ew.metrics.max_drawdown * 100:>7.2f}%  Calmar {ew.metrics.calmar:>6.2f}  "
    f"Turn {ew.metrics.annual_turnover:>5.2f}x  Names {ew.avg_names:>5.1f}"
)

print(header("SELECTION (TRAIN Sharpe, tie-break Calmar)"))
ranked = sorted(rows, key=lambda r: (-r["sharpe"], -r["calmar"]))
for i, r in enumerate(ranked, 1):
    print(
        f"  {i}. {r['variant']:<10} Sharpe {r['sharpe']:>6.2f}  "
        f"CAGR {r['cagr'] * 100:>7.2f}%  Calmar {r['calmar']:>6.2f}"
    )
winner = ranked[0]["variant"]
print(f"\nWINNER (frozen): {winner}")

with open("TRAIN_RESULTS.txt", "w") as f:
    f.write("TRAIN 2016-01-01 -> 2023-12-31\n")
    for r in rows:
        f.write(
            f"{r['variant']:<10} p={r['period']} entry={r['entry']:.0f} {r['rebal']} "
            f"{r['rank_by']:<7} CAGR {r['cagr'] * 100:7.2f}% Sharpe {r['sharpe']:6.2f} "
            f"MaxDD {r['maxdd'] * 100:7.2f}% Calmar {r['calmar']:6.2f} "
            f"Turn {r['turnover']:.2f}x Cost {r['cost_drag'] * 100:.2f}%/y "
            f"Names {r['avg_names']:.1f} LongFrac {r['bar_long_frac'] * 100:.2f}%\n"
        )
    f.write(
        f"equal_weight_book CAGR {ew.metrics.cagr * 100:.2f}% "
        f"Sharpe {ew.metrics.sharpe:.2f} MaxDD {ew.metrics.max_drawdown * 100:.2f}%\n"
    )
    f.write(f"WINNER {winner}\n")
print("wrote TRAIN_RESULTS.txt")
