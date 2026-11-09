"""Step 00 -- fidelity + liveness + TRAIN-only forward-return profile.

Two jobs, both TRAIN-only, neither touches TEST:
  1. prove the vectorised ``roc_panel`` IS the catalog's ``roc()`` (not a lookalike);
  2. measure, per declared variant, what the catalog's three-way branch actually
     produces (liveness) and whether the long leg is even positively predictive.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    TRAIN,
    VARIANTS,
    build_signal,
    panel,
    roc_panel,
    signal_liveness,
    slice_w,
)

FWD = 21  # ~1 trading month; the strategy's natural holding horizon
OUT = {}


def catalog_roc_fidelity(px) -> dict:
    """Re-implement the catalog's streaming roc() and compare, bar by bar."""
    from cryptobot.strategies.indicators import roc as cat_roc

    # Probe the longest clean history so the rolling window is never NaN-contaminated.
    col = px.notna().sum().idxmax()
    print(f"    probe symbol: {col} ({int(px[col].notna().sum())} non-NaN bars)")
    res = {}
    for period in sorted({v["period"] for v in VARIANTS}):
        series = px[col].to_numpy(dtype=float)
        # Every 37th valid index keeps this quick but still covers ~120 probes per period.
        idx = [i for i in range(period + 5, len(series)) if i % 37 == 0 and np.isfinite(series[i])]
        mine = roc_panel(px, period)[col].to_numpy(dtype=float)
        diffs = []
        for i in idx:
            window = series[i - period : i + 1]  # exactly period+1 bars
            if len(window) != period + 1 or not np.all(np.isfinite(window)):
                continue
            cat = cat_roc(list(window), period)
            diffs.append(abs(cat - mine[i]))
        res[str(period)] = {
            "n_probes": len(diffs),
            "max_abs_diff": float(max(diffs)) if diffs else None,
        }
    return res


def fwd_profile(roc, px, window) -> dict:
    """Mean forward return of flagged vs unflagged symbol-bars, in-window only.

    This is the single most informative number for this strategy: if the gate is
    anti-predictive the whole idea dies here, on TRAIN, before any portfolio exists.
    """
    w = slice_w(roc, window)
    base = slice_w(px, window)
    fwd = base.shift(-FWD) / base - 1.0
    fwd = slice_w(fwd, window)
    r = w.to_numpy(dtype=float)
    f = fwd.to_numpy(dtype=float)
    ok = np.isfinite(r) & np.isfinite(f)
    return {
        "n": int(ok.sum()),
        "mean_fwd": float(f[ok].mean()),
        "frac_pos": float((f[ok] > 0).mean()),
        "tstat": float(f[ok].mean() / (f[ok].std() / np.sqrt(ok.sum()))),
    }


def main() -> None:
    px = panel()
    print("=" * 78)
    print("STEP 00 -- fidelity, liveness, forward-return profile (TRAIN only)")
    print("=" * 78)

    OUT["roc_fidelity"] = catalog_roc_fidelity(px)
    print("\n[1] vectorised roc_panel vs catalog roc()")
    for p, d in OUT["roc_fidelity"].items():
        print(f"    period {p:>3}: n={d['n_probes']:>4}  max|diff| = {d['max_abs_diff']:.3e}")

    print("\n[2] liveness + forward-return profile, TRAIN 2016-2023")
    print(f"    forward horizon: {FWD} bars (~1 month)")
    OUT["variants"] = {}
    hdr = (
        f"{'variant':<16}{'long%':>8}{'flat%':>8}{'short%':>8}{'flagged/day':>13}"
        f"{'0flag days':>12}{'fwd(flag)':>11}{'fwd(unfl)':>11}{'t':>8}"
    )
    print(hdr)
    print("-" * len(hdr))
    for v in VARIANTS:
        roc = roc_panel(px, v["period"])
        sig = build_signal(px, v["period"], v["threshold"])
        live = signal_liveness(sig, roc, v["threshold"])
        out = dict(v, **live)

        r = slice_w(roc, TRAIN).to_numpy(dtype=float)
        f = slice_w(px, TRAIN).shift(-FWD) / slice_w(px, TRAIN) - 1.0
        f = slice_w(f, TRAIN).to_numpy(dtype=float)
        ok = np.isfinite(r) & np.isfinite(f)
        flagged, unflagged = ok & (r > v["threshold"]), ok & (r <= v["threshold"])
        mf, mu = f[flagged].mean(), f[unflagged].mean()
        se = np.sqrt(f[flagged].var() / flagged.sum() + f[unflagged].var() / unflagged.sum())
        out["fwd_flagged"], out["fwd_unflagged"] = float(mf), float(mu)
        out["spread_bps"], out["tstat"] = float((mf - mu) * 1e4), float((mf - mu) / se)
        out["n_flagged"], out["n_unflagged"] = int(flagged.sum()), int(unflagged.sum())
        OUT["variants"][v["name"]] = out

        print(
            f"{v['name']:<16}{live['frac_bars_long'] * 100:>7.1f}%{live['frac_bars_flat'] * 100:>7.1f}%"
            f"{live['frac_bars_short'] * 100:>7.1f}%{live['mean_flagged_per_day']:>13.1f}"
            f"{live['days_zero_flagged']:>12}{mf * 100:>10.2f}%{mu * 100:>10.2f}%"
            f"{(mf - mu) / se:>8.2f}"
        )

    print(
        "\n  'spread' is the mean forward 21-bar return of flagged minus unflagged "
        "symbol-bars.\n  A negative spread with a large |t| means the gate is "
        "ANTI-predictive, not merely weak."
    )

    with open("step00.json", "w") as fh:
        json.dump(OUT, fh, indent=2, default=float)
    print("\nwrote step00.json")


if __name__ == "__main__":
    main()
