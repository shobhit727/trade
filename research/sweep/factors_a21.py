"""Agent 21 -- Wave 1 -- Regime B: RANK MOMENTUM.

Assignment
----------
The change in a name's cross-sectional RANK over 1, 3 and 6 months. Rank
momentum is not the same thing as price momentum: momentum measures the LEVEL
of a name's trailing return, rank momentum measures whether the name is
MIGRATING UP or DOWN the cross-sectional league table. A name can have strong
price momentum and still be losing relative ground (the whole market rallied);
a name can have flat price momentum and still be gaining rank (the market
fell). Only the second is rank momentum.

Base signal
-----------
All five factors rank the same base: a NINE-MONTH momentum measured from
t-252 to t-63, i.e. a return that deliberately STOPS THREE MONTHS BEFORE
today. Two reasons, both mechanical rather than cosmetic:

1. Excluding the recent three months means the base's rank is a SLOW variable.
   It moves because months 4-9 of the past year drop out of the window, not
   because of last month's price action. So a change in its rank is a genuine
   migration measure, not a short-term-reversal echo.
2. Skipping the recent window is what makes the classic "frog in the pan"
   (Da, Gurun & Warachka 2014) effect measurable: information that diffuses
   gradually shows up as a steady, persistent climb in a slow momentum rank,
   while a "frog" that jumps shows up as a discontinuity in that rank's path.

Sign hypotheses (stated up front, before measuring)
---------------------------------------------------
- a21_rankmom_{1m,3m,6m}: HIGHER is better. A name whose slow-momentum rank
  is rising is being accumulated by informed money; the diffusion is still in
  progress, so the climb continues. The negation is registered and measured
  because the opposite reading (a name that has already climbed too far will
  give the gain back -- short-term reversal in rank space) is equally
  plausible in Indian equities, where 1-3 month reversal is strong.
- a21_rankeff_6m: HIGHER is better. This is the frog-in-the-pan measure. It
  is the net rank change divided by the total PATH LENGTH travelled over six
  monthly steps, so it is 1.0 for a monotone climber, near 0 for a name whose
  rank wandered, and -1 for a monotone faller. A straight climb is a gradual
  diffusion of information and should keep paying; a name that arrived at the
  same rank by a violent detour is a frog and should mean-revert.
- a21_rankcons_6m: HIGHER is better. The fraction of the six monthly steps in
  which the rank actually rose. This measures the MONOTONICITY of the
  migration rather than its size: consistency of improvement is the
  frog-in-the-pan signature.

No lookahead
------------
Every input is a backward shift of the price panel (``p.shift(k)`` puts the
value from k bars ago at row t) and every rank is computed WITHIN a single
date across symbols. Nothing reads a future bar. Verified numerically by
truncating the panel and confirming that the overlapping rows are bit-identical.

Cost
----
Pure price panel; no new data, no new dependencies.

MEASURED OUTCOME (agent21, wave 1, engine at this commit)
----------------------------------------------------------
Measured with the shared harness on TEST (2024-01-01..2026-10-01) and TRAIN
(2016-01-01..2023-12-31), 36 cells per factor per window, PIT universe and
the full 32.32bp statutory cost stack.

  factor          TEST n>null  TEST n>bench  TEST both   TRAIN both
  a21_rankmom_1m      31/36        13/36        13/36         0/36
  a21_rankmom_3m      19/36         0/36         0/36         0/36
  a21_rankmom_6m      25/36         0/36         0/36         0/36
  a21_rankeff_6m      29/36         0/36         0/36         0/36
  a21_rankcons_6m     28/36         0/36         0/36         0/36
  (and every *_neg)   6-16/36       0/36         0/36         0/36

VERDICT: clean negative for the family. Nothing here survives the TRAIN
check, and only one factor beats the equal-weight universe anywhere.

The best TEST cell is a21_rankmom_1m at n_hold=15, buffer=10, clock=A:
CAGR +9.71% vs null +3.68% vs bench +6.13% (edge_vs_null +6.03pp,
edge_vs_bench +3.59pp, Sharpe 0.90, MaxDD -10.52%). It does NOT replicate:
the same factor on TRAIN is 0/36 against the benchmark, median
edge_vs_bench -6.37pp. Three independent reasons the TEST cell should not be
believed, all checked and none favourable:

1. The annual clock in TEST has THREE rebalance dates. Eight of the thirteen
   winning cells are clock=A, i.e. three independent bets, not thirteen.
2. The mechanism is not rank momentum. a21_rankmom_1m correlates +0.82 with
   cs_rank(lagged 21d return @ t-63) - cs_rank(lagged 21d return @ t-252),
   because sliding a 9-month momentum window by one month swaps the 21-day
   segment leaving the window for the segment entering it. The factor is a
   lagged-reversal proxy wearing a rank-momentum costume, not a
   cross-sectional rank migration.
3. The sign is wrong in TRAIN. On TRAIN the NEGATED variant beats the null
   in 11/36 cells against the positive variant's 4/36, i.e. the direction
   of the effect flips with the window.

The 3m and 6m variants, which have the best out-of-sample IC in a
TRAIN-selected screen (6m: TRAIN IC +0.043, t=2.18), beat the scrambled null
in 25/36 TEST cells but beat the equal-weight universe in 0/36. That is the
programme's familiar signature: the ranking carries information about which
names to hold, but not enough to justify holding anything other than the
index.

The file is kept as the record of the negative result, not as a candidate.
"""

