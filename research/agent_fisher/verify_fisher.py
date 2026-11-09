"""Verify the vectorised Fisher panel matches the catalog scalar implementation."""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "src"))

from common import fisher_panel, fisher_signal, load  # noqa: E402

from cryptobot.strategies.indicators import fisher_transform as scalar  # noqa: E402


def main() -> None:
    panel, _ = load()
    # Deterministic, jittery synthetic series with flat stretches (hi == lo case).
    rng = np.random.default_rng(7)
    n = 900
    series = 100.0 + np.cumsum(rng.normal(0, 1.2, n))
    series[300:340] = 55.0  # flat -> hi == lo -> scalar returns 0.0
    series[500:520] = series[499]

    ok = True
    for period in (5, 10, 20):
        f = fisher_panel(pd_df(series, "X"), period)
        for i in range(n):
            hist = series[: i + 1]
            want = scalar(hist, period) if len(hist) >= period else float("nan")
            if len(hist) < period:
                # rolling(min_periods=period) yields NaN -> we substitute 0.0 only when
                # rng is notna, so before warm-up the value stays NaN.
                want = float("nan")
            got = float(f["X"].iloc[i])
            same = (np.isnan(want) and np.isnan(got)) or (
                not np.isnan(want) and abs(want - got) < 1e-12
            )
            if not same:
                print(f"MISMATCH period={period} i={i} scalar={want} vec={got}")
                ok = False
                break
        print(f"period={period}: scalar==vectorised over {n} bars -> {ok}")

    # Signal rule check against FisherStrategy.signal
    from cryptobot.strategies.catalog.fisher_transform import FisherConfig, FisherStrategy

    strat = FisherStrategy(FisherConfig(period=10, entry=0.5))
    f = fisher_panel(pd_df(series, "X"), 10)
    sig = fisher_signal(f, 0.5)
    for i in range(n):
        hist = series[: i + 1]
        want = strat.signal(hist, hist, hist, hist)
        got = int(sig["X"].iloc[i])
        if want != got:
            print(f"SIGNAL MISMATCH i={i} strat={want} vec={got}")
            ok = False
            break
    print(f"signal rule (period=10, entry=0.5) matches strategy -> {ok}")

    # entry -> percentile sanity on the real panel
    for entry in (0.5, 1.0, 1.5):
        s = fisher_signal(fisher_panel(panel, 10), entry)
        print(
            f"  period=10 entry={entry}: long {float((s>0).mean().mean())*100:.1f}% "
            f"of bars, flat {float((s==0).mean().mean())*100:.1f}%, "
            f"avoid {float((s<0).mean().mean())*100:.1f}%"
        )


def pd_df(series, name):
    import pandas as pd

    return pd.DataFrame({name: series})


if __name__ == "__main__":
    main()
