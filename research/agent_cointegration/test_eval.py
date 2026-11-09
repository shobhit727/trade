"""TEST-window evaluation. Touched once, AFTER V3 was locked on TRAIN.

Locked on TRAIN: **V3 = window 126, entry 1.0, rule "depth"**
(TRAIN Sharpe 0.454, best of the 5 declared variants; lock written down in REPORT.md
section 7 before this file existed). Nothing below re-tunes anything.

Reported: strategy vs equal-weight buy-and-hold vs the nsealgo composite, all net of
the same Indian delivery stack, on BOTH cost bases (see REPORT.md Bug-3), plus the
liveness-matched random control, yearly returns, cost stress, and the sanity checks
the brief demands (section 6).
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coinlib import (  # noqa: E402
    BASE_COSTS,
    CORRECTED_COSTS,
    TEST_END,
    TEST_START,
    build_score_window,
    buy_and_hold,
    composite_score,
    evaluate,
    fmt,
    panel,
    random_score_like,
)

from nsealgo.backtest.metrics import yearly_returns  # noqa: E402

CHOSEN = dict(window=126, entry=1.0, rule="depth")
OUT = Path(__file__).parent


def main() -> None:
    full = panel()
    te = full.loc[(full.index >= TEST_START) & (full.index <= TEST_END)]
    px, score = build_score_window((TEST_START, TEST_END), CHOSEN["window"],
                                    CHOSEN["entry"], CHOSEN["rule"])
    print(f"TEST window {px.index[0].date()} -> {px.index[-1].date()}  "
          f"{len(px)} bars  {px.shape[1]} symbols")
    print(f"variant (locked on TRAIN, unchanged): {CHOSEN}\n")

    cor = evaluate("cointegration", px, score)                     # headline
    asi = evaluate("cointegration", px, score, cost_model=BASE_COSTS)
    bh = buy_and_hold(px)
    comp = evaluate("composite", px, composite_score(full).loc[px.index])
    randoms = [evaluate(f"random s{s}", px, random_score_like(score, s))
               for s in (1, 2, 3, 4, 5)]

    print("=" * 100)
    print("TEST RESULTS — headline basis CORRECTED (21.92 bps of total turnover)")
    print("=" * 100)
    print(f"{'cointegration V3':<26} {fmt(cor.metrics)}")
    print(f"{'buy-and-hold (EW)':<26} {fmt(bh)}")
    print(f"{'nsealgo composite':<26} {fmt(comp.metrics)}")
    print(f"{'  exposure':<26} coin {cor.diag['avg_exposure'] * 100:.1f}%  "
          f"B&H 100.0%  composite {comp.diag['avg_exposure'] * 100:.1f}%")
    print(f"{'  avg names':<26} coin {cor.diag['avg_names']:.1f}  "
          f"composite {comp.diag['avg_names']:.1f}  B&H {px.shape[1]}")
    print(f"{'  signal liveness':<26} coin {cor.liveness * 100:.2f}% of symbol-bars")

    print(f"\n{'cointegration V3 (as-is costs)':<26} {fmt(asi.metrics)}")
    print(f"{'  -> cost basis gap':<26} "
          f"{(asi.metrics.cagr - cor.metrics.cagr) * 100:+.2f} pp/yr CAGR")

    m, b = cor.metrics, bh
    print("\n" + "-" * 100)
    print("VS BUY-AND-HOLD")
    print(f"  total return : {m.total_return * 100:>8.2f}%  vs {b.total_return * 100:>8.2f}%"
          f"  ({(m.total_return - b.total_return) * 100:+8.2f} pp) -> "
          f"{'BETTER' if m.total_return > b.total_return else 'WORSE'}")
    print(f"  CAGR         : {m.cagr * 100:>8.2f}%  vs {b.cagr * 100:>8.2f}%"
          f"  ({(m.cagr - b.cagr) * 100:+8.2f} pp)")
    print(f"  MaxDD        : {m.max_drawdown * 100:>8.2f}%  vs {b.max_drawdown * 100:>8.2f}%"
          f"  ({(m.max_drawdown - b.max_drawdown) * 100:+8.2f} pp) -> "
          f"{'BETTER (shallower)' if m.max_drawdown > b.max_drawdown else 'WORSE (deeper)'}")
    print(f"  Sharpe       : {m.sharpe:>8.2f}    vs {b.sharpe:>8.2f}")

    # Exposure-matched: the signal is thin, so raw CAGR is not the honest headline.
    e = float(cor.diag["avg_exposure"])
    scaled = cor.returns * (1.0 / e)
    eq_s = (1.0 + scaled).cumprod()
    y = max(len(eq_s) / 244, 1e-9)
    cs = float(eq_s.iloc[-1]) ** (1 / y) - 1
    print("\n  exposure-matched (grossed up to 100% deployed, costs NOT rescaled):")
    print(f"     CAGR {cs * 100:.2f}%  vs B&H {b.cagr * 100:.2f}%  -> "
          f"{'BETTER' if cs > b.cagr else 'WORSE'}")

    print("\n" + "-" * 100)
    print("RANDOM-SIGNAL CONTROL (same % of symbol-bars live, uniform draw)")
    for r in randoms:
        print(f"  {r.label:<12} {fmt(r.metrics)}  names {r.diag['avg_names']:.1f}  "
              f"exp {r.diag['avg_exposure'] * 100:.1f}%")
    rc = np.array([r.metrics.cagr for r in randoms])
    rs = np.array([r.metrics.sharpe for r in randoms])
    beat = m.cagr > rc.max()
    print(f"  random CAGR mean {rc.mean() * 100:.2f}%  sd {rc.std(ddof=1) * 100:.2f}  "
          f"range [{rc.min() * 100:.2f}, {rc.max() * 100:.2f}]")
    print(f"  random Sharpe mean {rs.mean():.2f}  sd {rs.std(ddof=1):.2f}")
    print(f"  strategy CAGR {m.cagr * 100:.2f}%  Sharpe {m.sharpe:.2f} -> "
          f"{'BEATS' if beat else 'does NOT beat'} even the BEST of 5 random seeds")

    print("\n" + "-" * 100)
    print("COST STRESS (V3). CORRECTED_COSTS already charges 21.92 bps of total")
    print("turnover; mult 1.0 is the headline, 0.5 is what the stock engine does.")
    class Stress:
        """Scales the corrected cost basis by a Decimal multiple."""

        def __init__(self, base, mult):
            self.b, self.m = base, Decimal(str(mult))

        def all_in_round_trip_bps(self, n):
            return self.b.all_in_round_trip_bps(n) * self.m

    for label, mult, note in (
        ("2x corrected", 2.0, "43.84 bps of total turnover — Gate 4 style stress"),
        ("corrected", 1.0, "21.92 bps — HEADLINE"),
        ("0.5x (as-is engine)", 0.5, "10.96 bps — what run_backtest really does"),
    ):
        rr = evaluate(label, px, score, cost_model=Stress(CORRECTED_COSTS, mult))
        print(f"  {label:<24} {fmt(rr.metrics)}   {note}")
    zero = type("Z", (), {"all_in_round_trip_bps": lambda self, n: Decimal(0)})()
    zr = evaluate("zero", px, score, cost_model=zero)
    print(f"  {'zero_cost':<24} {fmt(zr.metrics)}   <- gross, memo only")
    print(f"  cost drag {m.cost_drag_annual * 100:.2f}%/y, "
          f"gross-vs-net CAGR gap {(zr.metrics.cagr - m.cagr) * 100:+.2f} pp/yr")
    print(f"  => gross return IS positive ({zr.metrics.cagr * 100:+.2f}%/y) but net is "
          f"{m.cagr * 100:+.2f}%; and gross still loses to buy-and-hold "
          f"{b.cagr * 100:.2f}%/y")

    print("\n" + "-" * 100)
    print("YEARLY RETURNS (TEST)")
    bh_daily = te.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    yv = pd.concat([
        yearly_returns(cor.returns).rename("cointegration").rename_axis("year"),
        yearly_returns(comp.returns).rename("composite").rename_axis("year"),
        yearly_returns(bh_daily.reindex(cor.returns.index)).rename("buy&hold").rename_axis("year"),
    ], axis=1)
    print(yv.to_string(float_format=lambda x: f"{x * 100:>8.2f}%"))
    print(f"positive years — cointegration {(yv['cointegration'] > 0).sum()}/{len(yv)}, "
          f"composite {(yv['composite'] > 0).sum()}/{len(yv)}, "
          f"B&H {(yv['buy&hold'] > 0).sum()}/{len(yv)}")

    print("\n" + "-" * 100)
    print("SANITY CHECKS (brief section 6)")
    print(f"  1. plausibility   : CAGR {m.cagr * 100:.2f}%  "
          f"(long-only unlevered NIFTY-50; 40-50% is the ceiling) -> "
          f"{'OK' if m.cagr < 0.5 else 'IMPLAUSIBLE — INVESTIGATE'}")
    print(f"  2. weight count   : avg names {cor.diag['avg_names']:.1f} "
          f"(cap 22/30; 48 would mean weights accumulating)")
    print(f"  3. signal liveness: {cor.liveness * 100:.2f}% of symbol-bars "
          f"(brief floor 5%) -> "
          f"{'OK' if cor.liveness > 0.05 else 'TOO THIN — effectively always-flat'}")
    print(f"  4. cost drag      : {m.cost_drag_annual * 100:.2f}%/y, "
          f"Rs{cor.costs_paid:,.0f} total over the window")
    print("  5. negative ctrl  : see random control above")

    cor.equity.to_csv(OUT / "_test_equity.csv")
    comp.equity.to_csv(OUT / "_test_equity_composite.csv")
    yv.to_csv(OUT / "_test_yearly.csv")


if __name__ == "__main__":
    main()
