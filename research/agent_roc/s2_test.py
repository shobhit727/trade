"""Step 2 — TEST. Touched exactly once, at the end, with the TRAIN winner frozen.

Everything the report needs from the TEST window is produced in this one script so the
window is entered a single time.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    CFG,
    COST,
    ENGINE_SHA,
    HEADER,
    TEST_END,
    TEST_START,
    build_composite_score,
    build_score,
    buy_and_hold,
    coin_book,
    compute_metrics,
    fmt_yearly,
    load,
    random_book,
    roc_signal,
    row,
    run_backtest,
    yearly_returns,
)
from s1_train import VARIANTS

OUT: dict = {"_engine_sha": ENGINE_SHA}
NULL_SEEDS = 100


def main() -> None:
    panel, symbols, _ = load()
    test = panel.loc[TEST_START:TEST_END]

    print("=" * 78)
    print(f"TEST (OUT-OF-SAMPLE)  {TEST_START.date()} -> {TEST_END.date()}")
    print(f"engine {ENGINE_SHA}   panel {test.shape[0]} bars x {test.shape[1]} symbols")
    print("=" * 78)
    print()

    # ---------------------------------------------------------------- 5.1 ------
    print("### 5.1  PRIMARY RESULT — frozen TRAIN winner V3_wide "
          "(period 10, threshold 0.0, monthly, rank mom126)")
    sig_w = roc_signal(panel, 10, 0.0)
    score_w = build_score(panel, sig_w, "mom126").loc[TEST_START:TEST_END]
    res_w = run_backtest(test, score_w, COST, CFG, rebalance="M")
    m = res_w.metrics
    print(row("V3_wide  [PRIMARY]", m, {"names": f"{res_w.diag['avg_names']:.1f}"}))
    print(f"  rt_bps charged   : {res_w.diag['round_trip_bps']}")
    print(f"  engine_sha       : {res_w.engine_sha}")
    print(f"  total return     : {m.total_return * 100:.2f}%")
    print(f"  vol (ann)        : {m.volatility * 100:.2f}%")
    print(f"  sortino          : {m.sortino:.2f}")
    print(f"  win rate         : {m.win_rate * 100:.1f}%")
    print(f"  max DD days      : {m.max_drawdown_days}")
    print("  years            : "
          + fmt_yearly(res_w.returns))
    yrs = yearly_returns(res_w.returns)
    print(f"  positive years   : {int((yrs > 0).sum())} / {len(yrs)}")
    print(f"  bar long frac    : {float(sig_w.loc[TEST_START:TEST_END].mean().mean()) * 100:.2f}%"
          f"   (TRAIN {float(sig_w.loc[:TEST_START].iloc[:-1].mean().mean()) * 100:.2f}%)")
    OUT["primary"] = {
        k: v for k, v in res_w.metrics.as_dict().items()
    } | {
        "avg_names": res_w.diag["avg_names"],
        "rt_bps": res_w.diag["round_trip_bps"],
        "engine_sha": res_w.engine_sha,
        "bar_long_frac": float(sig_w.loc[TEST_START:TEST_END].mean().mean()),
        "yearly": {str(k): float(v) for k, v in yrs.items()},
    }
    print()

    # ---------------------------------------------------------------- 5.2 ------
    print("### 5.2  Whole declared family on TEST — FAMILY DIAGNOSTIC, NOT A SELECTION")
    print(HEADER)
    fam = {}
    for name, (p, thr, reb, rank) in VARIANTS.items():
        sc = build_score(panel, roc_signal(panel, p, thr), rank).loc[TEST_START:TEST_END]
        r = run_backtest(test, sc, COST, CFG, rebalance=reb)
        fam[name] = r
        print(row(name, r.metrics, {"names": f"{r.diag['avg_names']:.1f}"}))
        OUT.setdefault("family", {})[name] = r.metrics.as_dict()
    print()
    print("  (for reference the TRAIN Sharpes were: "
          + ", ".join(
              f"{k}={v:.2f}" for k, v in {
                  'V1_base': 0.63, 'V2_tight': 0.28, 'V3_wide': 0.88,
                  'V4_week': 0.09, 'V5_raw': 0.38}.items()) + ")")
    print()

    # ---------------------------------------------------------------- 5.3 ------
    print("### 5.3  Buy-and-hold over the identical TEST window (brief §4 rule 5)")
    bh_eq = buy_and_hold(test)
    bh_m = compute_metrics(bh_eq.pct_change(fill_method=None).fillna(0.0), bh_eq)
    print(row("buy_and_hold (48, unconstrained)", bh_m))
    print("  years            : " + fmt_yearly(bh_eq.pct_change().fillna(0.0)))
    OUT["buy_hold"] = bh_m.as_dict()

    comp = build_composite_score(panel).loc[TEST_START:TEST_END]
    res_c = run_backtest(test, comp, COST, CFG, rebalance="M")
    print(row("nsealgo composite", res_c.metrics,
              {"names": f"{res_c.diag['avg_names']:.1f}"}))
    OUT["composite"] = res_c.metrics.as_dict() | {"avg_names": res_c.diag["avg_names"]}
    print()
    OUT["buy_hold_equity"] = bh_eq
    OUT["primary_equity"] = res_w.equity
    OUT["family_returns"] = {k: v.returns for k, v in fam.items()}
    OUT["primary_returns"] = res_w.returns

    # ---------------------------------------------------------------- 5.4 ------
    print()
    print("### 5.4  TEST vs buy-and-hold / composite")
    print(f"{'':22s} {'CAGR':>8s} {'Sharpe':>8s} {'MaxDD':>9s} {'Calmar':>7s}")
    for lab, mm in (("ROC V3_wide", m), ("buy-and-hold", bh_m),
                    ("nsealgo composite", res_c.metrics)):
        print(f"{lab:22s} {mm.cagr * 100:7.2f}% {mm.sharpe:8.2f} "
              f"{mm.max_drawdown * 100:8.2f}% {mm.calmar:7.2f}")
    print(f"{'delta vs B&H':22s} "
          f"{(m.cagr - bh_m.cagr) * 100:+7.2f}pp {m.sharpe - bh_m.sharpe:+8.2f} "
          f"{(m.max_drawdown - bh_m.max_drawdown) * 100:+8.2f}pp "
          f"{m.calmar - bh_m.calmar:+7.2f}")
    print(f"{'delta vs composite':22s} "
          f"{(m.cagr - res_c.metrics.cagr) * 100:+7.2f}pp "
          f"{m.sharpe - res_c.metrics.sharpe:+8.2f} "
          f"{(m.max_drawdown - res_c.metrics.max_drawdown) * 100:+8.2f}pp "
          f"{m.calmar - res_c.metrics.calmar:+7.2f}")
    print()

    # ---------------------------------------------------------------- 5.5 ------
    print(f"### 5.5  NEGATIVE CONTROLS — {NULL_SEEDS}-seed random nulls on TEST")
    frac = float(sig_w.loc[TEST_START:TEST_END].mean().mean())

    def stats(vals):
        v = np.array(vals)
        return (v.mean(), v.std(ddof=1), np.percentile(v, 5), np.percentile(v, 50),
                np.percentile(v, 95))

    rb_cagr, rb_shp, rb_dd = [], [], []
    for s in range(NULL_SEEDS):
        r = random_book(test, s, frac)
        rb_cagr.append(r.metrics.cagr)
        rb_shp.append(r.metrics.sharpe)
        rb_dd.append(r.metrics.max_drawdown)
    cb_cagr, cb_shp = [], []
    for s in range(1000, 1000 + NULL_SEEDS):
        r = coin_book(test, s, frac)
        cb_cagr.append(r.metrics.cagr)
        cb_shp.append(r.metrics.sharpe)

    for lab, c, sh in (("random-elig+mom126", rb_cagr, rb_shp),
                       ("true coin (random scores)", cb_cagr, cb_shp)):
        cs = stats(c)
        ss = stats(sh)
        print(f"  {lab:24s} CAGR mean {cs[0] * 100:6.2f}% sd {cs[1] * 100:5.2f}  "
              f"p05 {cs[2] * 100:6.2f}% p50 {cs[3] * 100:6.2f}% p95 {cs[4] * 100:6.2f}%"
              f"   95% band [{cs[2] * 100:.2f}, {cs[4] * 100:.2f}]")
        print(f"  {'':24s} Sharpe mean {ss[0]:6.2f} sd {ss[1]:5.2f}  "
              f"p05 {ss[2]:6.2f} p50 {ss[3]:6.2f} p95 {ss[4]:6.2f}")

    for lab, c, sh in (("random-elig+mom126", rb_cagr, rb_shp),
                       ("true coin", cb_cagr, cb_shp)):
        c = np.array(c)
        sh = np.array(sh)
        pct_c = float((c < m.cagr).mean() * 100)
        pct_s = float((sh < m.sharpe).mean() * 100)
        z_c = (m.cagr - c.mean()) / c.std(ddof=1)
        z_s = (m.sharpe - sh.mean()) / sh.std(ddof=1)
        print(f"  ROC V3_wide  CAGR {m.cagr * 100:.2f}% Sharpe {m.sharpe:.2f}  vs {lab}:"
              f" percentile {pct_c:.0f}/{pct_s:.0f}   z {z_c:+.2f}/{z_s:+.2f}")
        OUT.setdefault("null", {})[lab] = {
            "cagr_mean": float(c.mean()), "cagr_sd": float(c.std(ddof=1)),
            "cagr_p05": float(np.percentile(c, 5)), "cagr_p95": float(np.percentile(c, 95)),
            "sharpe_mean": float(sh.mean()), "sharpe_sd": float(sh.std(ddof=1)),
            "pct_cagr": pct_c, "pct_sharpe": pct_s, "z_cagr": z_c, "z_sharpe": z_s,
        }

    # PAIRED MONTHLY EXCESS — moved to s3_posthoc.py §C.
    # The first version of this block ran here and returned NaN: it intersected a
    # PeriodIndex of months with a DatetimeIndex of bar dates, so the intersection was
    # empty (0/0 months) and the "t-statistic" it printed (+0.00) was meaningless.
    # s3 §C resamples both sides to month-ends first and is the version reported.
    print("  paired monthly excess: see s3_posthoc.py section C (this block was buggy)")
    print()

    # ---------------------------------------------------------------- 5.6 ------
    print("### 5.6  COST DRAG (brief §6.4) — same signal, cost model varied")
    print(HEADER)
    from nsealgo.costs import STRESS_MODELS

    for label, cm in STRESS_MODELS.items():
        r = run_backtest(test, score_w, cm, CFG, rebalance="M")
        print(row(label, r.metrics))
        OUT.setdefault("cost_stress", {})[label] = r.metrics.as_dict() | {
            "rt_bps": r.diag["round_trip_bps"]}
    print()

    # ---------------------------------------------------------------- 5.7 ------
    print("### 5.7  Brief §6 sanity checks")
    print(f"  1 plausibility   CAGR {m.cagr * 100:.2f}% "
          f"({'OK' if m.cagr < 0.5 else 'BUG'}) — unlevered long-only NIFTY-50 cap ~40-50%")
    print(f"  2 weight count  avg names {res_w.diag['avg_names']:.1f} "
          f"({'OK' if res_w.diag['avg_names'] < 25 else 'CHECK'}) — cap is 22, universe 48")
    print(f"  3 liveness      {float(sig_w.loc[TEST_START:TEST_END].mean().mean()) * 100:.2f}%"
          f" of bar/symbol cells flagged ({'OK' if frac > 0.05 else 'TOO DEAD'})")
    print(f"  4 cost drag     {m.cost_drag_annual * 100:.2f}%/y vs CAGR {m.cagr * 100:.2f}%"
          f" -> gross {m.cagr * 100 + m.cost_drag_annual * 100:.2f}%")
    print("  5 random ctrl   see §5.5")
    print()

    with open("test_results.json", "w") as f:
        json.dump(OUT, f, indent=2, default=str)
    print("wrote test_results.json")


if __name__ == "__main__":
    main()
