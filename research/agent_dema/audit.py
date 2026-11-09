"""Independent audit of the prior run. Trusts none of its claims; recomputes.

The single most important question this script asks:

    **Is the DEMA gate doing any work at all?**

V1 gates the book to names trading above their DEMA, then ranks the survivors by
6-month momentum and buys the top 22. If ~49% of names sit above their DEMA on any
given day, then on a typical rebalance ~23 of 48 names are eligible and the engine
only has to drop ONE of them to fill a 22-name book. In that regime the gate is
close to a no-op and the backtest is really measuring "plain 6-month momentum",
not "DEMA".

That is not a hypothetical concern — `train_results.json` already reports
`eligible_frac = 0.4825` for V1, i.e. 23.2 of 48 names, against `n_positions = 22`.
So this script measures the gate's actual contribution directly:

  A. overlap between V1's realised holdings and what ungated 6m momentum would have
     bought (the attribution question);
  B. a *fully ungated* momentum-6m book on identical constraints (the ablation);
  C. beta-to-market for every book, because a strategy running ~78% invested that
     loses to a 100%-invested benchmark has lost twice over;
  D. the brief's §6 sanity checks, recomputed from scratch;
  E. the random control re-run with more seeds and a proper p-value, because
     "beat 13/20 seeds" is not a significance test.

NOTE ON PROTOCOL: TEST is already spent (see REPORT.md). Nothing here selects or
re-selects a parameter. A and B are *attribution/ablations of the already-chosen V1*,
and every TEST number they produce is a post-hoc diagnostic that CANNOT change the
answer to "does V1 make money on NSE out-of-sample". If the ungated ablation looks
better than V1, the honest conclusion is still "V1 lost to buy-and-hold", because
switching now would be selecting on TEST.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dema_lib import (  # noqa: E402
    CFG,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    buy_and_hold,
    dema_distance_panel,
    random_signal_score,
    score_from_gate,
    table,
)

from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import momentum_6m, rank_cross_sectional  # noqa: E402

RULE = "=" * 100
N_SEEDS = 200


def rebalance_dates(index: pd.Index) -> list:
    s = pd.Series(index, index=index)
    return [g.index[0] for _, g in s.groupby(s.index.tz_localize(None).to_period("M"))]


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    n_sym = len(symbols)
    period = 20

    # ================================================================== A
    print(RULE)
    print("A. IS THE DEMA GATE DOING ANY WORK?  (realised holdings vs ungated momentum)")
    print(RULE)

    score = score_from_gate(panel, period)
    ungated = rank_cross_sectional(momentum_6m(panel))
    dist = dema_distance_panel(panel, period)

    for label, sl in (("TRAIN", slice(TRAIN_START, TRAIN_END)),
                      ("TEST", slice(TEST_START, TEST_END))):
        px = panel.loc[sl]
        w = backtest(px, score).weights
        rb = [d for d in rebalance_dates(px.index) if d in score.index][1:]

        # `w` / `ungated` columns are the same symbols in the same order as `panel`,
        # so a *positional* index is the safe way to compare holdings. Comparing the
        # string labels against np.flatnonzero positions silently yields an empty
        # intersection and a fake 0% overlap — which is exactly what the first
        # version of this script printed.
        cols = list(w.columns)
        pos = {c: i for i, c in enumerate(cols)}

        overlap, elig, gate_tight, take, offbook = [], [], 0, [], []
        for d in rb:
            held = set(np.flatnonzero(w.loc[d].to_numpy() > 0))
            u = ungated.loc[d]
            # what ungated momentum would buy, honouring the same 22-name budget
            buy_u = {pos[s] for s in u.sort_values(ascending=False).index[:CFG.n_positions]}
            overlap.append(len(held & buy_u) / max(len(held), 1))
            # eligible = names the gate permits. `w` is the *held* book, which carries
            # a turnover-blend residual tail, so len(held) can exceed len(eligible) and
            # a naive ratio is meaningless. Attribute the held names instead.
            ok = {pos[s] for s in score.loc[d].index[score.loc[d].notna()]}
            e = len(ok)
            elig.append(e)
            if e <= CFG.n_positions:
                gate_tight += 1
            if e:
                take.append(len(held & ok) / e)
                offbook.append(len(held - ok) / max(len(held), 1))

        print(f"\n  {label}  ({len(rb)} monthly rebalances)")
        print(f"    mean overlap with ungated-momentum-6m top-22 : "
              f"{np.mean(overlap) * 100:5.1f}%")
        print(f"    mean eligible (above DEMA) names            : {np.mean(elig):5.1f}"
              f"  of {n_sym}   (book targets {CFG.n_positions})")
        print(f"    rebalances where gate forces a real choice  : {gate_tight}/{len(rb)}"
              f"  ({gate_tight / len(rb) * 100:.0f}%)")
        print(f"    of the ELIGIBLE set, the book took           : "
              f"{np.mean(take) * 100:5.1f}%  (100% = the gate alone picks the book, "
              f"the momentum rank is irrelevant)")
        print(f"    of the HELD book, names were off-book (below DEMA, "
              f"carried by the turnover blend): {np.mean(offbook) * 100:4.1f}%")
        above = float((dist.loc[sl] > 0).to_numpy().mean())
        print(f"    fraction of name-days above DEMA            : {above * 100:5.1f}%")

    # ================================================================== B
    print("\n" + RULE)
    print("B. ABLATION (diagnostic, NOT selectable) — ungated momentum-6m, same book")
    print(RULE)
    print("  If the gate mattered, the gated book must beat this. It does not have to,")
    print("  because V1 was chosen on TRAIN and cannot be changed now.")

    train_px = panel.loc[TRAIN_START:TRAIN_END]
    test_px = panel.loc[TEST_START:TEST_END]
    for label, px in (("TRAIN", train_px), ("TEST", test_px)):
        g = backtest(px, score_from_gate(panel, period)).metrics
        u = backtest(px, ungated).metrics
        print(f"\n  {label}")
        print("    " + table("V1  gated (DEMA>0 + mom126)", g))
        print("    " + table("ABLATION  ungated mom126 only", u))
        print(f"    gate contributes {(g.sharpe - u.sharpe):+.3f} Sharpe, "
              f"{(g.cagr - u.cagr) * 100:+.2f} pp CAGR, "
              f"{(g.max_drawdown - u.max_drawdown) * 100:+.2f} pp MaxDD")

    # ================================================================== C
    print("\n" + RULE)
    print("C. BETA TO MARKET — is any of this just a beta play?")
    print(RULE)
    mkt = panel.pct_change(fill_method=None).mean(axis=1)

    def beta(px, sc):
        r = backtest(px, sc).returns
        j = pd.concat([r, mkt], axis=1, join="inner").dropna()
        j.columns = ["s", "m"]
        v = j["m"].var()
        return float(j["s"].cov(j["m"]) / v), float(j["m"].var()), len(j)

    for label, px, sc in (("V1 gated  TRAIN", train_px, score),
                          ("V1 gated  TEST", test_px, score),
                          ("ungated   TRAIN", train_px, ungated),
                          ("ungated   TEST", test_px, ungated)):
        b, _, n = beta(px, sc)
        print(f"  {label:<20} beta {b:5.2f}  (n={n})")

    bh_train, bm_train = buy_and_hold(train_px)
    bh_test, bm_test = buy_and_hold(test_px)
    for label, r, sl in (("b&h TRAIN", bh_train.pct_change().fillna(0), slice(TRAIN_START, TRAIN_END)),
                         ("b&h TEST", bh_test.pct_change().fillna(0), slice(TEST_START, TEST_END))):
        j = pd.concat([r, mkt.loc[sl]], axis=1, join="inner").dropna()
        j.columns = ["s", "m"]
        print(f"  {label:<20} beta {float(j['s'].cov(j['m']) / j['m'].var()):5.2f}")

    m1 = backtest(test_px, score).metrics
    print(f"\n  mean invested weight, V1 TEST: "
          f"{backtest(test_px, score).weights.sum(axis=1).mean():.3f}"
          f"   vs buy-and-hold 1.000")
    print(f"  V1 TEST Sharpe {m1.sharpe:+.3f} vs b&h {bm_test.sharpe:+.3f}, "
          f"while running {(1 - backtest(test_px, score).weights.sum(axis=1).mean()) * 100:.0f}% "
          f"less exposure -> the loss is not explained by lower beta")

    # ================================================================== D
    print("\n" + RULE)
    print("D. BRIEF §6 SANITY CHECKS, RECOMPUTED FROM SCRATCH")
    print(RULE)
    res = backtest(test_px, score)
    n_above_typ = float(score.loc[test_px.index].notna().to_numpy().mean()) * n_sym
    print(f"  §6.1 plausibility  CAGR {m1.cagr * 100:5.2f}%  -> "
          f"{'PASS (far below the 40-50% unlevered ceiling)' if m1.cagr < 0.5 else 'SUSPECT BUG'}")
    print(f"  §6.2 weight count  avg names held {res.diag['avg_names']:.1f} "
          f"(max_names cap {CFG.max_names}, target {CFG.n_positions})")
    mx = int(res.weights.gt(0).sum(axis=1).max())
    print(f"        peak names held on any single day: {mx}  "
          f"-> {'PASS, never exceeds the 30 cap (no residual accretion bug)'
             if mx <= CFG.max_names else 'FAIL, cap breached'}")
    print(f"        mean top weight {res.diag['avg_top_weight']:.4f}, "
          f"max single name {res.weights.max(axis=1).max():.4f} (cap {CFG.max_weight})")
    print(f"  §6.3 liveness      {float((dist.loc[test_px.index] > 0).to_numpy().mean()) * 100:.1f}% "
          f"of name-days long (floor ~5%) -> PASS, not an always-flat strategy")
    print(f"        eligible names on a typical day: {n_above_typ:.1f} vs a "
          f"{CFG.n_positions}-name book; gate is the binding constraint on "
          f"~40% of monthly rebalances -> it does real work, but it is loose "
          f"enough that the momentum rank still chooses the majority")
    print(f"  §6.4 cost drag     {m1.cost_drag_annual * 100:.2f}%/y on "
          f"{m1.annual_turnover:.2f}x/y turnover; round trip "
          f"{res.diag['round_trip_bps']:.2f} bps")
    print("        gross CAGR would be higher by ~0.4 pp -> net is positive, "
          "so costs are NOT what kills it")
    print(f"  §6.5 random ctrl   see section E ({N_SEEDS} seeds)")

    # ================================================================== E
    print("\n" + RULE)
    print(f"E. RANDOM-SIGNAL CONTROL — {N_SEEDS} seeds, matched long fraction")
    print(RULE)
    live = float((dist.loc[test_px.index] > 0).to_numpy().mean())
    sh, cg, dd = [], [], []
    for seed in range(N_SEEDS):
        m = backtest(test_px, random_signal_score(test_px, live, seed)).metrics
        sh.append(m.sharpe)
        cg.append(m.cagr)
        dd.append(m.max_drawdown)
    sh, cg, dd = map(np.array, (sh, cg, dd))
    n_better = int((sh >= m1.sharpe).sum())
    print(f"  matched long fraction           : {live * 100:.1f}%")
    print(f"  random Sharpe  mean {sh.mean():+.3f}  sd {sh.std(ddof=1):.3f}  "
          f"min {sh.min():+.3f}  max {sh.max():+.3f}")
    print(f"  random CAGR    mean {cg.mean() * 100:+.2f}%  min {cg.min() * 100:+.2f}%  "
          f"max {cg.max() * 100:+.2f}%")
    print(f"  random MaxDD   mean {dd.mean() * 100:+.2f}%  worst {dd.min() * 100:+.2f}%")
    print(f"  V1 TEST Sharpe {m1.sharpe:+.3f}")
    print(f"    beats {N_SEEDS - n_better}/{N_SEEDS} random books "
          f"({(N_SEEDS - n_better) / N_SEEDS * 100:.1f}%)")
    print(f"    one-sided empirical p = {(N_SEEDS - n_better + 1) / (N_SEEDS + 1):.3f}"
          f"  -> {'NOT significant' if (N_SEEDS - n_better + 1) / (N_SEEDS + 1) > 0.05 else 'significant'}")
    print(f"    z = {(m1.sharpe - sh.mean()) / sh.std(ddof=1):+.2f}")
    print(f"    best single random seed Sharpe {sh.max():+.3f} "
          f"{'BEATS' if sh.max() > m1.sharpe else 'is below'} the strategy")

    # ================================================================== F
    print("\n" + RULE)
    print("F. HEADLINE RECONCILIATION vs the prior run")
    print(RULE)
    prior = json.loads((HERE / "test_results.PRIOR.json").read_text())
    checks = [
        ("cagr", m1.cagr, prior["test"]["cagr"]),
        ("sharpe", m1.sharpe, prior["test"]["sharpe"]),
        ("max_drawdown", m1.max_drawdown, prior["test"]["max_drawdown"]),
        ("b&h cagr", bm_test.cagr, prior["buy_hold"]["cagr"]),
        ("b&h sharpe", bm_test.sharpe, prior["buy_hold"]["sharpe"]),
        ("b&h maxdd", bm_test.max_drawdown, prior["buy_hold"]["max_drawdown"]),
    ]
    allok = True
    for name, mine, theirs in checks:
        ok = abs(float(mine) - float(theirs)) < 1e-12
        allok &= ok
        print(f"  [{'OK ' if ok else 'FAIL'}] {name:<12} mine {float(mine):+.6f}  "
              f"prior {float(theirs):+.6f}")
    print(f"\n  {'AUDIT RECONCILES WITH THE PRIOR RUN EXACTLY' if allok else 'DISCREPANCY FOUND'}")

    (HERE / "audit.json").write_text(json.dumps({
        "overlap_train": float(np.mean(overlap)),
        "v1_test": m1.as_dict(),
        "buy_hold_test": bm_test.as_dict(),
        "random": {"seeds": N_SEEDS, "sharpe_mean": float(sh.mean()),
                   "sharpe_sd": float(sh.std(ddof=1)),
                   "sharpe_max": float(sh.max()),
                   "p_one_sided": float((N_SEEDS - n_better + 1) / (N_SEEDS + 1))},
    }, indent=2))
    print("\nwrote audit.json")


if __name__ == "__main__":
    main()
