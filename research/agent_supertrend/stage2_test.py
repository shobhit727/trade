"""Stage 2 — the single TEST evaluation of the frozen variant V4.

V4 (`st_p20_m3.0`) was selected on TRAIN Sharpe in `stage1_train.py` and is recorded in
`stage1_train.json`. This script re-derives it from that file, asserts the selection is
V4, and evaluates it once on TEST.

Per REPORT.md §4 (pre-declared before TEST was touched):

* **The single TEST verdict is V4's**, whatever it prints. No re-selection.
* The other four variants are also printed as a declared *family-robustness* check.
  This is an observation about the parameter family, not a selection step.
* Benchmarks on the identical window: equal-weight buy & hold, and nsealgo's
  `build_composite_score`.
* Negative control: random signal, same eligible-name count per rebalance, 30 seeds.

This script never writes to `stage1_train.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    as_shipped_signal,
    buy_and_hold,
    fmt_row,
    load_ohlc,
    momentum_score,
    random_control,
    run,
    summarise,
    supertrend_signal,
    window,
    year_table,
)

from nsealgo.factors.core import build_composite_score  # noqa: E402

HERE = Path(__file__).resolve().parent

VARIANTS = [
    ("V0", "as_shipped", None, None),
    ("V1", "st_p10_m3.0", 10, 3.0),
    ("V2", "st_p14_m3.0", 14, 3.0),
    ("V3", "st_p10_m2.0", 10, 2.0),
    ("V4", "st_p20_m3.0", 20, 3.0),
]

SELECTED = ("V4", "st_p20_m3.0", 20, 3.0)


def build_signal(close, high, low, period, mult):
    if period is None:
        return as_shipped_signal(close)
    return supertrend_signal(close, high, low, period, mult)


def main():
    # ---- freeze check: the selection must be the one recorded on TRAIN
    train = json.loads((HERE / "stage1_train.json").read_text())
    got = (train["selected"]["variant"], train["selected"]["label"])
    want = (SELECTED[0], SELECTED[1])
    assert got == want, f"selection drifted: TRAIN picked {got}, script expects {want}"
    print(f"FROZEN SELECTION (from stage1_train.json): {got[0]} {got[1]}")
    print("TEST window 2024-01-01 .. 2026-10-01 -- evaluated ONCE below.\n")

    close, high, low = load_ohlc()
    sigs = {vid: build_signal(close, high, low, p, m) for vid, _, p, m in VARIANTS}

    out = {"window": [str(TEST_START.date()), str(TEST_END.date())]}

    # ---- the verdict
    vid, name, p, m = SELECTED
    score = momentum_score(close, sigs[vid])
    res = run(close, score, TEST_START, TEST_END)
    sel = summarise(res, close, name)
    s_test = window(sigs[vid], TEST_START, TEST_END)
    sel["live_frac_test"] = float((s_test > 0).to_numpy().mean())
    elig = s_test.where(s_test > 0).notna().sum(axis=1)
    sel["avg_eligible_test"] = float(elig.mean())
    sel["max_weight_breach"] = float(res.weights.max().max())
    sel["variant"] = vid

    print("=" * 100)
    print(f"TEST VERDICT  [{vid}] {name}")
    print("=" * 100)
    print("  " + fmt_row(sel))
    print(f"  live {sel['live_frac_test'] * 100:.1f}%  "
          f"avg eligible/rebalance {sel['avg_eligible_test']:.1f}  "
          f"rebalances {sel['n_rebalances']}")
    print(f"  gross Sharpe {sel['gross_sharpe']:.2f} -> net Sharpe {sel['sharpe']:.2f}  "
          f"(cost drag {sel['cost_drag'] * 100:.2f}%/yr)")
    out["selected_test"] = sel

    # ---- benchmark: buy & hold, identical window
    bench = buy_and_hold(close, TEST_START, TEST_END)
    bench_r = bench.pop("returns")
    print("\n  " + fmt_row(bench))
    out["buy_and_hold_test"] = bench

    # ---- benchmark: nsealgo composite
    comp_score = build_composite_score(close)
    comp_res = run(close, comp_score, TEST_START, TEST_END)
    comp = summarise(comp_res, close, "nsealgo_composite")
    print("  " + fmt_row(comp))
    out["composite_test"] = comp

    # ---- family robustness (pre-declared, NOT a selection step)
    print("\n" + "-" * 100)
    print("FAMILY ROBUSTNESS on TEST (pre-declared observation, NOT re-selection; "
          "verdict stays V4)")
    fam = []
    for v_id, v_name, _v_p, _v_m in VARIANTS:
        if (v_id, v_name) == (vid, name):
            row = dict(sel)
        else:
            sc = momentum_score(close, sigs[v_id])
            row = summarise(run(close, sc, TEST_START, TEST_END), close, v_name)
        row["variant"] = v_id
        fam.append(row)
        print("  " + fmt_row(row))
    out["family_test"] = fam

    # ---- negative control: random signal, same eligible count per rebalance
    print("\n" + "-" * 100)
    print(f"NEGATIVE CONTROL: random signal, same eligible count per rebalance "
          f"(as {vid}), {30} seeds")
    rc = random_control(close, elig, TEST_START, TEST_END, seeds=30)
    arr = np.array([[r["cagr"], r["sharpe"], r["max_drawdown"], r["avg_names"],
                     r["cost_drag"]] for r in rc])
    out["random_control"] = {
        "n_seeds": len(rc),
        "cagr_mean": float(arr[:, 0].mean()),
        "cagr_std": float(arr[:, 0].std(ddof=1)),
        "cagr_p5": float(np.percentile(arr[:, 0], 5)),
        "cagr_p95": float(np.percentile(arr[:, 0], 95)),
        "sharpe_mean": float(arr[:, 1].mean()),
        "sharpe_std": float(arr[:, 1].std(ddof=1)),
        "maxdd_mean": float(arr[:, 2].mean()),
        "avg_names_mean": float(arr[:, 3].mean()),
        "cost_drag_mean": float(arr[:, 4].mean()),
        "pct_seeds_below_selected_cagr": float(
            (arr[:, 0] < sel["cagr"]).mean()
        ),
        "pct_seeds_below_selected_sharpe": float(
            (arr[:, 1] < sel["sharpe"]).mean()
        ),
        "rows": rc,
    }
    o = out["random_control"]
    print(f"  random CAGR     mean {o['cagr_mean'] * 100:>6.2f}%  sd {o['cagr_std'] * 100:.2f}%  "
          f"p5 {o['cagr_p5'] * 100:.2f}%  p95 {o['cagr_p95'] * 100:.2f}%")
    print(f"  random Sharpe   mean {o['sharpe_mean']:>6.3f}  sd {o['sharpe_std']:.3f}")
    print(f"  random MaxDD    mean {o['maxdd_mean'] * 100:>6.2f}%   "
          f"avg names {o['avg_names_mean']:.1f}  drag {o['cost_drag_mean'] * 100:.2f}%/y")
    print(f"  seeds beaten by {vid}: CAGR {o['pct_seeds_below_selected_cagr'] * 100:.0f}%  "
          f"Sharpe {o['pct_seeds_below_selected_sharpe'] * 100:.0f}%")

    # ---- yearly returns vs benchmark
    print("\n" + "-" * 100)
    print("CALENDAR-YEAR RETURNS (TEST)")
    yt = year_table(res.returns, bench_r)
    yt["composite"] = pd.Series(yearly_returns_safe(comp_res.returns), index=yt.index)
    for yr, r in yt.iterrows():
        print(f"  {yr}  strategy {r['strategy'] * 100:>7.2f}%   "
              f"equal-wt {r['equal_weight'] * 100:>7.2f}%   "
              f"composite {r['composite'] * 100:>7.2f}%   "
              f"alpha {r['alpha'] * 100:>7.2f}%")
    out["yearly"] = yt.to_dict(orient="index")

    # ---- head-to-head
    print("\n" + "=" * 100)
    print("HEAD TO HEAD (TEST)")
    print("=" * 100)
    d_cagr = sel["cagr"] - bench["cagr"]
    d_dd = sel["max_drawdown"] - bench["max_drawdown"]
    d_cal = sel["calmar"] - bench["calmar"]
    print(f"  CAGR      {sel['cagr'] * 100:>7.2f}% vs {bench['cagr'] * 100:.2f}%  "
          f"-> {d_cagr * 100:+.2f} pp")
    print(f"  MaxDD     {sel['max_drawdown'] * 100:>7.2f}% vs "
          f"{bench['max_drawdown'] * 100:.2f}%  -> {d_dd * 100:+.2f} pp "
          f"(positive = shallower)")
    print(f"  Calmar    {sel['calmar']:>7.2f} vs {bench['calmar']:.2f}  "
          f"-> {d_cal:+.2f}")
    print(f"  Sharpe    {sel['sharpe']:>7.2f} vs {bench['sharpe']:.2f}  "
          f"-> {sel['sharpe'] - bench['sharpe']:+.2f}")
    print(f"  vs nsealgo composite: CAGR {sel['cagr'] * 100:.2f}% vs "
          f"{comp['cagr'] * 100:.2f}%  Sharpe {sel['sharpe']:.2f} vs {comp['sharpe']:.2f}  "
          f"MaxDD {sel['max_drawdown'] * 100:.2f}% vs {comp['max_drawdown'] * 100:.2f}%")
    out["head_to_head"] = {
        "d_cagr_vs_bh": d_cagr,
        "d_maxdd_vs_bh": d_dd,
        "d_calmar_vs_bh": d_cal,
        "d_sharpe_vs_bh": sel["sharpe"] - bench["sharpe"],
        "vs_composite": {
            "d_cagr": sel["cagr"] - comp["cagr"],
            "d_sharpe": sel["sharpe"] - comp["sharpe"],
            "d_maxdd": sel["max_drawdown"] - comp["max_drawdown"],
        },
    }

    (HERE / "stage2_test.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {HERE / 'stage2_test.json'}")


def yearly_returns_safe(r):
    from nsealgo.backtest.metrics import yearly_returns

    return yearly_returns(r)


if __name__ == "__main__":
    main()
