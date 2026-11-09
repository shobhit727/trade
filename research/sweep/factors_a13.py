"""Agent 13 -- wave 1: MAXIMUM DRAWDOWN RECOVERY.

Directive: *"time since the 52-week low, as a recovery momentum proxy."*

Why this is not a duplicate of the catalogue
--------------------------------------------
The harness already carries three 52-week MAGNITUDE measures:

* ``low_52w``    -- distance above the 52-week low (negated).
* ``dd_252``     -- distance below the 52-week high (negated).
* ``range_pos``  -- where in the 52-week range the price sits.

All three answer *how far* the price is from an extreme. None carries the
TIMING information -- **when** the extreme happened -- which is what this
assignment owns. A name that bottomed 200 days ago and has been climbing
since is a different animal from a name that bottomed yesterday, even when
the two sit at the same distance from their 52-week low. Timing is a
different statistic, not a reparameterisation: it is invariant to the depth
of the recovery.

Sign hypotheses (all "higher = better", as the harness expects)
---------------------------------------------------------------
1. ``a13_tsl_252``      age of the 52-week trough, in bars.
   MECHANISM: recovery momentum. A trough that is OLD means the name bottomed
   long ago and the rebound since then has had time to establish itself as a
   trend; the recovery is the trend and trends persist over a 15-60 day
   holding horizon. A trough that is RECENT means the name is still in
   free-fall (or at the exact inflection, which is unidentifiable ex ante),
   and short-horizon continuation is the dominant behaviour after a fresh
   52-week low. So: older trough -> higher score.
   NOTE this is the OPPOSITE sign to ``low_52w`` (distance above the low):
   a name far above its low has already run, while a name AT its low has the
   most room. If the mechanism is real, one of the two wins and which one
   wins is the finding.

2. ``a13_tsl_252_neg``  the negation of (1). This is the capitulation
   reading: a fresh 52-week low is exhausted-seller exhaustion and the
   reversal is large. Running both is the point -- one of the two must win
   if either mechanism is real.

3. ``a13_low_upfrac_252``  up-day fraction of the recovery since the trough.
   MECHANISM: the SHAPE of the recovery, not its age. A recovery made of
   mostly up-days is persistent accumulation (the low was a capitulation low
   that found a base); a recovery that chops sideways and down is the rally
   being sold into, and predicts worse forward returns. Higher up-fraction
   -> better. Distinct from ``breadth`` (which counts the last 21 bars
   regardless of where the trough was) because the window is anchored on the
   trough date.

4. ``a13_low_reset_252``  negated count of NEW 52-week lows in the last year.
   MECHANISM: drawdown recurrence. A name that keeps printing fresh
   52-week lows is in an ongoing downtrend with supply still coming; a name
   that stopped making new lows has stopped bleeding. Fewer resets ->
   better. This is a COUNT of events, not a distance, so it separates
   "fell 40% once" from "bled 10% ten times".

5. ``a13_cycle_phase_252``  date(52-week high) - date(52-week low).
   MECHANISM: cycle phase. Positive means the peak came AFTER the trough --
   the drawdown is over and the recovery is confirmed; negative means the
   trough is the most recent extreme and the name is still making lows.
   This is the ORDERING of the two extremes, which no magnitude measure
   carries, and it is not the same as ``high_52w`` (a name can be 2% below
   its high while still making new lows, or at its high while making new
   lows).

6. ``a13_cycle_phase_252_neg``  the negation of (5), for the same sign-test
   reason as (2).

No lookahead: every construction uses bars up to and including the current
one. The rolling trough/high are trailing windows; the recovery statistics
only look forward from the trough to the current bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

#: 52 weeks in trading bars.
W52 = 252

#: Minimum fraction of the window that must be present for the trailing
#: extreme to be considered identified.
_MIN_COVERAGE = 0.80

#: Cache of the expensive trailing-extreme computation, keyed by the panel
#: identity and window. The harness calls a factor once per cell with the
#: SAME panel object, so this is computed once per factor, not once per cell.
_EXTREME_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _rolling_argmin(filled: np.ndarray, window: int, chunk: int = 256) -> np.ndarray:
    """Absolute row index of the minimum of each trailing ``window``.

    ``filled`` is (T, N) with no NaN -- the caller substitutes +inf (for a
    trough) or -inf (for a peak) so that missing bars can never win the
    argmin. Returns (T, N) int64, -1 where the window is not full.

    Vectorised with a sliding window view and processed in chunks so the
    intermediate never exceeds a few tens of MB.
    """
    T, N = filled.shape
    out = np.full((T, N), -1, dtype=np.int64)
    if T < window:
        return out
    for s in range(window - 1, T, chunk):
        e = min(s + chunk, T)
        lo = s - window + 1
        block = filled[lo:e]
        view = np.lib.stride_tricks.sliding_window_view(block, window, axis=0)
        rel = np.argmin(view, axis=2)
        k = np.arange(rel.shape[0])[:, None]
        rows = lo + k[:, 0] + (window - 1)
        out[rows] = rel + lo + k
    return out


def _extremes(px: pd.DataFrame, window: int) -> tuple[np.ndarray, np.ndarray]:
    """(trough_row_index, peak_row_index) of the trailing ``window`` bars.

    -1 marks a row where the window is not sufficiently covered.
    """
    key = (id(px), px.shape, str(px.index[0]), str(px.index[-1]), window)
    hit = _EXTREME_CACHE.get(key)
    if hit is not None:
        return hit

    arr = px.to_numpy(dtype=float)
    finite = np.isfinite(arr)
    trough = _rolling_argmin(np.where(finite, arr, np.inf), window)
    peak = _rolling_argmin(np.where(finite, -arr, -np.inf), window)

    coverage = pd.DataFrame(arr).rolling(window, min_periods=1).count().to_numpy()
    ok = coverage >= (_MIN_COVERAGE * window)
    trough = np.where(ok, trough, -1)
    peak = np.where(ok, peak, -1)

    _EXTREME_CACHE[key] = (trough, peak)
    return trough, peak


def _frame(values: np.ndarray, index, columns) -> pd.DataFrame:
    return pd.DataFrame(values, index=index, columns=columns)


def _age_from(index: np.ndarray) -> np.ndarray:
    """Bars elapsed since the trailing extreme; NaN where unidentified."""
    T = index.shape[0]
    rows = np.arange(T, dtype=np.int64)[:, None]
    age = rows - index
    return np.where(index >= 0, age.astype(float), np.nan)


# --------------------------------------------------------------------------- #
# 1 / 2 -- age of the 52-week trough
# --------------------------------------------------------------------------- #
@factor("a13_tsl_252")
def _a13_tsl_252(px: pd.DataFrame) -> pd.DataFrame:
    """Bars since the 52-week low. Higher = older trough = mature recovery."""
    trough, _ = _extremes(px, W52)
    return _frame(_age_from(trough), px.index, px.columns)


@factor("a13_tsl_252_neg")
def _a13_tsl_252_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation: a FRESH 52-week low is a capitulation setup. Higher = newer low."""
    trough, _ = _extremes(px, W52)
    return _frame(-_age_from(trough), px.index, px.columns)


