"""Stage 3 — post-hoc diagnostic. WHY did it fail?

Everything TEST-shaped here is measurement, not selection: no new parameter variant is
introduced, no book construction changes, no re-ranking of V4 against anything. The
questions are purely descriptive.

Q1  Does the Supertrend flag carry *any* directional information? (forward return of
    names flagged +1 vs -1, on TRAIN and TEST separately.)
Q2  Where did the 2026 loss come from — being in the wrong names, or being in the wrong
    *market* (the filter turning off)?
Q3  Does the momentum ranking on top of the flag help or hurt?
Q4  Is the book's identity churning (turnover) or is it genuinely sticky?
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
    TRAIN_END,
    TRAIN_START,
    as_shipped_signal,
    load_ohlc,
    momentum_score,
    run,
    summarise,
    supertrend_signal,
    window,
)

HERE = Path(__file__).resolve().parent


def fwd_rets(close: pd.DataFrame, days: int) -> pd.DataFrame:
    return close.shift(-days) / close - 1.0


def flag_information(sig: pd.DataFrame, close: pd.DataFrame, start, end, label: str):
    """Mean forward return of +1-flagged vs -1-flagged names."""
    out = {"window": label, "horizons": {}}
    for h in (21, 63, 126):
        f = window(fwd_rets(close, h), start, end)
        s = window(sig, start, end)
        up = f.where(s > 0).stack()
        dn = f.where(s < 0).stack()
        out["horizons"][h] = {
            "mean_fwd_up": float(up.mean()),
            "mean_fwd_dn": float(dn.mean()),
            "spread_up_minus_dn": float(up.mean() - dn.mean()),
            "hit_rate_up": float((up > 0).mean()),
            "hit_rate_dn": float((dn > 0).mean()),
            "n_up": int(up.notna().sum()),
            "n_dn": int(dn.notna().sum()),
        }
    return out


def main():
    close, high, low = load_ohlc()
    out = {}

    st = supertrend_signal(close, high, low, 20, 3.0)
    sh = as_shipped_signal(close)

    # ---- Q1 ---------------------------------------------------------------
    print("=" * 92)
    print("Q1  Does the +1 flag carry directional information? (raw price returns)")
    print("=" * 92)
    q1 = {}
    for label, start, end in (
        ("TRAIN", TRAIN_START, TRAIN_END),
        ("TEST", TEST_START, TEST_END),
    ):
        for name, s in (("supertrend_p20_m3.0", st), ("as_shipped", sh)):
            info = flag_information(s, close, start, end, label)
            q1[f"{name}__{label}"] = info
            print(f"\n  {label}  {name}")
            for h, d in info["horizons"].items():
                print(f"    {h:>3}d  fwd(+1) {d['mean_fwd_up'] * 100:>6.2f}%   "
                      f"fwd(-1) {d['mean_fwd_dn'] * 100:>6.2f}%   "
                      f"spread {d['spread_up_minus_dn'] * 100:>+6.2f}pp   "
                      f"hit(+1) {d['hit_rate_up'] * 100:>5.1f}%  "
                      f"n={d['n_up']:,}")
    uni = {}
    for label, start, end in (
        ("TRAIN", TRAIN_START, TRAIN_END),
        ("TEST", TEST_START, TEST_END),
    ):
        f = window(close, start, end)
        row = {h: float(fwd_rets(f, h).stack().mean()) for h in (21, 63, 126)}
        uni[label] = row
        print(f"\n  {label}  UNIVERSE mean fwd: "
              + "  ".join(f"{h}d {v * 100:+.2f}%" for h, v in row.items()))
    q1["universe"] = uni
    out["q1_flag_information"] = q1

    # ---- Q2 ---------------------------------------------------------------
    print("\n" + "=" * 92)
    print("Q2  TEST calendar breakdown: exposure, market, alpha by year")
    print("=" * 92)
    score = momentum_score(close, st)
    res = run(close, score, TEST_START, TEST_END)
    w = res.weights
    px = window(close, TEST_START, TEST_END)
    rets = px.pct_change(fill_method=None).fillna(0.0)
    held_ret = (w.shift(1).fillna(0.0) * rets).sum(axis=1)
    mkt = rets.mean(axis=1)
    frame = pd.DataFrame(
        {"strategy": held_ret, "mkt": mkt, "invested": w.sum(axis=1),
         "n_names": (w > 0).sum(axis=1)}
    )
    yr = frame.groupby(lambda d: d.year).agg(
        strategy=("strategy", lambda s: (1 + s).prod() - 1),
        mkt=("mkt", lambda s: (1 + s).prod() - 1),
        invested=("invested", "mean"),
        n_names=("n_names", "mean"),
    )
    yr["alpha"] = yr["strategy"] - yr["mkt"]
    # n_names is a COUNT, not a return -- formatting it as a percentage printed
    # "1835.77%" for an 18.4-name book. Render each column with the right unit.
    yr = yr.rename(columns={"invested": "invested_frac", "n_names": "n_names"})
    parts = []
    for idx, r in yr.iterrows():
        parts.append(
            f"  {idx}  strategy {r['strategy'] * 100:>7.2f}%  mkt {r['mkt'] * 100:>7.2f}%  "
            f"alpha {r['alpha'] * 100:>7.2f}pp  invested {r['invested_frac'] * 100:>5.1f}%  "
            f"names {r['n_names']:>5.1f}"
        )
    print("\n".join(parts))
    out["q2_yearly"] = yr.to_dict(orient="index")

    # ---- Q3 ---------------------------------------------------------------
    print("\n" + "=" * 92)
    print("Q3  Does the momentum rank on top of the flag help or hurt? (TEST)")
    print("=" * 92)
    q3 = {}
    q3["momentum_rank"] = summarise(res, close, "flag + momentum rank (as designed)")
    sig_t = window(st, TEST_START, TEST_END)
    eq_mask = sig_t > 0
    noise = np.random.default_rng(0).random(eq_mask.shape)
    eq_score = pd.DataFrame(
        np.where(eq_mask.to_numpy(), 1.0 + 1e-6 * noise, np.nan),
        index=eq_mask.index,
        columns=eq_mask.columns,
    )
    q3["flag_only_no_rank"] = summarise(
        run(close, eq_score, TEST_START, TEST_END), close, "flag only, no momentum rank"
    )
    for v in q3.values():
        print(f"  {v['label']:<34} CAGR {v['cagr'] * 100:>7.2f}%  "
              f"Sharpe {v['sharpe']:>6.2f}  MaxDD {v['max_drawdown'] * 100:>7.2f}%  "
              f"Names {v['avg_names']:.1f}")
    out["q3_rank_contribution"] = q3

    # ---- Q4 ---------------------------------------------------------------
    print("\n" + "=" * 92)
    print("Q4  Book identity churn on TEST (is the filter sticky or churning?)")
    print("=" * 92)
    rb = pd.DatetimeIndex(
        w.index.to_series()
        .groupby(w.index.tz_localize(None).to_period("M"))
        .apply(lambda g: g.index[0])
        .to_numpy()
    )
    keep2, ov = [], []
    for i in range(1, len(rb)):
        a = set(w.loc[rb[i - 1]][w.loc[rb[i - 1]] > 0].index)
        b = set(w.loc[rb[i]][w.loc[rb[i]] > 0].index)
        keep2.append(len(b))
        ov.append(len(a & b))
    print(f"  rebalances {len(rb)}   avg names {np.mean(keep2):.1f}")
    print(f"  overlap between consecutive months: mean {np.mean(ov):.1f} names "
          f"({np.mean(ov) / np.mean(keep2) * 100:.0f}% of the book)  "
          f"min {np.min(ov)}  max {np.max(ov)}")
    elig_t = window(eq_mask, TEST_START, TEST_END)
    print(f"  avg eligible names on TEST rebalance dates: "
          f"{elig_t.loc[rb].sum(axis=1).mean():.1f} "
          f"(PortfolioConfig.n_positions = 22)")
    print(f"  universe avg names available: {int(px.notna().sum(axis=1).mean())}")
    print("  -> when eligibility ~= 22 the momentum rank only RE-ORDERS the book; it "
          "cannot filter further. The rank is nearly a no-op.")
    out["q4_churn"] = {
        "n_rebalances": len(rb),
        "avg_names": float(np.mean(keep2)),
        "mean_overlap": float(np.mean(ov)),
        "mean_overlap_frac": float(np.mean(ov) / np.mean(keep2)),
        "min_overlap": int(np.min(ov)),
        "max_overlap": int(np.max(ov)),
        "avg_eligible": float(elig_t.loc[rb].sum(axis=1).mean()),
    }

    (HERE / "stage3_diagnostic.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {HERE / 'stage3_diagnostic.json'}")


if __name__ == "__main__":
    main()
