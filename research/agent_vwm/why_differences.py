"""Disambiguate WHY the volume-aware and volume-free signals differ.

(First attempt at this script compared `vwm_signal(long_only=True)` against a
volume-free reference built with `long_only=False` semantics, i.e. it flagged every
short signal as a "difference". 48,332 phantom cells. Both sides now use identical
long-only semantics; the honest count is far smaller.)

Question: on cells that differ, is volume a real observed number or NaN?
If all differences sit on NaN-volume cells, the volume *values* are irrelevant to
the signal and only "a volume observation exists" matters -- a listing/warmup
artefact, not alpha.
"""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "research/agent_vwm")

from common import avg_volume_panel, load_panels, roc_panel, vwm_signal  # noqa: E402

VARIANTS = ((20, 0.01), (20, 0.05), (63, 0.03), (126, 0.06), (252, 0.10))


def volume_free_signal(px: pd.DataFrame, period: int, thr: float) -> pd.DataFrame:
    """`+1 if roc>thr, 0 if roc<-thr, 0 otherwise` -- i.e. the catalog body with
    the volume term deleted. Long-only, matching `vwm_signal(long_only=True)`."""
    m = roc_panel(px, period)
    sig = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    sig[m > thr] = 1.0
    sig[m.isna()] = 0.0
    return sig


def main() -> None:
    px, vol, _ = load_panels()

    grand_total = 0
    grand_real = 0
    grand_nan = 0
    for period, thr in VARIANTS:
        sig_with, _ = vwm_signal(px, vol, period, thr, long_only=True)
        sig_without = volume_free_signal(px, period, thr)

        diff = sig_with != sig_without
        n = int(diff.to_numpy().sum())
        if n == 0:
            print(f"period={period:>3} thr={thr:<5}: 0 differing cells -- "
                  f"volume provably irrelevant at this setting")
            continue

        avgv = avg_volume_panel(vol, period)
        sub = diff.stack()
        sub = sub[sub]
        recs = []
        for (dt, sym) in sub.index:
            recs.append(
                {
                    "date": str(dt.date()),
                    "sym": sym,
                    "vol": vol.loc[dt, sym],
                    "avg_vol": avgv.loc[dt, sym],
                    "roc": roc_panel(px, period).loc[dt, sym],
                    "with_vol": sig_with.loc[dt, sym],
                    "no_vol": sig_without.loc[dt, sym],
                }
            )
        df = pd.DataFrame(recs)
        nan_cells = int(df["vol"].isna().sum())
        real_cells = int(df["vol"].notna().sum())
        grand_total += n
        grand_real += real_cells
        grand_nan += nan_cells

        print("=" * 74)
        print(f"period={period} thr={thr}: {n} differing cells "
              f"({real_cells} with real volume, {nan_cells} with NaN volume)")
        print(f"  columns in play: {sorted(df.sym.unique())[:10]}")
        print(f"  dates in play  : {sorted(df.date.unique())[:4]} "
              f"... {sorted(df.date.unique())[-2:]}")
        print(f"  vol values     : min={df['vol'].min()} max={df['vol'].max()}")
        print(f"  avg_vol        : all NaN? {bool(df.avg_vol.isna().all())}  "
              f"min={df.avg_vol.min()}")
        print(f"  roc range      : [{df.roc.min():.4f}, {df.roc.max():.4f}]")
        print(f"  -> differences driven by: "
              f"{'MISSING volume observation' if nan_cells == n else 'REAL VOLUME VALUE'}")
        if nan_cells == 0:
            print(df.head(8).to_string(index=False))

    print()
    print("=" * 74)
    print("SUMMARY across all 5 declared variants")
    print(f"  total cells where the signal differs with/without volume : {grand_total:,}")
    print(f"  ...where volume was a real observed number               : {grand_real:,}")
    print(f"  ...where volume was missing (NaN)                        : {grand_nan:,}")
    print()
    if grand_real == 0:
        print("  VERDICT: the strategy's OUTPUT IS DETERMINED ENTIRELY BY PRICE.")
        print("  The volume series changes nothing except through missingness,")
        print("  and missingness is a listing/warmup artefact.")
    else:
        print("  VERDICT: volume values DO influence the signal. Investigate above.")


if __name__ == "__main__":
    main()
