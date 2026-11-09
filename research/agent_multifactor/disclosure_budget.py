"""DISCLOSURE diagnostic — not a strategy variant, not a selection.

`AGENT_BRIEF.md` §4 caps parameter variants of the STRATEGY at 5. This script
changes `PortfolioConfig.turnover_budget`, which is a portfolio/harness setting,
in order to attribute how much of the TEST result is strategy alpha versus the
engine defect documented in REPORT.md §5.

The headline TEST number is V5 at PortfolioConfig() defaults and is unchanged by
anything here. This is reported for attribution only.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_multifactor")

from harness import (  # noqa: E402
    CM,
    PANEL,
    TEST,
    TRAIN,
    PortfolioConfig,
    run_backtest,
    score_variant,
    window_metrics,
)

from nsealgo.factors.core import build_composite_score  # noqa: E402

SELECTED = dict(period=20, rsip=21, rank_days=126, fill=False)
sc = score_variant(PANEL, **SELECTED)
COMP = build_composite_score(PANEL)

print("Attribution: default budget=0.35 (MANDATED, = headline) vs budget=1.0 (diagnostic)\n")
for wname, window in (("TRAIN", TRAIN), ("TEST", TEST)):
    print(f"{wname}")
    for label, s in (("V5", sc), ("composite", COMP)):
        for budget in (0.35, 1.0):
            cfg = PortfolioConfig(turnover_budget=budget)
            res = run_backtest(PANEL, s, CM, cfg, rebalance="M")
            m = window_metrics(res, *window)
            inv = res.weights.loc[window[0]:window[1]].sum(axis=1).mean()
            m["avg_names"] = inv  # reuse slot to print invested fraction
            print(
                f"  {label:<10} budget={budget:<5} "
                f"CAGR {m['cagr']*100:>6.2f}%  Sharpe {m['sharpe']:>6.2f}  "
                f"MaxDD {m['max_drawdown']*100:>7.2f}%  Turn {m['annual_turnover']:>4.2f}x/y  "
                f"invested {inv:.3f}"
            )
    print()

res = run_backtest(PANEL, sc, CM, PortfolioConfig(), rebalance="M")
m = window_metrics(res, *TEST)
print(f"\nHEADLINE (unchanged): V5 TEST @ PortfolioConfig() defaults -> "
      f"CAGR {m['cagr']*100:.2f}%  Sharpe {m['sharpe']:.2f}  "
      f"MaxDD {m['max_drawdown']*100:.2f}%")
