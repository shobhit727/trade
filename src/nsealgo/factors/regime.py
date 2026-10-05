"""Market regime filter — the drawdown lever.

The cross-sectional composite alone produced a **-40.9% max drawdown** over
2008-2026, which fails `GOAL.md` §2.3 Band C (<35%). Long-only factor portfolios in
India are structurally beta-laden (QED, SSRN 4000418: *"market exposure is significant
across all the style strategies"*), so without an overlay the book eats every decline.

The overlay is a **time-series momentum gate on the equal-weight market proxy**, the only
India-specific published support for such an overlay (Singh & Walia 2020). Its own FF4
regressions put the short leg as cash, so it is implementable in a pure delivery account.

Contract
--------
``exposure_series`` returns an **exposure multiplier** in ``[threshold, 1.0]``.
``blend_with_cash`` combines it with a strategy return series so that a de-risked day
earns the risk-free rate instead of going negative.

Both are strictly backward-looking: the exposure decided from data through *t-1* is
applied to day *t*.
"""

from __future__ import annotations

import pandas as pd

TRADING_DAYS = 244


def market_proxy(panel: pd.DataFrame) -> pd.Series:
    """Equal-weight universe daily return — our market proxy (no index data)."""
    return panel.pct_change(fill_method=None).mean(axis=1)


def exposure_series(
    panel: pd.DataFrame,
    lookback: int = 126,
    threshold: float = 0.35,
) -> pd.Series:
    """Exposure multiplier in ``[threshold, 1.0]``, decided from prior data only.

    Risk-on when the market proxy's trailing ``lookback`` window has a positive mean
    daily return **and** a cumulative return better than ``-max_drop``.
    """
    proxy = market_proxy(panel).fillna(0.0)
    min_bars = max(lookback // 2, 20)

    ma = proxy.rolling(lookback, min_periods=min_bars).mean()
    cum = proxy.rolling(lookback, min_periods=min_bars).sum()
    max_drop = 0.5 * threshold  # e.g. threshold 0.35 -> tolerate -17.5% window loss

    risk_on = (ma > 0) & (cum > -max_drop)

    # Exposure for day t uses information through t-1.
    raw = risk_on.astype(float).shift(1)
    raw = raw.fillna(1.0)  # insufficient history -> stay fully invested
    return raw.clip(lower=threshold, upper=1.0).rename("exposure")


def blend_with_cash(
    returns: pd.Series,
    exposure: pd.Series,
    rf_annual: float = 0.065,
) -> pd.Series:
    """Scale the strategy's exposure; the remainder earns the risk-free rate."""
    rf_daily = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    idx = returns.index.intersection(exposure.index)
    r = returns.loc[idx].fillna(0.0)
    e = exposure.loc[idx].fillna(1.0)
    return (e * r + (1.0 - e) * rf_daily).rename("blended")
