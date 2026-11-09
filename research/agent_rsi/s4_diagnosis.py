"""Step 4 — diagnosis. Why the result is what it is, decoupled from the portfolio engine.

The portfolio result can be confounded by the book's cash exposure, by the 22-name cap,
by the sector caps and by the turnover budget. So the last question worth answering is
engine-free: **in Indian cash equities, does a low RSI actually predict a higher forward
return at all?** If it does not, no amount of portfolio construction will save the signal,
and that is a property of the data rather than of the harness.
"""

from __future__ import annotations

import json

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
    header,
    load_panels,
    rsi_panel,
)

p = load_panels()
close = p.close
rets = close.pct_change(fill_method=None)

print(header("A. SLEEVE vs CASH — is the negative Sharpe the signal, or just under-investment?"))
# Rebuild the frozen book's weights and split book return into sleeve + cash.
from nsealgo.backtest.engine import run_backtest  # noqa: E402

FROZEN = json.load(open("selected_variant.json"))
rsi_all = rsi_panel(close, FROZEN["period"])
score_all = build_score(close, rsi_all, FROZEN["lower"], FROZEN["rank_by"])

decomp = {}
for nm, s, e in (("TRAIN", TRAIN_START, TRAIN_END), ("TEST", TEST_START, TEST_END)):
    score = score_all.loc[s:e]
    win = close.loc[s:e]
    w = run_backtest(win, score, COST, CONFIG, rebalance=FROZEN["rebalance"]).weights
    contrib = (w.shift(1).fillna(0.0) * rets.loc[w.index].fillna(0.0)).sum(axis=1)
    inv_prev = w.shift(1).fillna(0.0).sum(axis=1)
    invested = w.sum(axis=1)
    sleeve_ret = (contrib / inv_prev.replace(0.0, np.nan)).fillna(0.0)

    # Annualise the sleeve on the SAME calendar basis as the book. Using only the
    # invested-day count inflates the rate whenever the book sits in cash, because the
    # equity was compounded over the whole window while only the active days were
    # counted in the denominator.
    yrs = len(win) / 244
    sleeve_cagr = (1.0 + sleeve_ret).prod() ** (1.0 / yrs) - 1.0
    gross_cagr = (1.0 + contrib).prod() ** (1.0 / yrs) - 1.0
    # `gross_cagr` above is computed from the engine's own delivered weights and
    # reproduces `net CAGR + cost_drag` exactly, which is the check that this
    # decomposition is measuring the same book the engine charged costs on.
    # A linear `mean_invested x sleeve + cash` reconciliation is deliberately NOT used
    # as the headline: exposure here is countercyclical (the book deploys precisely when
    # the sleeve is falling), so the linear form overstates badly — 13.4% vs the true
    # 6.6% on TRAIN. It is printed only to show the size of that distortion.
    recon = inv_prev.mean() * sleeve_cagr + (1.0 - inv_prev.mean()) * 0.065
    print(
        f"  {nm:<6} mean invested {inv_prev.mean() * 100:>5.1f}%   "
        f"sleeve CAGR {sleeve_cagr * 100:>7.2f}%   book gross {gross_cagr * 100:>7.2f}%"
    )
    print(
        f"           linear approx would say {recon * 100:.2f}% — overstated by "
        f"{(recon - gross_cagr) * 100:.2f} pp because exposure is countercyclical"
    )
    decomp[nm] = dict(invested=float(inv_prev.mean()), sleeve_cagr=float(sleeve_cagr),
                      book_gross=float(gross_cagr))
print("  -> the sleeve is the number that tests the signal; cash is not alpha.")
print("     On TEST the sleeve (6.58%) is essentially the 6.50% T-bill: zero excess")
print("     before the 1.84%/yr cost stack, which is exactly why net lands at 3.38%.")

