"""Batch 4 -- the last five agents.

`atr_breakout` and `ma_cross` are library + runner splits; `mfi` and `obv` keep their
panel builders in the runner script next to the data-prep module; `inapplicable` cannot
be re-run at all on the new engine (see the note on that agent below).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import run_all as R  # noqa: E402
from agentlib import load  # noqa: E402
from core import panel  # noqa: E402

PX = panel()
MOM_DAYS = 126


@R.reg("atr_breakout", "V1 (period=10, mult=1.0)")
def _ab(a):
    sigmod = load(a, "signal")
    from nsealgo.data.loader import load_symbol

    close = PX
    hs, ls = {}, {}
    for sym in close.columns:
        df = load_symbol(f"data/nse/{sym}_1d.csv", sym)
        hs[sym] = df["high"].rename(sym)
        ls[sym] = df["low"].rename(sym)
    high = pd.DataFrame(hs).reindex(index=close.index, columns=close.columns)
    low = pd.DataFrame(ls).reindex(index=close.index, columns=close.columns)
    sig = sigmod.signal_panel(high, low, close, 10, 1.0)
    mom = close / close.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True), "M"


@R.reg("ma_cross", "V3 (50/200 SMA cross, flag)")
def _mac(a):
    m = load(a, "harness")
    return m.ma_cross_score(PX, 50, 200, "flag"), "M"


@R.reg("mfi", "V3_mfi_p14_l40")
def _mfi(a):
    lib = load(a, "mfi_lib")
    rv = load(a, "run_variants")
    from nsealgo.data.loader import load_symbol

    hs, ls, vs = {}, {}, {}
    for sym in PX.columns:
        df = load_symbol(f"data/nse/{sym}_1d.csv", sym)
        hs[sym] = df["high"].rename(sym)
        ls[sym] = df["low"].rename(sym)
        vs[sym] = df["vol"].rename(sym)

    def _mk(d):
        return pd.DataFrame(d).reindex(index=PX.index, columns=PX.columns)

    high, low, vol = _mk(hs), _mk(ls), _mk(vs)
    mf = lib.mfi_panel(high, low, PX, vol, 14)
    sig = lib.signal_panel(mf, 40.0)
    return rv.build_score(PX, sig), "M"


@R.reg("obv", "V2_obv_n5")
def _obv(a):
    dp = load(a, "data_prep")
    rv = load(a, "run_variants")
    close, vol = dp.load()
    return rv.build_score(close, vol, 5), "M"


if __name__ == "__main__":
    R.main()
