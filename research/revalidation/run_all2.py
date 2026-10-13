"""Batch 2 -- the remaining agents.

Same contract as `run_all.py`: rebuild each agent's frozen selected score panel from its
own harness library, run it on both engines, report the difference. Frozen variants are
taken from each agent's own recorded selection artifact (or its REPORT, where the
selection is written there in prose).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_all as R  # noqa: E402  (runs batch 1 on import, then re-exports `reg`/`probe`)
from agentlib import load  # noqa: E402
from core import panel  # noqa: E402


def _ohlc(m) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(close, high, low) via `load_symbol`, the loader `load_universe` itself calls.

    Two agents (`donchian`, `flag_pattern`) ship a `load_all()` that now *refuses to
    run*: it re-derives high/low per symbol and asserts the result matches
    `load_universe`, and on today's panel that assertion fails. Their harness cannot
    rebuild its own inputs. This fallback uses the same `load_symbol` cleaning path
    those functions use, so the signal maths is still theirs.
    """
    from nsealgo.data.loader import load_symbol

    close = panel()
    hs, ls = {}, {}
    for sym in close.columns:
        df = load_symbol(f"data/nse/{sym}_1d.csv", sym)
        hs[sym] = df["high"].rename(sym)
        ls[sym] = df["low"].rename(sym)
    return (
        close,
        pd.DataFrame(hs).reindex(index=close.index, columns=close.columns),
        pd.DataFrame(ls).reindex(index=close.index, columns=close.columns),
    )


@R.reg("bollinger_bands", "V4 p60 n2.0 entry1.0 pure")
def _bb(a):
    m = load(a)
    return m.make_score(panel(), 60, 2.0, 1.0, "pure"), "M"


@R.reg("cci", "V5_deep (p20 entry100, deepest)")
def _cci(a):
    m = load(a)
    P = m.load_panels()
    tp = (P.high + P.low + P.close) / 3.0
    cci = m.cci_panel(tp, 20)
    return m.build_score(P.close, cci, 100.0, "deepest"), "M"


@R.reg("cointegration", "L21 e2.0 depth")
def _coin(a):
    m = load(a)
    return m.build_score(panel(), 21, 2.0, "depth"), "M"


@R.reg("dispersion", "V5 p250 e1.0")
def _disp(a):
    m = load(a)
    px = panel()
    long_sig, _ = m.dispersion_signal(px, 250, 1.0)
    return m.dispersion_score(px, long_sig, 126), "M"


@R.reg("distance_ma", "V3 dev_depth p50 t0.05")
def _dma(a):
    m = load(a)
    return m.score_dev_depth(panel(), 50, 0.05), "M"


@R.reg("donchian", "breakout_p10")
def _don(a):
    m = load(a)
    close, high, low = _ohlc(m)
    sig = m.breakout_signal(close, high, low, 10)
    return m.build_score(sig, close, 126), "M"


@R.reg("fisher", "V2 (p10 e-2.0)")
def _fish(a):
    m = load(a)
    px = panel()
    sc, _sig = m.fisher_score(px, 10, -2.0)
    return sc, "M"


@R.reg("flag_pattern", "V0_LITERAL (2-bar run)")
def _flag(a):
    m = load(a)
    close, high, low = _ohlc(m)
    sig = m.literal_signal(close, 2)
    return m.build_score(sig, close, 126), "M"


@R.reg("gap", "V4 L5 thr0.010")
def _gap(a):
    m = load(a)
    return m.momentum_only_score(panel()) if False else m.score_from_flag(panel(), m.gap_flag(panel(), 5, 0.01)), "M"


@R.reg("keltner", "kelt_pure_p40_m2 (best TRAIN Sharpe)")
def _kelt(a):
    m = load(a)
    d = m.load_ohlc()
    return m.make_score(panel(), d["high"], d["low"], 40, 2.0, "pure"), "M"


@R.reg("momentum_factor", "M4 (p126 t0.08 rank126)")
def _mf(a):
    m = load(a)
    v = [x for x in m.VARIANTS if x.tag == "M4"][0]
    return m.build_score(panel(), v), "M"


@R.reg("multifactor", "V1 p20 rsip14 rank126")
def _mfu(a):
    m = load(a)
    return m.score_variant(panel(), 20, 14, 126, False), "M"


@R.reg("regime_switch", "V5_p200_verySlow")
def _rs(a):
    m = load(a)
    return m.strategy_score(panel(), 200), "M"


@R.reg("regression", "V4_p50_momrank")
def _reg(a):
    m = load(a)
    return m.regression_score(panel(), 50, "momrank"), "M"


@R.reg("relstrength", "V4 roc126 t8%")
def _rel(a):
    m = load(a)
    px = panel()
    sig = m.build_signal(px, 126, 0.08)
    return m.build_score(px, sig), "M"


@R.reg("stochastic", "V5:momentum (p14 30/70, rank mom126)")
def _sto(a):
    m = load(a)
    from nsealgo.data.loader import load_symbol

    close, syms, _rep = m.load_universe()
    hs, ls = {}, {}
    for sym in syms:
        df = load_symbol(f"data/nse/{sym}_1d.csv", sym)
        hs[sym] = df["high"].rename(sym)
        ls[sym] = df["low"].rename(sym)
    high = pd.DataFrame(hs).reindex(index=close.index, columns=close.columns)
    low = pd.DataFrame(ls).reindex(index=close.index, columns=close.columns)
    k = m.stoch_k_panel(high, low, close, 14)
    sig = m.signal_panel(k, 30.0, 70.0)
    mom = close / close.shift(126) - 1.0
    return m.build_score(mom.where(sig > 0)), "M"


@R.reg("timeseries", "V4 p126 thr0.00")
def _ts(a):
    m = load(a)
    return m.score_from_signal(panel(), 126, 0.0), "M"


@R.reg("tmr", "V4 slow40 entry1.0")
def _tmr(a):
    m = load(a)
    return m.tmr_score(panel(), 40, 1.0, 126), "M"


@R.reg("voltarget", "V4_atronly_mom126")
def _vt(a):
    m = load(a)
    return m.build_score("V4_atronly_mom126", panel()), "M"


@R.reg("volscaling", "V4_gateonly_mom126 (min_vol=0.0 mom126)")
def _vs(a):
    m = load(a)
    return m.build_score(0.0, "mom126", 14), "M"


@R.reg("vwm", "V1 p20 t0.01")
def _vwm(a):
    m = load(a)
    close, vol = m.load_panels()[:2]
    sig, _ = m.vwm_signal(close, vol, 20, 0.01, True)
    return m.momentum_rank_score(close, sig, 126), "M"


@R.reg("williamsr", "V4 fast-touch21 (p5 lower-80)")
def _wr(a):
    m = load(a)
    close, syms, _rep = m.load_panel()
    high, low = m.load_hl(syms, close)
    sig = m.signal_panel(close, high, low, 5, -80.0, 21)
    return m.wr_score(close, sig), "M"


@R.reg("zscore", "V5 L60 e0.5")
def _zs(a):
    m = load(a)
    return m.zscore_score(panel(), 60, 0.5), "M"


if __name__ == "__main__":
    R.main()
