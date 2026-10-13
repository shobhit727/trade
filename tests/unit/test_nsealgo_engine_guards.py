"""Guards for three silent-failure modes in the backtest engine.

Every test here exists because the engine returned a *plausible-looking but meaningless*
result rather than raising, and a published report drew a conclusion from it.

* :class:`TestEmptyScorePanel` — an all-NaN score panel (or an all-NaN slice of one on a
  single rebalance date) used to produce 0 rebalances, flat equity and a Sharpe of exactly
  0.00. Two agents reported "beats 100% of random" that way. Partial NaN is normal and
  must keep working.
* :class:`TestTieBreakIsUnbiased` — ties used to resolve alphabetically, because ranking
  was a stable argsort over the panel's alphabetical columns. A binary mask control then
  measured "alphabetically-first live names" (13.3%) instead of a random book (11.2%),
  which inverted a verdict.
* :class:`TestBookDiagnostics` — ``avg_invested_weight``, requested by three separate
  agents, which had to decompose a 55.8%-vs-90% investment gap by hand.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nsealgo.backtest.engine import (
    DEAD_WEIGHT_EPS,
    SECTORS,
    EmptyScorePanelError,
    PortfolioConfig,
    _tiebreak_key,
    apply_turnover_budget,
    build_rebalance_weights,
    run_backtest,
)
from nsealgo.costs import CostModel

CM = CostModel(segment="delivery", slippage_bps=5)

#: The 48 real symbols of the production universe, already in alphabetical order --
#: exactly the column order a loader produces, which is what made the old tie-break
#: alphabetical.
UNIVERSE = list(SECTORS)


def make_panel(
    seed: int = 0, n_days: int = 900, symbols: list[str] | None = None
) -> pd.DataFrame:
    """Deterministic synthetic prices. Prices only; no factor dependency.

    ``symbols`` defaults to real NIFTY-50 tickers. That matters: names not in
    :data:`~nsealgo.backtest.engine.SECTORS` all collapse into a single "other" sector,
    whose 25% cap then binds on a whole-universe book and makes an *investment* level
    assertion meaningless. Where the test is about how much capital is deployed, it must
    use names the sector map actually distinguishes.
    """
    cols = list(symbols) if symbols is not None else list(SECTORS)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-01", periods=n_days, tz="Asia/Kolkata")
    drifts = rng.normal(0.0004, 0.0006, len(cols))
    shocks = rng.normal(0, 0.012, (n_days, len(cols)))
    prices = np.empty((n_days, len(cols)))
    p0 = rng.uniform(100, 2000, len(cols))
    for t in range(n_days):
        p0 = p0 * (1.0 + drifts + shocks[t])
        prices[t] = p0
    return pd.DataFrame(prices, index=dates, columns=cols)


# --------------------------------------------------------------------------- #
# BUG 1 — a structurally empty score panel must raise, not return a flat result
# --------------------------------------------------------------------------- #


class TestEmptyScorePanel:
    def test_all_nan_score_panel_raises(self) -> None:
        """The headline failure: an all-NaN panel used to return Sharpe exactly 0.00
        with a flat equity curve, which reads as a real (terrible) strategy result."""
        panel = make_panel()
        score = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)

        with pytest.raises(EmptyScorePanelError):
            run_backtest(panel, score, CM, PortfolioConfig(), "M")

    def test_fully_tied_score_panel_does_not_raise(self) -> None:
        """Ties are not emptiness. A constant panel is a degenerate *but well-formed*
        input (it is what a factor with no dispersion produces) and must still build a
        book — it must just not build an alphabetical one."""
        panel = make_panel()
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)

        res = run_backtest(panel, score, CM, PortfolioConfig(), "M")
        assert res.diag["n_rebalances"] > 0
        assert res.diag["avg_names"] > 0

    def test_all_nan_on_one_rebalance_date_raises_and_names_that_date(self) -> None:
        """The second manifestation: the panel is fine except on one rebalance date.
        The error has to say *which* date, because that is the whole diagnosis."""
        panel = make_panel()
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)
        rb = sorted(set(score.index.tz_localize(None).to_period("M")))[40]
        bad = score.index.tz_localize(None).to_period("M") == rb
        assert 0 < int(bad.sum()) < len(score), "need exactly one partial month"
        score.loc[bad, :] = np.nan

        with pytest.raises(EmptyScorePanelError) as exc:
            run_backtest(panel, score, CM, PortfolioConfig(), "M")

        msg = str(exc.value)
        # The first trading day of that month is the rebalance date that fails.
        first_of_month = score.index[bad][0]
        assert str(first_of_month.date()) in msg, msg
        # ...and the message is actionable: it reports how many cells were unusable.
        assert f"of {panel.shape[1]} cells" in msg, msg

    def test_partial_nan_does_not_raise_and_still_builds_a_book(self) -> None:
        """A name with insufficient history is NORMAL. The names that do have a score
        must be selectable and must still produce a full, investable book."""
        panel = make_panel()
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)
        # A quarter of the universe is permanently unavailable.
        dead = list(panel.columns[: panel.shape[1] // 4])
        score[dead] = np.nan

        res = run_backtest(panel, score, CM, PortfolioConfig(), "M")

        assert res.diag["n_rebalances"] > 0
        assert res.diag["avg_names"] > 0
        # Nothing ineligible may be held: partial NaN is exclusion, not imputation.
        held = res.weights[dead].to_numpy()
        assert float(np.abs(held).max()) == 0.0
        # ...and the surviving names are genuinely invested, not left at zero.
        assert res.diag["avg_invested_weight"] > 0.5

    def test_partial_nan_that_clears_the_position_count_still_works(self) -> None:
        """The threshold is deliberately ZERO, not `n_positions`. A date that can only
        build a 3-name book is a real result and must be returned, not raised on."""
        panel = make_panel()
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)
        score.iloc[:, 3:] = np.nan  # only 3 of 48 names ever have a score

        res = run_backtest(panel, score, CM, PortfolioConfig(n_positions=22), "M")

        assert res.diag["avg_names"] > 0
        assert res.diag["avg_invested_weight"] > 0.0

    def test_one_eligible_name_does_not_raise(self) -> None:
        """The boundary case the zero-threshold exists for: exactly one usable name is
        a (degenerate but interpretable) book, and the old code handled it."""
        panel = make_panel()
        score = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
        score.iloc[:, 7] = 1.0

        res = run_backtest(panel, score, CM, PortfolioConfig(n_positions=10), "M")
        assert res.diag["avg_names"] > 0

    def test_error_is_a_value_error_so_existing_handlers_still_catch_it(self) -> None:
        panel = make_panel(n_days=400, symbols=UNIVERSE[:8])
        score = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
        with pytest.raises(ValueError):
            run_backtest(panel, score, CM, PortfolioConfig(), "M")

    def test_guard_fires_on_a_single_date_in_a_multi_year_panel(self) -> None:
        """Regression shape: a real 6-year panel with one dead month. This is what an
        agent's factor-lookback bug looks like from the engine's side."""
        panel = make_panel(n_days=1464, symbols=UNIVERSE[:20])
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)
        months = score.index.tz_localize(None).to_period("M")
        dead_month = months[900]
        score.loc[months == dead_month, :] = np.nan

        with pytest.raises(EmptyScorePanelError):
            run_backtest(panel, score, CM, PortfolioConfig(), "M")


# --------------------------------------------------------------------------- #
# BUG 2 — ties must not resolve alphabetically
# --------------------------------------------------------------------------- #


def tied_binary_weights(score: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    cfg = PortfolioConfig(n_positions=8)
    return build_rebalance_weights(score, list(score.index), vol, cfg)


class TestTieBreakIsUnbiased:
    """The regression: ``np.argsort(-score, kind='stable')`` broke every tie by column
    position, and the panel's columns are alphabetical — so a *fully tied* score panel
    selected the 8 alphabetically-first names on every single date, forever."""

    def _binary_panel(self, n_dates: int = 24) -> tuple[pd.DataFrame, pd.DataFrame]:
        """A panel where every name scores exactly 1.0 on every date: the maximum-tie
        case, and exactly the shape of the binary 0/1 mask control that mis-scored."""
        dates = pd.bdate_range("2020-01-01", periods=n_dates, tz="Asia/Kolkata")
        score = pd.DataFrame(1.0, index=dates, columns=UNIVERSE)
        vol = pd.DataFrame(0.02, index=dates, columns=UNIVERSE)
        return score, vol

    def test_fully_tied_panel_is_not_the_alphabetically_first_names(self) -> None:
        score, vol = self._binary_panel()
        w = tied_binary_weights(score, vol)

        row = w.iloc[0]
        held = set(row.index[row.to_numpy() > 0])
        assert held, "the book must not be empty"
        assert held != set(UNIVERSE[: len(held)]), (
            "a fully tied panel still selects the alphabetically-first names"
        )

    def test_selection_varies_across_dates(self) -> None:
        """With the alphabetical tie-break the selection is *identical on every date*.
        That invariance is the signature of the bug, and it is what a random book must
        not have."""
        score, vol = self._binary_panel(n_dates=40)
        w = tied_binary_weights(score, vol)

        books = [
            frozenset(row.index[row.to_numpy() > 0]) for _, row in w.iterrows()
        ]
        assert len(set(books)) > 1, "tied scores resolved to one fixed alphabetical book"

    def test_no_name_is_systematically_preferred(self) -> None:
        """Over many tied dates every name must be reachable, and none may be picked
        every time. An alphabetical tie-break picks the first N every time and the rest
        never."""
        score, vol = self._binary_panel(n_dates=120)
        w = tied_binary_weights(score, vol)
        picked = (w.to_numpy() > 0).sum(axis=0)

        assert int((picked > 0).sum()) > 8, "only a handful of names ever selected"
        assert int((picked == len(w)).sum()) == 0, "some name is selected on every date"
        # And the selection rate should be flat across the alphabet, not a step.
        assert picked[: len(UNIVERSE) // 2].std() < 3 * picked.std() + 1e-9

    def test_reproducible_for_a_fixed_input(self) -> None:
        """Determinism is mandatory: backtests must be re-runnable to the digit."""
        score, vol = self._binary_panel(n_dates=30)
        a = tied_binary_weights(score, vol)
        b = tied_binary_weights(score.copy(), vol.copy())
        pd.testing.assert_frame_equal(a, b)

    def test_reproducible_across_a_fresh_interpreter_state(self) -> None:
        """No global RNG state: two independent calls in one process, with the module
        cache cleared in between, must agree."""
        from nsealgo.backtest import engine

        score, vol = self._binary_panel(n_dates=20)
        a = tied_binary_weights(score, vol)
        engine._tiebreak_matrix_cached.cache_clear()
        b = tied_binary_weights(score, vol)
        pd.testing.assert_frame_equal(a, b)

    def test_column_order_does_not_change_which_names_win(self) -> None:
        """The tie-break is a function of the (date, symbol) identity, so a panel whose
        columns are shuffled must produce the same book -- not merely the same weights.
        Under the old position-based tie-break this test failed outright."""
        score, vol = self._binary_panel(n_dates=20)
        shuffled = list(np.random.default_rng(0).permutation(UNIVERSE))

        base = tied_binary_weights(score, vol)
        rot = tied_binary_weights(score[shuffled], vol[shuffled])
        rot = rot.reindex(columns=base.columns)

        # The selected *set* must be identical...
        for date in base.index:
            a = set(base.columns[base.loc[date].to_numpy() > 0])
            b = set(rot.columns[rot.loc[date].to_numpy() > 0])
            assert a == b, date
        # ...and so must the weights those names carry.
        np.testing.assert_allclose(base.to_numpy(), rot.to_numpy(), atol=1e-12)

    def test_tiebreak_key_is_a_pure_function_of_date_and_symbol(self) -> None:
        """No RNG, no process salt: the key is the same value every time."""
        first = [_tiebreak_key("2020-01-01T00:00:00+05:30", s) for s in UNIVERSE]
        second = [_tiebreak_key("2020-01-01T00:00:00+05:30", s) for s in UNIVERSE]
        assert first == second
        assert len(set(first)) == len(UNIVERSE), "keys must be distinct per symbol"
        # A different date gives a different ordering: that is what makes the book vary
        # across rebalances rather than being one fixed alphabetical pick.
        other = [_tiebreak_key("2020-01-02T00:00:00+05:30", s) for s in UNIVERSE]
        assert other != first

    def test_untied_panel_is_unaffected_by_the_tiebreak(self) -> None:
        """A panel with no ties must rank exactly on score — the fix must not reorder
        anything the signal actually decided."""
        dates = pd.bdate_range("2020-01-01", periods=5, tz="Asia/Kolkata")
        score = pd.DataFrame(
            np.arange(len(dates) * len(UNIVERSE), dtype=float).reshape(
                len(dates), len(UNIVERSE)
            ),
            index=dates,
            columns=UNIVERSE,
        )
        vol = pd.DataFrame(0.02, index=dates, columns=UNIVERSE)

        w = tied_binary_weights(score, vol)
        for _, row in score.iterrows():
            held = [c for c in w.columns if w.loc[row.name, c] > 0]
            expected = list(row.sort_values(ascending=False).index[:8])
            assert set(held) == set(expected)

    def test_thin_breaks_weight_ties_by_key_not_alphabetically(self) -> None:
        """`_thin` keeps the `max_names` largest weights. `Series.nlargest` breaks a tie
        by index position, and the index is the panel's column order — alphabetical."""
        names = [f"n{i:02d}" for i in range(20)]  # 20 names, 5 slots
        tgt = pd.Series(0.05, index=names)       # every weight exactly equal
        out = apply_turnover_budget(tgt, None, budget=0.35, max_names=5)

        kept = set(out[out > DEAD_WEIGHT_EPS].index)
        assert len(kept) == 5
        assert kept != set(names[:5]), "max_names slots went to the first five names"

    def test_exit_allocation_breaks_weight_ties_by_key_not_alphabetically(self) -> None:
        """Same bias, second site. `_exit_allocation` takes positions smallest-first when
        the turnover budget cannot clear them all, and `Series.sort_values` broke ties by
        index position — so equal positions were always sold alphabetically.

        The setup forces that branch: a wholly disjoint target means every held position
        must go, the exits alone exceed the whole allowance, and exactly five of ten
        equal 0.12 positions can be sold inside it (0.60 fits, 0.72 does not). Which
        five is then decided purely by the tie-break.
        """
        names = [f"n{i:02d}" for i in range(10)]  # alphabetically ordered
        cur = pd.Series(0.12, index=names)       # 1.2 gross
        tgt = pd.Series(0.12, index=[f"m{i:02d}" for i in range(10)])  # disjoint

        out = apply_turnover_budget(tgt, cur, budget=0.35, max_names=30)

        sold = sorted(n for n in names if cur[n] > out[n] + 1e-12)
        assert len(sold) == 5, sold          # five whole positions cleared the cap
        assert sold != sorted(names[:5]), "exits went alphabetically"

    def test_exit_allocation_still_respects_its_budget(self) -> None:
        """The tie-break must not weaken the constraint it is breaking ties inside."""
        from nsealgo.backtest.engine import _one_way_turnover

        names = [f"n{i:02d}" for i in range(10)]
        cur = pd.Series(0.12, index=names)
        tgt = pd.Series(0.12, index=[f"m{i:02d}" for i in range(10)])

        out = apply_turnover_budget(tgt, cur, budget=0.35, max_names=30)

        assert _one_way_turnover(out, cur) <= 0.35 + 1e-9
        survivors = out[out > DEAD_WEIGHT_EPS]
        assert len(survivors) > 0
        assert bool((survivors == cur.reindex(survivors.index)).all())


