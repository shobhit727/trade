"""Wave 1 -- Agent 16 -- REGIME A: PRICE-MEMORY EFFICIENCY.

Assignment
----------
A simple Amihudi-style illiquidity measure on returns, used as a *tradability
filter* rather than as an alpha source.

Mechanism under test
--------------------
Abdi & Ranaldo (2017) show that a price is "efficient" when it forgets the
past quickly, and they price that memory with an illiquidity ratio built from
returns and turnover: the more price impact a name shows per rupee traded, the
more stale information its price carries. The same construction (Amihudi 2002)
predicts a *liquidity premium*: less liquid names should earn higher expected
returns as compensation for bearing illiquidity risk.

Two opposite predictions follow, and both are measured here:

* ILLIQUIDITY PREMIUM (alpha reading) -- the less liquid names earn more, so
  HIGH illiquidity should rank better.
* TRADABILITY FILTER (filter reading) -- the less liquid names are exactly the
  ones you cannot trade without giving away the return, so HIGH liquidity
  should rank better.

The decisive caveat, stated up front: this harness charges a FLAT cost stack
(32.32 bp statutory + 10 bp slippage) to every name. It does not charge more
for an illiquid name. So if the illiquid side wins here, the win is an
upper bound that a real impact model would partly or wholly eat. That is a
property of the measurement, not of the factor.

Harness note (important, and a real trap)
-----------------------------------------
The book builder breaks score ties with a deterministic 1e-9 epsilon added to
each name's score. The raw Amihudi ratio lives around 1e-12, i.e. its entire
cross-sectional spread is ~100x SMALLER than that epsilon -- an unscaled
factor would have its ordering completely dominated by the tie-break and would
have measured nothing at all while looking like a clean negative. Every factor
below therefore returns a CROSS-SECTIONAL RANK in (0, 1], which is a strictly
monotone transform of the raw measure (so it selects exactly the same book)
but is scale-stable by construction.

Data
----
Close and volume come from the shared, C10-cleaned loader
(``research.sweep.harness.ohlc_wide``). Returns are taken from the RAW
(cleaned, un-forward-filled) close rather than from the sweep panel: the panel
is forward-filled, which smears a multi-day move across the days of a data
gap, and an illiquidity measure built on smeared returns is not a
measure of anything.

No lookahead: every window is trailing and ends on the current bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor, ohlc_wide

# --------------------------------------------------------------------------- #
# Shared, cached primitives
# --------------------------------------------------------------------------- #
_DAILY: tuple[pd.DataFrame, ...] | None = None


def _cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank in (0, 1]. Scale-free and tie-break-safe."""
    return df.rank(axis=1, pct=True)


def _daily() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(close, volume, return) wide frames from the shared cleaned loader.

    Cached at module level: the loader itself caches, but the derivations
    (log volume, returns) are recomputed for every factor otherwise.
    """
    global _DAILY
    if _DAILY is None:
        close = ohlc_wide("close")
        vol = ohlc_wide("vol")
        r = close.pct_change(fill_method=None)
        turnover = (close * vol).replace(0.0, np.nan)
        _DAILY = (close, vol, r, turnover)
    return _DAILY


def _amihudi(window: int, min_periods: int) -> pd.DataFrame:
    """Amihudi (2002) ILLIQ: mean of |return| per rupee of turnover.

    Higher = MORE illiquid. Trailing window, no lookahead.
    """
    _, _, r, turnover = _daily()
    daily = (r.abs() / turnover).replace([np.inf, -np.inf], np.nan)
    return daily.rolling(window, min_periods=min_periods).mean()


# --------------------------------------------------------------------------- #
# 1. Amihudi illiquidity, 21-day window -- both signs
# --------------------------------------------------------------------------- #
@factor("amihudi_illiq_21")
def _amihudi_illiq_21(px: pd.DataFrame) -> pd.DataFrame:
    """Amihudi illiquidity (21d). HIGHER = more illiquid ranks better.

    Sign hypothesis (liquidity premium): illiquid names compensate their
    holders for the liquidity risk they bear, so they should earn more.
    """
    return _cs_rank(_amihudi(21, 10))


@factor("amihudi_liq_21")
def _amihudi_liq_21(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of amihudi_illiq_21. HIGHER = more liquid ranks better.

    Sign hypothesis (tradability filter): the illiquid names are the ones you
    cannot trade without paying the return away, so prefer the liquid ones.
    """
    return _cs_rank(-_amihudi(21, 10))


# --------------------------------------------------------------------------- #
# 2. Amihudi illiquidity, 252-day window -- both signs
# --------------------------------------------------------------------------- #
@factor("amihudi_illiq_252")
def _amihudi_illiq_252(px: pd.DataFrame) -> pd.DataFrame:
    """Amihudi illiquidity (252d) -- STRUCTURAL liquidity, not a regime.

    Sign hypothesis (liquidity premium): the structural liquidity premium is
    the one Abdi & Ranaldo report, so more illiquid should rank better.
    """
    return _cs_rank(_amihudi(252, 120))


@factor("amihudi_liq_252")
def _amihudi_liq_252(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of amihudi_illiq_252. HIGHER = more liquid ranks better.

    Sign hypothesis (tradability filter): hold the names you can actually
    trade. Structural (1y) liquidity is the right horizon for that question --
    a 21-day measure mostly captures a temporary liquidity crunch.
    """
    return _cs_rank(-_amihudi(252, 120))


# --------------------------------------------------------------------------- #
# 3. Price-impact asymmetry -- does the price move more when it is illiquid?
# --------------------------------------------------------------------------- #
@factor("impact_asym_126")
def _impact_asym_126(px: pd.DataFrame) -> pd.DataFrame:
    """Price-memory asymmetry, measured against the name's OWN turnover history.

    For each name, split its own last-252-day turnover distribution into a
    thin half and a liquid half, and compare the mean absolute move on the two
    halves. If the price moves much more on thin days, the price is
    remembering (it does not clear against depth) -- that is price memory.

    Using the name's OWN history rather than the cross-section keeps this out
    of the size-proxy corner: it asks about the shape of the liquidity
    profile, not its level.

    Sign hypothesis (tradability filter): HIGHER = more efficient price
    discovery ranks better, because a name whose price does not distort when
    liquidity dries up is a name whose quoted price can be trusted.
    """
    _, vol, r, _ = _daily()
    a = r.abs()
    pct = np.log1p(vol).rolling(252, min_periods=60).rank(pct=True)
    thin = a.where(pct <= 0.5).rolling(126, min_periods=30).mean()
    rich = a.where(pct >= 0.5).rolling(126, min_periods=30).mean()
    asym = (thin - rich) / (thin + rich).replace(0.0, np.nan)
    return _cs_rank(-asym)


# --------------------------------------------------------------------------- #
# 4. Tradability capacity -- how much rupee volume this name actually has
# --------------------------------------------------------------------------- #
@factor("adv_capacity_63")
def _adv_capacity_63(px: pd.DataFrame) -> pd.DataFrame:
    """Mean daily rupee turnover over 63 days. HIGHER = more tradable ranks better.

    Sign hypothesis (tradability filter): at Rs 21 lakh of capital the
    binding constraint is not capacity but the price impact of a Rs 10 lakh
    clip in a thin book, so the deepest names should be preferred.

    HONEST CAVEAT: average daily rupee turnover is largely a size proxy.
    This is the purest form of the "tradability filter" the assignment asks
    for, and it is also the factor most likely to be a disguised size tilt.
    """
    close, vol, _, _ = _daily()
    adv = (close * vol).rolling(63, min_periods=30).mean()
    return _cs_rank(adv)
