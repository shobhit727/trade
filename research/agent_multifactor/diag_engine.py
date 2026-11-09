"""Is the under-investment caused by MY score panel, or by the engine?

Diagnostic only. Runs on TRAIN. No headline number in REPORT.md uses a modified
PortfolioConfig — this exists to attribute the `cash_buffer` shortfall to a
specific mechanism in `src/nsealgo/backtest/engine.py`.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_multifactor")

import pandas as pd  # noqa: E402
from harness import CM, PANEL, TEST, TRAIN, PortfolioConfig, run_backtest  # noqa: E402

from nsealgo.factors.core import build_composite_score  # noqa: E402

IST = "Asia/Kolkata"


def invested(res) -> pd.Series:
    return res.weights.sum(axis=1)


def report(label: str, score, cfg, window) -> None:
    res = run_backtest(PANEL, score, CM, cfg, rebalance="M")
    inv = invested(res).loc[window[0]:window[1]]
    names = (res.weights.loc[window[0]:window[1]] > 0).sum(axis=1)
    eq = res.equity.loc[window[0]:window[1]]
    cagr = float(eq.iloc[-1] / eq.iloc[0]) ** (244.0 / len(eq)) - 1.0
    print(
        f"  {label:<44} invested {inv.mean():.3f}  cash {1-inv.mean():.3f}  "
        f"names {names.mean():>4.1f}  CAGR {cagr*100:>6.2f}%"
    )


V1 = None
from harness import score_variant  # noqa: E402

V1 = score_variant(PANEL, 20, 14, 126, False)
COMP = build_composite_score(PANEL)
# Near-zero-turnover score: a static, always-equal ranking. If the book STILL
# under-invests with a target that barely changes, the leak is in the engine.
STATIC = pd.DataFrame(1.0, index=PANEL.index, columns=PANEL.columns)

for wname, window in (("TRAIN", TRAIN),):
    print(f"\n{wname} — engine attribution")
    report("V1 score, config defaults (budget=0.35)", V1, PortfolioConfig(), window)
    report("V1 score, budget=1.0 (blend disabled)",
           V1, PortfolioConfig(turnover_budget=1.0), window)
    report("composite score, config defaults", COMP, PortfolioConfig(), window)
    report("composite score, budget=1.0",
           COMP, PortfolioConfig(turnover_budget=1.0), window)
    report("STATIC score (zero turnover), defaults", STATIC, PortfolioConfig(), window)
    report("STATIC score (zero turnover), budget=1.0",
           STATIC, PortfolioConfig(turnover_budget=1.0), window)

print(f"\n{'='*70}")
print("Key question: with a STATIC score there is no turnover to budget, so")
print("lam must be 1 and the book must sit at 0.90. If it does not, _thin() is")
print("leaking weight regardless of the strategy.")
r_static = run_backtest(PANEL, STATIC, CM, PortfolioConfig(turnover_budget=1.0),
                        rebalance="M")
inv = invested(r_static).loc[TRAIN[0]:TRAIN[1]]
print(f"  STATIC+budget1.0 TRAIN invested: mean {inv.mean():.4f} "
      f"min {inv.min():.4f} max {inv.max():.4f}")
print(f"  TEST window declared but not needed for this diagnostic: "
      f"{TEST[0].date()} -> {TEST[1].date()}")
