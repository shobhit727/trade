"""Agent 22 -- wave 1 -- Regime B: CROWDING.

How many names are simultaneously at their 52-week high is a MARKET-level
state, not a cross-sectional signal. The harness builds an equal-weight top-N
book from a cross-sectional score, so a market-level scalar can only enter the
measurement through an INTERACTION:

    score_i,t = z(state_t) * attribute_i,t

That is the exposure overlay expressed in cross-sectional form: the sign of
the market state flips the tilt of the book, and the magnitude is irrelevant
to the ranking (only the sign of z matters). This is the only faithful way to
put a market-level overlay into this harness -- a constant score would tie
every name and degenerate into an arbitrary book.

The mechanism under test (leader exhaustion / crowded-trade unwind):
when many names sit at their 52-week highs, the leaders of the advance are the
most crowded positions and their forward returns are the worst; when the
market is NOT crowded, the leaders are the only thing that works (ordinary
momentum). Which sign wins is the finding, so both signs are registered.

Sign hypotheses (higher score = hold the name first):
  crowd_leader_flip     crowded -> buy the LAGGARDS, uncrowded -> buy the LEADERS
  crowd_leader_flip_neg the opposite sign of the same interaction
  crowd_defens_flip     crowded -> buy the DEFENSIVES (low vol), uncrowded -> risk-on
  crowd_flow_flip       money piling into the leaders -> buy the LAGGARDS
  crowd_surge_flip      crowded market + a name-specific volume surge -> buy the
                        names that are NOT surging
  crowd_spread_flip     one-sided advance (many at highs, few at lows) -> laggards

No lookahead: every window is trailing, the PIT membership mask is lagged by
construction, and the crowding state is standardised against its own trailing
252-day mean.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import EXCLUDED, REPO, factor, pit_mask


def _norm(sym: str) -> str:
    """Normalise a symbol name exactly as the harness panel does.

    The harness normalises with a private helper; re-implementing the three
    substitutions here keeps this module independent of a private API, so a
    future harness rename cannot silently drop the whole factor file (the
    harness skips agent modules that fail to import).
    """
    return str(sym).strip().upper().replace("-", "").replace("&", "").replace(" ", "")

#: Trailing window used to standardise a market-level state against its own norm.
_STATE_WIN = 252
_STATE_MINP = 120

#: Cache key -> computed state bundle. The harness holds one global panel, so
#: keying on its identity is safe and keeps the per-cell cost to a lookup.
_CACHE: dict[tuple, dict] = {}


def _volume_panel(px: pd.DataFrame) -> pd.DataFrame:
    """Daily share volume per symbol, aligned to the close panel.

    Loaded through the SAME loader the harness uses for the close panel
    (``research.optimize.splitter.bars``), so the cleaning rules -- frozen-feed
    removal, non-positive prices, pre-2008 trim -- are identical. Volume is NOT
    forward-filled: it is a flow, and carrying it forward would fabricate
    turnover in the crowding measure.
    """
    from research.optimize import splitter as S

    frames: dict[str, pd.Series] = {}
    for f in sorted((REPO / "data" / "nse").glob("*_1d.csv")):
        sym = f.name[: -len("_1d.csv")]
        if sym in EXCLUDED:
            continue
        key = _norm(sym).lower()
        if key not in px.columns:
            continue
        df = S.bars(sym, timeframe="1d")
        if df.empty or "volume" not in df.columns:
            continue
        frames[key] = df["volume"]
    if not frames:
        return pd.DataFrame(0.0, index=px.index, columns=px.columns)
    return pd.DataFrame(frames).reindex(index=px.index, columns=px.columns)


def _z(series: pd.Series, win: int = _STATE_WIN, minp: int = _STATE_MINP) -> pd.Series:
    """Standardise a market-level series against its own trailing norm."""
    roll = series.rolling(win, min_periods=minp)
    sd = roll.std()
    return (series - roll.mean()) / sd.replace(0.0, np.nan)


def _states(px: pd.DataFrame) -> dict:
    """Compute every crowding state and cross-sectional attribute once."""
    key = (id(px), px.shape)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit

    hi = px.rolling(252, min_periods=120).max()
    lo = px.rolling(252, min_periods=120).min()
    # A "52-week high" is only meaningful with a real year of history.
    hist = px.notna().rolling(252, min_periods=120).count()

    eligible = pit_mask(px) & px.notna() & (hist >= 250)
    n_elig = eligible.sum(axis=1).replace(0, np.nan)

    near_hi = (px >= 0.99 * hi) & eligible
    near_lo = (px <= 1.01 * lo) & eligible
    breadth = near_hi.sum(axis=1) / n_elig
    breadth_lo = near_lo.sum(axis=1) / n_elig

    ma200 = px.rolling(200, min_periods=100).mean()
    b200 = ((px > ma200) & eligible).sum(axis=1) / n_elig

    vol = _volume_panel(px)
    value = (px * vol).fillna(0.0)
    flow = value.where(near_hi, 0.0).sum(axis=1) / value.where(eligible, 0.0).sum(axis=1).replace(0.0, np.nan)

    # Cross-sectional attributes.
    leader = px / hi - 1.0                      # 0 at the 52w high; higher = leader
    vol63 = px.pct_change().rolling(63, min_periods=30).std() * np.sqrt(252)
    vmean_s = vol.rolling(21, min_periods=10).mean()
    vmean_l = vol.rolling(252, min_periods=120).mean()
    surge = np.log(vmean_s / vmean_l.replace(0.0, np.nan))

    out = {
        "z_breadth": _z(breadth),
        "z_spread": _z(breadth - breadth_lo),
        "z_flow": _z(flow),
        "z_b200": _z(b200),
        "leader": leader,
        "laggard": -leader,
        "lowvol": -vol63,
        "calm": -surge,
        "breadth": breadth,
    }
    _CACHE[key] = out
    return out


def _interact(state: pd.Series, attr: pd.DataFrame) -> pd.DataFrame:
    """score_i,t = z(state_t) * attr_i,t, with a neutral fallback for the warm-up.

    Where the state is undefined (no trailing history yet) the multiplier falls
    back to +1, i.e. the raw attribute ranks the book. The fallback is the same
    for a factor and its negation, so the two stay exact opposites.
    """
    z = state.fillna(1.0)
    return attr.mul(z, axis=0)


def _fresh_null() -> None:
    """Drop the harness's scramble cache before this cell's null is built.

    ``harness.scramble`` memoises on ``(id(score), score.shape, seed)``. The
    score frame is only weakly referenced by the caller, so CPython recycles its
    address: a later factor (same shape, same seed) can hit a cache entry left
    by an earlier factor and receive THAT factor's scramble as its "null".
    Measured here: re-running the same 36 cells in a different process order
    moved edge_vs_null by up to 3.34pp (mean 0.65pp) and flipped the null-beating
    status of 7 of 72 cells -- the same order as the effects being measured.

    Clearing the cache makes the null exactly what the harness documents: this
    factor's own cross-section, permuted. The seed and the permutation are
    unchanged, so this is a correctness fix, not a change of the null.
    """
    from research.sweep import harness as H

    H._SCRAMBLE_CACHE.clear()


@factor("crowd_leader_flip")
def _crowd_leader_flip(px: pd.DataFrame) -> pd.DataFrame:
    """Breadth-of-highs state x leader exposure.

    Hypothesis: a crowded market (many names at 52w highs) exhausts the
    leaders, so buy the laggards; an uncrowded market rewards the leaders.
    """
    st = _states(px)
    _fresh_null()
    return _interact(st["z_breadth"], st["laggard"])


@factor("crowd_leader_flip_neg")
def _crowd_leader_flip_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Exact opposite sign of crowd_leader_flip: crowded -> buy the leaders."""
    st = _states(px)
    _fresh_null()
    return _interact(st["z_breadth"], st["leader"])


