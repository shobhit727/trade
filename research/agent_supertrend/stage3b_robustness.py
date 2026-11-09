"""Stage 3b — is the anti-predictive spread a real effect or a sampling fluke?

Stage 3 found that names the Supertrend flags `-1` have *higher* forward returns than
names it flags `+1`, on both TRAIN and TEST. That is the mechanism behind the loss, so
it deserves a robustness check before it goes in the report as the explanation.

Three independent stresses, none of which involve changing the strategy:

1. **By calendar year.** Is the spread negative in most years, or driven by one?
2. **Rank statistic instead of means.** The mean forward return is outlier-sensitive;
   the fraction of names where the forward return is higher for `+1` than `-1` is not.
   If the mean result is real, the rank result should agree.
3. **Randomisation null.** Shuffle the signal within each bar (destroying the time-series
   information but preserving per-bar long-run rates) and re-measure. The observed spread
   should sit in the tail of that null.

Q1's `as_shipped` control already calibrates the diagnostic: it is a pure 1-day sign and
its spread is ~0.00pp on both windows. So the metric is not structurally biased toward
finding signal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    as_shipped_signal,
    load_ohlc,
    supertrend_signal,
    window,
)

HERE = Path(__file__).resolve().parent


def spread_by_year(sig, fwd, start, end, horizon):
    """(+1 mean fwd return) - (-1 mean fwd return), computed within each calendar year."""
    s = window(sig, start, end)
    f = window(fwd, start, end)
    rows = {}
    for yr in sorted(set(f.index.year)):
        sy, fy = s[s.index.year == yr], f[f.index.year == yr]
        up = fy.where(sy > 0).stack()
        dn = fy.where(sy < 0).stack()
        rows[int(yr)] = {
            "spread": float(up.mean() - dn.mean()),
            "mean_up": float(up.mean()),
            "mean_dn": float(dn.mean()),
            "n_up": int(up.notna().sum()),
            "n_dn": int(dn.notna().sum()),
        }
    return rows


def robust_spread(sig, fwd, start, end):
    """Outlier-robust mean/median/winsorised spread of +1 vs -1 forward returns.

    The mean forward return is dominated by a handful of large moves, so a negative
    mean spread does not by itself mean the signal is broadly anti-predictive. The
    median is immune to outliers; the winsorised mean clips the tails at the 10th/90th
    percentile and keeps some magnitude information.

    (An earlier "rank statistic" here compared each observation with the *next*
    observation in the same symbol. That tests return autocorrelation, not the +1/-1
    contrast, so it returned ~50% for both the strategy and its noise control and said
    nothing about the signal. Replaced.)
    """
    s_ = window(sig, start, end)
    f = window(fwd, start, end)
    up = f.where(s_ > 0).stack().to_numpy()
    dn = f.where(s_ < 0).stack().to_numpy()

    def winsor(a):
        a = a[np.isfinite(a)]
        lo, hi = np.percentile(a, [10, 90])
        return np.clip(a, lo, hi)

    return {
        "mean_up": float(np.nanmean(up)),
        "mean_dn": float(np.nanmean(dn)),
        "mean_spread": float(np.nanmean(up) - np.nanmean(dn)),
        "median_up": float(np.nanmedian(up)),
        "median_dn": float(np.nanmedian(dn)),
        "median_spread": float(np.nanmedian(up) - np.nanmedian(dn)),
        "wins_spread": float(np.nanmean(winsor(up)) - np.nanmean(winsor(dn))),
        "n_up": int(np.isfinite(up).sum()),
        "n_dn": int(np.isfinite(dn).sum()),
    }


def randomisation_null(sig, fwd, start, end, horizon, n=200, seed=0):
    """Within-bar shuffle null: preserves each bar's long-run rate, destroys the signal."""
    s = window(sig, start, end).to_numpy()
    f = window(fwd, start, end).to_numpy()
    rng = np.random.default_rng(seed)
    obs_up = f[s > 0]
    obs_dn = f[s < 0]
    obs = float(np.nanmean(obs_up) - np.nanmean(obs_dn))
    null = []
    for _ in range(n):
        p = s.copy()
        for i in range(p.shape[0]):  # shuffle each row independently
            row = p[i]
            ok = ~np.isnan(row)
            row[ok] = row[ok][rng.permutation(ok.sum())]
        null.append(float(np.nanmean(f[p > 0]) - np.nanmean(f[p < 0])))
    null = np.array(null)
    return {
        "observed_spread": obs,
        "null_mean": float(null.mean()),
        "null_std": float(null.std(ddof=1)),
        "null_p5": float(np.percentile(null, 5)),
        "null_p95": float(np.percentile(null, 95)),
        "p_value_one_sided_lower": float((null <= obs).mean()),
        "n_null": n,
    }


