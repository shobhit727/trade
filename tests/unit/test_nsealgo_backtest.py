"""Look-ahead and correctness tests for the backtest engine.

The look-ahead tests are the most important in this repo. A backtest with look-ahead
produces beautiful, worthless numbers — which is exactly the failure mode `GOAL.md` §6
exists to prevent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nsealgo.backtest.engine import (
    DEAD_WEIGHT_EPS,
    SECTORS,
    PortfolioConfig,
    _one_way_turnover,
    _rebalance_dates,
    apply_turnover_budget,
    build_rebalance_weights,
    run_backtest,
    sector_of,
)
from nsealgo.backtest.metrics import (
    compute_metrics,
    drawdown_series,
    max_drawdown,
    yearly_returns,
)
from nsealgo.costs import CostModel
from nsealgo.factors.core import (
    build_composite_score,
    momentum_12_1,
    zscore_cross_sectional,
)
from nsealgo.factors.regime import blend_with_cash, exposure_series

CM = CostModel(segment="delivery", slippage_bps=5)


def make_panel(seed: int = 0, n_days: int = 900, n_sym: int = 25) -> pd.DataFrame:
    """Deterministic synthetic panel with a genuine momentum structure, so the
    look-ahead tests have something real to detect."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-01", periods=n_days, tz="Asia/Kolkata")
    cols = [f"s{i:02d}" for i in range(n_sym)]

    # Give each symbol a persistent drift so momentum is real, not noise.
    drifts = rng.normal(0.0004, 0.0006, n_sym)
    shocks = rng.normal(0, 0.012, (n_days, n_sym))
    prices = np.empty((n_days, n_sym))
    p0 = rng.uniform(100, 2000, n_sym)
    for t in range(n_days):
        p0 = p0 * (1.0 + drifts + shocks[t])
        prices[t] = p0
    return pd.DataFrame(prices, index=dates, columns=cols)


class TestNoLookahead:
    """Weights decided at date t must not use information from t+1 onward."""

    def test_factors_are_trailing_only(self) -> None:
        p = make_panel()
        mom = momentum_12_1(p)          # DataFrame: dates x symbols
        # Truncating the panel must not change any *past* factor value.
        cut = p.index[600]
        mom_trunc = momentum_12_1(p.loc[:cut])
        pd.testing.assert_frame_equal(mom.loc[:cut], mom_trunc.loc[:cut])

    def test_future_prices_cannot_change_past_signals(self) -> None:
        p = make_panel()
        cut = p.index[700]
        before = build_composite_score(p.loc[:cut])

        # Corrupt everything AFTER the cut. Past signals must be bit-identical.
        poisoned = p.copy()
        poisoned.loc[poisoned.index > cut] *= 3.0
        after = build_composite_score(poisoned).loc[:cut]

        pd.testing.assert_frame_equal(before, after)

    def test_regime_exposure_is_lagged(self) -> None:
        p = make_panel()
        e = exposure_series(p, lookback=126, threshold=0.0)
        # exposure[t] may only use data through t-1, so poisoning t+1.. must not
        # change any past exposure.
        cutoff = p.index[800]
        p2 = p.copy()
        p2.loc[p2.index > cutoff] *= 5.0
        e2 = exposure_series(p2, lookback=126, threshold=0.0)
        pd.testing.assert_series_equal(e.loc[:cutoff], e2.loc[:cutoff])

    def test_zscore_is_cross_sectional_per_day(self) -> None:
        f = pd.DataFrame(
            [[1.0, 2.0, 3.0], [100.0, 200.0, 300.0]],
            index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
            columns=list("abc"),
        )
        z = zscore_cross_sectional(f)
        # Row 2 is a pure scale multiple of row 1 -> identical z-scores.
        np.testing.assert_allclose(z.iloc[0].values, z.iloc[1].values, atol=1e-9)


