"""Step 3 -- ablations and diagnostics. NO parameter selection here.

Everything below runs AFTER the TEST number was produced and none of it can change the
verdict. These are ablations of the already-frozen V4 (remove one component at a time)
plus diagnostics that answer "why did it fail?". None of them is a 6th variant: no new
`period` is tried and no alternative selection rule is applied. This is the honest
reading of the frozen result, not a search for a better one.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from harness import (
    COST_MODEL,
    HERE,
    RANKERS,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    ZERO_COST,
    build_score,
    buy_and_hold,
    composite,
    fmt,
    load_panel,
    run,
    signal_panel,
    summarise,
)

OUT: dict = {}


def ablations(panel_full: pd.DataFrame, period: int, ranker: str) -> dict:
    """V4 with one component removed. Both directions."""
    res = {}
    mom = RANKERS[ranker](panel_full)

    # (a) GATE ABLATION: the momentum ranking with NO TEMA gate at all.
    score_nogate = mom.rank(axis=1, pct=True)
    for wname, (s, e) in {
        "TRAIN": (TRAIN_START, TRAIN_END),
        "TEST": (TEST_START, TEST_END),
    }.items():
        r = run(panel_full.loc[:e].loc[s:], score_nogate.loc[:e].loc[s:], COST_MODEL)
        res[f"no_gate_{wname}"] = summarise(r, f"ABLATION no-TEMA-gate [{wname}]")

    # (b) RANKING ABLATION: the TEMA gate, ranked by the gate strength itself
    #     (distance above TEMA) instead of by momentum. Same 22-name book.
    sig = signal_panel(panel_full, period)
    dist = (panel_full - build_tema(panel_full, period)) / panel_full
    score_distrank = dist.where(sig > 0).rank(axis=1, pct=True)
    for wname, (s, e) in {
        "TRAIN": (TRAIN_START, TRAIN_END),
        "TEST": (TEST_START, TEST_END),
    }.items():
        r = run(panel_full.loc[:e].loc[s:], score_distrank.loc[:e].loc[s:], COST_MODEL)
        res[f"no_momentum_rank_{wname}"] = summarise(r, f"ABLATION no-mom-rank [{wname}]")

    # (c) the frozen V4 on both windows, for the ablation table
    sc = build_score(panel_full, period, ranker)
    for wname, (s, e) in {
        "TRAIN": (TRAIN_START, TRAIN_END),
        "TEST": (TEST_START, TEST_END),
    }.items():
        r = run(panel_full.loc[:e].loc[s:], sc.loc[:e].loc[s:], COST_MODEL)
        res[f"v4_{wname}"] = summarise(r, f"V4 FROZEN [{wname}]")
    return res


def build_tema(panel, period):
    from harness import tema_panel

    return tema_panel(panel, period)


def gate_information(panel_full: pd.DataFrame, period: int) -> dict:
    """Does the TEMA gate itself predict forward returns, cross-sectionally?

    For every symbol-day, bucket by (gate state) x (quintile of 21d forward return) and
    measure the spread. If the gate has no standalone information, that is the finding.
    """
    sig = signal_panel(panel_full, period)
    fwd = (panel_full.shift(-21) / panel_full - 1.0).stack(future_stack=True)
    state = pd.DataFrame(
        np.where(sig > 0, "above_TEMA", np.where(sig < 0, "below_TEMA", "warmup")),
        index=sig.index, columns=sig.columns,
    ).stack(future_stack=True)
    d = pd.DataFrame({"state": state, "fwd": fwd}).dropna()
    out = {}
    for st, g in d.groupby("state"):
        if len(g) < 500:
            continue
        q = pd.qcut(g["fwd"], 5, labels=False, duplicates="drop")
        means = g.groupby(q)["fwd"].mean()
        out[st] = {
            "n": int(len(g)),
            "mean_fwd": float(g["fwd"].mean()),
            "hit_rate": float((g["fwd"] > 0).mean()),
            "q1": float(means.iloc[0]), "q5": float(means.iloc[-1]),
            "q5_minus_q1": float(means.iloc[-1] - means.iloc[0]),
            "q5_minus_q1_ann": float((means.iloc[-1] - means.iloc[0]) * 244 / 21),
        }
    # Is the gate state itself informative? difference of the two states' means.
    if "above_TEMA" in out and "below_TEMA" in out:
        out["gate_state_edge_ann"] = float(
            (out["above_TEMA"]["mean_fwd"] - out["below_TEMA"]["mean_fwd"]) * 244 / 21
        )
    return out


def main() -> None:
    with open(os.path.join(HERE, "selected.json")) as f:
        sel = json.load(f)
    period, ranker = sel["period"], sel["rank"]
    panel_full = load_panel()

    print("=== ABLATIONS (post-TEST; explanatory only, cannot change the verdict) ===")
    ab = ablations(panel_full, period, ranker)
    for k in ("v4_TRAIN", "no_gate_TRAIN", "no_momentum_rank_TRAIN"):
        print("  " + fmt(ab[k]))
    print()
    for k in ("v4_TEST", "no_gate_TEST", "no_momentum_rank_TEST"):
        print("  " + fmt(ab[k]))
    OUT["ablations"] = ab

    print("\n=== DOES THE TEMA GATE CARRY INFORMATION? (full panel, 21d forward) ===")
    gi = gate_information(panel_full, period)
    for k, v in gi.items():
        if k == "gate_state_edge_ann":
            continue
        print(f"  {k:<12} n={v['n']:>7}  mean fwd {v['mean_fwd'] * 100:>6.3f}%  "
              f"hit {v['hit_rate'] * 100:>5.1f}%  Q5-Q1 {v['q5_minus_q1'] * 100:>6.3f}% "
              f"({v['q5_minus_q1_ann'] * 100:>6.2f}% ann.)")
    if "gate_state_edge_ann" in gi:
        print(f"  >>> gate-state edge (above minus below TEMA, annualised): "
              f"{gi['gate_state_edge_ann'] * 100:+.2f}%  "
              f"<- THE headline: is being above TEMA worth anything?")
    OUT["gate_information"] = gi

    # ---- beta / tracking vs buy-and-hold on TEST ---------------------------
    with open(os.path.join(HERE, "test_results.json")) as f:
        tr = json.load(f)
    te = panel_full.loc[:TEST_END].loc[TEST_START:]
    bh = buy_and_hold(te, COST_MODEL)
    sc = build_score(panel_full, period, ranker).loc[:TEST_END].loc[TEST_START:]
    res = run(te, sc, COST_MODEL)
    sr = res.returns
    br = bh["equity_net"].pct_change(fill_method=None).fillna(0.0).reindex(sr.index)
    comp = composite(panel_full, COST_MODEL, start=TEST_START, end=TEST_END)
    cr = comp["returns"].reindex(sr.index)
    beta = float(np.cov(sr, br, ddof=1)[0, 1] / np.var(br, ddof=1))
    corr = float(np.corrcoef(sr, br)[0, 1])
    up = sr[br > 0].mean()
    dn = sr[br < 0].mean()
    bh_up = br[br > 0].mean()
    bh_dn = br[br < 0].mean()
    print("\n=== BEHAVIOUR ON UP vs DOWN DAYS (TEST) ===")
    print(f"  beta vs B&H {beta:.2f}   corr {corr:.2f}")
    print(f"  on B&H up days   : strategy {up * 100:>6.3f}%   B&H {bh_up * 100:>6.3f}%")
    print(f"  on B&H down days : strategy {dn * 100:>6.3f}%   B&H {bh_dn * 100:>6.3f}%")
    print(f"  capture ratio up   {up / bh_up:.2f}    down {dn / bh_dn:.2f}")
    print(f"  corr(strategy, composite) {float(np.corrcoef(sr, cr)[0, 1]):.3f}   "
          f"corr(composite, B&H) {float(np.corrcoef(cr, br)[0, 1]):.3f}")
    OUT["behaviour"] = {
        "beta_vs_bh": beta, "corr_vs_bh": corr,
        "up_day_strategy": float(up), "up_day_bh": float(bh_up),
        "down_day_strategy": float(dn), "down_day_bh": float(bh_dn),
        "capture_up": float(up / bh_up), "capture_down": float(dn / bh_dn),
        "corr_strategy_composite": float(np.corrcoef(sr, cr)[0, 1]),
        "corr_composite_bh": float(np.corrcoef(cr, br)[0, 1]),
    }

    # ---- cost decomposition on TEST ---------------------------------------
    s0 = summarise(run(te, sc, ZERO_COST), "V4 zero-cost")
    print("\n=== COST DECOMPOSITION (TEST, frozen V4) ===")
    print(f"  gross of all trading cost : CAGR {s0['cagr'] * 100:>6.2f}%  "
          f"Sharpe {s0['sharpe']:>5.2f}  MaxDD {s0['max_drawdown'] * 100:>6.2f}%")
    print(f"  net of 21.92 bps          : CAGR {tr['strategy']['cagr'] * 100:>6.2f}%  "
          f"Sharpe {tr['strategy']['sharpe']:>5.2f}  MaxDD {tr['strategy']['max_drawdown'] * 100:>6.2f}%")
    print(f"  => cost costs {((s0['cagr'] - tr['strategy']['cagr']) * 100):.2f} pp/yr of CAGR")
    print(f"  => even GROSS it underperforms B&H gross "
          f"({bh['cagr_gross'] * 100:.2f}%) by "
          f"{((s0['cagr'] - bh['cagr_gross']) * 100):.2f} pp/yr "
          "-- COSTS ARE NOT THE REASON THIS FAILS.")
    OUT["cost_decomposition"] = {
        "gross_cagr": s0["cagr"], "gross_sharpe": s0["sharpe"],
        "net_cagr": tr["strategy"]["cagr"],
        "cost_cost_pp": (s0["cagr"] - tr["strategy"]["cagr"]),
        "bh_gross_cagr": bh["cagr_gross"],
        "gross_vs_bh_pp": s0["cagr"] - bh["cagr_gross"],
    }

    with open(os.path.join(HERE, "diagnostics.json"), "w") as f:
        json.dump(OUT, f, indent=2, default=str)
    print("\nwrote diagnostics.json")


if __name__ == "__main__":
    main()
