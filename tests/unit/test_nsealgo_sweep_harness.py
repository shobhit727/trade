"""Regression tests for the wave harness.

Every test here corresponds to a bug that a wave-1 agent hit in production.
These are the guardrails that stop the same defect from silently producing
"no edge" results in a later wave.
"""

from __future__ import annotations

from decimal import Decimal as D

import numpy as np
import pandas as pd
import pytest

from research.sweep.harness import (
    FACTORS,
    Cell,
    _tiebreak_vector,
    evaluate,
    panel,
    scramble,
)


class TestScrambleCache:
    """The scramble cache was keyed on ``id(score)``.

    ``id()`` is reused once a frame is freed, so a new factor's score could
    inherit the PREVIOUS factor's permutation -- a null built from a different
    factor's scores. Three wave-1 agents hit this independently; one measured
    78/468 cells with edge_vs_null shifted by up to 4.7pp.
    """

    def test_different_factors_get_different_scrambles(self):
        a = pd.DataFrame(np.random.default_rng(1).normal(size=(200, 6)),
                         columns=list("abcdef"))
        b = pd.DataFrame(np.random.default_rng(2).normal(size=(200, 6)),
                         columns=list("abcdef"))
        sa = scramble(a, 42)
        sb = scramble(b, 42)
        assert not np.allclose(sa.to_numpy(), sb.to_numpy()), (
            "two different factors must not share a scrambled null"
        )

    def test_same_content_gets_same_scramble(self):
        """The cache must still work, or every cell pays the full cost."""
        a = pd.DataFrame(np.random.default_rng(1).normal(size=(200, 6)),
                         columns=list("abcdef"))
        assert np.allclose(scramble(a, 42).to_numpy(), scramble(a, 42).to_numpy())

    def test_different_seed_gives_different_scramble(self):
        a = pd.DataFrame(np.random.default_rng(1).normal(size=(200, 6)),
                         columns=list("abcdef"))
        assert not np.allclose(scramble(a, 42).to_numpy(), scramble(a, 43).to_numpy())

    def test_scramble_preserves_the_score_distribution(self):
        """A null must destroy the symbol-score link, not the score distribution."""
        a = pd.DataFrame(np.random.default_rng(7).normal(size=(200, 8)),
                         columns=list("abcdefgh"))
        s = scramble(a, 3)
        assert np.allclose(np.sort(a.to_numpy(), axis=1),
                           np.sort(s.to_numpy(), axis=1), atol=1e-9)


class TestFactorShape:
    """``idio_vol`` returned 4,676 columns instead of 47.

    A wrong-shaped factor produces a degenerate EMPTY book -- cagr 0.0,
    exposure 0.0 -- which reads as "no edge" rather than "this factor never
    ran". It failed silently for an entire wave.
    """

    def test_every_builtin_factor_returns_one_column_per_symbol(self):
        px = panel()
        for name, fn in FACTORS.items():
            out = fn(px)
            assert out.shape[1] == px.shape[1], (
                f"factor {name!r} returned {out.shape[1]} columns, "
                f"expected {px.shape[1]}"
            )
            assert out.shape[0] == px.shape[0], f"factor {name!r} changed the row count"

    def test_wrong_shape_factor_raises_instead_of_returning_an_empty_book(self):
        cell = Cell(factor="__nonexistent__", n_hold=20, buffer=20, clock="A")
        # A missing factor returns None (unknown name), not a silent empty book.
        assert evaluate(cell, "TEST") is None


class TestTieBreak:
    """Tied scores were resolved by column position, and the columns are
    alphabetical -- so a boolean score (large tie groups) selected
    alphabetically. A wave-1 agent measured tie groups of 18 of 47 names.
    """

    def test_tie_break_is_not_alphabetical(self):
        cols = ["adaniports", "apollohosp", "axisbank", "bajajauto", "tcs"]
        tb = _tiebreak_vector(cols)
        order = [cols[i] for i in np.argsort(-tb)]
        assert order != sorted(cols), "ties must not resolve alphabetically"

    def test_tie_break_is_order_independent(self):
        cols = ["adaniports", "apollohosp", "axisbank", "bajajauto", "tcs"]
        shuffled = list(reversed(cols))
        a = dict(zip(cols, _tiebreak_vector(cols)))
        b = dict(zip(shuffled, _tiebreak_vector(shuffled)))
        for c in cols:
            assert a[c] == pytest.approx(b[c]), (
                "a symbol's tie-break must not depend on its column position"
            )


class TestPanelIsCleaned:
    """The sweep panel was built from the raw CSV reader, not the production
    loader, so loader rule C10 was not applied and TRENT's unadjusted 1:1.5
    bonus -- a fake -33% close-to-close move inside the TEST window -- was
    still in the data.
    """

    def test_trent_has_no_phantom_crash(self):
        px = panel()
        assert "trent" in px.columns
        r = px["trent"].pct_change()
        worst = r.abs().max()
        assert worst < 0.25, (
            f"TRENT shows a {worst:.1%} single-day move; the 2026-01-01 1:1.5 "
            "bonus is not back-adjusted, so the panel is not cleaned"
        )

    def test_gap_factor_is_a_real_overnight_gap(self):
        """The `gap` factor was a placeholder (px.shift(0) -- the close again)."""
        px = panel()
        g = FACTORS["gap"](px)
        assert g.shape[1] == px.shape[1]
        # A real overnight gap is small; the placeholder was exactly the close.
        assert float(g.abs().mean().mean()) < 0.05
        assert not np.allclose(g.iloc[-1].to_numpy(), px.iloc[-1].to_numpy())


class TestCosts:
    def test_delivery_stack_is_derived_not_restated(self):
        """The shipped figure was 21.92 bp; the true stack is 32.32 bp."""
        from nsealgo.costs import CostModel
        from research.sweep.harness import DELIVERY_ALL_IN_BPS, DELIVERY_STATUTORY_BPS

        engine = CostModel(segment="delivery", slippage_bps=D("0")).round_trip_bps(
            D("2100000")
        )
        assert DELIVERY_STATUTORY_BPS == pytest.approx(float(engine) * 2)
        assert DELIVERY_ALL_IN_BPS == pytest.approx(32.32, abs=0.05)

    def test_instrument_stacks_are_ordered(self):
        from research.sweep.harness import INSTRUMENT_BPS

        assert INSTRUMENT_BPS["etf"] < INSTRUMENT_BPS["futures"] < INSTRUMENT_BPS["delivery"]
