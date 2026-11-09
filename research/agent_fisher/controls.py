"""Controls + signal-level diagnostics.

1. Information coefficient (IC): rank correlation between the Fisher signal and the
   forward return, cross-sectionally each day. This isolates the indicator from every
   portfolio-construction choice, so a dead indicator cannot be rescued by the book.
2. Matched random controls for both constructions.
3. Context: composite and buy-and-hold on the SAME windows as Part B.
4. Exposure-matched comparison.
"""

from __future__ import annotations

import json
from decimal import Decimal

import numpy as np
import pandas as pd
from common import (
    TEST,
    TRAIN,
    bh_returns,
    bt,
    cost_model,
    fisher_panel,
    fisher_score,
    fisher_signal,
    load,
    random_signal_score,
    slice_metrics,
    window_diag,
)

RATE = float(cost_model().all_in_round_trip_bps(Decimal("100000"))) / 1e4
PERIOD = 20  # part A selection (period=20, entry=0.5) and part B selection (period=20)


def ic(signal: pd.DataFrame, fwd: pd.DataFrame, lo, hi) -> tuple[float, int]:
    """Mean daily cross-sectional Spearman IC of ``signal`` vs forward return."""
    idx = signal.index
    a = int(idx.searchsorted(pd.Timestamp(lo, tz=idx.tz)))
    b = int(idx.searchsorted(pd.Timestamp(hi, tz=idx.tz)))
    vals = []
    for t in range(a, b):
        s = signal.iloc[t]
        f = fwd.iloc[t]
        m = s.notna() & f.notna()
        if int(m.sum()) < 10:
            continue
        v = s[m].corr(f[m], method="spearman")
        if v is not None and np.isfinite(v):
            vals.append(float(v))
    return (float(np.mean(vals)) if vals else float("nan")), len(vals)


