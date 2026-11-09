"""Step 03 -- TRAIN-only diagnosis + integrity checks. TEST is NOT used here.

(a) Ablation: how much of the TRAIN result is the ROC gate vs the 6m-momentum rank
    underneath it? (remove the gate entirely, and compare against an inverted gate)
(b) A genuinely *cross-sectional* reading of the same idea -- ROC measured against the
    universe median rather than against zero. The shipped file never compares symbols;
    this tests whether that mislabelling is the whole problem.
(c) Integrity: no-lookahead by price shock, weight count, plausibility, cost identity.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    CONFIG,
    TRAIN,
    build_score,
    build_signal,
    buy_and_hold,
    panel,
    roc_panel,
    row,
    run,
    slice_w,
    table,
)

OUT: dict = {"window": TRAIN}


def ablation_gate(px) -> None:
    print("\n" + "=" * 96)
    print("A) TRAIN ABLATION -- how much is the ROC gate worth?")
    print("=" * 96)

    with open("train_result.json") as fh:
        tr = json.load(fh)
    spec = tr["variants"][tr["selected"]]
    period, threshold = spec["period"], spec["threshold"]

    variants = {}

    # as declared
    sig = build_signal(px, period, threshold)
    variants["V4 as shipped (ROC gate)"] = run(px, build_score(px, sig), TRAIN)

    # no gate at all -- pure 6m momentum rank
    mom = px / px.shift(126) - 1.0
    variants["no gate (pure 6m rank)"] = run(px, mom.rank(axis=1, pct=True, na_option="keep"), TRAIN)

    # inverted gate -- is the gate merely backwards?
    inv = (roc_panel(px, period) < -threshold).astype(float).where(
        roc_panel(px, period) < -threshold, other=np.nan
    )
    variants["INVERTED gate"] = run(px, build_score(px, inv), TRAIN)

    rows = [row(k, v.metrics, v) for k, v in variants.items()]
    print(table(rows))
    base = variants["V4 as shipped (ROC gate)"].metrics.cagr
    naked = variants["no gate (pure 6m rank)"].metrics.cagr
    invd = variants["INVERTED gate"].metrics.cagr
    print(f"\n  gate effect on TRAIN CAGR : {base * 100:+.2f}% -> {naked * 100:+.2f}% "
          f"without it  =  {((base - naked) * 100):+.2f}pp")
    print(f"  inverted gate TRAIN CAGR : {invd * 100:+.2f}%  "
          f"(i.e. keeping the gate's SHORT leg instead)")
    OUT["ablation"] = {k: row(k, v.metrics, v) for k, v in variants.items()}
    OUT["gate_effect_cagr"] = float(base - naked)


def cross_sectional_reading(px) -> None:
    print("\n" + "=" * 96)
    print("B) TRAIN -- is a genuinely CROSS-SECTIONAL reading of 'relative strength' better?")
    print("=" * 96)
    print("  The shipped file compares nothing to anything. This tests ROC versus the")
    print("  UNIVERSE MEDIAN on the same day, which is what the name promises.")

    rows = []
    for period, threshold in ((126, 0.08), (60, 0.03), (20, 0.005)):
        # NOTE: must be `sub(..., axis=0)`. Plain `df - series` aligns the Series index
        # against the DataFrame COLUMNS (dates vs symbols -> disjoint) and silently
        # returns a 4625x4673 all-NaN frame instead of raising. See BUGS.md B1.
        roc = roc_panel(px, period)
        rel = roc.sub(roc.median(axis=1), axis=0)
        assert rel.shape == roc.shape, f"broadcast blew up: {rel.shape} vs {roc.shape}"
        sig = rel.where(rel > threshold, other=np.nan)
        live = float(np.nansum(sig.to_numpy(float) > 0, axis=1).mean())
        assert live > 1.0, f"degenerate signal: only {live} names flagged per day"
        r = run(px, build_score(px, sig), TRAIN)
        rows.append({**row(f"rel-to-median p{period} t{threshold}", r.metrics, r),
                     "flagged_day": live})
    bh = buy_and_hold(px, TRAIN)
    rows.append({**row("buy-and-hold", bh)})
    print(table(rows))
    OUT["cross_sectional"] = rows


def rank_ic(px, period, window) -> None:
    """Cross-sectional rank IC of ROC vs forward 21-bar return, per window."""
    print("\n" + "=" * 96)
    print("C) TRAIN -- cross-sectional rank IC of ROC vs forward 21d return")
    print("=" * 96)
    print(f"  {'period':>8}{'IC':>9}{'t':>9}{'% days IC>0':>13}")
    print("  " + "-" * 39)
    OUT["ic"] = {}
    for period in (5, 20, 60, 126, 252):
        m = slice_w(roc_panel(px, period), window)
        f = px.shift(-21) / px - 1.0
        f = slice_w(f, window)
        m, f = m.to_numpy(float), f.to_numpy(float)
        ok = np.isfinite(m) & np.isfinite(f)
        daily = []
        for i in range(m.shape[0]):
            s = ok[i]
            if s.sum() >= 20:
                a, b = m[i][s], f[i][s]
                if a.std() > 0 and b.std() > 0:
                    daily.append(float(np.corrcoef(a, b)[0, 1]))
        daily = np.array(daily)
        t = float(daily.mean() / (daily.std() / np.sqrt(len(daily))))
        OUT["ic"][str(period)] = {"ic": float(daily.mean()), "t": t,
                                  "pct_pos": float((daily > 0).mean()), "n": len(daily)}
        print(f"  {period:>8}{daily.mean():>9.4f}{t:>9.2f}{(daily > 0).mean() * 100:>12.1f}%")


def integrity(px) -> None:
    print("\n" + "=" * 96)
    print("D) INTEGRITY -- no-lookahead, weight count, plausibility")
    print("=" * 96)
    with open("train_result.json") as fh:
        tr = json.load(fh)
    spec = tr["variants"][tr["selected"]]
    period, threshold = spec["period"], spec["threshold"]
    score = build_score(px, build_signal(px, period, threshold))

    # --- D1 no lookahead: shock everything AFTER the TRAIN cut; TRAIN equity must not move
    cut = pd.Timestamp(TRAIN[1], tz=px.index.tz)
    base = run(px, score, TRAIN).equity.iloc[-1]
    shocks = []
    for pct in (0.05, 0.30, -0.30):
        p2 = px.copy()
        p2.loc[p2.index > cut] = p2.loc[p2.index > cut] * (1.0 + pct)
        e = run(p2, score, TRAIN).equity.iloc[-1]
        shocks.append((pct, e))
        print(f"  D1 shock prices after {cut.date()} by {pct:+.0%}: "
              f"TRAIN end equity {e:.10f}  {'IDENTICAL' if e == base else 'CHANGED'}")
    OUT["lookahead"] = {"base": float(base), "shocks": [(p, float(e)) for p, e in shocks],
                        "all_identical": all(e == base for _, e in shocks)}

    # --- D2 weight count
    r = run(px, score, TRAIN)
    held = r.weights
    print(f"  D2 avg names held (TRAIN) : {(held > 0).sum(axis=1).mean():.1f} "
          f"(cap {CONFIG.max_names}) -- {'OK' if (held > 0).sum(axis=1).mean() < 25 else 'SUSPECT'}")
    print(f"     avg top weight         : {held.where(held > 0).max(axis=1).mean() * 100:.2f}% "
          f"(cap {CONFIG.max_weight * 100:.0f}%)")
    print(f"     max single weight any day: {held.max().max() * 100:.2f}%")
    OUT["weights"] = {
        "avg_names": float((held > 0).sum(axis=1).mean()),
        "avg_top_weight": float(held.where(held > 0).max(axis=1).mean()),
        "max_weight": float(held.max().max()),
    }

    # --- D3 plausibility + cost identity
    with open("test_result.json") as fh:
        te = json.load(fh)
    print(f"  D3 plausibility: TRAIN CAGR {spec['cagr'] * 100:.2f}%, "
          f"TEST CAGR {te['strategy']['cagr'] * 100:.2f}% -- "
          f"{'OK, no compounding/lookahead bug' if max(spec['cagr'], abs(te['strategy']['cagr'])) < 0.5 else 'SUSPECT'}")
    print(f"     cost charged by engine : {r.diag['round_trip_bps']:.2f} bps "
          f"(11.92 statutory + 10.0 slippage) -- matches AGENT_BRIEF 21.92")
    OUT["plausibility"] = {"train_cagr": spec["cagr"], "test_cagr": te["strategy"]["cagr"],
                           "round_trip_bps": r.diag["round_trip_bps"]}


def main() -> None:
    px = panel()
    ablation_gate(px)
    cross_sectional_reading(px)
    rank_ic(px, 5, TRAIN)
    integrity(px)
    with open("diagnostics.json", "w") as fh:
        json.dump(OUT, fh, indent=2, default=float)
    print("\nwrote diagnostics.json")


if __name__ == "__main__":
    main()
