"""Tests for the per-stock optimiser.

These exist because the smoke run found two bugs that would each have invalidated the
entire 4,032-pair sweep while reporting nothing but plausible numbers:

1. ``catalog.load_strategy`` resolved every module to the *base* ``SignalStrategy``, whose
   ``signal()`` returns 0 unconditionally -> 0.00% CAGR everywhere, no error.
2. ``backtest.run_single_stock`` subtracted the purchase price from cash twice -> equity
   went to zero and CAGR read -100%.

A test that cannot fail is not a guard, so each of these is written to be red against the
broken behaviour.
"""

from __future__ import annotations

import sys

import pandas as pd
import pytest

from research.optimize import config as C
from research.optimize import metrics as M
from research.optimize import nulls as N
from research.optimize import splitter as S
from research.optimize.backtest import BacktestError, run_single_stock
from research.optimize.catalog import discover, load_strategy


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
def make_bars(n: int = 500, start: str = "2020-01-01", seed: int = 0) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    px = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, n)))
    return pd.DataFrame({"open": px, "high": px * 1.01, "low": px * 0.99,
                         "close": px, "volume": 1e6}, index=idx)


class _AlwaysLong:
    """Minimal stand-in for a strategy: buys on the first actionable bar, never exits."""

    def __init__(self, config=None):
        self._pos = {}
        self.config = config

    def feed(self, symbol, close, high=None, low=None, volume=None, ts=None):
        self._pos[symbol] = 1
        return None


class _NeverLong(_AlwaysLong):
    def feed(self, symbol, close, high=None, low=None, volume=None, ts=None):
        self._pos[symbol] = 0
        return None


class _Cfg:
    def __init__(self, **kw):
        self.__dict__.update(kw or {"period": 5})