class TestCostRealism:
    def test_costs_reduce_return_monotonically(self) -> None:
        p = make_panel()
        sc = build_composite_score(p)
        cfg = PortfolioConfig()
        cheap = run_backtest(p, sc, CostModel(slippage_bps=0), cfg, "M")
        dear = run_backtest(p, sc, CostModel(slippage_bps=30), cfg, "M")
        assert dear.metrics.cagr < cheap.metrics.cagr
        assert dear.metrics.cost_drag_annual > cheap.metrics.cost_drag_annual

    def test_costs_are_actually_charged(self) -> None:
        """Regression: costs were once charged as a bare fraction of turnover rather
        than of equity, understating the drag ~20x on a compounding book."""
        p = make_panel()
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(), "M")
        assert res.costs_paid > 0
        assert res.metrics.cost_drag_annual > 0
        assert res.metrics.annual_turnover > 0

    def test_cost_scales_with_equity_growth(self) -> None:
        """On a book that compounds, later costs must be larger in rupee terms."""
        p = make_panel()
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(), "M")
        assert res.equity.iloc[-1] > 1.0


class TestConstraints:
    def test_position_count_respected(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(n_positions=12), "M")
        assert res.diag["avg_names"] <= 13  # +1 for a partial rebalance leg

    def test_single_name_cap_respected(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(max_weight=0.12), "M")
        assert res.weights.max().max() <= 0.1201

    def test_weights_sum_below_one_for_cash_buffer(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        cfg = PortfolioConfig(cash_buffer=0.15)
        res = run_backtest(p, sc, CM, cfg, "M")
        assert res.weights.sum(axis=1).max() <= 0.851

    def test_weights_never_negative(self) -> None:
        p = make_panel()
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(), "M")
        assert res.weights.min().min() >= 0.0

    def test_sector_map_is_total(self) -> None:
        assert all(isinstance(sector_of(s), str) for s in ["tcs", "hdfcbank", "zzz"])


# --------------------------------------------------------------------------- #
# Regression tests for the two portfolio-construction bugs.
# --------------------------------------------------------------------------- #

#: Symbols spanning three sectors, so a concentrated score can load one sector past
#: its cap *and* push the excess onto names that are already at the single-name cap.
SECTOR_SPAN = [
    "hdfcbank", "icicibank", "kotakbank", "axisbank", "sbin",   # bank
    "tcs", "infy", "hcltech", "techm", "lt", "wipro",           # it
    "maruti", "titan", "sunpharma",                             # auto / cons / pharma
]
ONE_DATE = pd.DatetimeIndex([pd.Timestamp("2013-04-01", tz="Asia/Kolkata")])


def concentrated_weights(
    config: PortfolioConfig, score_skew: float = 1e6, vol_skew: float = 1.0
) -> pd.DataFrame:
    """Weights from a score panel with one name 10^6x everything else.

    This is the shape that broke: the bank sector over-fills, so the sector cap has to
    spill onto names already sitting at the single-name cap.
    """
    score = pd.DataFrame(1.0, index=ONE_DATE, columns=SECTOR_SPAN)
    score.loc[:, "tcs"] = score_skew
    vol = pd.DataFrame(0.02, index=ONE_DATE, columns=SECTOR_SPAN)
    vol.loc[:, "tcs"] = 0.02 * vol_skew
    return build_rebalance_weights(score, ONE_DATE, vol, config)


def sector_sums(w: pd.DataFrame) -> pd.Series:
    """Per-sector weight totals."""
    out: dict[str, float] = {}
    for col in w.columns:
        out[sector_of(col)] = out.get(sector_of(col), 0.0) + float(w[col].iloc[0])
    return pd.Series(out)