# --------------------------------------------------------------------------- #
# BUG 3 — avg_invested_weight
# --------------------------------------------------------------------------- #


class TestBookDiagnostics:
    def test_avg_invested_weight_is_reported_and_consistent(self) -> None:
        panel = make_panel()
        score = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)

        res = run_backtest(panel, score, CM, PortfolioConfig(), "M")

        assert "avg_invested_weight" in res.diag
        assert res.diag["avg_invested_weight"] == pytest.approx(
            float(res.weights.sum(axis=1).mean()), abs=1e-12
        )

    def test_avg_invested_weight_exposes_an_underinvested_book(self) -> None:
        """The gap three agents had to decompose by hand: `avg_names` looks healthy
        while the book is barely funded. Here only 5 of 48 names can ever be scored,
        so ~18% of capital is at work."""
        panel = make_panel()
        score = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
        score.iloc[:, :5] = 1.0

        res = run_backtest(panel, score, CM, PortfolioConfig(n_positions=22), "M")

        assert 0 < res.diag["avg_invested_weight"] < 0.5
        # `avg_names` on its own would have looked unremarkable against max_names=30.
        assert res.diag["avg_names"] <= 5

    def test_diag_separates_an_empty_book_from_a_small_one(self) -> None:
        """The two failure shapes must be tellable apart from `diag` alone: a book that
        is small but working, versus a book that is empty. `avg_names` cannot do this
        on its own; `min_invested_weight` and `min_names` can."""
        panel = make_panel()
        dense = pd.DataFrame(1.0, index=panel.index, columns=panel.columns)
        thin = dense.copy()
        thin.iloc[:, 3:] = np.nan

        full = run_backtest(panel, dense, CM, PortfolioConfig(), "M")
        small = run_backtest(panel, thin, CM, PortfolioConfig(), "M")

        # Small, but never empty -- this is the shape that must NOT raise.
        assert small.diag["min_invested_weight"] > 0.0
        assert small.diag["min_names"] == pytest.approx(3.0)
        # A 3-name book is clearly under-invested next to a full one.
        assert small.diag["avg_invested_weight"] < 0.5 * full.diag["avg_invested_weight"]
        # A structurally empty book is now unreachable, so the minima must never be 0.
        assert full.diag["min_invested_weight"] > 0.0
