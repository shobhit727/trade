"""Audit step 0 — is the salvaged vectorised port faithful to the catalog?

The previous run left a vectorised `common.py`. Its docstring *claims* it is a faithful
port of `BbSqueeze2Strategy`. Claims are not evidence. This runs the ACTUAL catalog
class bar-by-bar against the vectorised panel and compares, cell by cell.

It also re-derives the two load-bearing primitives from their own source
(`cryptobot.strategies.indicators.sma` / `roc`) rather than assuming the port got them
right.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA, cv_panel, load_universe, roc_panel, squeeze_signal  # noqa: E402

from cryptobot.strategies.catalog.bollinger_band_squeeze import (  # noqa: E402
    BbSqueeze2Config,
    BbSqueeze2Strategy,
)
from cryptobot.strategies.indicators import roc as roc_ind  # noqa: E402
from cryptobot.strategies.indicators import sma as sma_ind  # noqa: E402

N_SYM = 6          # catalog class is O(n) per call; 6 names x ~4700 bars is plenty
BARS = 1500        # slice TRAIN only -- no TEST access in this audit


def main() -> None:
    panel, symbols, report = load_universe(str(DATA))
    print("=" * 100)
    print("0a. DATA REPORT")
    print("=" * 100)
    print(report.describe())
    print(f"\npanel: {panel.shape[0]} bars x {panel.shape[1]} symbols  "
          f"{panel.index[0].date()} -> {panel.index[-1].date()}  tz={panel.index.tz}")

    tr = panel.loc["2016-01-01":"2023-12-31"]
    sub = tr.iloc[:BARS, :N_SYM]
    print(f"\naudit slice: {sub.shape[0]} bars x {N_SYM} symbols "
          f"{sub.index[0].date()} -> {sub.index[-1].date()}  (TRAIN only)")

    print("\n" + "=" * 100)
    print("0b. PRIMITIVES — vectorised vs cryptobot.strategies.indicators")
    print("=" * 100)
    probe = sub.columns[0]
    print(f"\nprobe symbol (panel columns are lowercase): {probe!r}")
    closes = sub[probe].to_numpy()
    ok = True
    for i in (25, 100, 400, 900, len(closes) - 1):
        # NB: indicators.sma/roc read values[-period:], so they must be handed the
        # PREFIX closes[:i+1] to describe bar i. Feeding the whole array describes the
        # last bar only.
        v = float(sma_ind(closes[: i + 1], 20))
        r = float(roc_ind(closes[: i + 1], 3))
        pv = float(cv_panel(sub, 20).iloc[i][probe])
        pr = float(roc_panel(sub, 3).iloc[i][probe])
        win = closes[i - 19 : i + 1]
        ref_cv = float(np.std(win) / np.mean(win))
        d_sma = abs(v - float(np.mean(win)))
        d_roc = abs(r - (closes[i] / closes[i - 3] - 1.0))
        d_cv = abs(pv - ref_cv)
        d_pr = abs(pr - (sub[probe].iloc[i] / sub[probe].iloc[i - 3] - 1.0))
        good = d_sma < 1e-9 and d_roc < 1e-12 and d_cv < 1e-12 and d_pr < 1e-12
        ok &= good
        print(f"  bar {i:>5}: sma d={d_sma:.2e}  roc d={d_roc:.2e}  "
              f"cv d={d_cv:.2e} (ref {ref_cv:.6f}, port {pv:.6f})  "
              f"rocpanel d={d_pr:.2e}  {'OK' if good else 'MISMATCH'}")
    print(f"  -> primitives {'MATCH' if ok else 'DIVERGE'}")

    print("\n" + "=" * 100)
    print("0c. FULL SIGNAL — catalog class (bar-by-bar) vs vectorised port")
    print("=" * 100)
    cases = [(20, 0.050), (20, 0.020), (20, 0.012), (40, 0.030)]
    for period, thr in cases:
        strat = BbSqueeze2Strategy(BbSqueeze2Config(period=period, threshold=thr))
        cols = list(sub.columns)
        ref = np.full((len(sub), len(cols)), np.nan)
        for si, s in enumerate(cols):
            c = sub[s].to_numpy(dtype=float)
            o = sub[s].to_numpy(dtype=float)   # catalog ignores ohlv for this signal
            for t in range(len(c)):
                ref[t, si] = float(strat.signal(c[: t + 1], o[: t + 1], o[: t + 1], o[: t + 1]))
        lng, short, _ = squeeze_signal(sub, period, thr, 3)
        got = lng.to_numpy() - short.to_numpy()
        nanmask = np.isnan(ref)
        agree = np.array_equal(np.nan_to_num(ref[~nanmask]), got[~nanmask])
        n_cmp = int((~nanmask).sum())
        n_l1 = int((ref == 1).sum())
        n_sm1 = int((ref == -1).sum())
        n_z = int((ref == 0).sum())
        print(f"  period={period:>2} thr={thr:.3f}: compared {n_cmp} cells  "
              f"ref(+1/-1/0)={n_l1}/{n_sm1}/{n_z}  port(+1/-1)={int(lng.to_numpy().sum())}"
              f"/{int(short.to_numpy().sum())}  "
              f"{'EXACT MATCH' if agree else '*** MISMATCH ***'}")
        assert agree, f"port diverges from catalog at period={period} thr={thr}"

    print("\n  -> the salvaged vectorised port reproduces the catalog class EXACTLY")
    print("     on all 4 declared parameter pairs. Faithfulness confirmed, not assumed.")


if __name__ == "__main__":
    main()
