"""VERIFICATION RUN — independent reproduction of the cci_strategy result.

Why this file exists: the interrupted run left numbers in *.txt. This script
reproduces them from scratch and, critically, fixes two defects found in the prior
scratch (see REPORT.md §BUGS):

  BUG-1  s2_train.py built CCI and mom126 from the *TRAIN slice only*, so the first
         126 sessions of the selection window had no score and sat in cash. That is
         why its TRAIN numbers disagree with s4_posthoc.py. Here CCI/rank are always
         built on the FULL panel and then sliced (trailing indicators => slicing after
         the fact introduces no lookahead), which is what s3/s4 did for TEST.
  BUG-2  random_control() was handed the full 2016-2026 panel but reported as the
         TEST control. Every random control here is run on the TEST slice only.

Nothing in this file is used to select parameters. The 5 variants are the ones
already declared in REPORT.md / s2_train.py; no 6th is tested.
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
    buy_and_hold,
    cci_panel,
    equal_weight_score,
    header,
    load_panels,
    run_variant,
    signal_panel,
    typical_price,
    yearly_returns,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import STRESS_MODELS
from nsealgo.factors.core import build_composite_score

# The declared budget. Identical to REPORT.md §2. Not to be extended.
VARIANTS = [
    ("V1_base", 20, 100.0, "M", "mom126"),
    ("V2_tight", 20, 150.0, "M", "mom126"),
    ("V3_week", 20, 100.0, "W", "mom126"),
    ("V4_fast", 10, 100.0, "M", "mom126"),
    ("V5_deep", 20, 100.0, "M", "deepest"),
]

p = load_panels()
close_all = p.close
tp_all = typical_price(p)
cci_all = {per: cci_panel(tp_all, per) for per in (10, 20)}

TR = slice(TRAIN_START, TRAIN_END)
TE = slice(TEST_START, TEST_END)
close_tr, close_te = close_all.loc[TR], close_all.loc[TE]

print(header("WARM-UP CORRECTNESS: full-panel build then slice"))
for _nm, per, _entry, _reb, _rk in VARIANTS[:1]:
    sl_cci = cci_panel(typical_price(p).loc[TR], per)  # the s2_train.py way
    fl_cci = cci_all[per]
    n_nan_slice = int(sl_cci.isna().to_numpy().sum())
    n_nan_full = int(fl_cci.loc[TR].isna().to_numpy().sum())
    print(
        f"  CCI(20) NaNs inside TRAIN when built on TRAIN slice : {n_nan_slice:>6,}"
    )
    print(
        f"  CCI(20) NaNs inside TRAIN when built on FULL panel : {n_nan_full:>6,}  <- correct"
    )
    mom_slice = (close_tr / close_tr.shift(126) - 1.0).isna().to_numpy().sum()
    mom_full = (close_all / close_all.shift(126) - 1.0).loc[TR].isna().to_numpy().sum()
    print(f"  mom126 NaNs inside TRAIN, slice-build / full-build : {mom_slice:>6,} / {mom_full:>6,}")
    print(
        "  => s2_train.py held ~126 sessions (about 6 months) of TRAIN in cash.\n"
    )

# --------------------------------------------------------------------------- #
# 1. TRAIN selection, warm-up corrected
# --------------------------------------------------------------------------- #
print(header("1) TRAIN 2016-01-01 -> 2023-12-31, warm-up corrected (SELECTION ONLY)"))
print(f"bars={len(close_tr)}  symbols={close_tr.shape[1]}\n")

train_rows = {}
for nm, per, entry, reb, rk in VARIANTS:
    c = cci_all[per]
    sig_tr = signal_panel(c, entry).loc[TR]
    n_fin = int((~c.loc[TR].isna()).to_numpy().sum())
    lf = float((sig_tr > 0).to_numpy().sum()) / n_fin
    sc = build_score(close_all, c, entry, rank_by=rk).loc[TR]
    r = run_variant(nm, close_tr, sc, rebalance=reb, long_frac=lf)
    train_rows[nm] = (r, lf)
    m = r.metrics
    print(
        f"{nm:<10} p={per:>3} entry={entry:>5.0f} {reb} {rk:<7} CAGR {m.cagr * 100:>7.2f}%  "
        f"Sharpe {m.sharpe:>6.2f}  MaxDD {m.max_drawdown * 100:>7.2f}%  "
        f"Calmar {m.calmar:>6.2f}  Turn {m.annual_turnover:>5.2f}x  "
        f"Cost {m.cost_drag_annual * 100:>5.2f}%/y  Names {r.avg_names:>5.1f}  "
        f"LongFrac {lf * 100:>5.2f}%"
    )

ew_tr = run_variant("equal_weight_book", close_tr, equal_weight_score(close_tr))
print(
    f"{'equal_weight_book':<10} (comparator)              "
    f"CAGR {ew_tr.metrics.cagr * 100:>7.2f}%  Sharpe {ew_tr.metrics.sharpe:>6.2f}  "
    f"MaxDD {ew_tr.metrics.max_drawdown * 100:>7.2f}%  Names {ew_tr.avg_names:>5.1f}"
)

ranked = sorted(train_rows.items(), key=lambda kv: (-kv[1][0].metrics.sharpe, -kv[1][0].metrics.calmar))
print("\n  selection (TRAIN Sharpe, tie-break Calmar):")
for i, (nm, (r, _)) in enumerate(ranked, 1):
    print(f"    {i}. {nm:<10} Sharpe {r.metrics.sharpe:>6.2f}  Calmar {r.metrics.calmar:>6.2f}")
winner = ranked[0][0]
print(f"\n  WINNER (frozen): {winner}")
train_lf = train_rows[winner][1]
print(f"  TRAIN bar-long fraction, frozen: {train_lf * 100:.2f}%")

# --------------------------------------------------------------------------- #
# 2. TEST — the five declared variants, unchanged
# --------------------------------------------------------------------------- #
print(header("2) TEST 2024-01-01 -> 2026-10-01 — all 5 declared variants, unchanged"))
print(f"bars={len(close_te)}  symbols={close_te.shape[1]}\n")
print(
    f"{'variant':<10} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} "
    f"{'Turn':>6} {'Cost':>7} {'Names':>6} {'LongFrac':>9}"
)

test_runs = {}
for nm, per, entry, reb, rk in VARIANTS:
    c = cci_all[per]
    sc = build_score(close_all, c, entry, rank_by=rk).loc[TE]
    sig_te = signal_panel(c, entry).loc[TE]
    lf = float((sig_te > 0).to_numpy().sum()) / int((~c.loc[TE].isna()).to_numpy().sum())
    r = run_variant(nm, close_te, sc, rebalance=reb, long_frac=lf)
    test_runs[nm] = r
    m = r.metrics
    print(
        f"{nm:<10} {m.cagr * 100:>7.2f}% {m.sharpe:>7.2f} {m.max_drawdown * 100:>7.2f}% "
        f"{m.calmar:>7.2f} {m.annual_turnover:>5.2f}x {m.cost_drag_annual * 100:>6.2f}% "
        f"{r.avg_names:>6.1f} {lf * 100:>8.2f}%"
    )

primary = test_runs[winner]
pm = primary.metrics
print(f"\n  PRIMARY (frozen TRAIN winner '{winner}' on TEST):")
print(f"    CAGR {pm.cagr * 100:.2f}%   Sharpe {pm.sharpe:.2f}   "
      f"MaxDD {pm.max_drawdown * 100:.2f}% ({pm.max_drawdown_days}d)   Calmar {pm.calmar:.2f}")
print(f"    Turnover {pm.annual_turnover:.2f}x/yr   Cost drag {pm.cost_drag_annual * 100:.2f}%/yr   "
      f"Trades {pm.trades_per_year:.1f}/yr   Avg names {primary.avg_names:.1f}")
yr = yearly_returns(primary.returns)
print(f"    Positive years {int((yr > 0).sum())}/{len(yr)}")
for y, v in yr.items():
    print(f"      {y}: {v * 100:>7.2f}%")

# --------------------------------------------------------------------------- #
# 3. Buy-and-hold over the identical TEST window
# --------------------------------------------------------------------------- #
print(header("3) BUY-AND-HOLD, identical TEST window, net of costs"))
bh = buy_and_hold(close_te)
print("  panel.pct_change().mean(axis=1), one entry round trip (21.92 bps) charged d1")
print(f"  buy_and_hold_EW     CAGR {bh.metrics.cagr * 100:>7.2f}%  Sharpe {bh.metrics.sharpe:>6.2f}  "
      f"MaxDD {bh.metrics.max_drawdown * 100:>7.2f}%  Calmar {bh.metrics.calmar:>6.2f}")
ew_te = run_variant("equal_weight_book", close_te, equal_weight_score(close_te))
print(f"  equal_weight_book   CAGR {ew_te.metrics.cagr * 100:>7.2f}%  "
      f"Sharpe {ew_te.metrics.sharpe:>6.2f}  MaxDD {ew_te.metrics.max_drawdown * 100:>7.2f}%  "
      f"Names {ew_te.avg_names:.1f}   <- same 22-name cap / 10% cash / costs")
print("\n  DELTA strategy - buy_and_hold:")
print(f"    CAGR   {(pm.cagr - bh.metrics.cagr) * 100:+.2f} pp")
print(f"    Sharpe {pm.sharpe - bh.metrics.sharpe:+.2f}")
print(f"    MaxDD  {(pm.max_drawdown - bh.metrics.max_drawdown) * 100:+.2f} pp "
      f"({'shallower' if pm.max_drawdown > bh.metrics.max_drawdown else 'DEEPER'})")

# --------------------------------------------------------------------------- #
# 4. nsealgo composite
# --------------------------------------------------------------------------- #
print(header("4) vs nsealgo COMPOSITE (build_composite_score, same panel, monthly)"))
comp = build_composite_score(close_all).loc[TE]
cr = run_variant("nsealgo_composite", close_te, comp, rebalance="M")
print(f"  nsealgo_composite   CAGR {cr.metrics.cagr * 100:>7.2f}%  Sharpe {cr.metrics.sharpe:>6.2f}  "
      f"MaxDD {cr.metrics.max_drawdown * 100:>7.2f}%  Names {cr.avg_names:>5.1f}")
print(f"  CCI {winner:<14} CAGR {pm.cagr * 100:>7.2f}%  Sharpe {pm.sharpe:>6.2f}  "
      f"MaxDD {pm.max_drawdown * 100:>7.2f}%  Names {primary.avg_names:>5.1f}")

# --------------------------------------------------------------------------- #
# 5. Random-signal controls — TEST slice only (BUG-2 fixed)
# --------------------------------------------------------------------------- #
print(header("5) NEGATIVE CONTROLS on TEST, same long fraction, 20 seeds each"))
c20 = cci_all[20]
close_te_c = close_te
mom_te = (close_all / close_all.shift(126) - 1.0).loc[TE]

# (i) random eligibility, momentum rank kept (the brief's control as specified)
c1, s1_ = [], []
for seed in range(20):
    rng = np.random.default_rng(1000 + seed)
    mask = pd.DataFrame(
        rng.random(close_te_c.shape) < train_lf, index=close_te_c.index, columns=close_te_c.columns
    )
    r = run_backtest(close_te_c, mom_te.where(mask), COST, CONFIG, rebalance="M")
    c1.append(r.metrics.cagr)
    s1_.append(r.metrics.sharpe)
# (ii) true coin: random scores, no momentum rank at all
c2, s2_ = [], []
for seed in range(20):
    rng = np.random.default_rng(5000 + seed)
    sc = pd.DataFrame(
        rng.random(close_te_c.shape), index=close_te_c.index, columns=close_te_c.columns
    )
    r = run_backtest(close_te_c, sc, COST, CONFIG, rebalance="M")
    c2.append(r.metrics.cagr)
    s2_.append(r.metrics.sharpe)

for lab, cc, ss in (("(i)  random eligibility + mom126 rank", c1, s1_),
                    ("(ii) TRUE COIN (random scores, no rank)", c2, s2_)):
    print(
        f"  {lab:<42} CAGR mean {np.mean(cc) * 100:>6.2f}%  p05 {np.percentile(cc, 5) * 100:>6.2f}%  "
        f"p95 {np.percentile(cc, 95) * 100:>6.2f}%   Sharpe mean {np.mean(ss):>5.2f}"
    )
print(f"\n  CCI {winner} TEST" + " " * 32 +
      f"CAGR {pm.cagr * 100:>6.2f}%{' ' * 16}Sharpe {pm.sharpe:>5.2f}")
print(f"  vs control (i)  : CAGR {(pm.cagr - np.mean(c1)) * 100:+.2f} pp, "
      f"Sharpe {pm.sharpe - np.mean(s1_):+.2f}")
print(f"  vs control (ii) : CAGR {(pm.cagr - np.mean(c2)) * 100:+.2f} pp, "
      f"Sharpe {pm.sharpe - np.mean(s2_):+.2f}")

# --------------------------------------------------------------------------- #
# 6. Cost stress: is the edge there before costs?
# --------------------------------------------------------------------------- #
print(header("6) COST STRESS — same signal, cost model varied (TEST)"))
sc_win = build_score(close_all, c20, 100.0, rank_by="deepest").loc[TE]
for nm, cm in (("zero_cost", STRESS_MODELS["zero_cost"]),
               ("base 5bps/side (reported)", COST),
               ("double_slippage", STRESS_MODELS["double_slippage"]),
               ("triple_slippage", STRESS_MODELS["triple_slippage"])):
    res = run_backtest(close_te, sc_win, cm, CONFIG, rebalance="M")
    print(f"  {nm:<24} CAGR {res.metrics.cagr * 100:>7.2f}%  Sharpe {res.metrics.sharpe:>6.2f}  "
          f"rt_bps {res.diag['round_trip_bps']:>6.2f}")

# --------------------------------------------------------------------------- #
# 7. Bug checks (brief §6)
# --------------------------------------------------------------------------- #
print(header("7) BUG CHECKS (brief §6)"))
print(f"  1 plausibility : CAGR {pm.cagr * 100:5.1f}%  under 50% ceiling: "
      f"{'OK' if pm.cagr < 0.5 else 'SUSPICIOUS'}")
print(f"  2 weight count : avg names {primary.avg_names:.1f} (cap 22) : "
      f"{'OK' if primary.avg_names <= 24 else 'SUSPICIOUS'}")
sig_te = signal_panel(c20, 100.0).loc[TE]
lf_te = float((sig_te > 0).to_numpy().sum()) / int((~c20.loc[TE].isna()).to_numpy().sum())
print(f"  3 liveness     : bar long frac {lf_te * 100:.2f}% (TRAIN {train_lf * 100:.2f}%) : "
      f"{'OK' if lf_te > 0.05 else 'DEAD'}")
print(f"  4 cost drag    : {pm.cost_drag_annual * 100:.2f}%/yr against {pm.cagr * 100:.2f}% CAGR")
print("  5 random ctrl  : see §5")

print(header("DONE"))