from __future__ import annotations

import pandas as pd

from research.sweep.harness import factor

#: Bars per month. 21 trading days, the usual Indian monthly convention.
_M = 21


def _cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank in [0, 1] within each date.

    ``pct=True`` divides by the number of NON-NaN entries in the row, so the
    scale stays comparable across dates even as the number of listed names
    changes (new listings widen the cross-section).
    """
    return df.rank(axis=1, pct=True)


def _mom_9_3(p: pd.DataFrame) -> pd.DataFrame:
    """Nine-month momentum ending three months ago: P[t-63]/P[t-252] - 1.

    The recent three months are excluded on purpose -- see the module
    docstring. Backward-looking only.
    """
    return p.shift(_M * 3) / p.shift(_M * 12) - 1.0


def _rank_path(r: pd.DataFrame, steps: int) -> list[pd.DataFrame]:
    """The rank frame sampled at monthly offsets: [r(t), r(t-21), ..., r(t-21k)]."""
    return [r.shift(_M * k) for k in range(steps + 1)]


# --------------------------------------------------------------------------- #
# 1-3: the change in cross-sectional rank over 1, 3 and 6 months
# --------------------------------------------------------------------------- #
@factor("a21_rankmom_1m")
def _a21_rankmom_1m(px: pd.DataFrame) -> pd.DataFrame:
    """Change in cross-sectional rank of 9-month (t-3m) momentum over 1 month.

    Why higher should rank better: a name whose slow-momentum rank rose over
    the past month is gaining relative ground on a slow variable, which is the
    footprint of gradual information diffusion. The diffusion is incomplete,
    so the climb has more to run.
    """
    r = _cs_rank(_mom_9_3(px))
    return r - r.shift(_M)


@factor("a21_rankmom_3m")
def _a21_rankmom_3m(px: pd.DataFrame) -> pd.DataFrame:
    """Same construction over 3 months.

    Why higher should rank better: same mechanism as the 1-month version but
    measured over a horizon long enough that noise in the monthly rank path
    cannot dominate the signal.
    """
    r = _cs_rank(_mom_9_3(px))
    return r - r.shift(_M * 3)


@factor("a21_rankmom_6m")
def _a21_rankmom_6m(px: pd.DataFrame) -> pd.DataFrame:
    """Same construction over 6 months.

    Why higher should rank better: the longest horizon at which a slow
    momentum rank can migrate appreciably. A name that has climbed for six
    months has paid six months of accumulated costs to get there, so the
    position is not a one-week artefact.
    """
    r = _cs_rank(_mom_9_3(px))
    return r - r.shift(_M * 6)


# --------------------------------------------------------------------------- #
# 4-5: the SHAPE of the rank path, not just its net change
# --------------------------------------------------------------------------- #
@factor("a21_rankeff_6m")
def _a21_rankeff_6m(px: pd.DataFrame) -> pd.DataFrame:
    """Path efficiency of the 9-month momentum rank over 6 monthly steps.

    net rank change / total path length. +1 = monotone climber, 0 = the rank
    wandered and came back, -1 = monotone faller.

    Why higher should rank better: this is the "frog in the pan" test. A
    straight climb is what gradual information diffusion looks like, and
    gradual diffusion is underpriced. A name that reached the same rank by a
    violent detour is a frog: its move was a jump, jumps get crowded and
    reverse.
    """
    r = _cs_rank(_mom_9_3(px))
    path = _rank_path(r, 6)
    net = path[0] - path[6]
    length = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for k in range(6):
        length = length.add((path[k] - path[k + 1]).abs(), fill_value=0.0)
    return net / length.where(length > 1e-9)


@factor("a21_rankcons_6m")
def _a21_rankcons_6m(px: pd.DataFrame) -> pd.DataFrame:
    """Fraction of the last 6 monthly steps in which the momentum rank ROSE.

    Why higher should rank better: measures the monotonicity of the migration
    rather than its size. A name whose rank improved in five of the last six
    monthly steps is being accumulated steadily; a name with the same net
    change but only one improving step bought its position in a single move.
    Note this factor is discrete (values k/6), so it carries large tie groups;
    the harness's hash tie-break handles that, but it is a lower-information
    signal than the continuous members of this family.
    """
    r = _cs_rank(_mom_9_3(px))
    path = _rank_path(r, 6)
    ups = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    valid = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for k in range(6):
        ok = path[k].notna() & path[k + 1].notna()
        ups = ups.add(((path[k] > path[k + 1]) & ok).astype(float), fill_value=0.0)
        valid = valid.add(ok.astype(float), fill_value=0.0)
    return (ups / valid.where(valid > 0)).where(valid == 6)


# --------------------------------------------------------------------------- #
# Opposite-sign registrations
#
# The hypotheses above all say "higher is better". If the mechanism is real
# but the SIGN is wrong, the negation is where the edge shows up: a name whose
# slow-momentum rank has been FALLING is the short-term-reversal candidate
# (it has lagged, and Indian equities punish laggards over 1-3 months), and a
# name whose rank path is a violent detour is the frog that gives it back.
# The harness buys the TOP n_hold by score, so the negation has to be a
# separately registered factor to be tested at all.
# --------------------------------------------------------------------------- #
@factor("a21_rankmom_1m_neg")
def _a21_rankmom_1m_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a21_rankmom_1m: a FALLING slow-momentum rank is good.

    Hypothesis: the monthly rank climb is a short-term overshoot (crowded
    money chasing the recent leaders) and the better trade is the name that
    has been giving back relative ground over the past month.
    """
    r = _cs_rank(_mom_9_3(px))
    return -(r - r.shift(_M))