class TestCapsHoldSimultaneously:
    """Regression: the sector cap ran last and never re-capped what it spilled.

    A concentrated score produced a 20.25% position against a 12.00% cap, and pushed
    the bank sector to 42.86% against a 25.00% cap. Both caps must hold at once.
    """

    @pytest.mark.parametrize("n_positions", [5, 8, 10, 12, 15, 22, 30])
    def test_single_name_cap_holds_under_concentration(self, n_positions: int) -> None:
        cfg = PortfolioConfig(n_positions=n_positions)
        w = concentrated_weights(cfg)
        assert w.max(axis=1).max() <= cfg.max_weight + 1e-9

    def test_sector_cap_holds_under_concentration(self) -> None:
        cfg = PortfolioConfig(n_positions=12)
        w = concentrated_weights(cfg)
        assert sector_sums(w).max() <= cfg.max_sector_weight + 1e-9

    def test_all_invariants_hold_under_concentration(self) -> None:
        cfg = PortfolioConfig(n_positions=12)
        w = concentrated_weights(cfg)
        assert w.max(axis=1).max() <= cfg.max_weight + 1e-9
        assert sector_sums(w).max() <= cfg.max_sector_weight + 1e-9
        assert w.sum(axis=1).max() <= (1 - cfg.cash_buffer) + 1e-9
        assert w.min().min() >= 0.0

    @pytest.mark.parametrize("vol_skew", [1.0, 0.1, 0.01, 0.001])
    def test_single_name_cap_holds_when_inverse_vol_dominates(self, vol_skew: float) -> None:
        """A low-vol name takes most of the book, forcing the cap to bind, then the
        sector spill has to land on other capped names."""
        cfg = PortfolioConfig(n_positions=12)
        w = concentrated_weights(cfg, vol_skew=vol_skew)
        assert w.max(axis=1).max() <= cfg.max_weight + 1e-9
        assert sector_sums(w).max() <= cfg.max_sector_weight + 1e-9

    def test_infeasible_sector_panel_holds_rather_than_breaking(self) -> None:
        """One sector cannot absorb a full book under a 25% cap. The honest answer is
        to hold less than a full book, not to breach the cap."""
        cfg = PortfolioConfig()
        one_sector = ["hdfcbank", "icicibank", "kotakbank", "axisbank", "sbin"]
        score = pd.DataFrame(1.0, index=ONE_DATE, columns=one_sector)
        vol = pd.DataFrame(0.02, index=ONE_DATE, columns=one_sector)
        w = build_rebalance_weights(score, ONE_DATE, vol, cfg)
        assert sector_sums(w).max() <= cfg.max_sector_weight + 1e-9
        assert w.max(axis=1).max() <= cfg.max_weight + 1e-9
        assert w.sum(axis=1).max() <= (1 - cfg.cash_buffer) + 1e-9


