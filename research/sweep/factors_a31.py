"""Agent 31 -- correlation concentration as a risk-budget input (Regime B).

Mechanism
---------
A stock's contribution to the risk of an equal-weight book is driven by how
much it co-moves with the rest of the universe.  When the universe's
correlation is concentrated (one common factor dominates) the names that still
diversify are the scarce risk-budget assets, while names that co-move with
everything consume the budget without adding breadth.

The factors below turn that structure into cross-sectional scores:

* ``corr_avg63``       -- stock's mean pairwise correlation with the universe.
                          Negated: low correlation = more diversification per
                          rupee of risk budget.
* ``corr_avg63_hi``    -- the same measurement with the opposite sign, so the
                          "crowded / leadership" reading is tested explicitly.
* ``marg_risk63``      -- marginal risk contribution to an equal-weight book,
                          (sigma_i^2 + sum_{j!=i} sigma_ij) / k.  Negated:
                          names that eat the risk budget rank lower.
* ``corr_delta63``     -- change in mean pairwise correlation versus the prior
                          63-day window.  A name whose correlation is *falling*
                          is becoming a better diversifier; one whose
                          correlation is rising is being absorbed into the
                          common factor.
* ``corr_regime_switch`` -- the sign of the correlation tilt is conditioned on
                          the universe's own concentration (mean pairwise
                          correlation over 63d versus its trailing 2-year
                          median): in concentrated regimes tilt to the
                          diversifiers, in dispersed regimes tilt to the
                          co-movers.

All inputs are trailing daily returns; nothing reads a bar after the decision
date.  The pairwise correlation matrix is built on the columns that have a
complete return history in the window, so listings and gaps do not silently
enter as zero-correlation names.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .harness import factor

WINDOW = 63
MIN_NAMES = 10

# id(px) -> (px, mean_corr, marg_risk, concentration).  The harness passes the
# same cached panel object to every cell, so this saves the O(T * N^2) sweep
# once per process without touching harness internals.
_CACHE: dict[int, tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Index]] = {}


def _stats(px: pd.DataFrame, window: int = WINDOW):
    key = id(px)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] is px and hit[3].equals(px.index):
        return hit[1], hit[2]

    rets = px.pct_change(fill_method=None).to_numpy(dtype=float)
    n_dates, n_cols = rets.shape
    mean_corr = np.full((n_dates, n_cols), np.nan)
    marg_risk = np.full((n_dates, n_cols), np.nan)
    conc = np.full(n_dates, np.nan)

    for t in range(window - 1, n_dates):
        block = rets[t - window + 1 : t + 1]
        complete = np.isfinite(block).all(axis=0)
        if complete.sum() < MIN_NAMES:
            continue
        cols = np.nonzero(complete)[0]
        a = block[:, cols]
        a = a - a.mean(axis=0)
        sd = a.std(axis=0, ddof=1)
        alive = sd > 0
        if alive.sum() < MIN_NAMES:
            continue
        cols = cols[alive]
        sd = sd[alive]
        z = a[:, alive] / sd
        corr = (z.T @ z) / (window - 1)
        np.fill_diagonal(corr, np.nan)

        # Mean pairwise correlation, and marginal risk contribution of the
        # equal-weight book: (Sigma w)_i with w = 1/k.
        cov = corr * np.outer(sd, sd)
        np.fill_diagonal(cov, sd**2)
        k = len(cols)
        mean_corr[t, cols] = np.nanmean(corr, axis=1)
        marg_risk[t, cols] = cov.sum(axis=1) / k
        conc[t] = np.nansum(corr) / (k * (k - 1))

    mc = pd.DataFrame(mean_corr, index=px.index, columns=px.columns)
    mr = pd.DataFrame(marg_risk, index=px.index, columns=px.columns)
    cc = pd.Series(conc, index=px.index)
    _CACHE[key] = (px, mc, mr, px.index)
    return mc, mr


def _rank(x: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    return x.rank(axis=1, pct=True)


@factor("corr_avg63")
def corr_avg63(px: pd.DataFrame) -> pd.DataFrame:
    """Low mean pairwise correlation with the universe ranks higher."""
    mc, _ = _stats(px)
    return _rank(-mc)


@factor("corr_avg63_hi")
def corr_avg63_hi(px: pd.DataFrame) -> pd.DataFrame:
    """Explicit opposite sign: crowded / high-correlation names rank higher."""
    mc, _ = _stats(px)
    return _rank(mc)


@factor("marg_risk63")
def marg_risk63(px: pd.DataFrame) -> pd.DataFrame:
    """Low marginal risk contribution to the equal-weight book ranks higher."""
    _, mr = _stats(px)
    return _rank(-mr)


@factor("corr_delta63")
def corr_delta63(px: pd.DataFrame) -> pd.DataFrame:
    """Names whose correlation fell over the last quarter rank higher."""
    mc, _ = _stats(px)
    delta = mc - mc.shift(WINDOW)
    return _rank(-delta)


@factor("corr_regime_switch")
def corr_regime_switch(px: pd.DataFrame) -> pd.DataFrame:
    """Sign of the correlation tilt conditioned on universe concentration."""
    mc, _ = _stats(px)
    conc = mc.mean(axis=1)
    high = conc > conc.rolling(504, min_periods=252).median()
    sign = pd.Series(np.where(high, -1.0, 1.0), index=mc.index)
    return _rank(mc.mul(sign, axis=0))