@factor("a21_rankmom_3m_neg")
def _a21_rankmom_3m_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a21_rankmom_3m: a FALLING slow-momentum rank is good.

    Hypothesis: the quarterly rank climb is a short-term overshoot and the
    better trade is the laggard on the slow momentum ranking.
    """
    r = _cs_rank(_mom_9_3(px))
    return -(r - r.shift(_M * 3))


@factor("a21_rankmom_6m_neg")
def _a21_rankmom_6m_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a21_rankmom_6m: a FALLING slow-momentum rank is good.

    Hypothesis: the rank climb is a short-term overshoot (crowded money
    chasing the recent leaders) and the better trade is the name that has been
    giving back relative ground.
    """
    return -(_cs_rank(_mom_9_3(px)) - _cs_rank(_mom_9_3(px)).shift(_M * 6))


@factor("a21_rankeff_6m_neg")
def _a21_rankeff_6m_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a21_rankeff_6m: a CHOPPY, VIOLENT rank path is good.

    Hypothesis: the straight climb is the crowded one -- frog-in-the-pan
    reversed, where the frog (the jump) is the one that keeps running.
    """
    r = _cs_rank(_mom_9_3(px))
    path = _rank_path(r, 6)
    net = path[0] - path[6]
    length = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for k in range(6):
        length = length.add((path[k] - path[k + 1]).abs(), fill_value=0.0)
    return -(net / length.where(length > 1e-9))


@factor("a21_rankcons_6m_neg")
def _a21_rankcons_6m_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a21_rankcons_6m: an INCONSISTENT rank path is good.

    Hypothesis: a name whose rank fell in most of the last six monthly steps
    is a laggard on a slow variable, which is the classic short-term reversal
    candidate in Indian equities.
    """
    r = _cs_rank(_mom_9_3(px))
    path = _rank_path(r, 6)
    ups = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    valid = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for k in range(6):
        ok = path[k].notna() & path[k + 1].notna()
        ups = ups.add(((path[k] > path[k + 1]) & ok).astype(float), fill_value=0.0)
        valid = valid.add(ok.astype(float), fill_value=0.0)
    return -((ups / valid.where(valid > 0)).where(valid == 6))
