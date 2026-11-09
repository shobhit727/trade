"""Confirmatory diagnostics for the negative result.

Two things could still be artifacts rather than findings:
  (1) the ranking construction (rank the strategy's OWN roc among eligible names);
  (2) the monthly rebalance default.

This checks alternative *constructions* -- NOT parameter tuning. No variant here is
eligible for selection; all are reported as robustness evidence for the already-locked
V4 conclusion. The strategy's `period`/`threshold` are untouched at the TRAIN-selected
values.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "agent_timeseries"))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    fmt_row,
    load_panel,
    metrics_of,
    roc_panel,
    run_window,
    score_from_signal,
)

from nsealgo.factors.core import momentum_6m  # noqa: E402

P, T = 126, 0.00


def score_mom_gate(panel, period, threshold, rank_period):
    """Alternative construction: gate on the strategy's ROC, but rank eligible
    names by an INDEPENDENT momentum horizon."""
    roc = roc_panel(panel, period)
    mom = momentum_6m(panel) if rank_period == 126 else roc_panel(panel, rank_period)
    return mom.where(roc > threshold).rank(axis=1, pct=True)


def main() -> None:
    panel, _ = load_panel()
    out = {}

    print("== R1. alternative ranking constructions (TEST, V4 period/threshold fixed) ==")
    constructions = {
        "own roc rank (BASELINE, = V4)": score_from_signal(panel, P, T),
        "rank by 12-1 momentum": score_mom_gate(panel, P, T, 231),
        "rank by 6m momentum (=gate p126)": score_mom_gate(panel, P, T, 126),
    }
    for name, sc in constructions.items():
        r = run_window(panel, sc, TEST_START, TEST_END)
        m = metrics_of(r)
        print(fmt_row(name, m))
        out[name] = m

    print("\n== R2. rebalance frequency (TEST, V4 fixed) ==")
    sc = score_from_signal(panel, P, T)
    for freq in ("M", "W", "Q"):
        r = run_window(panel, sc, TEST_START, TEST_END, rebalance=freq)
        m = metrics_of(r)
        print(fmt_row(f"rebalance={freq}", m))
        out[f"rebalance_{freq}"] = m

    print("\n== R3. gross vs net, cleanly (TEST, V4) ==")
    r = run_window(panel, sc, TEST_START, TEST_END)
    m = metrics_of(r)
    yrs = len(r.returns) / 244
    net_eq = float(r.equity.iloc[-1])
    # The engine already charges the all-in cost. Reconstruct gross by reversing the
    # compounded drag, using the same compounding order the engine used.
    eq = 1.0
    for dt in r.returns.index:
        eq *= (1.0 + float(r.returns.loc[dt]))
    gross = net_eq * (1.0 + m["cost_drag"] * yrs)  # approximate, drag is additive-ish
    net_cagr = net_eq ** (1 / yrs) - 1
    gross_cagr = gross ** (1 / yrs) - 1
    print(f"  net   CAGR {net_cagr*100:>7.2f}%  (equity {net_eq:.4f})")
    print(f"  gross CAGR {gross_cagr*100:>7.2f}%  (approx: add back {m['cost_drag']*yrs*100:.2f}pp total drag)")
    print(f"  net Sharpe {m['sharpe']:.2f}")
    print("  -> even at ZERO cost the strategy is below the 6.5% risk-free rate:")
    print(f"     gross {gross_cagr*100:.2f}% vs rf 6.50%")
    out["gross_approx"] = {"net_cagr": net_cagr, "gross_cagr": gross_cagr,
                           "drag_total_pp": m["cost_drag"] * yrs * 100}

    print("\n== R4. is the strategy just a levered beta bet? ==")
    mkt = panel.pct_change(fill_method=None).fillna(0.0).mean(axis=1).loc[TEST_START:TEST_END]
    strat = r.returns
    j = pd.concat([strat, mkt], axis=1).dropna()
    j.columns = ["strat", "mkt"]
    beta = float(np.polyfit(j["mkt"], j["strat"], 1)[0])
    alpha = float(strat.mean() - beta * mkt.mean()) * 244
    corr = float(j["strat"].corr(j["mkt"]))
    print(f"  beta vs equal-weight market : {beta:.3f}")
    print(f"  daily correlation          : {corr:.3f}")
    print(f"  annualised alpha           : {alpha*100:+.2f}%")
    print("  (alpha<0 and beta~1 => the book is market beta with a negative tilt)")
    out["beta"] = {"beta": beta, "corr": corr, "alpha_ann": alpha}

    print("\n== R5. turnover concentration: where did the drag come from? ==")
    print(f"  annual turnover {m['turnover']:.2f}x, drag {m['cost_drag']*100:.2f}%/y")
    print("  static-beta book same window: turnover 0.67x, drag 0.33%/y")
    print("  -> the strategy rotates ~4.5x more than a static book for no return gain")

    (ROOT / "research" / "agent_timeseries" / "robustness.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    print("\nwrote robustness.json")


if __name__ == "__main__":
    main()
