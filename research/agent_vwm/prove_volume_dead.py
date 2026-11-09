"""Prove the strategy's volume component is dead code, and locate the TEST
zero-volume cluster.

Claim under test: in `VwMomentumStrategy.signal`, `vw = avg * (1.0 or 0.5)` and the
only test applied to `vw` is `vw > 0`. Since `avg >= 0` (volumes are non-negative)
and the factor is strictly positive, `vw > 0` is equivalent to `avg > 0`. Therefore
the returned signal is *identical* to `+1 if roc > threshold else -1 if roc < -threshold
else 0` — the volume series does not influence the output at all.

If this holds on the real data, `volume_weighted_momentum` is misnamed: it is plain
ROC momentum with a no-op volume filter.
"""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    avg_volume_panel,
    load_panels,
    roc_panel,
    vwm_signal,
)


def main() -> None:
    px, vol, _ = load_panels()

    print("=" * 74)
    print("TEST 1 — is signal(volume) == signal(no volume) on real data?")
    print("=" * 74)
    for period, thr in ((20, 0.01), (63, 0.03), (126, 0.06), (252, 0.10)):
        sig_with, _ = vwm_signal(px, vol, period, thr)

        # identical construction but the volume is replaced by a constant-1 series,
        # which can never make avg zero.
        ones = pd.DataFrame(1.0, index=vol.index, columns=vol.columns)
        sig_without, _ = vwm_signal(px, ones, period, thr)

        diff = int((sig_with != sig_without).to_numpy().sum())
        print(f"  period={period:>3} thr={thr:<5}: differing cells = {diff:,}")

    print()
    print("=" * 74)
    print("TEST 2 — direct algebra: replace the catalog body with a volume-free one")
    print("=" * 74)
    for period, thr in ((20, 0.01), (126, 0.06)):
        m = roc_panel(px, period)
        no_vol = pd.DataFrame(0.0, index=px.index, columns=px.columns)
        no_vol[m > thr] = 1.0
        no_vol[m < -thr] = -1.0
        no_vol[m.isna()] = 0.0

        sig_with, _ = vwm_signal(px, vol, period, thr, long_only=False)
        diff = int((sig_with != no_vol).to_numpy().sum())
        print(f"  period={period:>3}: cells where volume changes the answer = {diff:,}")

    print()
    print("=" * 74)
    print("TEST 3 — does the volume CONDITION (vol[-1]>=avg) ever matter?")
    print("  It scales vw by 0.5 vs 1.0. The signal only tests vw>0, so it cannot.")
    print("=" * 74)
    for period in (20, 126):
        avg = avg_volume_panel(vol, period)
        cond = vol >= avg
        print(
            f"  period={period:>3}: vol[-1]>=avg on {cond.stack().mean():.2%} of cells; "
            f"signalling conditional on that condition is IDENTICAL by construction."
        )

    print()
    print("=" * 74)
    print("TEST 4 — locate the TEST-window zero-volume cluster")
    print("=" * 74)
    z = vol.loc[(vol.index >= TEST_START) & (vol.index <= TEST_END)] <= 0
    per_sym = z.sum().sort_values(ascending=False)
    per_sym = per_sym[per_sym > 0]
    print("  zero-volume bars per symbol in TEST window:")
    for s, n in per_sym.items():
        first = z.index[z[s]].min().date()
        last = z.index[z[s]].max().date()
        print(f"    {s:<12} {n:>4}  first={first} last={last}")
    yr = z.groupby(z.index.year).sum().sum(axis=1)
    print("  zero-volume bars by calendar year:")
    for y, n in yr.items():
        if n:
            print(f"    {y}: {n}")

    print()
    print("  Same, for TRAIN (for contrast):")
    zt = vol.loc[(vol.index >= TRAIN_START) & (vol.index <= TRAIN_END)] <= 0
    yrt = zt.groupby(zt.index.year).sum().sum(axis=1)
    for y, n in yrt.items():
        if n:
            print(f"    {y}: {n}")

    print()
    print("  Do the zero-volume bars coincide with frozen CLOSE runs (loader C9)?")
    # loader C9 drops >=5 identical closes, so check the remaining ones
    _sub = vol.loc[(vol.index >= TEST_START) & (vol.index <= TEST_END)]
    for s in per_sym.index[:5]:
        run = (px[s] == px[s].shift(1)).rolling(5).sum()
        n_frozen = int((run >= 5).sum())
        print(f"    {s:<12} zero-vol={per_sym[s]:>4}  bars inside a >=5 frozen-close "
              f"run (should be 0, C9 removed them) = {n_frozen}")

    print()
    print("  Impact: is a zero-volume bar a *bad* bar, or just a flat holiday?")
    px_test = px.loc[(px.index >= TEST_START) & (px.index <= TEST_END)]
    ret = px_test.pct_change(fill_method=None)
    rows = []
    for s in per_sym.index:
        m = z[s]
        if m.any():
            rows.append(
                {
                    "sym": s,
                    "n_zero": int(m.sum()),
                    "ret_on_zero_vol": float(ret[s].where(m).abs().mean()),
                    "ret_other": float(ret[s].where(~m).abs().mean()),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        print(df.to_string(index=False))
        print(f"  mean |return| on zero-vol bars  = {df.ret_on_zero_vol.mean():.5f}")
        print(f"  mean |return| on normal bars   = {df.ret_other.mean():.5f}")
        print(
            "  -> zero-volume bars move at "
            f"{df.ret_on_zero_vol.mean() / max(df.ret_other.mean(), 1e-12):.2%} "
            "of a normal bar (flat/holiday vs real move)"
        )


if __name__ == "__main__":
    main()
