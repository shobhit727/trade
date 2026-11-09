"""Step 1: load panel, verify the vectorised signal against the catalog strategy.

Fidelity check is the whole point of this script. If max_err != 0 the port is
wrong and nothing downstream means anything.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_dispersion")

from signal import dispersion_signal, verify_against_catalog  # noqa: E402

import pandas as pd  # noqa: E402

from nsealgo.data.loader import load_universe  # noqa: E402


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print()
    print(f"panel shape : {panel.shape}")
    print(f"symbols     : {len(symbols)}")
    print(f"index       : {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"tz          : {panel.index.tz}")
    print(f"NaN cells   : {int(panel.isna().sum().sum())}")

    for period, entry in ((30, 1.0), (60, 0.5), (120, 0.25), (20, 2.0), (250, 1.0)):
        err = verify_against_catalog(panel, period=period, entry=entry, n_check=25)
        long_sig, short_sig = dispersion_signal(panel, period=period, entry=entry)
        live = long_sig.mean().mean()
        short_live = short_sig.mean().mean()
        print(
            f"period={period:>3} entry={entry:<5} max_err={err:.0f}  "
            f"long_frac={live:.3%}  short_frac={short_live:.3%}"
        )

    # TRAIN/TEST index boundaries the brief fixes.
    tr = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
    te = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
    print()
    print(f"TRAIN rows  : {(panel.index >= tr).sum()} (from {tr.date()})")
    print(f"TEST rows   : {(panel.index >= te).sum()} (from {te.date()})")
    print(f"test end    : {panel.index[-1].date()}")


if __name__ == "__main__":
    main()