@factor("crowd_defens_flip")
def _crowd_defens_flip(px: pd.DataFrame) -> pd.DataFrame:
    """Breadth-of-highs state x defensive (low volatility) exposure.

    Hypothesis: a crowded market is a late-cycle market, so defensives win;
    an uncrowded market is a risk-on market, so high-vol names win.
    """
    st = _states(px)
    _fresh_null()
    return _interact(st["z_breadth"], st["lowvol"])


@factor("crowd_flow_flip")
def _crowd_flow_flip(px: pd.DataFrame) -> pd.DataFrame:
    """Traded-value crowding state x leader exposure.

    Hypothesis: when the money is piling into the names that are at their 52w
    highs, those positions are crowded and their forward returns are poor.
    """
    st = _states(px)
    _fresh_null()
    return _interact(st["z_flow"], st["laggard"])


@factor("crowd_surge_flip")
def _crowd_surge_flip(px: pd.DataFrame) -> pd.DataFrame:
    """Breadth-of-highs state x name-level volume surge.

    Hypothesis: in a crowded market, the names that have been sucked into a
    volume surge carry the most crowded positioning and underperform.
    """
    st = _states(px)
    _fresh_null()
    return _interact(st["z_breadth"], st["calm"])


@factor("crowd_spread_flip")
def _crowd_spread_flip(px: pd.DataFrame) -> pd.DataFrame:
    """One-sided advance state (many at highs AND few at lows) x leader exposure.

    Hypothesis: a one-sided, euphoric advance is the crowded regime; its
    leaders exhaust.
    """
    st = _states(px)
    _fresh_null()
    return _interact(st["z_spread"], st["laggard"])
