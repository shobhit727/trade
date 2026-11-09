"""Vectorised port of `DispersionStrategy` (src/cryptobot/strategies/catalog/dispersion_strategy.py).

Fidelity notes
--------------
The catalog signal is::

    z = zscore(closes)              # EXPANDING window: all history up to t
    m = sma(closes, period)         # period-bar simple moving average
    if z >= entry and close[-1] > m:  -> +1
    if z <= -entry and close[-1] < m: -> -1
    else                               -> 0

`strategies.indicators.zscore` uses `a.std()` over the **entire** array it is handed,
which in the engine is the whole history up to t. So the faithful vectorised form is
an *expanding* z-score, not a rolling one. `verify_against_catalog()` asserts this.

NSE adaptation (documented, not silent):
* The book is long-only, so only the ``+1`` branch can be acted on. The ``-1``
  branch is kept in the signal panel for reporting, never traded.
* A time-series +/-1/0 signal has no cross-sectional ordering, so it is turned into
  a score exactly as AGENT_BRIEF §5 prescribes: among flagged names, rank by
  trailing momentum.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def expanding_zscore(panel: pd.DataFrame) -> pd.DataFrame:
    """(x_t - expanding_mean) / expanding_std, using only data up to t."""
    mean = panel.expanding(min_periods=2).mean()
    std = panel.expanding(min_periods=2).std(ddof=0)  # np.std default ddof=0
    z = (panel - mean) / std.replace(0.0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan)


def sma_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Simple moving average over the trailing ``period`` bars (past-inclusive)."""
    return panel.rolling(period, min_periods=period).mean()


def dispersion_signal(
    panel: pd.DataFrame,
    period: int = 30,
    entry: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(long_signal, short_signal)`` boolean panels, faithful to the catalog.

    `long_signal[t, s]` is True iff, using closes up to and including t only,
    zscore >= entry and close[t] > sma(period)[t].
    """
    z = expanding_zscore(panel)
    m = sma_panel(panel, period)
    long_sig = (z >= entry) & (panel > m)
    short_sig = (z <= -entry) & (panel < m)
    return long_sig.fillna(False), short_sig.fillna(False)


def dispersion_score(
    panel: pd.DataFrame,
    long_sig: pd.DataFrame,
    mom_days: int = 126,
) -> pd.DataFrame:
    """AGENT_BRIEF §5 construction: rank trailing momentum among flagged names.

    Non-flagged names get NaN so `build_rebalance_weights` skips them
    (`valid = isfinite(score)`), which is how the long-only gate is enforced.
    """
    mom = panel / panel.shift(mom_days) - 1.0
    return mom.where(long_sig).rank(axis=1, pct=True)


def verify_against_catalog(
    panel: pd.DataFrame,
    period: int,
    entry: float,
    n_check: int = 40,
) -> float:
    """Max |vectorised - catalog| over random-ish sampled (t, symbol) points.

    Imports the real catalog class and calls it with the true trailing slice, so
    the vectorised port is checked against the shipped code, not against my
    reading of it.
    """

    from cryptobot.strategies.catalog.dispersion_strategy import (
        DispersionConfig,
        DispersionStrategy,
    )

    strat = DispersionStrategy(DispersionConfig(period=period, entry=entry))
    warm = strat.warmup(None)

    rng = np.random.default_rng(0)
    cols = list(panel.columns)
    rows = rng.choice(len(panel.index), size=n_check, replace=False)

    long_sig, short_sig = dispersion_signal(panel, period=period, entry=entry)

    disagreements: list = []
    checked = 0
    for r in rows:
        if r < warm + 1:
            continue
        for c in cols:
            slice_ = panel.iloc[: r + 1][c]
            if slice_.isna().any():
                continue
            checked += 1
            expected = strat.signal(
                slice_.tolist(), slice_.tolist(), slice_.tolist(), [1] * len(slice_)
            )

            is_long = bool(long_sig.iat[r, cols.index(c)])
            is_short = bool(short_sig.iat[r, cols.index(c)])

            # The catalog returns a single signed value. Map it onto the pair of
            # booleans the vectorised port produces and require an exact match.
            if expected == 1:
                ok = is_long and not is_short
            elif expected == -1:
                ok = is_short and not is_long
            else:
                ok = not is_long and not is_short

            if not ok:
                disagreements.append(
                    (panel.index[r].date(), c, expected, is_long, is_short)
                )

    if disagreements:
        for d in disagreements[:10]:
            print("  MISMATCH", d)
    max_err = len(disagreements)
    print(f"  (checked {checked} (t, symbol) points)")

    return float(max_err)
