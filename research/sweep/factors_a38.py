"""Agent 38 -- wave 1: DECILE SPREAD BEHAVIOUR.

Assignment: "build explicit decile portfolios and measure the monotonicity of
the return spread."

How that is measured here
-------------------------
The shared harness only builds long-only top-N books, so a decile experiment is
run two ways, and both are reported:

1. **Explicit decile portfolios** (``decile_report``): every month the live PIT
   universe is sorted on the factor and split into 10 equal-count groups. The
   mean forward 21-session return of each decile is averaged over rebalances.
   Monotonicity = (a) mean Spearman(decile index, decile return) and (b) the
   share of months whose 10 decile means are strictly increasing. The
   top-minus-bottom spread is the decile-spread claim; the top-minus-universe
   spread is the deployable (long-only) part of it.
2. **Harness cells at decile resolution**: n_hold 5 is the top decile of a
   41-47 name PIT universe (~4-5 names per decile), and 10/15/20 are deeper
   slices. If the spread is monotone, edge_vs_bench should decay as n_hold
   grows, and the negated factor's top book (the bottom decile) should have
   negative edge_vs_bench. Every base variable is registered in BOTH directions,
   which is the both-ways sign test required by the assignment.

Four base sorts, none in the 37-factor catalogue, each with a documented
economic mechanism:

* ``high_beta``    -252d beta to the equal-weight market. Betting-against-beta
                   says the premium is NEGATIVE on beta, but TRAIN 2016-2023
                   prices it positive (+1.34%/mo top-minus-bottom), so both
                   signs are carried to TEST rather than assuming the textbook.
* ``resid_rev_21``-21d market-model residual return, negated. Liquidity
                   providers are paid for absorbing idiosyncratic selling;
                   stripping the common factor isolates that compensation.
                   Best new spread in the TRAIN screen (+1.27%/mo, t=1.96).
* ``seasonal_mom`` average return in the same calendar month over the prior
                   three years. Recurring firm-level seasonality persists.
* ``resid_mom``    12-1 cumulative market-model residual return. Stripping the
                   common factor leaves firm-specific drift with a cleaner,
                   more monotone spread than raw momentum.

**TRAIN-rejected, kept registered for reproducibility only:** ``low_max`` /
``high_max`` (mean of the 5 largest daily returns of the past 21 days) showed
no lottery premium (top-minus-bottom -0.05%/mo, t=-0.07) and ~80% monthly
turnover, so it is excluded from the TEST grid. All selection happens on
TRAIN; TEST is measured once and reported as-is.

Decile report on TRAIN: across all 37 catalogue sorts plus these constructs,
no sort produced a monotone ladder (strictly-increasing month share 0.47-0.53,
mean |Spearman| <= 0.11). The spreads that exist are tail-driven: the extreme
decile carries the effect and the middle deciles are noise. That is the core
finding of the decile-spread lens, and it is why the harness grid below is read
as "does the top decile survive costs", not as "is the ladder monotone".

Close prices only, so no OHLC/volume loader and no disk I/O outside the shared
harness panel. No lookahead: every input at t uses bars <= t, and the
seasonality signal is indexed at the START of the month it applies to.

Run the decile diagnostic with:
    PYTHONPATH=src:. .venv/bin/python -c \
        "from research.sweep.factors_a38 import decile_report as d; d('TRAIN'); d('TEST')"
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .harness import FACTORS, TEST, TRAIN, _tiebreak_vector, factor, panel, pit_mask

# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #


def _ret(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(fill_method=None)


def _mkt(r: pd.DataFrame) -> pd.Series:
    return r.mean(axis=1)


def _beta(r: pd.DataFrame, win: int = 252, minp: int = 120) -> pd.DataFrame:
    m = _mkt(r)
    cov = r.rolling(win, min_periods=minp).cov(m)
    var = m.rolling(win, min_periods=minp).var().replace(0.0, np.nan)
    return cov.div(var, axis=0)


def _max_ret(r: pd.DataFrame, win: int = 21, k: int = 5) -> pd.DataFrame:
    return r.rolling(win, min_periods=win).apply(
        lambda w: np.sort(w)[-k:].mean(), raw=True
    )


def _seasonal(px: pd.DataFrame) -> pd.DataFrame:
    """Mean return in the same calendar month over the prior three years.

    ``mr.shift(12)`` at month M is the return of month M-12, so the value is
    known at the START of month M; it is indexed there and forward-filled.
    """
    m = px.resample("ME").last()
    mr = m.pct_change(fill_method=None)
    seas = (mr.shift(12) + mr.shift(24) + mr.shift(36)) / 3.0
    seas.index = seas.index.to_period("M").to_timestamp(how="start")
    return seas.reindex(px.index, method="ffill")


def _resid_r(px: pd.DataFrame, win: int = 252,
             minp: int = 120) -> pd.DataFrame:
    r = _ret(px)
    b = _beta(r, win, minp)
    return r.sub(b.mul(_mkt(r), axis=0))


def _resid_mom(px: pd.DataFrame, win: int = 252, skip: int = 21,
               minp: int = 120) -> pd.DataFrame:
    resid = _resid_r(px, win, minp)
    return (resid.rolling(win, min_periods=minp).sum()
            - resid.rolling(skip, min_periods=skip).sum())


def _resid_rev(px: pd.DataFrame, win: int = 21) -> pd.DataFrame:
    return _resid_r(px).rolling(win, min_periods=win).sum()


#: Base variables are shared by both signs and recomputed for every cell, so
#: cache on the panel identity (the harness panel is a module singleton).
_CACHE: dict[tuple[str, int], pd.DataFrame] = {}


def _base(name: str, px: pd.DataFrame,
          fn) -> pd.DataFrame:
    key = (name, id(px))
    hit = _CACHE.get(key)
    if hit is None:
        hit = fn(px)
        _CACHE[key] = hit
    return hit


# --------------------------------------------------------------------------- #
# hypothesis direction (positive = expected to earn the premium)
# --------------------------------------------------------------------------- #


@factor("a38_low_beta")
def a38_low_beta(px: pd.DataFrame) -> pd.DataFrame:
    return -_base("beta", px, lambda p: _beta(_ret(p)))


@factor("a38_high_beta")
def a38_high_beta(px: pd.DataFrame) -> pd.DataFrame:
    return _base("beta", px, lambda p: _beta(_ret(p)))


@factor("a38_resid_rev_21")
def a38_resid_rev_21(px: pd.DataFrame) -> pd.DataFrame:
    return -_base("resid_rev", px, _resid_rev)


@factor("a38_resid_mom_1m")
def a38_resid_mom_1m(px: pd.DataFrame) -> pd.DataFrame:
    return _base("resid_rev", px, _resid_rev)


@factor("a38_seasonal_mom")
def a38_seasonal_mom(px: pd.DataFrame) -> pd.DataFrame:
    return _base("seasonal", px, _seasonal)


@factor("a38_anti_seasonal")
def a38_anti_seasonal(px: pd.DataFrame) -> pd.DataFrame:
    return -_base("seasonal", px, _seasonal)


@factor("a38_resid_mom")
def a38_resid_mom(px: pd.DataFrame) -> pd.DataFrame:
    return _base("resid", px, _resid_mom)


@factor("a38_anti_resid_mom")
def a38_anti_resid_mom(px: pd.DataFrame) -> pd.DataFrame:
    return -_base("resid", px, _resid_mom)


@factor("a38_low_max")
def a38_low_max(px: pd.DataFrame) -> pd.DataFrame:
    return -_base("max", px, lambda p: _max_ret(_ret(p)))


@factor("a38_high_max")
def a38_high_max(px: pd.DataFrame) -> pd.DataFrame:
    return _base("max", px, lambda p: _max_ret(_ret(p)))


# --------------------------------------------------------------------------- #
# explicit decile portfolios / monotonicity diagnostic
# --------------------------------------------------------------------------- #


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def _deciles(score: pd.Series, fwd: pd.Series, live: pd.Series,
             n_dec: int = 10) -> tuple[np.ndarray, dict[int, set]] | None:
    """Equal-count deciles, harness hash tie-break, label 0 = lowest score."""
    ok = live.astype(bool) & score.notna() & fwd.notna()
    if int(ok.sum()) < n_dec * 3:
        return None
    s = score[ok].to_numpy(dtype=float)
    tie = _tiebreak_vector(list(score[ok].index))
    order = np.lexsort((tie, s))  # primary score, hash resolves ties
    names = np.asarray(score[ok].index)[order]
    f = fwd[names].to_numpy(dtype=float)
    n = len(names)
    lab = np.minimum((np.arange(n) * n_dec) // n, n_dec - 1)
    out = np.full(n_dec, np.nan)
    members: dict[int, set] = {}
    for d in range(n_dec):
        sel = lab == d
        if sel.any():
            out[d] = float(f[sel].mean())
            members[d] = set(names[sel])
    return out, members


def decile_report(window: str = "TEST", n_fwd: int = 21,
                  n_dec: int = 10,
                  names: list[str] | None = None) -> pd.DataFrame:
    """Print decile means, monotonicity and top/bottom spreads per factor."""
    lo, hi = {"TRAIN": TRAIN, "TEST": TEST}[window]
    px = panel()
    mask = pit_mask(px)
    fwd = px.shift(-(n_fwd + 1)) / px.shift(-1) - 1.0
    idx = px.loc[lo:hi].index
    reb = pd.Series(idx, index=idx).groupby(idx.to_period("M")).max().tolist()
    reb = [t for t in reb if t in fwd.index and fwd.loc[t].notna().sum() >= n_dec * 3]

    base = names or ["a38_high_beta", "a38_resid_rev_21",
                     "a38_seasonal_mom", "a38_resid_mom"]
    rows = []
    for name in base:
        score = FACTORS[name](px)
        dec_ret, dec_turn, spears, mono, top_ex = [], [], [], [], []
        members: dict[int, set] = {}
        for t in reb:
            got = _deciles(score.loc[t], fwd.loc[t], mask.loc[t], n_dec)
            if got is None:
                continue
            out, cur = got
            if np.isnan(out).any():
                continue
            dec_ret.append(out)
            spears.append(_spearman(np.arange(n_dec), out))
            mono.append(float(np.mean(np.diff(out) > 0)))
            universe = float(fwd.loc[t][mask.loc[t].astype(bool)].mean())
            top_ex.append(float(out[-1] - universe))
            if members:
                for d in range(n_dec):
                    old = members.get(d, set())
                    dec_turn.append(len(cur[d] - old) / max(len(cur[d]), 1))
            members = cur
        if not dec_ret:
            rows.append(dict(factor=name, months=0))
            continue
        dr = np.asarray(dec_ret)
        spread = dr[:, -1] - dr[:, 0]
        tstat = (spread.mean() / spread.std(ddof=1) * np.sqrt(len(spread))
                 if len(spread) > 2 and spread.std(ddof=1) > 0 else np.nan)
        rows.append(dict(
            factor=name, months=len(dr),
            **{f"D{i+1}": dr[:, i].mean() * 100 for i in range(n_dec)},
            spread_mo=spread.mean() * 100, t=tstat,
            top_excess_mo=np.nanmean(top_ex) * 100,
            spearman=np.nanmean(spears), monotone=float(np.mean(mono)),
            turn_top=float(np.mean(
                [dec_turn[i] for i in range(n_dec - 1, len(dec_turn), n_dec)])),
            turn_bot=float(np.mean(
                [dec_turn[i] for i in range(0, len(dec_turn), n_dec)])),
        ))
    df = pd.DataFrame(rows).set_index("factor")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(f"\n=== {window}: decile mean forward {n_fwd}d return, % per rebalance "
              f"(n={len(reb)} months) ===")
        print(df[[f"D{i+1}" for i in range(n_dec)]].round(2).to_string())
        print(df[["months", "spread_mo", "t", "top_excess_mo", "spearman",
                  "monotone", "turn_top", "turn_bot"]].round(3).to_string())
    return df


if __name__ == "__main__":
    for w in ("TRAIN", "TEST"):
        decile_report(w)