class TestPositionCountDoesNotAccumulate:
    """Regression: turnover blending left a residual on every dropped name, so dead
    weights accreted until 48 names held a non-zero position against a limit of 30."""

    def test_blend_drops_dead_weights(self) -> None:
        cur = pd.Series({"a": 0.10, "b": 0.09, "c": 0.08})
        tgt = pd.Series({"a": 0.10, "b": 0.09, "d": 0.08})
        out = apply_turnover_budget(tgt, cur, budget=0.35, max_names=30)
        assert float(out["c"]) == 0.0, "dead residual must be dropped, not carried"
        assert (out > DEAD_WEIGHT_EPS).sum() <= 30

    def test_blend_never_exceeds_max_names(self) -> None:
        """Rotate the target across 40 disjoint names; a residual book must not grow."""
        cfg = PortfolioConfig()
        names = [f"n{i}" for i in range(40)]
        prev = None
        for step in range(20):
            tgt = pd.Series(0.0, index=names)
            for j in range(12):  # a fresh dozen names each rebalance
                tgt[names[(step * 12 + j) % 40]] = 0.05
            prev = apply_turnover_budget(tgt, prev, cfg.turnover_budget, cfg.max_names)
            assert int((prev > DEAD_WEIGHT_EPS).sum()) <= cfg.max_names

    def test_turnover_budget_still_respected_after_thinning(self) -> None:
        """Dropping a name is itself a trade, so it must come out of the same budget."""
        cfg = PortfolioConfig()
        names = [f"n{i}" for i in range(40)]
        prev = None
        for step in range(20):
            tgt = pd.Series(0.0, index=names)
            for j in range(12):
                tgt[names[(step * 12 + j) % 40]] = 0.05
            out = apply_turnover_budget(tgt, prev, cfg.turnover_budget, cfg.max_names)
            if prev is not None:
                # one-way turnover between consecutive *delivered* books
                one_way = float((out - prev).abs().sum() / 2.0)
                assert one_way <= cfg.turnover_budget + 1e-9, one_way
            prev = out

    def test_backtest_held_weights_respect_max_names(self) -> None:
        p = make_panel(n_sym=40)
        sc = build_composite_score(p)
        res = run_backtest(p, sc, CM, PortfolioConfig(n_positions=40), "M")
        assert int((res.weights > DEAD_WEIGHT_EPS).sum(axis=1).max()) <= 30

    def test_backtest_held_weights_respect_max_names_default(self) -> None:
        """n_positions above max_names must not leak extra positions into the book."""
        p = make_panel(seed=3, n_sym=40)
        sc = build_composite_score(p)
        cfg = PortfolioConfig(n_positions=40, max_names=22)
        res = run_backtest(p, sc, CM, cfg, "M")
        assert int((res.weights > DEAD_WEIGHT_EPS).sum(axis=1).max()) <= 22


# --------------------------------------------------------------------------- #
# Regression: the turnover budget was diluting the book with stale residue.
#
# `apply_turnover_budget` blended the whole book toward the new target, so a name that
# dropped OUT of the target (`tgt[s] == 0`) only decayed by `1 - lam` per rebalance and
# was carried for months: `_thin` kills a weight only below DEAD_WEIGHT_EPS. With a
# sparse signal (13 of 48 names eligible) that left 32% of the book -- up to 47% on a
# single date -- sitting in names the signal did not want, and 29.6 names against a
# 22-name target. The headline Sharpe was measuring the dilution, not the signal.
#
# These tests run the real engine end to end over the real 48-symbol universe, because
# the failure is in the interaction of the blend, `_thin` and the caps: a synthetic
# panel of unknown symbols collapses into one "other" sector and never gets there.
# --------------------------------------------------------------------------- #

UNIVERSE = list(SECTORS)
N_ELIGIBLE = 13
N_DAYS = 1200


