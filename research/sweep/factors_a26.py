"""Agent 26 -- Regime B: bottom-quartile construction.

The question: build the book from the WORST names. Is the short-side / junk end
where the edge lives?

The harness only ever goes long: it buys the top-``n_hold`` names by score and
its ``short_side`` flag is accepted but never read. So a bottom-quartile book is
expressed as a factor whose *highest* score is the worst name. Each idea is
registered in both directions (``*_bottom`` = long the bad end; its twin = long
the good end) so the report can say which end pays rather than assuming one.

Why these are new information: none of the 37 catalogue factors reads
open/high/low/volume. ``gap`` is a stub that returns ``px`` unchanged,
``amihud`` divides by nothing (no volume term) and ``intraday_vs_overnight`` is
a mean/std ratio of close returns, not a decomposition. So the entire volume
and intrabar information set is unused, and that is where all five ideas below
get their content.

Bars come from ``research.optimize.splitter`` -- the loader-C10-repaired reader
already used by the close panel -- never from a private CSV parser, so the OHLCV
columns line up with ``harness.panel()`` row for row.

Lookahead: every window is trailing. Overnight returns use ``open[t]`` against
``close[t-1]``; intraday uses ``close[t]`` against ``open[t]``. Both are known
by the close of ``t``, which is where the harness assumes execution.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor, panel

_WIDE: dict[str, pd.DataFrame] = {}


def _wide(field: str) -> pd.DataFrame:
    """One OHLCV column as a dates x names panel aligned to ``harness.panel()``."""
    if field in _WIDE:
        return _WIDE[field]

    from research.optimize import splitter as S

    px = panel()
    frames: dict[str, pd.Series] = {}
    for path in sorted(S.C.DATA_DIR.glob("*_1d.csv")):
        sym = path.name[: -len("_1d.csv")]
        if sym in S.EXCLUDED_SYMBOLS:
            continue
        df = S.bars(sym, timeframe="1d")
        if df.empty or field not in df.columns:
            continue
        frames[sym.lower()] = df[field]

    out = pd.DataFrame(frames).sort_index()
    out = out.reindex(index=px.index, columns=px.columns).ffill()
    _WIDE[field] = out
    return out


def _overnight() -> pd.DataFrame:
    """log(open[t] / close[t-1]): return earned while the market was shut."""
    o = _wide("open").where(lambda x: x > 0)
    c = _wide("close").where(lambda x: x > 0)
    return np.log(o / c.shift(1))


def _intraday() -> pd.DataFrame:
    """log(close[t] / open[t]): return earned during the session."""
    o = _wide("open").where(lambda x: x > 0)
    c = _wide("close").where(lambda x: x > 0)
    return np.log(c / o)


# --- 1. overnight vs intraday drift --------------------------------------- #
# Literature (Lou/Polk/Skouras): the persistent part of a stock's return is the
# overnight part, and it proxies institutional demand; the intraday part is the
# retail/liquidity part and mean-reverts. A name whose entire move happens in
# the session is the "weak hands" name -- the bottom-quartile candidate.
@factor("onid_hi")
def _onid_hi(px: pd.DataFrame) -> pd.DataFrame:
    return (_overnight().rolling(63, min_periods=40).mean()
            - _intraday().rolling(63, min_periods=40).mean())


@factor("onid_lo_bottom")
def _onid_lo_bottom(px: pd.DataFrame) -> pd.DataFrame:
    return -_onid_hi(px)


# --- 2. real Amihud illiquidity ------------------------------------------- #
# The catalogue's ``amihud`` divides |return| by nothing, so it cannot see the
# volume column at all. This is the actual Amihud (2002) ratio: absolute return
# per rupee of turnover. Higher = more illiquid. The illiquidity-premium /
# neglected-firm hypothesis says the *worst* (least liquid) names should pay,
# so ``illiq_hi_bottom`` is the long-the-junk book.
@factor("illiq_hi_bottom")
def _illiq_hi_bottom(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change().abs()
    dv = (_wide("close") * _wide("volume")).replace(0, np.nan)
    # Raw |r| / rupee-turnover is ~1e-12, three decades below the harness's
    # 1e-9 tie epsilon: every name would tie on every date and the book would
    # be chosen by the hash tie-break instead of by this factor (measured: both
    # signs selected the identical book). Rescale to O(1); ranking is unchanged.
    return 1e11 * (r / dv).rolling(63, min_periods=40).median()


@factor("illiq_lo")
def _illiq_lo(px: pd.DataFrame) -> pd.DataFrame:
    return -_illiq_hi_bottom(px)


# --- 3. MAX / lottery demand ---------------------------------------------- #
# Bali/Cakici/Whitelaw: the single best day in the last month attracts lottery
# buyers and predicts low future returns. The names with the highest MAX are
# therefore the most overpriced "worst" names -- if the short-side has edge,
# ``max_hi_bottom`` should lose to the bench in a way that is not just cost.
@factor("max_lo")
def _max_lo(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    return -r.rolling(21, min_periods=15).max()


@factor("max_hi_bottom")
def _max_hi_bottom(px: pd.DataFrame) -> pd.DataFrame:
    return -_max_lo(px)


# --- 4. volume-return co-movement ----------------------------------------- #
# Does volume show up on up days (accumulation) or on down days (distribution)?
# Correlation is scale-free, so it survives the fact that C10 rescales price but
# not share volume: rupee turnover is split-invariant and the log volume is
# de-meaned inside the window before the correlation is taken.
@factor("vpcorr_hi")
def _vpcorr_hi(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    v = np.log1p(_wide("volume").where(lambda x: x > 0))
    rel = (v - v.rolling(63, min_periods=40).mean()).clip(-3.0, 3.0)
    return r.rolling(63, min_periods=40).corr(rel)


@factor("vpcorr_lo_bottom")
def _vpcorr_lo_bottom(px: pd.DataFrame) -> pd.DataFrame:
    return -_vpcorr_hi(px)


# --- 5. junk composite: literally "the worst names" ----------------------- #
# The assignment's book, assembled from four independent badness axes. Rank
# based, so no single axis can dominate through scale, and NaN propagates (a
# name missing any axis is not selectable rather than being silently filled
# with the median the way ``_zcs`` does).
@factor("junk_hi_bottom")
def _junk_hi_bottom(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    vol = r.rolling(63, min_periods=40).std()
    hi = px.rolling(252, min_periods=120).max()
    dd = 1.0 - px / hi
    mom = -px.pct_change(252)
    mx = r.rolling(21, min_periods=15).max()

    def pct(x: pd.DataFrame) -> pd.DataFrame:
        return x.rank(axis=1, pct=True)

    return (0.35 * pct(vol) + 0.25 * pct(dd)
            + 0.25 * pct(mom) + 0.15 * pct(mx))


@factor("junk_lo")
def _junk_lo(px: pd.DataFrame) -> pd.DataFrame:
    return -_junk_hi_bottom(px)
