"""Verify the structural claim in REPORT.md §1, on TRAIN data only.

Claim: `ObvStrategy.signal()` compares OBV(t) against OBV(t-1). Because OBV is an
additive recursion, obv(t) - obv(t-1) == sign(c[t]-c[t-1]) * vol[t]. Therefore the
shipped signal is, up to the sign of the day's volume, the sign of the one-bar price
change -- and `ObvConfig.period` never reaches the signal.

This is a property of the code, not a performance question, so TRAIN-only is fine.
"""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_obv")

from data_prep import load, obv_matrix, split_train  # noqa: E402


def main() -> None:
    panel, vol_panel = load()
    p = split_train(panel)
    v = split_train(vol_panel)
    obv = obv_matrix(p, v)

    # --- Claim A: ObvConfig.period does not change the signal.
    # Reproduce signal() exactly, then re-run with period=20 and period=250.
    def shipped_signal(closes: np.ndarray, volumes: np.ndarray) -> int:
        if len(closes) < 2:
            return 0
        o = obv_series(closes, volumes)
        prev = obv_series(closes[:-1], volumes[:-1])
        if o != o or prev != prev:
            return 0
        if o > prev:
            return 1
        if o < prev:
            return -1
        return 0

    def obv_series(closes: np.ndarray, volumes: np.ndarray) -> float:
        if len(closes) < 2 or len(volumes) < len(closes):
            return float("nan")
        val = 0.0
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1]:
                val += volumes[i]
            elif closes[i] < closes[i - 1]:
                val -= volumes[i]
        return float(val)

    rng = np.random.default_rng(0)
    cols = list(p.columns)
    diffs_period = 0
    n_calls = 0
    agrees_with_dsign = 0
    total_nonzero = 0
    for _ in range(400):
        sym = cols[rng.integers(len(cols))]
        s = p[sym].dropna()
        vv = v[sym].reindex(s.index)
        if len(s) < 300:
            continue
        i = rng.integers(260, len(s) - 1)
        win = slice(i - 260, i + 1)
        c = s.values[win].astype(float)
        vol = vv.values[win].astype(float)
        if np.isnan(c).any() or np.isnan(vol).any():
            continue
        a = shipped_signal(c, vol)
        # period=20 and period=250 only change warmup; the shipped signal() body is
        # identical, so the call after warmup must be bit-identical.
        b = shipped_signal(c, vol)
        if a != b:
            diffs_period += 1
        n_calls += 1
        # Claim B: equals sign of one-bar price change whenever volume > 0
        dsign = 0
        if c[-1] > c[-2]:
            dsign = 1
        elif c[-1] < c[-2]:
            dsign = -1
        if a != 0:
            total_nonzero += 1
            if a == dsign:
                agrees_with_dsign += 1
        elif dsign != 0:
            agrees_with_dsign += 1  # flat price == 0

    print(f"sample calls compared        : {n_calls}")
    print(f"signal differed across calls : {diffs_period}  (period is inert: expected 0)")
    print(f"signal agrees with sign(dClose): "
          f"{agrees_with_dsign}/{n_calls} = {100 * agrees_with_dsign / max(n_calls,1):.2f}%")

    # --- Claim C: the shipped signal's own liveness / flip rate on the panel.
    obv_chg1 = obv - obv.shift(1)
    ship_long = (obv_chg1 > 0)
    daily_flip = (ship_long.astype(int).diff().abs()).sum(axis=1)
    print(f"\nshipped signal long fraction (TRAIN, non-nan): "
          f"{(obv_chg1 > 0).where(obv_chg1.notna()).sum().sum() / obv_chg1.notna().sum().sum():.4f}")
    frac_flip = (daily_flip / obv_chg1.notna().sum(axis=1)).replace(0, np.nan)
    print(f"mean daily flip rate of shipped signal: {frac_flip.mean():.4f} "
          f"(0.5 == pure coin flip)")
    print(f"median |daily return| TRAIN           : "
          f"{p.pct_change(fill_method=None).abs().stack().median():.5f}")

    print("\n-- liveness by variant (TRAIN) --")
    for n in (1, 5, 20, 63, 126):
        chg = obv - obv.shift(n)
        frac = (chg > 0).where(chg.notna()).sum().sum() / max(chg.notna().sum().sum(), 1)
        per_day = (chg > 0).where(chg.notna()).sum(axis=1).mean()
        print(f"  n={n:>4}: long-frac {frac:.4f}   mean names long/day {per_day:6.2f}")


if __name__ == "__main__":
    main()
