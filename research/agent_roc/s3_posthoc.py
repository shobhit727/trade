"""Step 3 — post-hoc diagnostics on TEST. NONE of these are selectable variants.

Answers: what did the ROC gate actually contribute, is ROC informative cross-sectionally
at all, and is the strategy better than a random book at the same exposure.

Supersedes the first draft of this script, which had two defects of its own:
  * `rank(pct=True)` produced hundreds of distinct group labels instead of 5 quintiles,
    so the "quintile" table was actually a top-1-vs-bottom-1 comparison;
  * the market-return-by-year line used `series.resample("YE").last()`, which is the
    last *daily* return of the year, not the year's compounded return — it printed
    +565.87% for 2025. Fixed by compounding first.
Both were caught before any number reached the report.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    CFG,
    COST,
    ENGINE_SHA,
    HEADER,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    build_score,
    buy_and_hold,
    coin_book,
    load,
    random_book,
    roc_panel,
    roc_signal,
    row,
    run_backtest,
)

OUT: dict = {"_engine_sha": ENGINE_SHA}
NULL_SEEDS = 100


def main() -> None:
    panel, _, _ = load()
    test = panel.loc[TEST_START:TEST_END]
    sig = roc_signal(panel, 10, 0.0)
    frac = float(sig.loc[TEST_START:TEST_END].mean().mean())
    r10 = roc_panel(panel, 10)
    mom_full = panel / panel.shift(126) - 1.0
    fwd21 = panel / panel.shift(-21) - 1.0

    # ---------------------------------------------------------------- A --------
    print("=" * 78)
    print("A. ABLATION — does the ROC gate add anything over momentum alone?")
    print("   (comparator/diagnostic; NOT a variant, NOT selectable)")
    print("=" * 78)
    mom_rank_full = mom_full.rank(axis=1, pct=True)
    books = {
        "momentum126 only, TRAIN": ("train", mom_rank_full, "M"),
        "momentum126 only, TEST": ("test", mom_rank_full, "M"),
        "ROC gate + mom rank, TRAIN": ("train", build_score(panel, sig, "mom126"), "M"),
        "ROC gate + mom rank, TEST": ("test", build_score(panel, sig, "mom126"), "M"),
    }
    res_by = {}
    print(HEADER)
    for lab, (win, sc_full, reb) in books.items():
        pnl = panel.loc[TEST_START:TEST_END] if win == "test" \
            else panel.loc[TRAIN_START:TRAIN_END]
        r = run_backtest(pnl, sc_full.loc[pnl.index], COST, CFG, rebalance=reb)
        res_by[lab] = r
        print(row(lab, r.metrics, {"names": f"{r.diag['avg_names']:.1f}"}))
    for w in ("TRAIN", "TEST"):
        a = res_by[f"momentum126 only, {w}"].metrics
        b = res_by[f"ROC gate + mom rank, {w}"].metrics
        print(f"  {w:5s} gate effect: CAGR {b.cagr * 100 - a.cagr * 100:+.2f}pp   "
              f"Sharpe {b.sharpe - a.sharpe:+.2f}   "
              f"MaxDD {(b.max_drawdown - a.max_drawdown) * 100:+.2f}pp   "
              f"Calmar {b.calmar - a.calmar:+.2f}")
    OUT["ablation"] = {k: v.metrics.as_dict() for k, v in res_by.items()}
    print()

    # ---------------------------------------------------------------- B --------
    print("=" * 78)
    print("B. IS ROC-10 CROSS-SECTIONALLY INFORMATIVE?")
    print("   mean 21d forward return by ROC-10 cross-sectional quintile,")
    print("   first raw then momentum-matched (within mom126 quartile).")
    print("=" * 78)
    for wname, lo, hi in (("TRAIN", TRAIN_START, TRAIN_END),
                          ("TEST", TEST_START, TEST_END)):
        pct = r10.loc[lo:hi].rank(axis=1, pct=True)
        # pct in (0,1] -> quintile 0..4. The upper bin edge must exceed 1.0 or the
        # top-ranked name (rank pct == 1.0 exactly) falls into a spurious 6th bucket.
        # NaN must be mapped out too: `np.digitize` maps NaN to len(bins), i.e. the
        # TOP bucket, which would silently turn missing data into a strong signal.
        _p = pct.to_numpy(dtype=float)
        _q = np.where(np.isnan(_p), -1,
                      np.digitize(_p, [0.2, 0.4, 0.6, 0.8, 1.0000001]))
        quint = pd.DataFrame(_q, index=pct.index, columns=pct.columns)
        # NOTE: `pd.DataFrame({name: DataFrame})` is broken on pandas 3.0.5 (raises
        # "If using all scalar values, you must pass an index"). Stack first, then build
        # from Series, which works. See BUG-2 in REPORT.md.
        dd = pd.DataFrame({
            "fwd": fwd21.loc[lo:hi].stack(),
            "quint": quint.stack(),
            "mom": mom_full.loc[lo:hi].stack(),
        })
        dd.index = dd.index.swaplevel(0, 1)
        dd.index.names = ["sym", "date"]
        dd = dd.loc[
            (dd.index.get_level_values("date") >= lo)
            & (dd.index.get_level_values("date") <= hi)
            & (dd["quint"] >= 0)
        ].dropna()
        dd["momq"] = dd.groupby(level="date")["mom"].transform(
            lambda s: pd.qcut(s, 4, labels=False, duplicates="drop"))
        print(f"  --- {wname}  (n = {len(dd):,} symbol-day observations) ---")
        g = dd.groupby("quint")["fwd"].mean()
        n = dd.groupby("quint")["fwd"].count()
        print("    Q1 = weakest ROC-10 ... Q5 = strongest")
        for i in range(len(g)):
            print(f"      Q{i + 1}: mean 21d forward return {g.iloc[i] * 100:+6.3f}%   "
                  f"n = {int(n.iloc[i]):,}")
        raw = float((g.iloc[-1] - g.iloc[0]) * 100)
        gm = dd.groupby(["momq", "quint"])["fwd"].mean().unstack()
        sp = gm[4] - gm[0]
        print(f"    raw Q5 - Q1 spread                : {raw:+.3f} pp per 21d")
        print("    momentum-matched spread, by mom quartile (Q5 - Q1):")
        print("      " + "   ".join(
            f"momQ{i + 1} {v * 100:+.3f}pp" for i, v in enumerate(sp)))
        print(f"    mean over mom quartiles           : {float(sp.mean()) * 100:+.3f} pp"
              f" per 21d")
        OUT.setdefault("quintile", {})[wname] = {
            "raw_spread_pp": raw,
            "mom_matched_spread_pp": float(sp.mean()) * 100,
            "n": int(len(dd)),
        }
    print()

    # ---------------------------------------------------------------- C --------
    print("=" * 78)
    print("C. PAIRED MONTHLY EXCESS vs the random-eligibility null")
    print("=" * 78)
    roc_eq = (1 + res_by["ROC gate + mom rank, TEST"].returns).cumprod()
    roc_m = roc_eq.resample("ME").last().pct_change()
    roc_m.iloc[0] = roc_eq.iloc[0] - 1.0
    n_rand = 20
    rand_m = []
    for s in range(n_rand):
        e = (1 + random_book(test, s, frac).returns).cumprod()
        m = e.resample("ME").last().pct_change()
        m.iloc[0] = e.iloc[0] - 1.0
        rand_m.append(m)
    rand_mean = pd.concat(rand_m, axis=1).mean(axis=1)
    exc = (roc_m - rand_mean).dropna()
    t = float(exc.mean() / (exc.std(ddof=1) / np.sqrt(len(exc))))
    print(f"  months compared      : {len(exc)}")
    print(f"  ROC monthly mean     : {roc_m.mean() * 100:+.3f}%")
    print(f"  random-book monthly  : {rand_mean.mean() * 100:+.3f}%")
    print(f"  mean monthly excess  : {exc.mean() * 100:+.3f}%")
    print(f"  positive in          : {int((exc > 0).sum())} / {len(exc)} months")
    print(f"  paired t-stat        : {t:+.2f}  "
          f"({'not significant at 5%' if abs(t) < 1.96 else 'significant'})")
    OUT["paired"] = {"n": len(exc), "mean": float(exc.mean()), "pos": int((exc > 0).sum()),
                     "t": t}
    print()

    # ---------------------------------------------------------------- D --------
    print("=" * 78)
    print("D. YEAR-BY-YEAR — what did the book actually do, and against what?")
    print("=" * 78)
    r = res_by["ROC gate + mom rank, TEST"]
    eq = r.equity
    mkt = panel.pct_change(fill_method=None).mean(axis=1)          # daily EW market ret
    mkt_eq = (1 + mkt.fillna(0.0)).cumprod()
    bh = buy_and_hold(test)   # cost-charged, same basis as §5.3 of s2_test.py

    def by_year(s: pd.Series) -> pd.Series:
        e = s.resample("YE").last()
        out = e.pct_change()
        out.iloc[0] = e.iloc[0] - 1.0
        return out

    roc_y, mkt_y, bh_y = by_year(eq), by_year(mkt_eq), by_year(bh)
    names = r.weights.gt(0).sum(axis=1)
    invested = r.weights.sum(axis=1)
    print("  yr   ROC book   EW market   buy&hold(48)   avg names   invested")
    for y in roc_y.index:
        w = r.weights.loc[str(y.year)]
        print(f"  {y.year}  {roc_y.loc[y] * 100:+7.2f}%   {mkt_y.loc[y] * 100:+7.2f}%"
              f"    {bh_y.loc[y] * 100:+7.2f}%        "
              f"{names.loc[str(y.year)].mean():5.1f}      "
              f"{(invested.loc[str(y.year)] * 100).mean():5.1f}%")
    OUT["yearly"] = {"roc": {str(k): float(v) for k, v in roc_y.items()},
                     "market": {str(k): float(v) for k, v in mkt_y.items()},
                     "buy_hold": {str(k): float(v) for k, v in bh_y.items()}}
    print()

    flag = sig.loc[TEST_START:TEST_END].sum(axis=1)
    print(f"  bars with fewer than 22 names passing the gate: "
          f"{float((flag < 22).mean()) * 100:.1f}%  (min {int(flag.min())}, "
          f"mean {flag.mean():.1f})")
    m10 = panel.mean(axis=1) / panel.mean(axis=1).shift(10) - 1.0
    for wname, lo, hi in (("TRAIN", TRAIN_START, TRAIN_END), ("TEST", TEST_START, TEST_END)):
        print(f"  {wname}: equal-weight market ROC10 > 0 on "
              f"{float(m10.loc[lo:hi].gt(0).mean()) * 100:.1f}% of bars; universe "
              f"ROC10 > 0 on {float(r10.loc[lo:hi].gt(0).mean().mean()) * 100:.1f}% of cells")
    corr = float(np.corrcoef(
        m10.loc[TEST_START:TEST_END].fillna(0).to_numpy(),
        np.sign(r.returns).to_numpy())[0, 1])
    print(f"  corr(universe-mean ROC10, sign of daily book P&L) on TEST = {corr:+.3f}")
    print("  -> the gate is close to a market-direction overlay: it was in the market")
    print("     61.4% of TRAIN bars and 55.8% of TEST bars.")
    print()

    # ---------------------------------------------------------------- E --------
    print("=" * 78)
    print(f"E. {NULL_SEEDS}-SEED NULL — the gate vs a coin at the same exposure")
    print("=" * 78)
    prim = res_by["ROC gate + mom rank, TEST"].metrics
    cc, cs, cd, cn = [], [], [], []
    for s in range(NULL_SEEDS):
        rb = coin_book(test, s, frac)
        cc.append(rb.metrics.cagr)
        cs.append(rb.metrics.sharpe)
        cd.append(rb.metrics.max_drawdown)
        cn.append(rb.diag["avg_names"])
    cc, cs, cd, cn = (np.array(x) for x in (cc, cs, cd, cn))
    print(f"  matched long fraction (bar/symbol cells flagged) = {frac * 100:.2f}%")
    print(f"  true coin    CAGR {cc.mean() * 100:6.2f}% ± {cc.std(ddof = 1) * 100:.2f}"
          f"   Sharpe {cs.mean():+.2f} ± {cs.std(ddof = 1):.2f}   "
          f"MaxDD {cd.mean() * 100:6.2f}%   names {cn.mean():.1f}")
    print(f"  ROC V3_wide  CAGR {prim.cagr * 100:6.2f}%              "
          f"        Sharpe {prim.sharpe:+.2f}         "
          f"MaxDD {prim.max_drawdown * 100:6.2f}%   "
          f"names {res_by['ROC gate + mom rank, TEST'].diag['avg_names']:.1f}")
    pct_c = float((cc < prim.cagr).mean() * 100)
    pct_s = float((cs < prim.sharpe).mean() * 100)
    pct_d = float((cd < prim.max_drawdown).mean() * 100)
    z_c = float((prim.cagr - cc.mean()) / cc.std(ddof=1))
    z_s = float((prim.sharpe - cs.mean()) / cs.std(ddof=1))
    print(f"  ROC percentile inside the coin null : CAGR {pct_c:.0f}th   "
          f"Sharpe {pct_s:.0f}th   MaxDD {pct_d:.0f}th (0th = worst of 100)")
    print(f"  z vs the coin                      : CAGR {z_c:+.2f}   Sharpe {z_s:+.2f}")
    OUT["coin_null"] = {
        "cagr_mean": float(cc.mean()), "cagr_sd": float(cc.std(ddof=1)),
        "sharpe_mean": float(cs.mean()), "sharpe_sd": float(cs.std(ddof=1)),
        "maxdd_mean": float(cd.mean()), "names_mean": float(cn.mean()),
        "pct_cagr": pct_c, "pct_sharpe": pct_s, "pct_maxdd": pct_d,
        "z_cagr": z_c, "z_sharpe": z_s, "frac_long": frac,
    }
    print()

    # ---------------------------------------------------------------- F --------
    print("=" * 78)
    print("F. GATE TIMING — is 'market up over 10 days' actually a useful overlay?")
    print("   For each month, fraction of the universe passing the gate, and the")
    print("   equal-weight market's return over the NEXT month.")
    print("=" * 78)
    mkt_d = panel.pct_change(fill_method=None).mean(axis=1)
    mkt_eq = (1 + mkt_d.fillna(0.0)).cumprod()
    flag_frac = sig.mean(axis=1)
    for wname, lo, hi in (("TRAIN", TRAIN_START, TRAIN_END), ("TEST", TEST_START, TEST_END)):
        f = flag_frac.loc[lo:hi]
        me = mkt_eq.loc[lo:hi]
        fwd_m = me.shift(-21) / me - 1.0          # market return over the next 21 bars
        d = pd.concat([f.rename("frac"), fwd_m.rename("fwd_m")], axis=1).dropna()
        d["bucket"] = pd.qcut(d["frac"], 4, labels=False, duplicates="drop")
        g = d.groupby("bucket").agg(frac_lo=("frac", "min"), frac_hi=("frac", "max"),
                                    fwd=("fwd_m", "mean"), n=("fwd_m", "count"))
        print(f"  --- {wname} ---")
        for _i, rw in g.iterrows():
            print(f"    gate pass-rate {rw['frac_lo'] * 100:5.1f}%-{rw['frac_hi'] * 100:5.1f}%"
                  f"  ->  mean next-21d market return {rw['fwd'] * 100:+6.2f}%   "
                  f"n = {int(rw['n'])}")
        corr = float(d["frac"].corr(d["fwd_m"]))
        print(f"    corr(gate pass-rate, next-21d market return) = {corr:+.3f}")
        OUT.setdefault("gate_timing", {})[wname] = {
            "corr": corr,
            "buckets": {str(i): {"lo": float(rw["frac_lo"]), "hi": float(rw["frac_hi"]),
                                 "fwd_market": float(rw["fwd"]), "n": int(rw["n"])}
                        for i, rw in g.iterrows()},
        }
    print()

    with open("posthoc_results.json", "w") as f:
        json.dump(OUT, f, indent=2, default=str)
    print("wrote posthoc_results.json")


if __name__ == "__main__":
    main()