@pytest.fixture(scope="module")
def sector_panel() -> pd.DataFrame:
    """Real symbols, real sectors, deterministic prices."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2010-01-01", periods=N_DAYS, tz="Asia/Kolkata")
    n = len(UNIVERSE)
    drifts = rng.normal(0.0005, 0.0008, n)
    shocks = rng.normal(0, 0.011, (N_DAYS, n))
    prices = np.empty((N_DAYS, n))
    p0 = rng.uniform(100, 3000, n)
    for t in range(N_DAYS):
        p0 = p0 * (1.0 + drifts + shocks[t])
        prices[t] = p0
    return pd.DataFrame(prices, index=dates, columns=UNIVERSE)


@pytest.fixture(scope="module")
def dense_score(sector_panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(1.0, index=sector_panel.index, columns=UNIVERSE)


@pytest.fixture(scope="module")
def sparse(sector_panel: pd.DataFrame) -> pd.DataFrame:
    """NaN everywhere except `n_elig` names a month, chosen by a sticky AR(1) ranking.

    Sticky so consecutive months overlap -- the shape a real sparse factor has, and
    the shape in which the turnover budget can actually afford the exits.
    """
    panel = sector_panel
    rng = np.random.default_rng(11)
    dates = panel.index
    eps = rng.normal(0, 0.9, (len(UNIVERSE), len(dates)))
    x = np.zeros_like(eps)
    x[:, 0] = eps[:, 0]
    for t in range(1, len(dates)):
        x[:, t] = 0.97 * x[:, t - 1] + eps[:, t]
    latent = pd.DataFrame(x.T, index=dates, columns=UNIVERSE).rolling(
        30, min_periods=1
    ).mean()

    months = dates.tz_localize(None).to_period("M")
    score = pd.DataFrame(np.nan, index=dates, columns=UNIVERSE)
    for _, idx in pd.Series(dates, index=dates).groupby(months).groups.items():
        idx = pd.DatetimeIndex(idx)
        picks = latent.loc[idx].mean().nlargest(N_ELIGIBLE).index
        score.loc[idx, picks] = rng.uniform(0.1, 1.0, N_ELIGIBLE)
    return score


def rebalance_books(panel: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    return weights.loc[
        [d for d in _rebalance_dates(panel.index, "M") if d in weights.index][1:]
    ]


def unsignalled_share(books: pd.DataFrame, score: pd.DataFrame) -> pd.Series:
    """Share of gross weight in names the signal does not carry that date."""
    signalled = score.reindex(books.index).notna()
    gross = books.sum(axis=1)
    stale = books.where(~signalled).sum(axis=1)
    return (stale / gross).where(gross > 0, 0.0)


class TestSparseSignalIsNotDiluted:
    """A book that cannot be rebuilt must not be held, stale names and all."""

    def test_dense_score_reaches_full_investment_and_position_count(
        self, sector_panel: pd.DataFrame, dense_score: pd.DataFrame
    ) -> None:
        """(a) A signal on every name must produce the configured book, undiluted."""
        cfg = PortfolioConfig()
        res = run_backtest(sector_panel, dense_score, CM, cfg, "M")
        books = rebalance_books(sector_panel, res.weights)

        assert books.sum(axis=1).mean() == pytest.approx(
            1.0 - cfg.cash_buffer, abs=1e-6
        )
        counts = (books > DEAD_WEIGHT_EPS).sum(axis=1)
        assert counts.mean() == pytest.approx(cfg.n_positions, abs=1)
        assert counts.max() <= cfg.max_names

    def test_sparse_score_does_not_hold_unsignalled_weight(
        self, sector_panel: pd.DataFrame, sparse: pd.DataFrame
    ) -> None:
        """(b) The regression. Before the fix this averaged 2.5% and peaked at 18.3%
        on a sticky signal (32.4% mean / 47.4% peak on a fully-rotating one)."""
        res = run_backtest(sector_panel, sparse, CM, PortfolioConfig(), "M")
        books = rebalance_books(sector_panel, res.weights)

        share = unsignalled_share(books, sparse)
        assert share.max() <= 0.10, share[share > 0.10].to_dict()
        assert share.mean() <= 0.02, share.mean()

    def test_sparse_book_holds_only_signalled_names(
        self, sector_panel: pd.DataFrame, sparse: pd.DataFrame
    ) -> None:
        """The book must not accret a tail of names past its position limit."""
        res = run_backtest(sector_panel, sparse, CM, PortfolioConfig(), "M")
        books = rebalance_books(sector_panel, res.weights)

        signalled = sparse.reindex(books.index).notna()
        held = books > DEAD_WEIGHT_EPS
        assert int((held & ~signalled).to_numpy().sum()) == 0
        counts = held.sum(axis=1)
        assert counts.max() <= N_ELIGIBLE, counts.max()

    def test_sparse_book_respects_every_cap(
        self, sector_panel: pd.DataFrame, sparse: pd.DataFrame
    ) -> None:
        """Unwinding the residue must not break the caps it was diluting."""
        cfg = PortfolioConfig()
        books = rebalance_books(
            sector_panel, run_backtest(sector_panel, sparse, CM, cfg, "M").weights
        )

        assert books.max().max() <= cfg.max_weight + 1e-9
        assert books.min().min() >= 0.0
        assert books.sum(axis=1).max() <= (1.0 - cfg.cash_buffer) + 1e-9
        sectors = books.T.groupby([sector_of(c) for c in books.columns]).sum().T
        assert sectors.max(axis=1).max() <= cfg.max_sector_weight + 1e-9

    def test_one_way_turnover_stays_within_budget_every_rebalance(
        self, sector_panel: pd.DataFrame, sparse: pd.DataFrame
    ) -> None:
        """(c) Unwinding is a trade like any other and must come out of the budget."""
        cfg = PortfolioConfig()
        books = rebalance_books(
            sector_panel, run_backtest(sector_panel, sparse, CM, cfg, "M").weights
        )

        turn = (books.diff().abs().sum(axis=1) / 2.0).iloc[1:]
        assert len(turn) > 40
        assert turn.max() <= cfg.turnover_budget + 1e-9, turn.max()

    def test_budget_is_bidirectionally_bounded_on_a_rotating_target(self) -> None:
        """The worst case for the budget: a fully disjoint 13-of-48 target every
        rebalance. It cannot be rebuilt inside the allowance, but the book must still
        leave the stale names -- and must still respect the budget doing it."""
        cfg = PortfolioConfig()
        rng = np.random.default_rng(3)
        prev = None
        for _ in range(40):
            picks = rng.choice(len(UNIVERSE), size=N_ELIGIBLE, replace=False)
            tgt = pd.Series(0.0, index=UNIVERSE)
            tgt.iloc[picks] = 1.0 / N_ELIGIBLE * 0.9
            out = apply_turnover_budget(
                tgt, prev, cfg.turnover_budget, cfg.max_names
            )
            if prev is not None:
                assert _one_way_turnover(out, prev) <= cfg.turnover_budget + 1e-9
            assert int((out > DEAD_WEIGHT_EPS).sum()) <= cfg.max_names
            prev = out

    def test_a_dropped_name_exits_in_one_rebalance(self) -> None:
        """The unit of the bug: `tgt[s] == 0` must mean zero, not `cur[s] * (1-lam)`.

        The weights here are chosen so the budget actually binds (`lam < 1`), which is
        the regime the bug lived in. Under the old blend `d` came out at 0.088 against
        a 0.20 position; it is now sold.
        """
        cur = pd.Series({"a": 0.20, "b": 0.20, "c": 0.20, "d": 0.20})
        tgt = pd.Series(
            {"a": 0.05, "b": 0.05, "c": 0.05, "e": 0.20, "f": 0.20, "g": 0.20}
        )
        out = apply_turnover_budget(tgt, cur, budget=0.35, max_names=30)

        assert _one_way_turnover(out, cur) <= 0.35 + 1e-9
        assert float(out["d"]) == 0.0
        assert float(out["a"]) == pytest.approx(0.1286, abs=1e-3)  # blended, not sold

    def test_sale_is_all_or_nothing_when_the_budget_binds(self) -> None:
        """A half-sold position leaves a sliver that is untradable, still costs its
        former weight to clear, and still holds a `max_names` slot until it does — the
        dust the old blend accreted. What cannot be sold must stay whole or not move."""
        cur = pd.Series({f"n{i}": 0.12 for i in range(10)})       # 1.2 gross, cap 0.70
        tgt = pd.Series({f"m{i}": 0.12 for i in range(10)})       # wholly disjoint
        out = apply_turnover_budget(tgt, cur, budget=0.35, max_names=30)

        assert _one_way_turnover(out, cur) <= 0.35 + 1e-9
        survivors = out[out > DEAD_WEIGHT_EPS]
        assert len(survivors) > 0
        assert bool((survivors == cur.reindex(survivors.index)).all())   # whole or absent
        assert int(len(survivors)) <= 30


class TestMetrics:
    def test_annualisation_uses_244_days(self) -> None:
        """Regression risk: the parent repo mixed sqrt(252) and sqrt(244)."""
        rng = np.random.default_rng(1)
        daily = pd.Series(rng.normal(0.0004, 0.01, 244 * 3))
        m = compute_metrics(daily)
        assert 0.15 < m.volatility < 0.25, m.volatility

    def test_sharpe_subtracts_risk_free(self) -> None:
        """A strategy earning exactly the risk-free rate must have Sharpe ~0."""
        rf = 0.065
        per_day = (1 + rf) ** (1 / 244) - 1
        flat = pd.Series([per_day] * 488)
        assert abs(compute_metrics(flat, rf_annual=rf).sharpe) < 1e-6

    def test_zero_volatility_gives_zero_sharpe_not_nan(self) -> None:
        flat = pd.Series([0.0] * 300)
        m = compute_metrics(flat)
        assert m.sharpe == 0.0
        assert m.volatility == 0.0

    def test_max_drawdown_on_equity_curve(self) -> None:
        eq = pd.Series([1.0, 1.5, 0.75, 1.2, 0.9])
        dd, days = max_drawdown(eq)
        assert dd == pytest.approx(-0.5)
        assert days >= 2
        assert drawdown_series(eq).min() == pytest.approx(-0.5)

    def test_monotonic_equity_has_no_drawdown(self) -> None:
        eq = pd.Series([1.0, 1.1, 1.2, 1.3])
        dd, _ = max_drawdown(eq)
        assert dd == pytest.approx(0.0)

    def test_yearly_returns_are_per_year_not_cumulative(self) -> None:
        """Regression: this once returned cumulative equity, showing +467% 'annual'
        returns. Each entry must now be growth within that year."""
        idx = pd.DatetimeIndex(
            ["2020-01-02", "2020-01-03", "2021-01-04", "2021-01-05"], tz="Asia/Kolkata"
        )
        r = pd.Series([0.10, 0.10, 0.10, 0.10], index=idx)
        y = yearly_returns(r)
        assert y[2020] == pytest.approx(0.21)
        assert y[2021] == pytest.approx(0.21)

    def test_empty_input_is_safe(self) -> None:
        m = compute_metrics(pd.Series(dtype=float))
        assert m.n_periods == 0
        assert m.cagr == 0.0


class TestOverlay:
    def test_blend_keeps_shares_summed_to_one(self) -> None:
        p = make_panel()
        r = pd.Series(0.001, index=p.index)
        e = pd.Series(0.5, index=p.index)
        out = blend_with_cash(r, e)
        assert len(out) == len(r)
        assert (out > -1).all()

    def test_full_exposure_reproduces_strategy(self) -> None:
        p = make_panel()
        r = pd.Series(0.001, index=p.index)
        e = pd.Series(1.0, index=p.index)
        out = blend_with_cash(r, e)
        np.testing.assert_allclose(out.values, 0.001, atol=1e-9)

    def test_zero_exposure_earns_risk_free(self) -> None:
        p = make_panel()
        r = pd.Series(-0.05, index=p.index)  # catastrophic strategy day
        e = pd.Series(0.0, index=p.index)   # fully de-risked
        out = blend_with_cash(r, e)
        assert (out > 0).all(), "de-risked day should not follow the strategy down"


class TestWalkForwardSafety:
    def test_insufficient_data_raises(self) -> None:
        from nsealgo.backtest.walkforward import walk_forward

        p = make_panel(n_days=300, n_sym=10)
        with pytest.raises(ValueError, match="not enough data"):
            walk_forward(p, [{"n": 1}], lambda pn, prm: None, n_folds=5,
                         train_years=6, test_years=2)

    def test_rejects_unknown_rebalance_freq(self) -> None:
        from nsealgo.backtest.engine import _rebalance_dates

        with pytest.raises(ValueError, match="W.*M.*Q"):
            _rebalance_dates(make_panel().index, "Y")
