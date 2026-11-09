"""Agent 18 (wave 1) -- Regime A: RELATIVE STRENGTH VS OWN SECTOR.

Directive
---------
Proxy a sector by clustering on correlation, then measure strength WITHIN the
cluster.

Mechanism and sign hypothesis
-----------------------------
A name that is strong RELATIVE TO ITS OWN PEERS carries sector-specific
information -- an order win, a new plant, a management change, a product cycle
-- that the sector as a whole has not yet priced. The industry-momentum result
(Moskowitz & Grinblatt 1999) says the industry LEADER, not the industry, is
what pays; the sector-neutral momentum result says a name's momentum is mostly
a sector bet, so stripping the sector component leaves a cleaner
stock-selection signal. Both point the same way:

    HIGHER peer-relative strength = better.

The opposite sign (intra-peer mean reversion) is a live hypothesis too, so it
is registered as its own factor and the sign is MEASURED, not assumed.

Sector proxy
------------
This repo has no sector labels, so sectors are built from the data: the
pairwise-complete 252-day correlation of daily returns, Ward-linkage
agglomeration into K=16 clusters, re-estimated every 21 bars (~monthly) and
forward-filled -- never back-filled -- so the cluster in force on a date is the
one that was knowable on that date.

K=16 was fixed on QUALITATIVE grounds before any measurement: at K=16 the
clusters are recognisable sectors (IT = hcltech/infy/tcs/techm/wipro, banks =
axisbank/hdfcbank/icicibank/kotakbank, autos = bajajauto/eichermot/mm/maruti,
metals = hindalco/jswsteel/tatasteel, power = ntpc/powergrid, insurance =
hdfclife/sbilife, plus the FMCG and pharma groupings), whereas K=8 leaves a
24-name blob of "everything else" and a market-neutral correlation variant
shatters into singletons. No return statistic was consulted when choosing it.

Point-in-time discipline
------------------------
* the clustering at date t uses returns up to and including t only;
* the label in force at t is the most recent clustering <= t (forward fill);
* peer-relative strength uses returns up to t only;
* no shift(-1), no centred windows, no future information anywhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from research.sweep.harness import factor

# --- sector-proxy construction --------------------------------------------- #
_CLUSTER_GRID = 21     # re-cluster every 21 bars (~monthly)
_CORR_WIN = 252       # correlation lookback used to build the clusters
_MIN_OBS = 120        # min jointly-observed bars for a pairwise correlation
_K_TARGET = 16        # target number of clusters (sectors)

#: (px reference, labels) cache -- the clustering is expensive and the harness
#: calls the factor once per cell, so it must be computed exactly once.
_CACHE: dict[tuple, tuple[pd.DataFrame, pd.DataFrame]] = {}


def _cluster_at(w: pd.DataFrame) -> np.ndarray:
    """One clustering of the (window x N) return block.

    Returns a label per column; -1 means "no cluster" (not enough history to
    estimate a correlation for this name over the window).
    """
    n_cols = w.shape[1]
    labels = np.full(n_cols, -1, dtype=np.int16)
    valid = w.notna().sum(axis=0).to_numpy() >= _MIN_OBS
    idx = np.flatnonzero(valid)
    if len(idx) < 8:
        return labels

    corr = w.corr(min_periods=_MIN_OBS).to_numpy()
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1.0, 1.0)

    sub = corr[np.ix_(idx, idx)]
    dist = np.sqrt(np.clip(2.0 * (1.0 - sub), 0.0, None))
    np.fill_diagonal(dist, 0.0)
    k = int(min(_K_TARGET, max(2, len(idx) // 2)))
    if len(idx) < k:
        return labels
    Z = linkage(squareform(dist, checks=False), method="ward")
    lab = fcluster(Z, k, criterion="maxclust").astype(np.int16) - 1
    labels[idx] = lab
    return labels


def _labels(px: pd.DataFrame) -> pd.DataFrame:
    """(T x N) integer cluster-label frame, forward-filled from monthly clusters.

    Rows before the first clustering are -1 (no cluster). The label in force at
    date t is the most recent clustering on or before t -- forward fill only.
    """
    key = (id(px), _CLUSTER_GRID, _CORR_WIN, _MIN_OBS, _K_TARGET)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] is px:
        return hit[1]

    r = px.pct_change()
    n_bars = len(px)
    grid = list(range(_CORR_WIN - 1, n_bars, _CLUSTER_GRID))
    rows: list[np.ndarray] = []
    dates: list[pd.Timestamp] = []
    for t in grid:
        rows.append(_cluster_at(r.iloc[t - _CORR_WIN + 1: t + 1]))
        dates.append(px.index[t])
    lab_df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=px.columns)
    full = lab_df.reindex(px.index, method="ffill")
    full = full.fillna(-1).astype(np.int16)
    _CACHE[key] = (px, full)
    return full


def _peer_diff(lab: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """base minus its OWN cluster mean.

    The cluster mean is subtracted only from the members of that cluster, so
    the result is zero-sum inside every cluster: the sector's own move is
    removed and only the within-sector ordering survives.
    """
    L = lab.to_numpy()
    B = base.to_numpy(dtype=float)
    out = np.full(B.shape, np.nan)
    for k in np.unique(L):
        if k < 0:
            continue
        members = (L == k) & np.isfinite(B)
        cnt = members.sum(axis=1)
        s = np.where(members, np.nan_to_num(B), 0.0).sum(axis=1)
        mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
        vals = B - mean[:, None]
        out[members] = vals[members]
    return pd.DataFrame(out, index=base.index, columns=base.columns)


def _peer_z(lab: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """Within-cluster z-score of base: scale-free, so a wide-dispersion cluster
    cannot dominate the cross-sectional ranking."""
    L = lab.to_numpy()
    B = base.to_numpy(dtype=float)
    out = np.full(B.shape, np.nan)
    for k in np.unique(L):
        if k < 0:
            continue
        members = (L == k) & np.isfinite(B)
        cnt = members.sum(axis=1)
        s = np.where(members, np.nan_to_num(B), 0.0).sum(axis=1)
        mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
        dev = np.where(members, np.nan_to_num(B) - mean[:, None], 0.0)
        var = (dev ** 2).sum(axis=1)
        sd = np.sqrt(np.where(cnt > 1, var / np.maximum(cnt - 1, 1), np.nan))
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (B - mean[:, None]) / sd[:, None]
        out[members] = z[members]
    return pd.DataFrame(out, index=base.index, columns=base.columns)


# --------------------------------------------------------------------------- #
# Factors
# --------------------------------------------------------------------------- #
@factor("sect_rs_63")
def _sect_rs_63(px: pd.DataFrame) -> pd.DataFrame:
    """3-month return relative to the name's own correlation-cluster peers.

    Sign hypothesis: HIGHER is better -- intra-sector momentum; the name
    leading its peers carries information the sector has not priced.
    """
    return _peer_diff(_labels(px), px.pct_change(63))


@factor("sect_rs_126")
def _sect_rs_126(px: pd.DataFrame) -> pd.DataFrame:
    """6-month return relative to the name's own correlation-cluster peers.

    Sign hypothesis: HIGHER is better -- intra-sector momentum at the
    industry-momentum horizon (Moskowitz & Grinblatt used 6-12 months).
    """
    return _peer_diff(_labels(px), px.pct_change(126))


@factor("sect_rs_252")
def _sect_rs_252(px: pd.DataFrame) -> pd.DataFrame:
    """12-month return relative to the name's own correlation-cluster peers.

    Sign hypothesis: HIGHER is better -- the full-year industry-momentum
    horizon, sector component removed.
    """
    return _peer_diff(_labels(px), px.pct_change(252))


@factor("sect_rs_z_126")
def _sect_rs_z_126(px: pd.DataFrame) -> pd.DataFrame:
    """6-month peer-relative strength, standardised INSIDE each cluster.

    Sign hypothesis: HIGHER is better -- same intra-sector ordering as
    sect_rs_126 but scale-free, so a wide-dispersion cluster cannot outrank a
    tight one purely because its members moved more.
    """
    return _peer_z(_labels(px), px.pct_change(126))


@factor("sect_rs_126_neg")
def _sect_rs_126_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of sect_rs_126: the intra-peer laggard ranks highest.

    Sign hypothesis: HIGHER is better -- intra-sector mean reversion, where
    the name that has fallen behind its own peers bounces back. Registered so
    the sign of the mechanism is measured rather than assumed.
    """
    return -_peer_diff(_labels(px), px.pct_change(126))
