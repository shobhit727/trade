"""Per-stock null models.

This module exists because of a measured failure. In the cross-sectional harness, **100
of 100 random 22-name books were profitable**, averaging +8.59%/yr. Any strategy scored
against buy-and-hold alone therefore clears an absurdly low bar. We measured that the
composite's own "edge" was *negative* on selection while its positive return came entirely
from trading less.

So every ``(strategy, stock)`` pair here is scored against **three** references that share
its own data:

``buy_hold``
    That stock's own return over the same window. A stock that returned 40%/yr proves
    nothing about the strategy that traded it.

``random_timing``
    Random long/flat decisions on the *same* stock with the *same* turnover rate and
    costs. This isolates "was the timing informative" from "was the exposure informative".

``random_params``
    The same strategy with random Config draws. This isolates "did the search find
    anything" from "is the strategy family informative at all".

Any pair whose optimised result fails to beat its own ``random_params`` null has learned
nothing. That check is applied in ``analyze.py`` with FDR correction across all 4,200 pairs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def buy_and_hold(bars: pd.DataFrame, start: str | None = None, end: str | None = None) -> float:
    """Total return of holding the stock across the window (no costs, no rebalance)."""
    if start is not None:
        bars = bars[bars.index >= pd.Timestamp(start)]
    if end is not None:
        bars = bars[bars.index <= pd.Timestamp(end)]
    if len(bars) < 2 or float(bars["close"].iloc[0]) <= 0:
        return 0.0
    return float(bars["close"].iloc[-1] / bars["close"].iloc[0] - 1.0)


def buy_and_hold_cagr(bars: pd.DataFrame, start: str | None = None, end: str | None = None) -> float:
    if start is not None:
        bars = bars[bars.index >= pd.Timestamp(start)]
    if end is not None:
        bars = bars[bars.index <= pd.Timestamp(end)]
    n = len(bars)
    if n < 2:
        return 0.0
    a, b = float(bars["close"].iloc[0]), float(bars["close"].iloc[-1])
    if a <= 0 or b <= 0:
        return 0.0
    years = n / C.TRADING_DAYS
    return float((b / a) ** (1.0 / years) - 1.0) if years > 0 else 0.0


def random_timing_returns(
    bars: pd.DataFrame,
    target_exposure: float,
    rng: np.random.Generator,
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.Series:
    """Daily returns of a random-timing long/flat book, cost-charged on changes.

    ``target_exposure`` is the realised exposure of the strategy being tested, so the null
    is exposure-matched. That matters: we measured that a book turning over 3.75x/yr earns
    a cost *penalty* versus one turning over 2.51x/yr, and comparing across exposures
    credits the wrong channel.
    """
    if start is not None:
        bars = bars[bars.index >= pd.Timestamp(start)]
    if end is not None:
        bars = bars[bars.index <= pd.Timestamp(end)]
    if len(bars) < 2:
        return pd.Series(dtype=float)

    px = bars["close"].to_numpy(dtype=float)
    rets = np.zeros_like(px)
    rets[1:] = px[1:] / px[:-1] - 1.0
    rets[~np.isfinite(rets)] = 0.0

    n = len(px)
    target = rng.random(n) < float(np.clip(target_exposure, 0.0, 1.0))
    target[0] = bool(target[0])

    # Charge on position changes only. ``diff`` is length n-1 because day 0 has no prior
    # position; pad it back to length n so it broadcasts against the returns.
    switches = np.zeros(n, dtype=float)
    switches[1:] = np.abs(np.diff(target.astype(float)))
    cost_per_switch = float(C.ALL_IN_ROUND_TRIP_BPS) / 10_000.0
    net = np.where(target, rets, 0.0) - switches * cost_per_switch
    return pd.Series(net, index=bars.index, name="null")


def timing_null_cagr(
    bars: pd.DataFrame,
    target_exposure: float,
    seed: int,
    replicas: int = C.DEFAULT_NULL_REPLICAS,
    *,
    start: str | None = None,
    end: str | None = None,
) -> np.ndarray:
    """Distribution of CAGR under random timing at matched exposure."""
    rng = np.random.default_rng(seed)
    out = np.empty(replicas, dtype=float)
    n_years = (len(bars) / C.TRADING_DAYS) if len(bars) else 0.0
    for i in range(replicas):
        r = random_timing_returns(bars, target_exposure, rng, start=start, end=end)
        if n_years <= 0 or r.empty:
            out[i] = 0.0
            continue
        curve = (1.0 + r).cumprod()
        out[i] = float(curve.iloc[-1] ** (1.0 / n_years) - 1.0)
    return out


def params_null_cagrs(cagrs: list[float]) -> np.ndarray:
    """The null for 'did the search find something': the spread of random Config draws.

    ``cagrs`` are the TRAIN CAGRs of the random configs evaluated for this pair. If the
    optimised result does not clear this distribution, the optimiser found noise. The
    seed is unused by design -- this is an empirical distribution over configs already
    drawn, not a resample.
    """
    if not cagrs:
        return np.zeros(1)
    return np.asarray(cagrs, dtype=float)


def p_value(observed: float, null: np.ndarray) -> float:
    """One-sided empirical p-value with the standard +1 correction.

    With 200 replicas the smallest reportable p is 1/201 ~ 0.005. That floor is a real
    limit of the design and is why FDR correction, not the raw p, drives the headline.
    """
    null = np.asarray(null, dtype=float)
    if null.size == 0:
        return 1.0
    return float((np.sum(null >= observed) + 1) / (null.size + 1))