# --------------------------------------------------------------------------- #
# 3 -- shape of the recovery
# --------------------------------------------------------------------------- #
@factor("a13_low_upfrac_252")
def _a13_low_upfrac_252(px: pd.DataFrame) -> pd.DataFrame:
    """Fraction of up-days between the 52-week low and now. Higher = smoother
    recovery = accumulation rather than distribution."""
    trough, _ = _extremes(px, W52)
    arr = px.to_numpy(dtype=float)
    up = np.nan_to_num((np.diff(arr, axis=0) > 0).astype(float), nan=0.0)
    up_cum = np.vstack([np.zeros((1, arr.shape[1])), np.cumsum(up, axis=0)])

    T, N = arr.shape
    clip = np.clip(trough, 0, T - 1)
    at_trough = up_cum[clip, np.arange(N)[None, :]]
    n_up = up_cum - at_trough                 # up-days strictly after the trough
    n_bars = _age_from(trough)                # transitions from the trough to now
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(n_bars > 0, n_up / np.where(n_bars > 0, n_bars, 1.0), 0.0)
    frac = np.where(trough >= 0, frac, np.nan)
    return _frame(frac, px.index, px.columns)


# --------------------------------------------------------------------------- #
# 4 -- recurrence of drawdown lows
# --------------------------------------------------------------------------- #
@factor("a13_low_reset_252")
def _a13_low_reset_252(px: pd.DataFrame) -> pd.DataFrame:
    """Negated count of new 52-week lows in the trailing year. Higher = fewer
    fresh lows = the bleeding has stopped."""
    prev_min = px.shift(1).rolling(W52 - 1, min_periods=60).min()
    new_low = (px < prev_min).fillna(False)
    resets = new_low.rolling(W52, min_periods=120).sum()
    return -resets


# --------------------------------------------------------------------------- #
# 5 / 6 -- cycle phase: did the peak come after the trough?
# --------------------------------------------------------------------------- #
@factor("a13_cycle_phase_252")
def _a13_cycle_phase_252(px: pd.DataFrame) -> pd.DataFrame:
    """Date(52w high) - date(52w low). Higher = the peak is newer than the
    trough = the drawdown is over and the recovery is confirmed."""
    trough, peak = _extremes(px, W52)
    phase = np.where((trough >= 0) & (peak >= 0), peak - trough, np.nan)
    return _frame(phase.astype(float), px.index, px.columns)


@factor("a13_cycle_phase_252_neg")
def _a13_cycle_phase_252_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of the cycle phase: still making new lows is the better bet."""
    trough, peak = _extremes(px, W52)
    phase = np.where((trough >= 0) & (peak >= 0), peak - trough, np.nan)
    return _frame(-phase.astype(float), px.index, px.columns)