def main():
    close, high, low = load_ohlc()
    out = {}
    st = supertrend_signal(close, high, low, 20, 3.0)
    sh = as_shipped_signal(close)
    H = 63

    print("=" * 100)
    print(f"ROBUSTNESS OF THE ANTI-PREDICTIVE SPREAD (horizon {H}d forward return)")
    print("=" * 100)

    # ---- 1. by calendar year, both windows
    for label, start, end in (
        ("TRAIN 2016-2023", TRAIN_START, TRAIN_END),
        ("TEST 2024-2026", TEST_START, TEST_END),
    ):
        fwd = close.shift(-H) / close - 1.0
        rows = spread_by_year(st, fwd, start, end, H)
        neg = sum(1 for v in rows.values() if v["spread"] < 0)
        print(f"\n  {label}  — supertrend p20 m3.0, {H}d forward")
        for yr, d in rows.items():
            mark = "  <-- negative (uptrend does WORSE)" if d["spread"] < 0 else ""
            print(f"    {yr}  spread {d['spread'] * 100:>+6.2f}pp   "
                  f"(+1 {d['mean_up'] * 100:>5.2f}%  vs -1 {d['mean_dn'] * 100:>5.2f}%)"
                  f"{mark}")
        print(f"    => negative in {neg}/{len(rows)} years")
        out[f"by_year_{label.split()[0]}"] = rows

        # control: as_shipped must show ~0
        ctrl = spread_by_year(sh, fwd, start, end, H)
        negc = sum(1 for v in ctrl.values() if v["spread"] < 0)
        print(f"    CONTROL as_shipped: negative in {negc}/{len(ctrl)} years, "
              f"mean spread "
              f"{np.mean([v['spread'] for v in ctrl.values()]) * 100:+.3f}pp")
        out[f"by_year_{label.split()[0]}_control"] = ctrl

    # ---- 2. rank statistic
    print("\n" + "-" * 100)
    print("OUTLIER-ROBUST SPREAD. If the negative mean spread is a broad effect it")
    print("survives on the median and on a winsorised mean. If it is a handful of big")
    print("names, the median spread is ~0.")
    print("-" * 100)
    for label, start, end in (
        ("TRAIN", TRAIN_START, TRAIN_END),
        ("TEST", TEST_START, TEST_END),
    ):
        for name, sig_ in (("supertrend p20 m3.0", st), ("control as_shipped", sh)):
            d = robust_spread(sig_, fwd, start, end)
            out[f"robust_{name.split()[0]}_{label}"] = d
            print(f"  {label:<6} {name:<20} mean {d['mean_spread'] * 100:>+6.3f}pp   "
                  f"winsorised {d['wins_spread'] * 100:>+6.3f}pp   "
                  f"median {d['median_spread'] * 100:>+6.3f}pp")

    # ---- 3. randomisation null
    print("\n" + "-" * 100)
    print(f"RANDOMISATION NULL ({H}d spread, 200 within-bar shuffles)")
    print("-" * 100)
    for label, start, end in (
        ("TRAIN", TRAIN_START, TRAIN_END),
        ("TEST", TEST_START, TEST_END),
    ):
        r = randomisation_null(st, fwd, start, end, H)
        out[f"null_{label}"] = r
        print(f"  {label:<6} observed {r['observed_spread'] * 100:>+6.3f}pp   "
              f"null {r['null_mean'] * 100:>+6.3f} +/- {r['null_std'] * 100:.3f}pp   "
              f"[p5 {r['null_p5'] * 100:+.3f}, p95 {r['null_p95'] * 100:+.3f}]   "
              f"one-sided p = {r['p_value_one_sided_lower']:.3f}")

    (HERE / "stage3b_robustness.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {HERE / 'stage3b_robustness.json'}")


if __name__ == "__main__":
    main()