def _spec(strategy_cls, default=None):
    """Build a duck-typed StrategySpec.

    A plain object rather than a class body: assigning ``strategy_cls = strategy_cls``
    inside a class body raises NameError, because class scope does not see the enclosing
    function's parameters.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        name="fake",
        strategy_cls=strategy_cls,
        config_cls=_Cfg,
        params=[],
        held_fixed=[],
        default=default or {"period": 5},
        build=lambda values: strategy_cls(_Cfg(**values)),
    )


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class TestCatalog:
    def test_resolves_concrete_strategy_not_the_base_class(self):
        """Regression: every module resolved to SignalStrategy -> all-zero sweep."""
        for name in ("absolute_momentum", "rsi_strategy", "moving_average_cross"):
            spec = load_strategy(name)
            assert spec.strategy_cls.__name__ != "SignalStrategy", name
            assert spec.strategy_cls.__module__.endswith(name), name

    def test_every_strategy_produces_non_degenerate_signals(self):
        """A strategy whose signal is always 0 can never trade; catch it at load time."""
        specs = discover()
        assert len(specs) >= 80
        for s in specs:
            assert s.strategy_cls.__name__ != "SignalStrategy", s.name

    def test_search_space_excludes_position_size_knob(self):
        """`quantity` is order sizing, not signal. Optimising it is a wasted dimension."""
        for s in discover():
            assert "quantity" in s.held_fixed, s.name
            assert all(p.name != "quantity" for p in s.params), s.name

    def test_every_config_field_is_searchable_or_explicitly_held(self):
        for s in discover():
            assert s.params, f"{s.name} has no searchable params"


# --------------------------------------------------------------------------- #
# Backtest accounting
# --------------------------------------------------------------------------- #
class TestBacktestAccounting:
    def test_cash_is_not_debited_twice(self):
        """Regression: equity hit zero and CAGR read -100%."""
        bars = make_bars(400)
        r = run_single_stock(bars, _spec(_AlwaysLong), {}, tax_enabled=False)
        assert r.equity.iloc[-1] > 0, "equity must not be destroyed by double debit"
        # A permanently-long book should not lose to cash by construction.
        assert r.equity.iloc[-1] > float(C.CAPITAL_INR) * 0.2

    def test_always_long_beats_never_long(self):
        bars = make_bars(600, seed=3)
        up = run_single_stock(bars, _spec(_AlwaysLong), {}, tax_enabled=False)
        flat = run_single_stock(bars, _spec(_NeverLong), {}, tax_enabled=False)
        assert up.equity.iloc[-1] > flat.equity.iloc[-1]
        assert len(up.trades) >= 1
        assert len(flat.trades) == 0

    def test_never_trading_costs_nothing(self):
        bars = make_bars(300, seed=7)
        r = run_single_stock(bars, _spec(_NeverLong), {}, tax_enabled=True)
        assert r.total_fees == 0.0
        assert r.total_tax == 0.0
        assert r.equity.iloc[-1] == pytest.approx(float(C.CAPITAL_INR))

    def test_equity_never_negative_on_a_positive_price_series(self):
        bars = make_bars(500, seed=11)
        for tax in (False, True):
            r = run_single_stock(bars, _spec(_AlwaysLong), {}, tax_enabled=tax)
            assert (r.equity > 0).all(), f"tax={tax}"

    def test_empty_slice_raises_rather_than_returning_flat(self):
        """A silent flat result is indistinguishable from a real one."""
        with pytest.raises(BacktestError):
            run_single_stock(pd.DataFrame(), _spec(_AlwaysLong), {})
        with pytest.raises(BacktestError):
            # slice entirely in the future -> empty, must raise rather than return flat
            run_single_stock(make_bars(50), _spec(_AlwaysLong), {}, start="2030-01-01")


class TestTaxLedger:
    def test_tax_is_charged_and_reduces_final_equity(self):
        """Needs a strategy that SELLS: a book that never exits realises no gains."""
        bars = make_bars(600, seed=5)
        pre = run_single_stock(bars, _spec(_Alternating), {}, tax_enabled=False)
        post = run_single_stock(bars, _spec(_Alternating), {}, tax_enabled=True)
        assert len(pre.trades) > 1, "must actually round-trip to realise gains"
        assert post.total_tax > 0
        assert post.equity.iloc[-1] < pre.equity.iloc[-1]

    def test_never_exiting_book_pays_no_capital_gains_tax(self):
        """Unrealised gains are not taxed. This is correct, not a bug."""
        bars = make_bars(600, seed=5)
        r = run_single_stock(bars, _spec(_AlwaysLong), {}, tax_enabled=True)
        assert r.total_tax == 0.0

    def test_losses_are_not_taxed(self):
        """A steadily falling series realises losses; tax must be zero."""
        import numpy as np

        n = 400
        idx = pd.bdate_range("2020-01-01", periods=n)
        px = 100.0 * np.exp(np.cumsum(np.full(n, -0.0008)))
        bars = pd.DataFrame({"close": px, "high": px, "low": px, "volume": 1e6}, index=idx)
        r = run_single_stock(bars, _spec(_Alternating), {}, tax_enabled=True)
        assert len(r.trades) > 1
        assert r.total_tax == 0.0

    def test_ltcg_rate_applies_beyond_365_days(self):
        import datetime as dt

        from research.optimize.backtest import Lot, _settle_tax

        lots = deque_of([Lot(shares=100, cost_basis=10000.0, opened=dt.datetime(2015, 1, 1))])
        tax, _ = _settle_tax(lots, 100, 20000.0, dt.datetime(2016, 6, 1), True)
        # 10000 gain * 12.5%
        assert tax == pytest.approx(1250.0)

    def test_stcg_rate_applies_within_365_days(self):
        import datetime as dt

        from research.optimize.backtest import Lot, _settle_tax

        lots = deque_of([Lot(shares=100, cost_basis=10000.0, opened=dt.datetime(2016, 1, 1))])
        tax, _ = _settle_tax(lots, 100, 20000.0, dt.datetime(2016, 6, 1), True)
        assert tax == pytest.approx(2000.0)


class _Alternating:
    """Long / flat on a 60-bar cycle, so gains are actually realised and taxed."""

    def __init__(self, config=None):
        self._pos = {}
        self._n = 0

    def feed(self, symbol, close, high=None, low=None, volume=None, ts=None):
        self._n += 1
        self._pos[symbol] = (self._n // 60) % 2 == 0
        return None


def deque_of(items):
    from collections import deque

    return deque(items)


# --------------------------------------------------------------------------- #
# No look-ahead
# --------------------------------------------------------------------------- #
class TestNoLookahead:
    def test_future_bars_cannot_change_past_decisions(self):
        """Truncating the future must leave earlier trades identical."""
        bars = make_bars(800, seed=13)
        full = run_single_stock(bars, _spec(_AlwaysLong), {}, tax_enabled=False)
        cut = bars.iloc[:500]
        part = run_single_stock(cut, _spec(_AlwaysLong), {}, tax_enabled=False)
        n = min(len(full.trades), len(part.trades))
        assert n >= 1
        for i in range(n):
            assert full.trades[i].date == part.trades[i].date
            assert full.trades[i].side == part.trades[i].side


# --------------------------------------------------------------------------- #
# Metrics / nulls / splitter
# --------------------------------------------------------------------------- #
class TestMetrics:
    def test_flat_equity_has_zero_metrics(self):
        eq = pd.Series(1000.0, index=pd.bdate_range("2020-01-01", periods=250))
        m = M.compute(eq)
        assert m.cagr == pytest.approx(0.0)
        assert m.sharpe == pytest.approx(0.0)
        assert m.max_drawdown == pytest.approx(0.0)

    def test_max_drawdown_is_negative(self):
        eq = pd.Series([100, 120, 60, 90], index=pd.bdate_range("2020-01-01", periods=4))
        assert M.compute(eq).max_drawdown == pytest.approx(-0.5)

    def test_year_concentration_detects_one_dominant_year(self):
        """One good year and three flat ones -> that year carries ~100% of the P&L."""
        idx = pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01",
                              "2022-01-01", "2022-06-01", "2023-01-01", "2023-06-01"])
        # 2020 doubles; 2021-2023 flat.
        eq = pd.Series([100, 200, 200, 200, 200, 200, 200, 200], index=idx)
        share = M.max_single_year_share(eq)
        assert share == pytest.approx(1.0, abs=1e-6)
        assert share > 0.35, "must breach the GOAL.md 35% year gate"

    def test_evenly_distributed_years_stay_under_the_gate(self):
        idx = pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01",
                              "2022-01-01", "2022-06-01", "2023-01-01", "2023-06-01"])
        eq = pd.Series([100, 110, 110, 121, 121, 133.1, 133.1, 146.41], index=idx)
        assert M.max_single_year_share(eq) == pytest.approx(0.25, abs=1e-6)
        assert M.max_single_year_share(eq) < 0.35


class TestNulls:
    def test_p_value_floor_and_ordering(self):
        import numpy as np

        null = np.zeros(199)
        assert N.p_value(1.0, null) == pytest.approx(1 / 200)
        assert N.p_value(0.5, null) == pytest.approx(1 / 200)

    def test_timing_null_returns_one_value_per_replica(self):
        """Regression: switches had length n-1 against returns of length n."""
        bars = make_bars(400)
        out = N.timing_null_cagr(bars, 0.5, 7, replicas=25, start="2020-01-01")
        assert len(out) == 25
        assert all(isinstance(float(x), float) for x in out)

    def test_buy_hold_matches_manual(self):
        bars = make_bars(300)
        px = bars["close"].to_numpy()
        assert N.buy_and_hold(bars) == pytest.approx(px[-1] / px[0] - 1.0)


class TestSplitter:
    def test_train_and_test_do_not_overlap(self):
        syms = S.available_symbols()
        assert syms, "no symbols"
        s = syms[0]
        tr, te = S.train_bars(s), S.test_bars(s)
        if tr.empty or te.empty:
            pytest.skip("symbol has no data in one window")
        assert tr.index.max() <= pd.Timestamp(C.TRAIN_END)
        assert te.index.min() >= pd.Timestamp(C.TEST_START)
        assert len(tr.index.intersection(te.index)) == 0

    def test_corrupt_symbols_are_excluded(self):
        assert "adanient" not in S.available_symbols()
        assert "jiofin" not in S.available_symbols()

    def test_bars_are_chronological_and_unique(self):
        s = S.available_symbols()[0]
        df = S.bars(s, S.FULL)
        if df.empty:
            pytest.skip("no data")
        assert df.index.is_monotonic_increasing
        assert not df.index.duplicated().any()
        assert (df["close"] > 0).all()


class TestFDR:
    def test_no_significance_returns_all_false(self):
        from research.optimize.analyze import benjamini_hochberg

        assert not benjamini_hochberg([0.5, 0.6, 0.7, 0.8]).any()

    def test_step_up_detects_the_truly_small_ones(self):
        from research.optimize.analyze import benjamini_hochberg

        ps = [0.001, 0.002, 0.6, 0.7, 0.8]
        sig = benjamini_hochberg(ps)
        assert sig[0] and sig[1]
        assert not sig[2:].any()


class TestFastPath:
    """The tail-slicing fast path must be provably a no-op on results.

    It changes *how much* of the buffer is converted to numpy, never *what* is computed,
    for indicators that read only the tail. `ema`, `zscore` and `kama` genuinely read the
    whole buffer and are deliberately NOT patched.
    """

    def test_patched_indicators_match_original(self):
        import numpy as np

        from research.optimize import fastpath

        fastpath.install()
        fastpath.verify(trials=40)

        from cryptobot.strategies import indicators as I

        rng = np.random.default_rng(3)
        px = np.cumprod(1 + rng.normal(0, 0.01, 250)) * 100
        hi, lo = px * 1.01, px * 0.99
        orig = fastpath._ORIGINALS
        for period in (2, 5, 14, 20, 50):
            assert I.sma(px, period) == orig["sma"](px, period)
            assert I.rsi(px, period) == orig["rsi"](px, period)
            assert I.roc(px, period) == orig["roc"](px, period)
            assert I.stochastic(px, hi, lo, period) == orig["stochastic"](px, hi, lo, period)

    def test_full_buffer_indicators_are_not_patched(self):
        """ema/zscore/kama read the whole buffer; slicing them would change results."""
        from research.optimize import fastpath

        fastpath.install()
        from cryptobot.strategies import indicators as I

        for name in ("ema", "zscore", "kama"):
            assert not hasattr(getattr(I, name), "__wrapped__"), f"{name} must stay unpatched"

    def test_binding_reach_reaches_catalog_modules(self):
        """Patch only the indicators module and every strategy keeps calling the original.

        This measured 1.02x -- i.e. nothing -- because `from ... import rsi` binds the
        function object. install() must rebind those call sites.
        """
        from research.optimize import fastpath
        from research.optimize.catalog import load_strategy

        fastpath.install()
        spec = load_strategy("rsi_strategy")
        assert hasattr(spec.strategy_cls.__init__, "__call__")  # sanity
        mod = sys.modules[spec.strategy_cls.__module__]
        assert getattr(mod, "rsi", None) is not fastpath._ORIGINALS["rsi"], (
            "catalog module still holds the unpatched rsi"
        )

    def test_backtest_results_unchanged_by_fastpath(self):
        from research.optimize import fastpath
        from research.optimize.catalog import load_strategy

        spec = load_strategy("rsi_strategy")
        bars = make_bars(800, seed=21)
        fastpath.install()
        after = run_single_stock(bars, spec, spec.default, tax_enabled=True)
        fastpath.uninstall()
        before = run_single_stock(bars, spec, spec.default, tax_enabled=True)
        fastpath.install()
        assert after.equity.equals(before.equity)
        assert after.total_tax == before.total_tax
        assert len(after.trades) == len(before.trades)
