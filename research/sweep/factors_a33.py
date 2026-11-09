"""Wave-1 agent 33 -- correlation clusters and within-cluster relative returns.

Mechanism.  Sector labels are not in the panel, so they are estimated from
returns: residualise each name's daily return on the equal-weight market,
correlate the residuals over a trailing year, and cut the correlation tree into
``_K`` groups.  On the 2026-10-01 snapshot this recovers IT, metals/utilities,
pharma, banks/NBFC, autos, cement/insurance and FMCG blocks without being told
the sectors -- the construction is data-derived, not a lookup table.

The question the assignment asks is whether a name's return *relative to its own
cluster* predicts.  Four horizon/sign variants plus one top-down control:

    clu_relmom_63   within-cluster 63d relative return (momentum)
    clu_relrev_63   the exact negation
    clu_relmom_21   within-cluster 21d relative return (momentum)
    clu_relrev_21   the exact negation (short-term within-sector reversal)
    clu_sector_rot  cluster 126d return minus market -- the sector, not the name

Relative return is leave-one-out: own formation return minus the mean of the
*other* members of the same cluster.  A name with no cluster peers (or no
cluster at all) falls back to the market mean, so the investable set never
shrinks because of a degenerate cluster.

No lookahead.  A cluster block is formed from the ``_CORR_WIN`` returns strictly
before the block's first day and held for ``_STEP`` bars.  Formation returns at
t use prices up to and including t, as the harness convention allows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from research.sweep.harness import factor

#: Correlation formation window (bars) and re-estimation cadence (bars).
_CORR_WIN = 252
_STEP = 63
#: Number of correlation clusters.  Calibrated so the recovered blocks are
#: sector-sized (~5 names) rather than one market blob plus singletons.
_K = 10
#: Minimum overlapping observations for a pairwise residual correlation.
_MIN_PAIRS = 60

_CACHE: dict[int, tuple[pd.DataFrame, np.ndarray]] = {}


def _build_labels(px: pd.DataFrame) -> np.ndarray:
    """Cluster labels (T, N); row t is the block estimate in force at t.

    Labels are 0..K-1, or -1 while there is not yet a full formation window.
    """
    R = px.pct_change()
    mkt = R.mean(axis=1)
    Rv = R.to_numpy(dtype=float)
    mv = mkt.to_numpy(dtype=float)
    T, N = Rv.shape
    labels = np.full((T, N), -1, dtype=np.int16)

    for t0 in range(_CORR_WIN, T - 1, _STEP):
        win = Rv[t0 - _CORR_WIN:t0]
        m = mv[t0 - _CORR_WIN:t0]
        ok = np.isfinite(win).sum(axis=0) >= _MIN_PAIRS
        if ok.sum() < _K + 2:
            continue
        W = win[:, ok]
        # Beta on the equal-weight market, pairwise-complete so a partly listed
        # name is not biased toward zero.
        fin = np.isfinite(W)
        WM = np.where(fin, W, 0.0)
        MM = np.where(fin, m[:, None], 0.0)
        var = (MM * MM).sum(axis=0)
        beta = np.divide((WM * MM).sum(axis=0), var, out=np.ones_like(var), where=var > 0)
        resid = W - beta[None, :] * m[:, None]
        C = pd.DataFrame(resid, columns=np.flatnonzero(ok)).corr(min_periods=_MIN_PAIRS)
        C = C.to_numpy(dtype=float)
        C = np.nan_to_num(C, nan=0.0, posinf=0.0, neginf=0.0)
        np.fill_diagonal(C, 1.0)
        D = 1.0 - C
        np.fill_diagonal(D, 0.0)
        D = 0.5 * (D + D.T)
        if not np.isfinite(D).all():
            continue
        try:
            Z = linkage(squareform(D, checks=False), method="average")
            sub = fcluster(Z, _K, criterion="maxclust") - 1
        except ValueError:
            continue
        labels[t0:t0 + _STEP, ok] = sub
    return labels


def _labels(px: pd.DataFrame) -> np.ndarray:
    """Cached cluster labels for ``px`` (the panel is a harness singleton)."""
    hit = _CACHE.get(id(px))
    if hit is not None and hit[0] is px:
        return hit[1]
    lab = _build_labels(px)
    if len(_CACHE) > 2:
        _CACHE.clear()
    _CACHE[id(px)] = (px, lab)
    return lab


def _group_means(formation: pd.DataFrame, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cluster mean and leave-one-out peer mean of ``formation`` (T, N) each.

    Labels are piecewise constant, so the (T, N) work is done one block at a
    time.  Missing formation returns are dropped from the mean rather than
    poisoning it.
    """
    F = formation.to_numpy(dtype=float)
    finite = np.isfinite(F)
    T, N = F.shape
    cm = np.full((T, N), np.nan)
    loo = np.full((T, N), np.nan)

    for lab in np.unique(labels, axis=0):
        sel = (labels == lab).all(axis=1)
        if lab.max() < 0:
            continue
        Fs, fin = F[sel], finite[sel]
        good = lab >= 0
        K = int(lab.max()) + 1
        M = np.zeros((N, K), dtype=float)
        M[np.flatnonzero(good), lab[good]] = 1.0
        F0 = np.where(fin, Fs, 0.0)
        sums = F0 @ M
        cnts = fin.astype(float) @ M
        kk = np.where(good, lab, 0)
        csum, ccnt = sums[:, kk], cnts[:, kk]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = csum / ccnt
            peer = (csum - F0) / (ccnt - fin)
        if (~good).any():
            mean[:, ~good] = np.nan
            peer[:, ~good] = np.nan
        mean[~fin] = np.nan
        peer[~fin] = np.nan
        cm[sel] = mean
        loo[sel] = peer
    return cm, loo


def _rel(px: pd.DataFrame, n: int) -> pd.DataFrame:
    """Within-cluster relative formation return over ``n`` bars."""
    F = px.pct_change(n)
    _, loo = _group_means(F, _labels(px))
    rel = F - loo
    mkt = F.mean(axis=1)
    fallback = rel.isna() & F.notna()
    if fallback.to_numpy().any():
        rel = rel.where(~fallback, F.sub(mkt, axis=0))
    return rel


@factor("clu_relmom_63")
def _clu_relmom_63(px: pd.DataFrame) -> pd.DataFrame:
    return _rel(px, 63)


@factor("clu_relrev_63")
def _clu_relrev_63(px: pd.DataFrame) -> pd.DataFrame:
    return -_rel(px, 63)


@factor("clu_relmom_21")
def _clu_relmom_21(px: pd.DataFrame) -> pd.DataFrame:
    return _rel(px, 21)


@factor("clu_relrev_21")
def _clu_relrev_21(px: pd.DataFrame) -> pd.DataFrame:
    return -_rel(px, 21)


@factor("clu_sector_rot")
def _clu_sector_rot(px: pd.DataFrame) -> pd.DataFrame:
    F = px.pct_change(126)
    cm, _ = _group_means(F, _labels(px))
    mkt = F.mean(axis=1)
    return pd.DataFrame(cm, index=F.index, columns=F.columns).sub(mkt, axis=0)