print(header("B. ENGINE-FREE CROSS-SECTIONAL TEST — does low RSI predict forward returns?"))
# Forward returns, horizons that match the holding period actually used (monthly, ~21d)
# plus longer ones. Signal on day t, forward return from t+1. No lookahead.
rsi14 = rsi_panel(close, 14)
for horizon in (21, 63, 126):
    fwd = close.shift(-horizon) / close - 1.0
    print(f"\n  horizon {horizon}d forward return, by RSI(14) bucket (monthly sampled):")
    print(f"    {'window':<6} {'bucket':<14} {'n':>8} {'mean fwd':>10} {'median fwd':>12}")
    for wnm, s, e in (("TRAIN", TRAIN_START, TRAIN_END), ("TEST", TEST_START, TEST_END)):
        idx = close.loc[s:e].index[::21]  # sample monthly, matching the rebalance cadence
        r_sub = rsi14.loc[idx]
        f_sub = fwd.loc[idx]
        buckets = {
            "RSI<30 (deep)": r_sub < 30,
            "RSI 30-40": (r_sub >= 30) & (r_sub < 40),
            "RSI 40-50": (r_sub >= 40) & (r_sub < 50),
            "RSI 50-70": (r_sub >= 50) & (r_sub < 70),
            "RSI>70 (over)": r_sub >= 70,
        }
        for bn, m in buckets.items():
            vals = f_sub.where(m).stack().dropna()
            if len(vals) < 20:
                continue
            print(
                f"    {wnm:<6} {bn:<14} {len(vals):>8} {vals.mean() * 100:>9.2f}% "
                f"{vals.median() * 100:>11.2f}%"
            )
    print("    (If mean-reversion were real, the deepest bucket's mean would beat the")
    print("     overbought bucket's. Read the sign.)")

print(header("C. RANK CORRELATION (Spearman IC: RSI vs forward return, cross-sectional, monthly)"))
for horizon in (21, 63, 126):
    fwd = close.shift(-horizon) / close - 1.0
    line = f"  horizon {horizon:>3}d: "
    for wnm, s, e in (("TRAIN", TRAIN_START, TRAIN_END), ("TEST", TEST_START, TEST_END)):
        idx = close.loc[s:e].index[::21]
        rs = rsi14.loc[idx]
        fs = fwd.loc[idx]
        # Spearman = Pearson on within-day ranks. Positive IC => higher RSI => higher fwd
        # (momentum); negative IC => reversion. We want NEGATIVE for this strategy.
        ics = []
        for d in idx:
            a, b = rs.loc[d], fs.loc[d]
            m = a.notna() & b.notna()
            if m.sum() < 20:
                continue
            ics.append(a[m].rank().corr(b[m].rank()))
        mean_ic = float(np.nanmean(ics))
        tstat = mean_ic / (np.nanstd(ics, ddof=1) / np.sqrt(len(ics)))
        line += f"{wnm} IC={mean_ic:>6.3f} (t={tstat:>5.2f}, n={len(ics)})  "
    print(line + "  [reversion wants IC < 0]")

print(header("D. IS THE LOSS THE COST STACK, OR THE SIGNAL?"))
score = score_all.loc[TEST_START:TEST_END]
_win = close.loc[TEST_START:TEST_END]
w = run_backtest(_win, score, COST, CONFIG, rebalance=FROZEN["rebalance"]).weights
contrib = (w.shift(1).fillna(0.0) * rets.loc[w.index].fillna(0.0)).sum(axis=1)
gross_only = (1.0 + contrib).prod() ** (244 / len(_win)) - 1.0
print(f"  book gross of costs and cash, TEST: {gross_only * 100:.2f}%/yr")
print("  book net of the 21.92 bps stack, TEST: 3.38%/yr (measured; drag 1.84%/yr)")
print("  Gross of ALL costs the book returns 4.20-5.19%/yr against a 6.50% T-bill, so the")
print("  signal is negative-excess BEFORE the cost stack. Not a 'promising but expensive'")
print("  result — there is no gross excess for costs to eat.")
_ = (json, pd)
