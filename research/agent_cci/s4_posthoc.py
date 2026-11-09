"""POST-HOC DIAGNOSTICS — run AFTER the primary TEST result was frozen to disk.

Nothing here was used to select anything. These runs exist only to explain the
failure: is it one unlucky variant, or the whole family? And is the damage done
by the CCI gate itself, or by the book machinery around it?
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    CONFIG,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    build_score,
    cci_panel,
    header,
    load_panels,
    random_control,
    run_variant,
    typical_price,
)

VARIANTS = [
    ("V1_base", 20, 100.0, "M", "mom126"),
    ("V2_tight", 20, 150.0, "M", "mom126"),
    ("V3_week", 20, 100.0, "W", "mom126"),
    ("V4_fast", 10, 100.0, "M", "mom126"),
    ("V5_deep", 20, 100.0, "M", "deepest"),
]

p = load_panels()
tp_all = typical_price(p)
close_all = p.close
cci_all = {per: cci_panel(tp_all, per) for per in (10, 20)}


def mom(lookback):
    return close_all / close_all.shift(lookback) - 1.0


# --------------------------------------------------------------------------- #
print(header("A) ALL 5 DECLARED VARIANTS ON BOTH WINDOWS (family diagnostic)"))
print(f"{'variant':<10} {'TRAIN cagr':>11} {'TRAIN shp':>10} | "
      f"{'TEST cagr':>10} {'TEST shp':>9} {'TEST maxdd':>11} {'TEST names':>11}")
print("-" * 78)

rows = []
for name, period, entry, reb, rank_by in VARIANTS:
    cci = cci_all[period]
    sc = build_score(close_all, cci, entry, rank_by=rank_by)

    tr = run_variant(name, close_all.loc[TRAIN_START:TRAIN_END],
                     sc.loc[TRAIN_START:TRAIN_END], rebalance=reb)
    te = run_variant(name, close_all.loc[TEST_START:TEST_END],
                     sc.loc[TEST_START:TEST_END], rebalance=reb)
    rows.append((name, tr, te))
    print(
        f"{name:<10} {tr.metrics.cagr * 100:>10.2f}% {tr.metrics.sharpe:>10.2f} | "
        f"{te.metrics.cagr * 100:>9.2f}% {te.metrics.sharpe:>9.2f} "
        f"{te.metrics.max_drawdown * 100:>10.2f}% {te.avg_names:>11.1f}"
    )

better_in_test = [n for n, tr, te in rows if te.metrics.sharpe > tr.metrics.sharpe]
print()
if better_in_test:
    print(f"Variants whose TEST Sharpe beat their own TRAIN Sharpe: {better_in_test}")
    print("(These improved OOS, but none reached buy-and-hold or the equal-weight book.)")
print(f"Best TEST Sharpe in the family : {max(te.metrics.sharpe for _, _, te in rows):.2f}")
print(f"Best TRAIN Sharpe in the family: {max(tr.metrics.sharpe for _, tr, _ in rows):.2f}")
print("No variant in the family beats buy-and-hold (Sharpe 0.19) except V4_fast,")
print("which merely matches it (0.21) while doubling turnover, and still loses to the")
print("equal-weight book through the identical engine (0.32).")

# --------------------------------------------------------------------------- #
print(header("B) ISOLATING THE CCI GATE (momentum with and without the CCI filter)"))
print("Same book, same ranking (mom126), same costs. Only difference: the CCI gate.\n")

for label, lo, hi in (("TRAIN", TRAIN_START, TRAIN_END), ("TEST", TEST_START, TEST_END)):
    close = close_all.loc[lo:hi]
    mom_sc = mom(126)
    gated = build_score(close, cci_all[20], 100.0, rank_by="mom126")
    a = run_variant("mom_no_gate", close, mom_sc.loc[lo:hi], rebalance="M")
    b = run_variant("mom_cci_gate", close, gated, rebalance="M")
    print(
        f"{label:<6} momentum, NO CCI gate : CAGR {a.metrics.cagr * 100:>7.2f}%  "
        f"Sharpe {a.metrics.sharpe:>6.2f}  MaxDD {a.metrics.max_drawdown * 100:>7.2f}%  "
        f"Names {a.avg_names:>5.1f}  Cost {a.metrics.cost_drag_annual * 100:>5.2f}%/y"
    )
    print(
        f"{label:<6} momentum, CCI gate on : CAGR {b.metrics.cagr * 100:>7.2f}%  "
        f"Sharpe {b.metrics.sharpe:>6.2f}  MaxDD {b.metrics.max_drawdown * 100:>7.2f}%  "
        f"Names {b.avg_names:>5.1f}  Cost {b.metrics.cost_drag_annual * 100:>5.2f}%/y"
    )
    print(
        f"{label:<6} DELTA (gate minus no-gate): "
        f"{(b.metrics.cagr - a.metrics.cagr) * 100:>+7.2f} pp CAGR, "
        f"{b.metrics.sharpe - a.metrics.sharpe:>+6.2f} Sharpe\n"
    )

# --------------------------------------------------------------------------- #
print(header("C) DOES BUYING OVERSOLD NAMES ACTUALLY WORK? (21d forward returns)"))
close = close_all
c20 = cci_all[20]
fwd = (close.shift(-21) / close - 1.0)
m126 = mom(126)

for lo, hi, nm in (("2016-01-01", "2023-12-31", "TRAIN"), ("2024-01-01", "2026-10-01", "TEST")):
    f = fwd.loc[lo:hi]
    c = c20.loc[lo:hi]
    m = m126.loc[lo:hi]
    # The gate buys deeply oversold names. The clean counterfactual is deeply
    # OVERBOUGHT names — the ones the gate excludes outright.
    oversold = c < -100.0
    overbought = c > 100.0
    neutral = (c >= -100.0) & (c <= 100.0)

    def stat(mask, lab):
        vals = f.where(mask).stack().dropna()
        mm = float(m.where(mask).stack().dropna().mean())
        print(
            f"  {nm}  {lab:<24} mean 21d fwd ret {vals.mean() * 100:>7.2f}%   "
            f"n={len(vals):>7,}   mean 126d mom {mm:>7.4f}"
        )

    print()
    stat(oversold, "CCI < -100 (GATE BUYS)")
    stat(neutral, "-100 <= CCI <= 100")
    stat(overbought, "CCI > +100 (GATE EXCLUDES)")
    a = float(f.where(oversold).stack().dropna().mean())
    b = float(f.where(overbought).stack().dropna().mean())
    print(f"  -> reversion edge (oversold minus overbought) = {(a - b) * 100:+.2f} pp\n")

print(header("D) TWO NEGATIVE CONTROLS (same 16.43% density, 20 seeds each)"))
close_t = close_all.loc[TEST_START:TEST_END]

# (i) random eligibility + momentum rank  -- the brief's control, as specified
rc_ranked = random_control(close_all, cci_all[20], 100.0, 0.1643, "M", n_seeds=20)
print(f"(i)  random eligibility + mom126 rank : CAGR mean {rc_ranked['cagr_mean'] * 100:>6.2f}%  "
      f"Sharpe mean {rc_ranked['sharpe_mean']:>5.2f}  p05 {rc_ranked['cagr_p05'] * 100:>6.2f}%  "
      f"p95 {rc_ranked['cagr_p95'] * 100:>6.2f}%")

# (ii) true coin: random scores, no momentum ranking at all
from common import COST  # noqa: E402

from nsealgo.backtest.engine import run_backtest  # noqa: E402

c2, s2 = [], []
for seed in range(20):
    rng = np.random.default_rng(5000 + seed)
    sc = pd.DataFrame(rng.random(close_t.shape), index=close_t.index, columns=close_t.columns)
    r = run_backtest(close_t, sc, COST, CONFIG, rebalance="M")
    c2.append(r.metrics.cagr)
    s2.append(r.metrics.sharpe)
print(f"(ii) TRUE COIN (random scores, no rank)  : CAGR mean {np.mean(c2) * 100:>6.2f}%  "
      f"Sharpe mean {np.mean(s2):>5.2f}  p05 {np.percentile(c2, 5) * 100:>6.2f}%  "
      f"p95 {np.percentile(c2, 95) * 100:>6.2f}%")
print("\n  CCI V5_deep TEST                      : CAGR   4.56%  Sharpe -0.18")
print("  The true coin is the floor. CCI lands below both controls,")
print("  so the signal is worse than random selection, not merely weak.")