def main() -> None:
    panel, _ = load()
    out: dict = {}
    f = fisher_panel(panel, PERIOD)
    neg_f = -f  # contrarian direction: high = oversold = good

    print("=" * 78)
    print("PART C — INFORMATION COEFFICIENT of the Fisher value (period=20)")
    print("  IC = mean daily cross-sectional Spearman rank corr(-fisher, fwd return)")
    print("  IC > 0  => the strategy's own (contrarian) direction carries information")
    print("=" * 78)
    print(f"{'horizon':>8} {'TRAIN IC':>10} {'t-stat':>8} {'n':>6} | "
          f"{'TEST IC':>10} {'t-stat':>8} {'n':>6}")
    out["ic"] = {}
    for h in (5, 10, 21, 42, 63, 126):
        fwd = panel.shift(-h) / panel - 1.0  # forward return, known only in hindsight
        row = {}
        for label, (lo, hi) in (("TRAIN", TRAIN), ("TEST", TEST)):
            v, n = ic(neg_f, fwd, lo, hi)
            t = v / (1.0 / np.sqrt(n)) if n and np.isfinite(v) else float("nan")
            row[label] = {"ic": v, "t": t, "n": n}
        out["ic"][h] = row
        print(f"{h:>8}d {row['TRAIN']['ic']:>+10.4f} {row['TRAIN']['t']:>+8.2f} "
              f"{row['TRAIN']['n']:>6} | {row['TEST']['ic']:>+10.4f} "
              f"{row['TEST']['t']:>+8.2f} {row['TEST']['n']:>6}")

    # Trend direction, as a contrast: high fisher (price at top of range) should also
    # be checked, since a trend book and a contrarian book are opposite.
    print("\n  same IC but with the sign REVERSED (i.e. a trend-following Fisher):")
    for h in (21, 63):
        fwd = panel.shift(-h) / panel - 1.0
        a, na = ic(f, fwd, *TRAIN)
        b, nb = ic(f, fwd, *TEST)
        print(f"{h:>8}d {a:>+10.4f} {a*np.sqrt(na):>+8.2f} {na:>6} | "
              f"{b:>+10.4f} {b*np.sqrt(nb):>+8.2f} {nb:>6}")

    # Reference IC: plain 126d momentum, the repo's own best long-only factor.
    mom = panel / panel.shift(126) - 1.0
    print("\n  reference — 126d momentum, same IC construction:")
    for h in (21, 63):
        fwd = panel.shift(-h) / panel - 1.0
        a, na = ic(mom, fwd, *TRAIN)
        b, nb = ic(mom, fwd, *TEST)
        print(f"{h:>8}d {a:>+10.4f} {a*np.sqrt(na):>+8.2f} {na:>6} | "
              f"{b:>+10.4f} {b*np.sqrt(nb):>+8.2f} {nb:>6}")

    # ---------------- matched controls ----------------
    print("\n" + "=" * 78)
    print("PART C — matched random controls + context, TEST window, net of 21.92 bps")
    print("=" * 78)
    N_SEEDS = 20

    # --- Part A construction: binary gate of the same sparsity, then momentum rank.
    sig = fisher_signal(neg_f, 0.50)
    gate_c, gate_s = [], []
    for s_ in range(N_SEEDS):
        scc = random_signal_score(panel, sig, seed=2000 + s_)
        rr = bt(panel, scc)
        mm = slice_metrics(rr.equity, rr.returns, *TEST)
        gate_c.append(mm.cagr)
        gate_s.append(mm.sharpe)
    gate_c = np.array(gate_c)
    gate_s = np.array(gate_s)
    out["random_gate_dist"] = {"cagr_mean": float(gate_c.mean()),
                               "cagr_sd": float(gate_c.std()),
                               "cagr_min": float(gate_c.min()),
                               "cagr_max": float(gate_c.max()),
                               "sharpe_mean": float(gate_s.mean()),
                               "sharpe_sd": float(gate_s.std()),
                               "sharpe_min": float(gate_s.min()),
                               "sharpe_max": float(gate_s.max()),
                               "n_seeds": N_SEEDS}

    # Part A official strategy, for side-by-side against the gate control.
    scA, _ = fisher_score(panel, 20, 0.50)
    resA = bt(panel, scA)
    mA = slice_metrics(resA.equity, resA.returns, *TEST)
    dgA = window_diag(resA, *TEST, gross_result=bt(panel, scA, zero_cost=True))
    out["partA"] = {"cagr": mA.cagr, "sharpe": mA.sharpe, "max_dd": mA.max_drawdown,
                    "bookwt": dgA["avg_book_weight"]}

    # Part B construction: continuous rank over all names.
    scB = neg_f.rank(axis=1, pct=True, na_option="keep")
    resB = bt(panel, scB)
    mB = slice_metrics(resB.equity, resB.returns, *TEST)
    dgB = window_diag(resB, *TEST, gross_result=bt(panel, scB, zero_cost=True))

    # A fresh independent random ranking EVERY bar. NB: `rng.permutation(2d)` permutes
    # rows, not columns -- that silently yields an identical score every day and turns
    # this control into a buy-and-hold of one random basket. Random draws + argsort
    # along axis=1 gives the per-day permutation we actually want.
    # 20 seeds, because one seed is a single draw and cannot settle "beats a coin flip".
    rand_res = []
    for s_ in range(N_SEEDS):
        rsg = np.random.default_rng(1000 + s_)
        scc = pd.DataFrame(
            rsg.random((len(panel), panel.shape[1])), index=panel.index,
            columns=panel.columns,
        ).rank(axis=1, pct=True)
        rr = bt(panel, scc)
        mm = slice_metrics(rr.equity, rr.returns, *TEST)
        dd_ = window_diag(rr, *TEST, gross_result=bt(panel, scc, zero_cost=True))
        rand_res.append((mm, dd_, scc))
    cagrs = np.array([m.cagr for m, _, _ in rand_res])
    shps = np.array([m.sharpe for m, _, _ in rand_res])
    mR = max(rand_res, key=lambda r: r[0].sharpe)[0]
    dgR = max(rand_res, key=lambda r: r[0].sharpe)[1]
    scR = rand_res[0][2]
    print(f"random continuous rank, {N_SEEDS} seeds, TEST window:")
    print(f"  CAGR    mean {cagrs.mean()*100:6.2f}%  sd {cagrs.std()*100:5.2f}  "
          f"range [{cagrs.min()*100:.2f}%, {cagrs.max()*100:.2f}%]")
    print(f"  Sharpe  mean {shps.mean():6.3f}   sd {shps.std():5.3f}   "
          f"range [{shps.min():.3f}, {shps.max():.3f}]")
    out["random_cont_dist"] = {"cagr_mean": float(cagrs.mean()),
                               "cagr_sd": float(cagrs.std()),
                               "cagr_min": float(cagrs.min()),
                               "cagr_max": float(cagrs.max()),
                               "sharpe_mean": float(shps.mean()),
                               "sharpe_sd": float(shps.std()),
                               "sharpe_min": float(shps.min()),
                               "sharpe_max": float(shps.max()),
                               "n_seeds": N_SEEDS}
    print(f"\nrandom BINARY GATE (Part A construction), {N_SEEDS} seeds, TEST:")
    print(f"  CAGR    mean {gate_c.mean()*100:6.2f}%  sd {gate_c.std()*100:5.2f}  "
          f"range [{gate_c.min()*100:.2f}%, {gate_c.max()*100:.2f}%]")
    print(f"  Sharpe  mean {gate_s.mean():6.3f}   sd {gate_s.std():5.3f}   "
          f"range [{gate_s.min():.3f}, {gate_s.max():.3f}]")
    print(f"  Part A Fisher V2 for comparison:  CAGR {mA.cagr*100:6.2f}%  "
          f"Sharpe {mA.sharpe:6.3f}  bookwt {dgA['avg_book_weight']:.3f}")
    print(f"  -> Fisher is BELOW the random-gate mean on CAGR: "
          f"{mA.cagr < gate_c.mean()}")

    from nsealgo.factors.core import build_composite_score

    comp = build_composite_score(panel)
    cres = bt(panel, comp)
    mC = slice_metrics(cres.equity, cres.returns, *TEST)
    dgC = window_diag(cres, *TEST, gross_result=bt(panel, comp, zero_cost=True))

    d, e, tot = bh_returns(panel, None, RATE)
    mH = slice_metrics(e, d, *TEST)

    rows = [
        ("Part A Fisher V2 (gate)", mA, dgA),
        ("Part B Fisher-rank(20)", mB, dgB),
        ("Random continuous rank", mR, dgR),
        ("nsealgo composite", mC, dgC),
        ("Buy & hold", mH, {"avg_material_names": 48.0}),
    ]
    print(f"{'':<24}{'CAGR':>8}{'Sharpe':>9}{'MaxDD':>10}{'Calmar':>8}"
          f"{'bookwt':>9}{'Turn':>8}{'Cost':>8}")
    for nm, m, dg in rows:
        bw = dg.get("avg_book_weight", 1.0)
        print(f"{nm:<24}{m.cagr*100:>7.2f}%{m.sharpe:>9.2f}"
              f"{m.max_drawdown*100:>9.2f}%{m.calmar:>8.2f}{bw:>9.3f}"
              f"{dg.get('annual_turnover', 0):>8.2f}"
              f"{dg.get('cost_drag_annual', 0)*100:>7.2f}%")
    out["controls_test"] = {
        "partB": {"cagr": mB.cagr, "sharpe": mB.sharpe, "max_dd": mB.max_drawdown,
                  "bookwt": dgB["avg_book_weight"]},
        "random_cont": {"cagr": mR.cagr, "sharpe": mR.sharpe, "max_dd": mR.max_drawdown,
                        "bookwt": dgR["avg_book_weight"]},
        "composite": {"cagr": mC.cagr, "sharpe": mC.sharpe, "max_dd": mC.max_drawdown,
                      "bookwt": dgC["avg_book_weight"]},
        "buyhold": {"cagr": mH.cagr, "sharpe": mH.sharpe, "max_dd": mH.max_drawdown,
                    "bookwt": 1.0},
    }

    # Exposure-matched: scale every book's beta-free part of CAGR by its invested
    # fraction so the comparison is not just "how much was deployed".
    print("\n  exposure-matched (CAGR scaled by invested book weight; cash earns 0):")
    base = [("Part A Fisher V2 (gate)", mA, dgA),
            ("Part B Fisher-rank(20)", mB, dgB), ("Random continuous rank", mR, dgR),
            ("nsealgo composite", mC, dgC), ("Buy & hold", mH, None)]
    bw_ref = max(d.get("avg_book_weight", 1.0) if d else 1.0 for _, _, d in base)
    for nm, m, dg in base:
        bw = dg.get("avg_book_weight", 1.0) if dg else 1.0
        scaled = m.cagr * (bw / bw_ref)
        print(f"    {nm:<24} raw {m.cagr*100:>7.2f}%  x{bw:.3f} -> "
              f"{scaled*100:>7.2f}%  (bw_ref {bw_ref:.3f})")

    # TRAIN context for composite / B&H so the Part B TRAIN number can be judged.
    print("\n  same books on TRAIN (2016-2023) for context:")
    scB = neg_f.rank(axis=1, pct=True, na_option="keep")
    mBt = slice_metrics(bt(panel, scB).equity, bt(panel, scB).returns, *TRAIN)
    mCt = slice_metrics(bt(panel, comp).equity, bt(panel, comp).returns, *TRAIN)
    dt, et, _ = bh_returns(panel, None, RATE)
    mHt = slice_metrics(et, dt, *TRAIN)
    mRt = slice_metrics(bt(panel, scR).equity, bt(panel, scR).returns, *TRAIN)
    for nm, m in (("Part B Fisher-rank(20)", mBt), ("Random continuous rank", mRt),
                  ("nsealgo composite", mCt), ("Buy & hold", mHt)):
        print(f"    {nm:<24} CAGR {m.cagr*100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
              f"MaxDD {m.max_drawdown*100:>8.2f}%")
    out["controls_train"] = {
        "partB": {"cagr": mBt.cagr, "sharpe": mBt.sharpe},
        "random_cont": {"cagr": mRt.cagr, "sharpe": mRt.sharpe},
        "composite": {"cagr": mCt.cagr, "sharpe": mCt.sharpe},
        "buyhold": {"cagr": mHt.cagr, "sharpe": mHt.sharpe},
    }

    with open("controls.json", "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("\nsaved controls.json")


if __name__ == "__main__":
    main()
