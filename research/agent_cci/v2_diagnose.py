"""VERIFICATION PART 2 — comparator audit, CCI-gate ablation, and the reversion question.

Three questions, none of which can select a parameter (the 5-variant budget is
already exhausted and V5_deep is frozen):

  A) Is `equal_weight_book` (score = 1.0 everywhere) actually equal weight?  A constant
     score panel ties every name, and `build_rebalance_weights` breaks ties with a
     *stable* argsort, so the book may be "the first 22 symbols alphabetically" rather
     than the universe.  If so it is a biased comparator and every sentence that leaned
     on it needs re-weighting.
  B) Is the damage done by the CCI gate, or by the ranking around it?
  C) Is there any reversion edge in oversold NIFTY names at all, once the momentum
     confound is priced in?
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    CONFIG,
    COST,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    build_score,
    cci_panel,
    equal_weight_score,
    header,
    load_panels,
    run_variant,
    typical_price,
)

from nsealgo.backtest.engine import run_backtest

p = load_panels()
close_all = p.close
tp_all = typical_price(p)
c20 = cci_panel(tp_all, 20)
TR, TE = slice(TRAIN_START, TRAIN_END), slice(TEST_START, TEST_END)
close_tr, close_te = close_all.loc[TR], close_all.loc[TE]
cols = list(close_all.columns)

# --------------------------------------------------------------------------- #
print(header("A) IS equal_weight_score(score=1.0) ACTUALLY AN UNTILTED BOOK?"))
ew = run_backtest(close_te, equal_weight_score(close_te), COST, CONFIG, rebalance="M")
w = ew.weights
held = w[w > 1e-6]
per_name = held.sum() / max(len(w), 1)
first22 = cols[:22]
print(f"  universe: {len(cols)} symbols, alphabetically first 22 = {first22[:6]} ...")
print(f"  names ever held in the 22-name cap: {len(per_name)}")
overlap = [c for c in per_name.index if c in first22]
print(f"  of those, in the alphabetical first 22: {len(overlap)}")
print(f"  symbols NEVER held: {sorted(set(cols) - set(per_name.index))[:20]}")
print("  => equal_weight_book is a FIXED alphabetical 22-name book, not the universe.")
print(f"     It is a biased comparator. Reported CAGR "
      f"{ew.metrics.cagr * 100:.2f}%, Sharpe {ew.metrics.sharpe:.2f}.\n")

print(header("A2) CORRECTED UNTILTED COMPARATORS on TEST"))
# (a) rotating random 22-name book, 20 seeds — the honest "no signal" book
cr, sr = [], []
for seed in range(20):
    rng = np.random.default_rng(7000 + seed)
    sc = pd.DataFrame(rng.random(close_te.shape), index=close_te.index, columns=close_te.columns)
    r = run_backtest(close_te, sc, COST, CONFIG, rebalance="M")
    cr.append(r.metrics.cagr)
    sr.append(r.metrics.sharpe)
print(f"  random 22-name book, 20 seeds : CAGR mean {np.mean(cr) * 100:>6.2f}%  "
      f"p05 {np.percentile(cr, 5) * 100:>6.2f}%  p95 {np.percentile(cr, 95) * 100:>6.2f}%  "
      f"Sharpe mean {np.mean(sr):>5.2f}")
# (b) what the alphabetical book actually held
print(f"  alphabetical 22-name book      : CAGR {ew.metrics.cagr * 100:>6.2f}%  "
      f"Sharpe {ew.metrics.sharpe:>5.2f}  <- {'inside' if np.percentile(cr,5) < ew.metrics.cagr < np.percentile(cr,95) else 'OUTSIDE'} "
      f"the random p05-p95 band")
# (c) all-48 unconstrained book via the market proxy
from common import buy_and_hold  # noqa: E402

bh = buy_and_hold(close_te)
print(f"  all-48 unconstrained (buy&hold): CAGR {bh.metrics.cagr * 100:>6.2f}%  "
      f"Sharpe {bh.metrics.sharpe:>5.2f}  MaxDD {bh.metrics.max_drawdown * 100:>6.2f}%")

# --------------------------------------------------------------------------- #
print(header("B) CCI-GATE ABLATION — identical book/ranking/costs, gate toggled"))


def mom(panel, n=126):
    return panel / panel.shift(n) - 1.0


for lab, lo, hi, close_w in (("TRAIN", TRAIN_START, TRAIN_END, close_tr),
                             ("TEST", TEST_START, TEST_END, close_te)):
    m_all = mom(close_all).loc[lo:hi]
    gated = build_score(close_all, c20, 100.0, rank_by="mom126").loc[lo:hi]
    a = run_variant("no_gate", close_w, m_all, rebalance="M")
    b = run_variant("gate", close_w, gated, rebalance="M")
    print(f"  {lab}  mom126, NO gate : CAGR {a.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {a.metrics.sharpe:>6.2f}  MaxDD {a.metrics.max_drawdown * 100:>7.2f}%  "
          f"Names {a.avg_names:>5.1f}  Cost {a.metrics.cost_drag_annual * 100:>4.2f}%/y")
    print(f"  {lab}  mom126, CCI gate : CAGR {b.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {b.metrics.sharpe:>6.2f}  MaxDD {b.metrics.max_drawdown * 100:>7.2f}%  "
          f"Names {b.avg_names:>5.1f}  Cost {b.metrics.cost_drag_annual * 100:>4.2f}%/y")
    print(f"  {lab}  DELTA           : {(b.metrics.cagr - a.metrics.cagr) * 100:+7.2f} pp CAGR, "
          f"{b.metrics.sharpe - a.metrics.sharpe:+6.2f} Sharpe\n")

print("  Same ablation for the strategy-faithful rank (deepest CCI):")
for lab, lo, hi, close_w in (("TRAIN", TRAIN_START, TRAIN_END, close_tr),
                             ("TEST", TEST_START, TEST_END, close_te)):
    d_all = (-c20).loc[lo:hi]
    gated = build_score(close_all, c20, 100.0, rank_by="deepest").loc[lo:hi]
    a = run_variant("no_gate", close_w, d_all, rebalance="M")
    b = run_variant("gate", close_w, gated, rebalance="M")
    print(f"  {lab}  deepest-CCI, NO gate : CAGR {a.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {a.metrics.sharpe:>6.2f}  Names {a.avg_names:>5.1f}")
    print(f"  {lab}  deepest-CCI, gate on : CAGR {b.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {b.metrics.sharpe:>6.2f}  Names {b.avg_names:>5.1f}")
    print(f"  {lab}  DELTA                : {(b.metrics.cagr - a.metrics.cagr) * 100:+7.2f} pp\n")

# --------------------------------------------------------------------------- #
print(header("C) IS THERE A REVERSION EDGE? 21d forward returns by CCI bucket"))
fwd = (close_all.shift(-21) / close_all - 1.0)
m126 = mom(close_all)

for lo, hi, nm in ((TRAIN_START, TRAIN_END, "TRAIN"), (TEST_START, TEST_END, "TEST")):
    f, c, m = fwd.loc[lo:hi], c20.loc[lo:hi], m126.loc[lo:hi]
    over = c < -100.0
    overb = c > 100.0
    neu = (c >= -100.0) & (c <= 100.0)

    def stat(fwdw: pd.DataFrame, momw: pd.DataFrame, mask: pd.DataFrame, lab: str,
             window: str) -> float:
        v = fwdw.where(mask).stack().dropna()
        mm = float(momw.where(mask).stack().dropna().mean())
        print(f"  {window}  {lab:<26} mean 21d fwd {v.mean() * 100:>6.2f}%  "
              f"n={len(v):>7,}  mean mom126 {mm:>7.4f}")
        return float(v.mean())

    print()
    a = stat(f, m, over, "CCI < -100 (GATE BUYS)", nm)
    stat(f, m, neu, "-100 <= CCI <= 100", nm)
    b = stat(f, m, overb, "CCI > +100 (GATE EXCLUDES)", nm)
    print(f"  {nm}  raw reversion edge (oversold - overbought) = {(a - b) * 100:+.2f} pp")
    # momentum-matched: only overbought names that were ALSO strong
    strong = overb & (m126 > 0)
    v = f.where(strong).stack().dropna()
    print(f"  {nm}  momentum-matched counterfactual (CCI>+100 AND mom126>0): "
          f"mean 21d fwd {v.mean() * 100:>6.2f}%  n={len(v):>7,}  "
          f"=> edge {(a - float(v.mean())) * 100:+.2f} pp")
    print()

print(header("DONE"))
