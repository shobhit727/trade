"""STEP 3 — ABLATION & GATE DIAGNOSTICS on TEST.

The strategy beat buy-and-hold by only +0.7 pp on TEST. Before reporting that, I need
to know WHERE the return came from. Three candidates:

  A. the cross-sectional 252d momentum ranking   (alpha)
  B. the absolute-momentum gate (roc > 0)       (the strategy's actual idea)
  C. plain long-only beta                       (just being invested)

Ablations run on TEST with the SAME period (252) and SAME costs. These are not
parameter variants — they are diagnostics, not candidates for selection, and the
selected variant is unchanged.

  R_no_gate      : rank all 48 names by 252d ROC, no sign filter
  R_gate_only    : gate on roc>0 but rank randomly among survivors (isolates the gate)
  G_gate_rank    : the real strategy
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (  # noqa: E402
    TEST_END,
    TEST_START,
    VARIANTS,
    buy_and_hold,
    cost_model,
    load,
    portfolio_config,
    roc_panel,
    run_backtest,
    window,
    yearly_returns,
)

OUT = Path(__file__).resolve().parent
N_SEEDS = 60


def beta_stats(daily: pd.Series, mkt: pd.Series) -> tuple[float, float, float]:
    """(beta, alpha_ann, corr) of the daily return series vs the equal-weight market."""
    d = pd.concat([daily, mkt], axis=1).dropna()
    d.columns = ["s", "m"]
    cov = float(d["s"].cov(d["m"]))
    var = float(d["m"].var())
    beta = cov / var if var > 0 else 0.0
    alpha = float(d["s"].mean() - beta * d["m"].mean()) * 244
    corr = float(d["s"].corr(d["m"]))
    return beta, alpha, corr


def main() -> None:
    panel, symbols, _ = load()
    selected = (OUT / "selected_variant.txt").read_text().strip()
    v = next(x for x in VARIANTS if x.name == selected)
    te = window(panel, TEST_START, TEST_END)
    cost, cfg = cost_model(), portfolio_config()

    roc = roc_panel(panel, v.period)
    gate = roc.where(roc > v.threshold)

    # A: cross-sectional ranking, no absolute-momentum gate
    score_no_gate = roc.rank(axis=1, pct=True)
    # B: gate on, but the "ranking" carries no momentum information
    rng = np.random.default_rng(12345)
    noise = pd.DataFrame(rng.random(gate.shape), index=gate.index, columns=gate.columns)
    noise_rank = noise.where(gate.notna()).rank(axis=1, pct=True)

    mkt = te.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    bh = buy_and_hold(panel, cost, TEST_START, TEST_END)

    books = {
        "GATE+RANK (selected)": gate.rank(axis=1, pct=True).reindex(te.index),
        "RANK only (no gate)": score_no_gate.reindex(te.index),
        "GATE only (random rank)": noise_rank.reindex(te.index),
        "BUY-AND-HOLD": None,
    }

    print("=" * 96)
    print(f"ABLATION on TEST 2024-01-01 -> 2026-10-01  (period={v.period}, same costs)")
    print("=" * 96)
    print(f"{'book':<24} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} "
          f"{'beta':>6} {'alpha/y':>9} {'corr':>6} {'turn':>6}")

    results = {}
    for label, sc in books.items():
        if sc is None:
            r = bh
            m = r["metrics"]
            b, a, c = beta_stats(r["returns"], mkt)
            turn = m.annual_turnover
        else:
            r = run_backtest(te, sc, cost, cfg, rebalance="M")
            m = r.metrics
            b, a, c = beta_stats(r.returns, mkt)
            turn = m.annual_turnover
        results[label] = m
        print(f"{label:<24} {m.cagr * 100:>7.2f}% {m.sharpe:>7.2f} "
              f"{m.max_drawdown * 100:>7.2f}% {m.calmar:>7.2f} "
              f"{b:>6.2f} {a * 100:>8.2f}% {c:>6.2f} {turn:>5.2f}x")

    sel = results["GATE+RANK (selected)"]
    ngt = results["RANK only (no gate)"]
    gat = results["GATE only (random rank)"]

    print("\nAttribution on TEST:")
    print(f"  A. cross-sectional 252d momentum RANKING contributes "
          f"{(sel.cagr - gat.cagr) * 100:+.2f} pp/yr "
          f"(gate+rank {sel.cagr * 100:.2f}% vs gate+random {gat.cagr * 100:.2f}%)")
    print(f"  B. the absolute-momentum GATE contributes "
          f"{(sel.cagr - ngt.cagr) * 100:+.2f} pp/yr "
          f"(gate+rank {sel.cagr * 100:.2f}% vs rank-only {ngt.cagr * 100:.2f}%)")
    print(f"  C. beta: strategy beta {beta_stats(run_backtest(te, gate.rank(axis=1, pct=True).reindex(te.index), cost, cfg).returns, mkt)[0]:.2f}, "
          f"annual alpha {beta_stats(run_backtest(te, gate.rank(axis=1, pct=True).reindex(te.index), cost, cfg).returns, mkt)[1] * 100:+.2f}%")

    # ---- TRAIN-side sanity: was the gate useful in-sample at all? ---------
    tr = window(panel, pd.Timestamp("2016-01-01"), pd.Timestamp("2023-12-31"))
    gate_tr = gate.rank(axis=1, pct=True).reindex(tr.index)
    nogate_tr = roc.rank(axis=1, pct=True).reindex(tr.index)
    g = run_backtest(tr, gate_tr, cost, cfg, rebalance="M").metrics
    n = run_backtest(tr, nogate_tr, cost, cfg, rebalance="M").metrics
    print("\nSame ablation on TRAIN (2016-2023), for contrast:")
    print(f"  gate+rank CAGR {g.cagr * 100:.2f}% Sharpe {g.sharpe:.2f} | "
          f"rank-only CAGR {n.cagr * 100:.2f}% Sharpe {n.sharpe:.2f} | "
          f"gate worth {(g.cagr - n.cagr) * 100:+.2f} pp/yr in-sample")

    # ---- GOAL.md §5 gates --------------------------------------------------
    print("\nGOAL.md §5 GATE CHECK on TEST (selected variant):")
    g1 = sel.cagr
    g2 = sel.sharpe
    g3 = float((yearly_returns(run_backtest(te, gate.rank(axis=1, pct=True).reindex(te.index), cost, cfg).returns) > 0).mean())
    print(f"  Gate 1  CAGR >= 3%/mo net  : {g1 * 100:>6.2f}%/yr  "
          f"-> {'PASS' if g1 >= 0.36 else 'FAIL'}")
    print(f"  Gate 2  Sharpe >= 1.0      : {g2:>6.2f}     "
          f"-> {'PASS' if g2 >= 1.0 else 'FAIL'}")
    print(f"  Gate 3  positive >=60% of yr: {g3 * 100:>5.0f}%     "
          f"-> {'PASS' if g3 >= 0.60 else 'FAIL'}")
    print(f"  Gate 4  MaxDD <= 20%        : {sel.max_drawdown * 100:>6.2f}%   "
          f"-> {'PASS' if abs(sel.max_drawdown) <= 0.20 else 'FAIL'}")
    print("  (GOAL.md's 3%/month = 43.3%/yr compounding; the 0.36 test above is the "
          "linear floor and is generous to the strategy.)")


if __name__ == "__main__":
    main()
