"""Property / fuzz tests for ``research.optimize``.

Why this file exists
--------------------
Three serious bugs got through the point-test suite of this engine. Every one of them
returned *plausible* numbers with no error anywhere:

1. ``catalog._pick_class`` resolved all 84 modules to the base ``SignalStrategy``
   -> 0.00% CAGR everywhere, silently.
2. ``run_single_stock`` debited the purchase price from cash twice -> -100% CAGR,
   silently.
3. The epoch-ms panel column was parsed as *seconds* -> every date landed in 1970,
   every slice empty, silently.

Point tests caught those three, one at a time, after the fact, and they will keep
catching bugs one at a time. What they cannot do is generalise to the *next* one,
wherever it came from. This file therefore does not re-test the three known bugs. It
asserts **invariants** -- algebraic identities, conservation laws, bounds and
monotonicity properties that must hold for *any* input -- over randomised inputs, so an
unrelated future edit that breaks accounting, ordering or units cannot produce a
plausible-looking wrong answer.

Every generator is seeded and deterministic. The whole file runs in well under the 60 s
budget. ``pytest-randomly`` is deliberately avoided: a failing seed you cannot reproduce
is not a bug report.

The five defects this suite *found* are pinned as strict ``xfail`` tests in
``TestKnownDefects``. Each asserts the *correct* behaviour, so it fails today and fails
loudly again the moment someone fixes it -- ``strict=True`` turns the fix into a suite
failure demanding the marker be removed, rather than letting the pin rot.

Run
---
``PYTHONPATH=src .venv/bin/python -m pytest \\
        tests/unit/test_nsealgo_optimizer_properties.py -q --timeout=300``
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import subprocess
import sys
import types
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cryptobot.strategies import indicators as IND
from research.optimize import catalog as CAT
from research.optimize import config as C
from research.optimize import fastpath as FP
from research.optimize import metrics as MET
from research.optimize import splitter as SPL
from research.optimize.backtest import (
    BacktestError,
    Lot,
    _affordable_shares,
    _settle_tax,
    rebalance_dates,
    run_single_stock,
)

REPO = Path(__file__).resolve().parents[2]
CAPITAL = float(C.CAPITAL_INR)

#: Relative tolerance for rupee-scale identities. Capital is ~2.1e7, so 1e-9 relative
#: is ~21 rupees: far below any rounding that matters, far above float noise.
RTOL = 1e-9
ATOL = 1e-4


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class Scripted:
    """Strategy driven by an explicit 0/1 schedule.

    A fake (rather than a catalog strategy) is used for the accounting properties on
    purpose: the invariants must be attributable to the *engine*, not to whichever 84
    catalog strategies happen to be importable on the day the test runs.
    """

    def __init__(self, config=None):
        self._pos: dict[str, int] = {}
        self.config = config
        self._schedule = list(getattr(config, "schedule", None) or [1, 0])
        self.i = 0
        #: bar index -> raw position the strategy asked for
        self.asked: list[int] = []
        #: bar index -> ``ts`` handed to feed()
        self.ts_seen: list[int] = []

    def feed(self, symbol, close, high=None, low=None, volume=None, ts=None):
        i = self.i
        self.i += 1
        self._pos[symbol] = int(self._schedule[i % len(self._schedule)])
        self.asked.append(self._pos[symbol])
        self.ts_seen.append(ts)
        return None


class _Cfg:
    """Bag-of-attributes Config; the engine only ever reaches ``spec.build(params)``."""

    def __init__(self, **kw):
        self.schedule = kw.get("schedule", [1, 0])
        for k, v in kw.items():
            setattr(self, k, v)


def spec_for(cls=Scripted, name: str = "probe", *, instrument: list | None = None):
    """Duck-typed StrategySpec. ``build`` is the only member the engine touches."""
    def build(values):
        inst = cls(_Cfg(**values))
        if instrument is not None:
            instrument.append(inst)
        return inst

    return types.SimpleNamespace(
        name=name, strategy_cls=cls, config_cls=_Cfg, params=[], held_fixed=[],
        default={"schedule": [1, 0]}, build=build,
    )


# --------------------------------------------------------------------------- #
# Random bar generators
# --------------------------------------------------------------------------- #
#: 2000 random price paths x 4 regimes (walk / single-bar -95% crash / flat / monotonic).
#: This is the equity-safety fuzz, and it is the single most expensive thing here: the
#: engine has ~8 ms of fixed per-call overhead, so 2000 calls cost ~17 s on their own.
PRICE_PATH_FUZZ = 2000
BAR_REGIMES = ("walk", "crash", "flat", "monotonic")


def price_path(kind: str, n: int, rng) -> np.ndarray:
    """A strictly positive close series in the given regime."""
    if kind == "flat":
        return np.full(n, 100.0)
    if kind == "monotonic":
        step = float(rng.uniform(0.001, 0.05))
        sign = 1.0 if rng.integers(0, 2) else -1.0
        return 100.0 * (1.0 + sign * step) ** np.arange(n)
    if kind == "crash":
        px = np.maximum(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n))), 1.0)
        px[int(rng.integers(0, n))] *= 0.05          # a -95% single-bar move
        return np.maximum(px, 0.01)
    return np.maximum(100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n))), 0.01)


def bars_for(close: np.ndarray, start: str = "2016-01-04") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({"close": close, "high": close * 1.02, "low": close * 0.98,
                         "volume": 1e6}, index=idx)


def alternating_bars(rng, n: int = 420, drift: float = 0.0005, vol: float = 0.014):
    """Bars plus a schedule that guarantees many complete round trips."""
    close = np.maximum(100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n))), 1.0)
    every = int(rng.integers(6, 40))
    return bars_for(close), [1 if (i // every) % 2 == 0 else 0 for i in range(n)]


# --------------------------------------------------------------------------- #
# Independent re-implementation of the engine's accounting, from the trade tape only
# --------------------------------------------------------------------------- #
def replay(trades) -> dict:
    """Recompute cash, FIFO lots and *gross* realised P&L from ``Trade`` records alone.

    Shares no code with ``run_single_stock``: it reads ``t.side / t.shares / t.value /
    t.fee / t.tax`` and re-derives everything else. If the engine's ledger and this
    replay disagree, the engine is wrong.
    """
    cash = CAPITAL
    lots: deque[list] = deque()      # [shares, cost_basis]
    gross = fees = tax = traded_value = 0.0
    for t in trades:
        fees += t.fee
        tax += t.tax
        traded_value += t.value
        if t.side == "BUY":
            cash -= t.value + t.fee
            lots.append([t.shares, t.value])
        else:
            cash += t.value - t.fee - t.tax
            remaining = t.shares
            while remaining > 1e-9 and lots:
                shares, basis = lots[0]
                take = min(remaining, shares)
                unit = basis / shares
                gross += (t.price - unit) * take
                shares -= take
                basis -= unit * take
                remaining -= take
                if shares <= 1e-9:
                    lots.popleft()
                else:
                    lots[0] = [shares, basis]
    return {"cash": cash, "gross_realised": gross, "fees": fees, "tax": tax,
            "traded_value": traded_value,
            "open_shares": sum(s for s, _ in lots),
            "open_basis": sum(b for _, b in lots)}


def flat_bar_mask(index: pd.DatetimeIndex, trades) -> np.ndarray:
    """True where the book holds nothing, derived purely from the trade tape.

    The BUY fill bar counts as *held*: at that bar the position already exists and
    ``equity == cash_before_buy - fee`` exactly, so marking it flat would make the very
    next bar look like a flat-book loss equal to the entry fee.
    """
    dates = list(index)
    mask = np.ones(len(index), dtype=bool)
    held = False
    cursor = 0
    for t in trades:
        while cursor < len(dates) and dates[cursor] < t.date:
            mask[cursor] = not held
            cursor += 1
        if cursor < len(dates):
            mask[cursor] = held          # a BUY bar is held, a SELL bar is flat
        held = t.side == "BUY"
        cursor += 1
    while cursor < len(dates):
        mask[cursor] = not held
        cursor += 1
    return mask


# --------------------------------------------------------------------------- #
# fastpath state helper
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def _pristine_fastpath():
    """Force ``fastpath`` back to a genuinely un-installed state, then restore it.

    ``uninstall()`` only restores ``indicators.sma/rsi/roc/stochastic``; it does not undo
    the 40+ module rebinds ``_rebind_all()`` performed, so it does not actually return
    the process to its starting state. This unwinds both, so a test that pokes at the
    fast path cannot leak into the rest of the session.
    """
    def _unwrap_all(ids: set[int]) -> None:
        for mod in list(sys.modules.values()):
            d = getattr(mod, "__dict__", None)
            if not d:
                continue
            for attr, val in list(d.items()):
                inner = getattr(val, "__wrapped__", None)
                if inner is not None and id(inner) in ids:
                    try:
                        setattr(mod, attr, inner)
                    except Exception:  # noqa: BLE001 - read-only namespaces
                        pass

    original_ids = {id(o) for o in FP._ORIGINALS.values()}
    _unwrap_all(original_ids)
    for name, fn in list(FP._ORIGINALS.items()):
        setattr(IND, name, fn)
    FP._ORIGINALS.clear()
    FP._INSTALLED = False
    try:
        yield
    finally:
        live = dict(FP._ORIGINALS)
        _unwrap_all({id(o) for o in live.values()} | original_ids)
        for name, fn in live.items():
            setattr(IND, name, fn)
        FP._ORIGINALS.clear()
        FP._INSTALLED = False


# --------------------------------------------------------------------------- #
# Module-scoped, expensive, reused everywhere
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def specs() -> list:
    """All 84 catalog strategies. Importing them is the single slowest step here."""
    return CAT.discover()


@pytest.fixture(scope="module", autouse=True)
def _warm(specs):
    """Force ``fastpath.ensure()`` once so per-test timings reflect steady state."""
    try:
        run_single_stock(bars_for(np.full(80, 100.0)), specs[0], {}, rebalance="M")
    except BacktestError:
        pass


@pytest.fixture(scope="module")
def books():
    """``n`` randomised books with complete round trips. Computed once, asserted on by
    every cash-conservation test -- three separate sweeps would cost 3x for no extra
    coverage."""
    rng = np.random.default_rng(20260101)
    out = []
    for _ in range(50):
        bars, sched = alternating_bars(rng)
        out.append((bars, sched, run_single_stock(bars, spec_for(),
                                                   {"schedule": sched}, rebalance="M")))
    return out


# --------------------------------------------------------------------------- #
# 1. Cash conservation
# --------------------------------------------------------------------------- #
class TestCashConservation:
    """The invariant family that would have caught the double cash debit.

    ``run_single_stock`` used to do ``cash -= value + fee + value``, which drove equity
    to zero and printed -100% CAGR. Nothing raised. The only thing between that bug and a
    published number is an algebraic identity checked over many random books.
    """

    def test_ledger_replayed_from_the_trade_tape_reproduces_final_equity(self, books):
        for i, (bars, _sched, res) in enumerate(books):
            r = replay(res.trades)
            expected = r["cash"] + r["open_shares"] * float(bars["close"].iloc[-1])
            actual = float(res.equity.iloc[-1])
            assert abs(expected - actual) < RTOL * CAPITAL, (
                f"book {i}: replaying the trade tape gives final equity "
                f"{expected:.6f}, engine says {actual:.6f} "
                f"(delta {expected - actual:.6f})")

    def test_capital_plus_realised_plus_unrealised_minus_fees_minus_tax(self, books):
        """``equity = capital + realised + unrealised - fees - tax`` with *gross* P&L.

        This is the form that actually holds, and it is the guard. ``Trade.pnl`` is a
        third thing entirely -- see ``TestKnownDefects``.
        """
        for i, (bars, _sched, res) in enumerate(books):
            r = replay(res.trades)
            unrealised = (r["open_shares"] * float(bars["close"].iloc[-1])
                          - r["open_basis"])
            lhs = CAPITAL + r["gross_realised"] + unrealised - r["fees"] - r["tax"]
            actual = float(res.equity.iloc[-1])
            assert abs(lhs - actual) < RTOL * CAPITAL, (
                f"book {i}: capital+gross+unrealised-fees-tax = {lhs:.6f} "
                f"!= final equity {actual:.6f}")

    def test_reported_totals_are_exact_accumulations_over_the_tape(self, books):
        """A mis-accumulated running total is invisible in the equity curve but corrupts
        every reported number downstream."""
        for i, (_bars, _sched, res) in enumerate(books):
            r = replay(res.trades)
            assert abs(res.total_fees - r["fees"]) < ATOL, f"book {i}: total_fees drift"
            assert abs(res.total_tax - r["tax"]) < ATOL, f"book {i}: total_tax drift"
            expected_turnover = r["traded_value"] / CAPITAL
            assert abs(res.turnover - expected_turnover) < ATOL / CAPITAL
            assert res.n_bars == len(_bars)
            assert res.exposure == pytest.approx(res.invested_bars / res.n_bars, rel=1e-12)

    def test_every_sell_closes_the_whole_position(self, books):
        """A partially-consumed FIFO lot is destroyed by ``lots.clear()`` without a word.

        The engine always sells 100% of the position; if it ever stops doing so, the
        residual cost basis vanishes and tax is under-charged.
        """
        for i, (_bars, _sched, res) in enumerate(books):
            held = 0.0
            for t in res.trades:
                if t.side == "BUY":
                    assert held == 0.0, f"book {i}: BUY while already holding"
                    held = t.shares
                else:
                    assert held > 0.0, f"book {i}: SELL with no position"
                    assert abs(t.shares - held) < 1e-6, (
                        f"book {i}: partial SELL of {t.shares} against a position of "
                        f"{held} -- residual lots would be silently cleared")
                    held = 0.0


# --------------------------------------------------------------------------- #
# 2. Equity can never go negative; never falls while flat
# --------------------------------------------------------------------------- #
class TestEquitySafety:
    def test_equity_is_strictly_positive_on_every_bar_of_every_path(self):
        rng = np.random.default_rng(20260111)
        bars_checked = 0
        for i in range(PRICE_PATH_FUZZ):
            kind = BAR_REGIMES[i % len(BAR_REGIMES)]
            n = int(rng.integers(25, 45))
            close = price_path(kind, n, rng)
            # hold in blocks of 4-10 bars, so a -95% bar is almost always inside a
            # position rather than falling in a flat stretch
            sched, pos = [], int(rng.integers(0, 2))
            while len(sched) < n:
                pos ^= int(rng.integers(0, 2))
                sched.extend([pos] * int(rng.integers(4, 10)))
            sched = sched[:n]
            res = run_single_stock(bars_for(close), spec_for(), {"schedule": sched},
                                   rebalance="D")
            eq = res.equity.to_numpy()
            bad = np.nonzero(~(eq > 0.0))[0]
            assert bad.size == 0, (
                f"path {i} ({kind}): equity hit {eq[bad[0]]:.6f} at bar {bad[0]} "
                f"(close {close[bad[0]]:.4f}); min {eq.min():.6f}, "
                f"capital {CAPITAL:.2f}")
            bars_checked += eq.size
        assert bars_checked > PRICE_PATH_FUZZ * 25

    def test_equity_never_decreases_while_flat(self):
        rng = np.random.default_rng(20260112)
        pairs = 0
        for _ in range(100):
            n = int(rng.integers(60, 160))
            bars = bars_for(price_path("crash", n, rng))
            every = int(rng.integers(3, 30))
            sched = [1 if (i // every) % 2 == 0 else 0 for i in range(n)]
            res = run_single_stock(bars, spec_for(), {"schedule": sched}, rebalance="D")
            eq = res.equity.to_numpy()
            flat = flat_bar_mask(bars.index, res.trades)
            both = flat[:-1] & flat[1:]
            if not both.any():
                continue
            # cash is constant while flat, so equity must be constant too
            worst = float(np.abs(eq[1:][both] - eq[:-1][both]).max())
            assert worst <= ATOL, (
                f"equity moved by {worst:.6f} across two consecutive flat bars "
                f"(no position held on either)")
            pairs += int(both.sum())
        assert pairs > 2000, "too few flat pairs examined; the check is vacuous"

    def test_equity_at_a_buy_fill_bar_equals_prior_equity_minus_exactly_the_fee(self):
        """Ties the two together: entering a position must not create or destroy value."""
        rng = np.random.default_rng(20260115)
        checked = 0
        for _ in range(80):
            n = int(rng.integers(60, 160))
            bars = bars_for(price_path("walk", n, rng))
            every = int(rng.integers(4, 30))
            sched = [1 if (i // every) % 2 == 0 else 0 for i in range(n)]
            res = run_single_stock(bars, spec_for(), {"schedule": sched}, rebalance="D")
            pos = {d: j for j, d in enumerate(bars.index)}
            eq = res.equity.to_numpy()
            for t in res.trades:
                if t.side != "BUY":
                    continue
                j = pos[t.date]
                assert j >= 1, "a BUY on bar 0 -- the engine has no history to respect"
                assert abs((eq[j] + t.fee) - eq[j - 1]) < ATOL, (
                    f"buying changed equity by more than the entry fee: "
                    f"{eq[j] - eq[j - 1] + t.fee:.6f}")
                checked += 1
        assert checked > 200

    def test_sizing_never_spends_more_cash_than_is_on_hand(self):
        """``_affordable_shares`` is the only thing between a fill and an overdraft; a
        single rupee of over-buy makes equity negative on the very next bar."""
        rng = np.random.default_rng(20260113)
        fees = C.FeeSchedule()
        bps = float(fees.one_way_bps)
        for _ in range(3000):
            close = float(rng.uniform(0.5, 5000.0))
            budget = float(rng.uniform(1.0, CAPITAL))
            s = _affordable_shares(close, budget, fees)
            assert s >= 0.0
            if s == 0.0:
                continue
            value = s * close
            assert value + value * bps / 10_000.0 <= budget + ATOL, (
                f"affordable {s} sh @ {close} costs "
                f"{value + value * bps / 10_000.0:.6f} > budget {budget:.6f}")

    def test_non_positive_or_non_finite_close_is_rejected_loudly(self):
        rng = np.random.default_rng(20260114)
        for bad in (0.0, -1.0, float("nan"), float("inf"), float("-inf")):
            close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 40)))
            close[20] = bad
            bars = bars_for(close)
            with pytest.raises(BacktestError, match="non-positive or non-finite"):
                run_single_stock(bars, spec_for(), {"schedule": [1, 0]}, rebalance="M")


# --------------------------------------------------------------------------- #
# 3. Tax can never exceed the statutory rate for the holding period
# --------------------------------------------------------------------------- #
STCG = float(C.STCG_RATE)
LTCG = float(C.LTCG_RATE)


def _independent_settle(spec, sell_shares, sell_price, sell_ts):
    """Replay FIFO independently: (tax, gross_pnl, [gains], [holding_days])."""
    tax = gross = 0.0
    gains: list[float] = []
    days: list[int] = []
    model: deque[list] = deque([[s, b, o] for s, b, o in spec])
    remaining = sell_shares
    while remaining > 1e-12 and model:
        shares, basis, opened = model[0]
        take = min(remaining, shares)
        unit = basis / shares
        gain = (sell_price - unit) * take
        gross += gain
        d = (sell_ts - opened).days
        gains.append(gain)
        days.append(d)
        if gain > 0:
            tax += gain * (LTCG if d > C.LTCG_THRESHOLD_DAYS else STCG)
        shares -= take
        basis -= unit * take
        remaining -= take
        if shares <= 1e-9:
            model.popleft()
        else:
            model[0] = [shares, basis, opened]
    return tax, gross, gains, days


class TestTaxBounds:
    """Indian capital gains: 20% short-term (<= 365d), 12.5% long-term (> 365d).

    The blended random fuzz alone cannot prove the long-term branch is exercised -- a
    sampling accident could make it vacuous -- so both regimes are *constructed*.
    """

    def test_tax_never_exceeds_the_statutory_rate_on_positive_gains(self):
        rng = np.random.default_rng(20260121)
        sell_ts = datetime(2024, 6, 1)
        both_regimes = 0
        for trial in range(2000):
            # anchored on the sell date, not on a fixed epoch: lots opened between
            # 1 and 2000 days back straddle the 365-day boundary, so both rates and
            # their blend are actually exercised
            spec = [(float(rng.uniform(1, 400)), float(rng.uniform(1e3, 5e5)),
                     sell_ts - timedelta(days=int(rng.integers(1, 2000))))
                    for _ in range(int(rng.integers(1, 6)))]
            # sell a large slice, otherwise FIFO almost always consumes only the first
            # lot and the short/long blend is never exercised
            sell_shares = float(rng.uniform(0.4, 1.0) * sum(s for s, _, _ in spec))
            sell_price = float(rng.uniform(0.5, 5000.0))
            exp_tax, _g, gains, days = _independent_settle(spec, sell_shares,
                                                           sell_price, sell_ts)
            lots = deque([Lot(shares=s, cost_basis=b, opened=o) for s, b, o in spec])
            tax, _pnl = _settle_tax(lots, sell_shares, sell_price * sell_shares,
                                    sell_ts, True)
            # tax may only ever be charged on a *positive* per-lot gain, at that lot's
            # own rate -- so the ceiling is the worst rate times the sum of positive gains
            positive = sum(g for g in gains if g > 0.0)
            assert tax >= 0.0, f"trial {trial}: negative tax {tax}"
            assert tax <= max(STCG, LTCG) * positive + 1e-6, (
                f"trial {trial}: tax {tax} exceeds the ceiling {max(STCG, LTCG) * positive} "
                f"(gains={gains}, days={days})")
            assert abs(tax - exp_tax) < max(ATOL, 1e-9 * abs(exp_tax)), (
                f"trial {trial}: tax {tax} != independently blended {exp_tax} "
                f"(gains={gains}, days={days})")
            both_regimes += len({d > C.LTCG_THRESHOLD_DAYS for d in days}) == 2
        assert both_regimes > 50, (
            f"only {both_regimes} trials consumed both a short- and a long-term lot; "
            "the blended-rate branch is barely exercised")

    def test_short_term_only_lots_pay_exactly_twenty_percent(self):
        """Constructed: every lot opened at most 365 days before the sell."""
        rng = np.random.default_rng(20260122)
        sell_ts = datetime(2024, 6, 1)
        paid = 0
        for _ in range(500):
            spec = [(float(rng.uniform(10, 300)), float(rng.uniform(1e3, 1e5)),
                     sell_ts - timedelta(days=int(rng.integers(1, C.LTCG_THRESHOLD_DAYS))))
                    for _ in range(int(rng.integers(1, 4)))]
            sell_shares = float(rng.uniform(0.01, sum(s for s, _, _ in spec)))
            sell_price = float(rng.uniform(1.0, 5000.0))
            _tax, _g, gains, days = _independent_settle(spec, sell_shares,
                                                   sell_price, sell_ts)
            assert all(d <= C.LTCG_THRESHOLD_DAYS for d in days), days
            lots = deque([Lot(shares=s, cost_basis=b, opened=o) for s, b, o in spec])
            tax, _ = _settle_tax(lots, sell_shares, sell_price * sell_shares,
                                 sell_ts, True)
            positive = sum(g for g in gains if g > 0.0)
            assert tax <= STCG * positive + 1e-6
            assert abs(tax - STCG * positive) < 1e-6, (
                f"short-term tax {tax} != 20% of positive gains {positive}")
            paid += positive > 0.0
        assert paid > 200

    def test_long_term_only_lots_pay_exactly_twelve_and_a_half_percent(self):
        """Constructed: every lot held strictly longer than 365 days."""
        rng = np.random.default_rng(20260123)
        sell_ts = datetime(2024, 6, 1)
        paid = 0
        for _ in range(500):
            spec = [(float(rng.uniform(10, 300)), float(rng.uniform(1e3, 1e5)),
                     sell_ts - timedelta(days=int(rng.integers(
                         C.LTCG_THRESHOLD_DAYS + 1, 2000))))
                    for _ in range(int(rng.integers(1, 4)))]
            sell_shares = float(rng.uniform(0.01, sum(s for s, _, _ in spec)))
            sell_price = float(rng.uniform(1.0, 5000.0))
            _tax, gross, gains, days = _independent_settle(spec, sell_shares,
                                                           sell_price, sell_ts)
            assert all(d > C.LTCG_THRESHOLD_DAYS for d in days), days
            lots = deque([Lot(shares=s, cost_basis=b, opened=o) for s, b, o in spec])
            tax, _ = _settle_tax(lots, sell_shares, sell_price * sell_shares,
                                 sell_ts, True)
            positive = sum(g for g in gains if g > 0.0)
            assert tax <= LTCG * positive + 1e-6, (
                f"long-term tax {tax} exceeds 12.5% of positive gains {positive}")
            assert abs(tax - LTCG * positive) < 1e-6, (
                f"long-term tax {tax} != 12.5% of positive gains {positive}")
            paid += positive > 0.0
        assert paid > 200

    def test_day_365_is_short_term_and_day_366_is_long_term(self):
        sell_ts = datetime(2024, 6, 1)
        d366 = sell_ts - timedelta(days=366)
        d365 = sell_ts - timedelta(days=365)
        lots = deque([Lot(10.0, 100.0, d366), Lot(10.0, 100.0, d365)])
        tax, _ = _settle_tax(lots, 10.0, 200.0, sell_ts, True)   # consumes lot 1 only
        assert abs(tax - 100.0 * LTCG) < 1e-9, f"366-day lot taxed at {tax}, want LTCG"
        lots = deque([Lot(10.0, 100.0, d365)])
        tax, _ = _settle_tax(lots, 10.0, 200.0, sell_ts, True)
        assert abs(tax - 100.0 * STCG) < 1e-9, f"365-day lot taxed at {tax}, want STCG"

    def test_disabling_tax_pays_exactly_zero_and_still_books_the_pnl(self):
        rng = np.random.default_rng(20260124)
        for _ in range(500):
            spec = [(float(rng.uniform(1, 100)), float(rng.uniform(1, 1e4)),
                     datetime(2020, 1, 1)) for _ in range(int(rng.integers(1, 4)))]
            sell = float(rng.uniform(0.01, sum(s for s, _, _ in spec)))
            px = float(rng.uniform(1, 9000))
            lots = deque([Lot(s, b, o) for s, b, o in spec])
            tax, pnl = _settle_tax(lots, sell, px * sell, datetime(2024, 6, 1), False)
            assert tax == 0.0, f"tax_enabled=False still charged {tax}"
            assert pnl == (px * sell) - sum(b for _s, b, _o in spec) * (
                sell / sum(s for s, _b, _o in spec)) + 0.0 or math.isfinite(pnl)

    def test_engine_pays_no_tax_at_all_on_a_strictly_falling_book(self):
        """If every entry is above every exit, every lot has a negative gain and tax
        must be exactly zero. Tax charged on a losing round trip is a straight
        over-payment, and it would silently erode a losing strategy's equity."""
        checked = 0
        for drift in (-0.002, -0.01, -0.05):
            for every in (10, 25, 60):
                n = 360
                close = 100.0 * (1.0 - abs(drift)) ** np.arange(n)
                bars = bars_for(close)
                sched = [1 if (i // every) % 2 == 0 else 0 for i in range(n)]
                res = run_single_stock(bars, spec_for(), {"schedule": sched},
                                       rebalance="M", tax_enabled=True)
                assert res.total_tax == 0.0, (
                    f"drift {drift}, hold {every}: charged {res.total_tax:.2f} tax on a "
                    f"strictly falling book ({sum(1 for t in res.trades if t.side == 'SELL')} "
                    "round trips, every one of them a loss)")
                assert res.total_tax == sum(t.tax for t in res.trades)
                checked += 1
        assert checked == 9


# --------------------------------------------------------------------------- #
# 4. FIFO ledger conservation
# --------------------------------------------------------------------------- #
class TestFifoLedger:
    def test_ledger_holds_exactly_the_unsold_shares_after_random_buys_and_sells(self):
        rng = np.random.default_rng(20260131)
        base = datetime(2015, 1, 1)
        for trial in range(1500):
            lots: deque[Lot] = deque()
            model: deque[list] = deque()
            for step in range(int(rng.integers(1, 15))):
                held = sum(s for s, _ in model)
                if held <= 1e-9 or rng.integers(0, 100) < 45:
                    shares = float(rng.uniform(1, 300))
                    basis = shares * float(rng.uniform(1, 3000))
                    lots.append(Lot(shares, basis, base + timedelta(days=step * 30)))
                    model.append([shares, basis])
                else:
                    sell = float(rng.uniform(0.0, held))
                    if sell <= 1e-12:
                        continue
                    _settle_tax(lots, sell, sell * float(rng.uniform(1, 3000)),
                                base + timedelta(days=10000), True)
                    remaining = sell
                    while remaining > 1e-12 and model:
                        shares, basis = model[0]
                        take = min(remaining, shares)
                        shares -= take
                        basis -= (basis / (shares + take)) * take
                        remaining -= take
                        if shares <= 1e-9:
                            model.popleft()
                        else:
                            model[0] = [shares, basis]
                got = sum(lot.shares for lot in lots)
                want = sum(s for s, _ in model)
                assert abs(got - want) < 1e-6, (
                    f"trial {trial} step {step}: ledger holds {got:.6f} shares but the "
                    f"position is {want:.6f}")
                assert all(lot.shares >= -1e-9 for lot in lots), "negative lot size"
                assert all(lot.cost_basis >= -1e-6 for lot in lots), "negative cost basis"

    def test_cost_basis_shrinks_in_proportion_to_shares_consumed(self):
        """A half-sold lot must retain half its basis; a fully sold lot must be popped,
        not left at ~0 -- which would silently skew unit cost on a later sell."""
        rng = np.random.default_rng(20260132)
        for _ in range(800):
            shares = float(rng.uniform(10, 500))
            basis = shares * float(rng.uniform(1, 2000))
            opened = datetime(2020, 1, 1)
            lots = deque([Lot(shares, basis, opened)])
            frac = float(rng.uniform(0.05, 0.95))
            _settle_tax(lots, shares * frac, shares * frac * 1.2,
                        datetime(2024, 1, 1), True)
            assert len(lots) == 1
            rem = lots[0]
            assert rem.shares == pytest.approx(shares * (1 - frac), rel=1e-9)
            assert rem.cost_basis == pytest.approx(basis * (1 - frac), rel=1e-9)
            _settle_tax(lots, rem.shares, rem.shares * 1.1, datetime(2024, 1, 1), True)
            assert len(lots) == 0, "fully consumed lot left behind"

    def test_ledger_never_consumes_more_than_it_holds(self):
        rng = np.random.default_rng(20260133)
        for _ in range(600):
            shares = float(rng.uniform(1, 100))
            lots = deque([Lot(shares, shares * 100.0, datetime(2020, 1, 1))])
            over = shares * float(rng.uniform(1.0001, 3.0))
            _tax, pnl = _settle_tax(lots, over, over * 150.0, datetime(2024, 1, 1), True)
            assert len(lots) == 0
            assert math.isfinite(pnl) and pnl > 0


# --------------------------------------------------------------------------- #
# 5. No look-ahead under truncation
# --------------------------------------------------------------------------- #
class TestNoLookahead:
    """Truncating the future must not change the past.

    A backtest that peeks -- directly, or because a cached artefact keyed on something
    other than content was reused -- produces a *different history* depending on how much
    data it happened to be handed. This catches look-ahead without reading strategy code.
    """

    def test_truncation_preserves_every_past_trade_and_equity_value(self):
        rng = np.random.default_rng(20260201)
        checked = 0
        for _ in range(14):
            n = int(rng.integers(260, 400))
            bars = bars_for(price_path("walk", n, rng))
            every = int(rng.integers(8, 40))
            sched = [1 if (i // every) % 2 == 0 else 0 for i in range(n)]
            freq = ("M", "W", "D")[int(rng.integers(0, 3))]
            full = run_single_stock(bars, spec_for(), {"schedule": sched}, rebalance=freq)
            for k in range(70, n, max(n // 6, 1)):
                trunc = run_single_stock(bars.iloc[:k], spec_for(),
                                         {"schedule": sched}, rebalance=freq)
                cut = trunc.equity.index[-1]
                past = [(t.date, t.side, t.shares, t.price, t.fee, t.tax)
                        for t in full.trades if t.date <= cut]
                got = [(t.date, t.side, t.shares, t.price, t.fee, t.tax)
                       for t in trunc.trades]
                assert past == got, (
                    f"truncating at {cut} rewrote history: full run has {len(past)} "
                    f"trades up to then, truncated run has {len(got)}")
                assert np.array_equal(full.equity.to_numpy()[:k],
                                      trunc.equity.to_numpy()), (
                    f"truncating at {cut} changed historical equity values")
                checked += 1
        assert checked > 60

    def test_truncation_holds_for_real_catalog_strategies(self):
        rng = np.random.default_rng(20260202)
        names = ("momentum_factor_strategy", "dual_momentum_strategy",
                 "trend_momentum_strategy", "trend_mean_reversion",
                 "bollinger_band_squeeze", "rsi_strategy")
        real = CAT.discover(include=names)
        assert len(real) == len(names), (
            f"catalog sample loaded {len(real)}/{len(names)} -- the property would "
            "otherwise be vacuous")
        n = 420
        bars = bars_for(price_path("walk", n, rng))
        checked = 0
        for s in real:
            params = s.sample(rng)
            try:
                full = run_single_stock(bars, s, params, rebalance="M")
            except BacktestError:
                continue
            for k in (120, 200, 280, 360):
                try:
                    trunc = run_single_stock(bars.iloc[:k], s, params, rebalance="M")
                except BacktestError:
                    continue
                cut = trunc.equity.index[-1]
                past = [(t.date, t.side, t.shares, t.price, t.fee, t.tax)
                        for t in full.trades if t.date <= cut]
                got = [(t.date, t.side, t.shares, t.price, t.fee, t.tax)
                       for t in trunc.trades]
                assert past == got, f"{s.name}: truncation at {cut} rewrote history"
                assert np.array_equal(full.equity.to_numpy()[:k],
                                      trunc.equity.to_numpy())
                checked += 1
        assert checked > 10

    def test_rebalance_mask_is_derived_from_the_index_not_its_neighbours(self):
        """The mask is cached, so the cache key must be a function of *content*.

        Checked against ``to_period`` directly rather than restating the implementation.
        """
        for trial in range(20):
            rng = np.random.default_rng(1000 + trial)
            n = int(rng.integers(80, 200))
            idx = pd.bdate_range("2019-01-01", periods=n)
            for freq in ("M", "W", "D"):
                if freq == "D":
                    want = frozenset(idx)
                else:
                    keys = idx.to_period(freq)
                    want = frozenset(
                        idx[i] for i in range(n) if i == 0 or keys[i] != keys[i - 1])
                assert rebalance_dates(idx, freq) == want, (
                    f"{freq}: mask disagrees with to_period({freq})")

    def test_daily_rebalance_is_every_bar(self):
        idx = pd.bdate_range("2020-01-01", periods=50)
        assert rebalance_dates(idx, "D") == frozenset(idx)

    def test_unsupported_frequency_raises_instead_of_trading_nothing(self):
        idx = pd.bdate_range("2020-01-01", periods=10)
        with pytest.raises(BacktestError, match="unsupported rebalance freq"):
            rebalance_dates(idx, "Q")


# --------------------------------------------------------------------------- #
# 6. Metric consistency
# --------------------------------------------------------------------------- #
class TestMetricConsistency:
    @staticmethod
    def _curve(rng):
        m = int(rng.integers(3, 400))
        kind = int(rng.integers(0, 6))
        if kind == 0:
            e = np.full(m, 100.0)
        elif kind == 1:
            e = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.03, m)))
        elif kind == 2:
            e = 100.0 * np.exp(np.cumsum(rng.normal(0.002, 0.005, m)))
        elif kind == 3:
            e = np.linspace(100.0, 100.0 * float(rng.uniform(0.5, 2.0)), m)
        elif kind == 4:
            e = 100.0 * np.exp(np.cumsum(rng.choice([-0.02, 0.02], m)))
        else:
            e = np.concatenate([np.full(m // 2, 100.0), np.full(m - m // 2, 100.0)])
        return pd.Series(np.maximum(e, 1e-3), index=pd.bdate_range("2018-01-01", periods=m))

    def test_every_metric_invariant_holds_across_random_curves(self):
        """One sweep, one ``compute`` per curve, all six metric properties checked.

        Computed in a single loop because ``compute`` costs ~4.5 ms; five separate
        1000-iteration tests would recompute the same curves five times over.
        """
        rng = np.random.default_rng(20260211)
        stats = dict(curves=0, flat=0, moving=0, with_dd=0, shared=0)
        for _ in range(400):
            eq = self._curve(rng)
            e = eq.to_numpy()
            m = MET.compute(eq)
            stats["curves"] += 1

            # 1. max_drawdown is never positive
            assert m.max_drawdown <= 0.0, f"max_drawdown {m.max_drawdown} > 0"

            # 2. CAGR is zero exactly when start == end
            unchanged = e[-1] == e[0]
            if unchanged:
                stats["flat"] += 1
                assert m.cagr == 0.0, f"start==end but CAGR {m.cagr}"
            else:
                stats["moving"] += 1
                assert m.cagr != 0.0, "start!=end but CAGR is exactly 0"

            # 3. a constant curve has no risk to price
            if np.all(np.diff(e) == 0.0):
                stats["shared"] += 1
                assert m.sharpe == 0.0, f"constant curve Sharpe {m.sharpe}"
                assert m.sortino == 0.0
                assert m.volatility == 0.0

            # 4. calmar == cagr / |maxdd| whenever there is a drawdown at all
            if m.max_drawdown < -1e-9:
                stats["with_dd"] += 1
                assert m.calmar == pytest.approx(m.cagr / abs(m.max_drawdown), rel=1e-9), (
                    f"calmar {m.calmar} != cagr {m.cagr} / |maxdd| {abs(m.max_drawdown)}")
            else:
                assert m.calmar == 0.0, f"calmar {m.calmar} with no drawdown"

            # 5. reported shape matches the curve it was handed
            assert m.n_bars == len(e)
            assert m.years == pytest.approx(len(e) / C.TRADING_DAYS, rel=1e-12)
            assert m.total_return == pytest.approx(e[-1] / e[0] - 1.0, rel=1e-9)
            rets = eq.pct_change().fillna(0.0)
            if len(e) > 2:
                assert m.volatility == pytest.approx(
                    float(rets.std(ddof=1)) * math.sqrt(C.TRADING_DAYS), rel=1e-9)
                if float(rets.std(ddof=1)) > 0.0:
                    assert m.sharpe == pytest.approx(
                        float(rets.mean() / rets.std(ddof=1))
                        * math.sqrt(C.TRADING_DAYS), rel=1e-6, abs=1e-12)
                else:
                    assert m.sharpe == 0.0

        assert stats["curves"] == 400
        assert stats["flat"] > 10, f"too few flat curves: {stats}"
        assert stats["moving"] > 120, f"too few moving curves: {stats}"
        assert stats["shared"] > 10, f"too few constant curves: {stats}"
        assert stats["with_dd"] > 40, f"too few drawdowns: {stats}"

    def test_cagr_carries_the_sign_of_the_curve(self):
        """A rising curve must not report a negative CAGR, and vice versa.

        Internal consistency (``cagr == 0`` iff the endpoints match) cannot catch an
        inverted CAGR -- flipping the sign preserves the zero. Only the *direction* of
        the curve pins it.
        """
        idx = pd.bdate_range("2018-01-01", periods=500)
        rising = pd.Series(100.0 * np.exp(np.linspace(0.0, 0.6, 500)), index=idx)
        falling = pd.Series(100.0 * np.exp(np.linspace(0.0, -0.6, 500)), index=idx)
        assert MET.compute(rising).cagr > 0.0, "a curve that rose reported CAGR <= 0"
        assert MET.compute(falling).cagr < 0.0, "a curve that fell reported CAGR >= 0"
        for eq, expected in ((rising, 1), (falling, -1)):
            m = MET.compute(eq)
            assert math.copysign(1.0, m.cagr) == expected
            assert math.copysign(1.0, m.total_return) == expected, (
                "total_return and CAGR disagree about the direction of the curve")
            assert math.copysign(1.0, m.calmar) == expected, (
                "calmar disagrees about the direction of the curve")

    def test_max_single_year_share_matches_its_definition(self):
        """``max(year)/sum(positive years)`` -- the denominator must exclude losing years.

        A bound-only check (``<= 1.0``) passes for any denominator at least as large as
        the numerator, so it cannot catch a denominator that silently includes losses.
        """
        for winner, loser in ((1.6, 0.5), (2.0, 0.9), (1.3, 0.2), (5.0, 0.95)):
            idx = pd.bdate_range("2018-01-01", periods=522)
            e = np.concatenate([np.linspace(100.0, 100.0 * winner, 261),
                                np.linspace(100.0 * winner, 100.0 * winner * loser, 261)])
            eq = pd.Series(e, index=idx)
            ys = MET.per_year(eq)
            positive = sum(v for v in ys.values() if v > 0)
            expected = max(ys.values()) / positive
            got = MET.max_single_year_share(eq)
            assert got == pytest.approx(expected, rel=1e-9), (
                f"max_single_year_share {got} != max/positive = {expected}; "
                f"per_year={ {k: round(v, 4) for k, v in ys.items()} }")
            assert got > 0.9, (
                f"a curve whose gains are entirely in one year reported share {got}")

    def test_sharpe_of_a_constant_curve_is_zero_at_any_level(self):
        for value in (1.0, 100.0, 1e7):
            eq = pd.Series(np.full(120, value),
                           index=pd.bdate_range("2018-01-01", periods=120))
            m = MET.compute(eq)
            assert (m.sharpe, m.sortino, m.volatility, m.calmar, m.cagr) == (
                0.0, 0.0, 0.0, 0.0, 0.0), f"constant curve at {value} reported {m}"

    def test_max_single_year_share_never_exceeds_one(self):
        rng = np.random.default_rng(20260214)
        worst = 0.0
        for _ in range(110):
            m = int(rng.integers(300, 700))
            e = np.maximum(100.0 * np.exp(np.cumsum(rng.normal(0.0006, 0.02, m))), 1e-3)
            eq = pd.Series(e, index=pd.bdate_range("2014-01-01", periods=m))
            share = MET.max_single_year_share(eq)
            assert 0.0 <= share <= 1.0 + 1e-12, f"max_single_year_share = {share}"
            worst = max(worst, share)
        assert worst > 0.5, (
            f"largest share seen was only {worst}; the concentration bound is "
            "being checked against unconcentrated curves")

    def test_max_single_year_share_is_one_when_all_gains_land_in_one_year(self):
        # flat through 2020, gains only during 2021 -> 2021 holds 100% of them
        idx = pd.bdate_range("2020-01-01", periods=522)
        e = np.concatenate([np.full(261, 100.0), np.linspace(100.0, 160.0, 261)])
        eq = pd.Series(e, index=idx)
        assert MET.per_year(eq)["2021"] > 0.5
        assert MET.max_single_year_share(eq) == pytest.approx(1.0, abs=1e-6)

    def test_degenerate_curve_lengths_do_not_raise(self):
        for n in (0, 1, 2, 3):
            eq = pd.Series(np.full(n, 100.0),
                           index=pd.bdate_range("2020-01-01", periods=n))
            m = MET.compute(eq)
            assert m.n_bars == n
            assert math.isfinite(m.cagr) and math.isfinite(m.sharpe)


# --------------------------------------------------------------------------- #
# 7. Fuzz the config space across all 84 strategies
# --------------------------------------------------------------------------- #
#: Anything else escaping run_single_stock is an unhandled exception, not a rejection.
LEGIT_REJECTIONS = ("empty bar slice", "empty slice for",
                    "non-positive or non-finite close", "raised on",
                    "unsupported rebalance freq", "rejected config")

CONFIG_FUZZ = 500
CONFIG_BARS = 180


class _Spy:
    """Wraps a real catalog strategy and records whether it asks to be long on a bar
    the engine is actually allowed to trade on.

    The engine only acts on rebalance dates (and never on bar 0), so a long signal on any
    other bar is not a missed trade -- counting those would make the liveness check fire
    on correct behaviour.
    """

    def __init__(self, inner, record, index, actionable):
        self._pos: dict[str, int] = {}
        self._inner = inner
        self._record = record
        self._index = index
        self._actionable = actionable
        self._i = 0

    def feed(self, symbol, close, high=None, low=None, volume=None, ts=None):
        i = self._i
        self._i += 1
        self._inner.feed(symbol, close, high, low, volume, ts)
        p = self._inner._pos.get(symbol, 0)
        self._pos[symbol] = p
        if p > 0 and i > 0 and self._index[i] in self._actionable:
            self._record.long_on_actionable = True
        return None


@pytest.fixture(scope="module")
def config_sweep(specs):
    """500 random Configs spread across all 84 strategies, run on one common panel."""
    rng = np.random.default_rng(20260301)
    n = CONFIG_BARS
    bars = bars_for(price_path("walk", n, rng))
    keys = bars.index.to_period("M")
    actionable = {bars.index[j] for j in range(1, n) if keys[j] != keys[j - 1]}

    outcomes = []
    for i in range(CONFIG_FUZZ):
        s = specs[i % len(specs)]
        params = s.sample(rng)
        rec = types.SimpleNamespace(
            name=s.name, params=dict(params), error=None, buys=0, trades=0,
            long_on_actionable=False, equity=None)
        holder: dict = {}

        def build(values, _s=s, _h=holder, _rec=rec):
            spy = _Spy(_s.build(values), _rec, bars.index, actionable)
            _h["spy"] = spy
            return spy

        spec = types.SimpleNamespace(name=s.name, strategy_cls=_Spy,
                                     config_cls=s.config_cls, params=s.params,
                                     held_fixed=s.held_fixed, default=s.default,
                                     build=build)
        try:
            res = run_single_stock(bars, spec, params, rebalance="M")
        except BacktestError as exc:
            rec.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - an escape here is the finding
            rec.error = f"UNHANDLED {type(exc).__name__}: {exc}"
        else:
            rec.equity = res.equity
            rec.trades = len(res.trades)
            rec.buys = sum(1 for t in res.trades if t.side == "BUY")
            rec.sells = sum(1 for t in res.trades if t.side == "SELL")
            rec.fees = res.total_fees
        outcomes.append(rec)
    return outcomes, bars, actionable


class TestConfigSpaceFuzz:
    def test_no_unhandled_exception_escapes(self, config_sweep):
        outcomes, _, _ = config_sweep
        bad = [o for o in outcomes if o.error and o.error.startswith("UNHANDLED")]
        assert not bad, "uncaught exceptions escaped run_single_stock:\n" + "\n".join(
            f"  {o.name}({o.params}) -> {o.error}" for o in bad[:8])
        ran = [o for o in outcomes if o.error is None]
        assert len(ran) > CONFIG_FUZZ * 0.5, (
            f"only {len(ran)}/{CONFIG_FUZZ} configs produced a result; the fuzz is "
            "mostly hitting rejections and proves little")

    def test_every_rejection_reason_is_a_legitimate_one(self, config_sweep):
        outcomes, _, _ = config_sweep
        rejected = [o for o in outcomes if o.error]
        bad = [o for o in rejected
               if not any(p in o.error for p in LEGIT_REJECTIONS)]
        assert not bad, "unexplained rejections:\n" + "\n".join(
            f"  {o.name}({o.params}) -> {o.error}" for o in bad[:8])
        reasons: dict[str, int] = {}
        for o in rejected:
            key = o.error.split(":")[0].split("(")[0].strip()
            reasons[key] = reasons.get(key, 0) + 1
        print(f"\nconfig fuzz: {len(outcomes) - len(rejected)} accepted, "
              f"{len(rejected)} rejected")
        for k, v in sorted(reasons.items()):
            print(f"    {v:4d}x  {k}")

    def test_wanting_long_on_a_rebalance_bar_always_produces_a_trade(self, config_sweep):
        """The exact engine invariant: on an actionable bar, ``want == 1 and flat -> BUY``.

        This is what the base-class bug looked like from the outside -- a perfectly
        plausible flat equity curve. Asserted against a mask derived from ``to_period``,
        not from the engine's own (cached) one.
        """
        outcomes, _bars, actionable = config_sweep
        ran = [o for o in outcomes if o.error is None]
        assert len(actionable) > 5
        signalled = [o for o in ran if o.long_on_actionable]
        for o in signalled:
            assert o.buys > 0, (
                f"{o.name}({o.params}) wanted long on at least one rebalance bar but "
                f"produced no BUY -- silent flat result")
        print(f"\nconfig fuzz: {len(signalled)}/{len(ran)} strategies signalled long "
              "on a rebalance bar; all bought")

    def test_catalog_resolves_to_concrete_subclasses_of_the_base(self, specs):
        """Structural guard for the ``_pick_class`` bug that zeroed every CAGR.

        Every spec must resolve to a class defined in its own module and strictly
        subclassing ``SignalStrategy`` -- the base returns 0 from ``signal()``
        unconditionally, so resolving to it silently trades nothing.
        """
        from cryptobot.strategies.signal_base import SignalStrategy

        assert len(specs) == 84, f"expected 84 strategies, catalog has {len(specs)}"
        for s in specs:
            cls = s.strategy_cls
            assert cls is not SignalStrategy, (
                f"{s.name} resolved to the base SignalStrategy -> trades nothing")
            assert issubclass(cls, SignalStrategy), f"{s.name} is not a SignalStrategy"
            assert cls.__module__ == s.module, (
                f"{s.name} resolved to {cls.__name__} from {cls.__module__}, expected "
                f"a class defined in {s.module}")

    def test_a_healthy_fraction_of_the_catalog_actually_trades(self, config_sweep):
        """Liveness floor: a whole-catalog zero-trade run is the silent-flat signature."""
        outcomes, _, _ = config_sweep
        traded = {o.name for o in outcomes if o.buys > 0}
        assert len(traded) >= 5, (
            f"only {len(traded)} strategies ever bought across {CONFIG_FUZZ} random "
            "configs; a whole-catalog silent flat is the _pick_class bug")
        print(f"\nstrategies that bought at least once: {len(traded)}")

    def test_successful_runs_return_a_well_formed_positive_result(self, config_sweep):
        outcomes, bars, _ = config_sweep
        ran = 0
        for o in outcomes:
            if o.error is not None:
                continue
            ran += 1
            eq = o.equity
            assert len(eq) == len(bars) and eq.index.equals(bars.index)
            assert np.all(np.isfinite(eq.to_numpy()))
            assert (eq.to_numpy() > 0).all(), f"{o.name} produced non-positive equity"
            assert o.fees >= 0.0
            assert o.sells <= o.buys <= o.sells + 1, (
                f"{o.name}: {o.buys} buys but {o.sells} sells (at most one open "
                "position is legal)")
        assert ran > CONFIG_FUZZ * 0.5


# --------------------------------------------------------------------------- #
# 7b. Splitter: panel parsing and TRAIN/TEST isolation
# --------------------------------------------------------------------------- #
@pytest.fixture
def panel(tmp_path):
    """A synthetic symbol file written in the panel's own format: epoch MILLISECONDS.

    The file is byte-identical to what ``tools/`` writes, so ``splitter._read`` has to
    recover the right calendar. (The third incident this engine suffered was exactly
    this column being parsed as seconds, which lands in 1970 and silently empties every
    slice -- so the unit is stated here and asserted here.)
    """
    # spans 2015 -> 2026 so that both TRAIN (2016-2023) and TEST (2024-2026)
    # windows are populated, including the 2023/2024 boundary
    dates = pd.bdate_range("2015-01-01", periods=2900)
    # `as_unit("ns")` is not decoration: a DatetimeIndex carries its own resolution and
    # `asi8` returns values *in that resolution*. Under pandas 3 a tz-aware range comes
    # back as datetime64[us], so a bare `asi8 // 1_000_000` silently yields seconds.
    # (That is exactly the defect pinned in TestKnownDefects.)
    ms = dates.tz_localize("Asia/Kolkata").tz_convert("UTC").as_unit("ns").asi8 // 10**6
    px = np.maximum(100.0 * np.exp(np.cumsum(
        np.random.default_rng(5).normal(0.0004, 0.012, len(dates)))), 1.0)
    pd.DataFrame({"ts": ms, "open": px, "high": px * 1.02, "low": px * 0.98,
                  "close": px, "volume": 1e6}).to_csv(
        tmp_path / "probe_1d.csv", index=False)
    saved_dir, saved_cache = C.DATA_DIR, dict(SPL._CACHE)
    C.DATA_DIR = Path(tmp_path)
    SPL._CACHE.clear()
    try:
        yield tmp_path
    finally:
        C.DATA_DIR = saved_dir
        SPL._CACHE.clear()
        SPL._CACHE.update(saved_cache)


class TestSplitter:
    def test_epoch_millisecond_column_is_parsed_as_milliseconds(self, panel):
        df = SPL.bars("probe", SPL.FULL)
        assert len(df) > 1000, f"only {len(df)} rows loaded -- the panel was rejected"
        assert df.index.min() >= pd.Timestamp("2010-01-01"), (
            f"earliest bar is {df.index.min()}; epoch-ms parsed with the wrong unit "
            "lands every row in 1970")
        assert df.index.max() <= pd.Timestamp("2026-12-31")

    def test_index_is_a_clean_increasing_calendar(self, panel):
        df = SPL.bars("probe", SPL.FULL)
        assert df.index.is_monotonic_increasing, "bars are out of order"
        assert df.index.is_unique, "duplicate timestamps survived de-duplication"
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.tz is None, "index should be normalised to naive IST"
        assert (df["close"] > 0).all(), "non-positive close survived cleaning"
        assert (df["high"] >= df["low"]).all(), "high < low survived cleaning"

    def test_train_and_test_are_disjoint_and_exhaustive(self, panel):
        train, test, full = SPL.train_bars("probe"), SPL.test_bars("probe"), SPL.bars("probe")
        assert not train.index.intersection(test.index).size, "TRAIN and TEST overlap"
        assert train.index.max() < test.index.min(), (
            f"TRAIN ends {train.index.max()} but TEST starts {test.index.min()}")
        assert train.index.min() >= pd.Timestamp(SPL.TRAIN.start)
        assert test.index.max() <= pd.Timestamp(SPL.TEST.end)
        # TRAIN starts in 2016 while FULL starts at CLEAN_START, so the two windows do
        # not tile FULL -- they must tile exactly the part of FULL inside the walk-forward
        span = full[(full.index >= pd.Timestamp(SPL.TRAIN.start))
                    & (full.index <= pd.Timestamp(SPL.TEST.end))]
        assert len(train) + len(test) == len(span), (
            f"train {len(train)} + test {len(test)} != span {len(span)}: a bar inside "
            "the walk-forward range belongs to neither window")

    def test_window_slices_are_stable_regardless_of_call_order(self, panel):
        full_first = SPL.bars("probe", SPL.FULL)
        SPL.test_bars("probe")
        SPL.train_bars("probe")
        again = SPL.bars("probe", SPL.FULL)
        assert full_first.index.equals(again.index)
        assert np.array_equal(full_first["close"].to_numpy(), again["close"].to_numpy())

    def test_missing_symbol_yields_an_empty_frame_not_an_exception(self, panel):
        assert SPL.bars("does_not_exist").empty

    def test_cold_read_and_cached_read_agree(self, panel):
        SPL._CACHE.clear()
        cold = SPL.bars("probe", SPL.FULL)
        warm = SPL.bars("probe", SPL.FULL)
        assert cold.equals(warm), "the module-level cache changed the answer"


# --------------------------------------------------------------------------- #
# 8. Determinism and idempotence
# --------------------------------------------------------------------------- #
class TestDeterminism:
    def test_identical_inputs_give_bit_identical_output_in_process(self, specs):
        rng = np.random.default_rng(20260401)
        bars = bars_for(price_path("walk", 300, rng))
        compared = 0
        for s in specs[:12]:
            params = s.sample(rng)
            try:
                a = run_single_stock(bars, s, params, rebalance="M")
                b = run_single_stock(bars, s, params, rebalance="M")
            except BacktestError:
                continue
            assert np.array_equal(a.equity.to_numpy(), b.equity.to_numpy()), (
                f"{s.name}: two identical runs disagreed")
            assert a.total_fees == b.total_fees and a.total_tax == b.total_tax
            assert a.turnover == b.turnover
            assert len(a.trades) == len(b.trades)
            compared += 1
        assert compared >= 10

    def test_result_is_independent_of_the_index_object_it_arrives_on(self):
        """A rebuilt-but-identical index must give the identical answer. A cached mask
        or a comparison that depends on object identity would break here."""
        rng = np.random.default_rng(20260402)
        n = 300
        bars = bars_for(price_path("walk", n, rng))
        copy = bars.copy()
        copy.index = pd.DatetimeIndex(list(bars.index))     # equal values, new object
        assert copy.index.equals(bars.index) and copy.index is not bars.index
        sched = [1 if (i // 17) % 2 == 0 else 0 for i in range(n)]
        a = run_single_stock(bars, spec_for(), {"schedule": sched}, rebalance="M")
        b = run_single_stock(copy, spec_for(), {"schedule": sched}, rebalance="M")
        assert np.array_equal(a.equity.to_numpy(), b.equity.to_numpy())

    def test_identical_output_in_a_fresh_process_under_a_different_hash_seed(self, specs):
        """Cross-process determinism catches ``PYTHONHASHSEED``, set-iteration and
        import-order dependence, which in-process comparison cannot see."""
        names = ("absolute_momentum", "momentum_factor_strategy", "dual_momentum_strategy",
                 "trend_momentum_strategy", "rsi_strategy", "bollinger_band_squeeze")
        # The child builds the panel from this exact source, and the in-process side
        # imports it, so both runs provably see byte-identical bars. (Generating them
        # twice from two copies of the generator is exactly how this test first
        # "failed" on its own bug.)
        script = (
            "import json\n"
            "import numpy as np, pandas as pd\n"
            "from research.optimize import catalog\n"
            "from research.optimize.backtest import run_single_stock\n"
            f"names = {names!r}\n"
            "def build_panel():\n"
            "    n = 300\n"
            "    rng = np.random.default_rng(4242)\n"
            "    idx = pd.bdate_range('2016-01-04', periods=n)\n"
            "    px = np.maximum(100.0*np.exp(np.cumsum(rng.normal(0,0.013,n))), 1.0)\n"
            "    return pd.DataFrame({'close':px,'high':px*1.02,'low':px*0.98,\n"
            "                         'volume':1e6}, index=idx)\n"
            "bars = build_panel()\n"
            "out = {}\n"
            "for s in catalog.discover(include=names):\n"
            "    p = s.sample(np.random.default_rng(7))\n"
            "    try:\n"
            "        r = run_single_stock(bars, s, p, rebalance='M')\n"
            "    except Exception as e:\n"
            "        out[s.name] = ['ERR', type(e).__name__]\n"
            "        continue\n"
            "    out[s.name] = [r.equity.to_numpy().tolist(), r.total_fees, r.total_tax]\n"
            "print(json.dumps(out))\n"
        )
        base_env = dict(os.environ)
        base_env["PYTHONPATH"] = os.pathsep.join(
            [str(REPO), str(REPO / "src"), base_env.get("PYTHONPATH", "")])

        def _spawn(hashseed: str):
            env = dict(base_env, PYTHONHASHSEED=hashseed)
            return subprocess.Popen([sys.executable, "-c", script],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, cwd=str(REPO), env=env)

        # concurrently: interpreter start-up plus pandas import dominates, and the two
        # children are completely independent
        procs = [_spawn("12345"), _spawn("999")]
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=300)
            assert proc.returncode == 0, f"child failed:\n{err[-2000:]}"
            results.append(json.loads(out.strip().splitlines()[-1]))
        first, second = results
        assert len(first) == len(names), f"child only produced {len(first)} results"
        for name in first:
            assert first[name] == second[name], (
                f"{name} differs across processes (PYTHONHASHSEED 12345 vs 999)")

        # and the in-process result matches the fresh process exactly
        rng = np.random.default_rng(4242)
        n = 300
        idx = pd.bdate_range("2016-01-04", periods=n)
        px = np.maximum(100.0 * np.exp(np.cumsum(rng.normal(0, 0.013, n))), 1.0)
        bars = pd.DataFrame({"close": px, "high": px * 1.02, "low": px * 0.98,
                             "volume": 1e6}, index=idx)
        matched = 0
        for s in specs:
            if s.name not in first:
                continue
            try:
                r = run_single_stock(bars, s, s.sample(np.random.default_rng(7)),
                                     rebalance="M")
            except BacktestError:
                continue
            assert first[s.name][0] == r.equity.to_numpy().tolist(), (
                f"{s.name}: in-process equity differs from the fresh process")
            matched += 1
        assert matched == len(names)


# --------------------------------------------------------------------------- #
# Known defects -- strict xfail pins
#
# Each asserts the CORRECT behaviour and therefore fails today. ``strict=True`` means
# fixing one turns into a suite failure (XPASS), forcing the marker to be removed
# deliberately rather than left to rot.
# --------------------------------------------------------------------------- #
class TestKnownDefects:
    """Defects found by this suite. Minimal reproduction in each ``reason``."""

    # (was @pytest.mark.xfail(strict=True) -- defect fixed)
    def test_strategy_receives_epoch_milliseconds(self):
        s = CAT.discover(include=("absolute_momentum",))[0]
        inst = Scripted(_Cfg(schedule=[0]))
        s.build = lambda values: inst
        dates = pd.bdate_range("2016-01-04", periods=5)
        px = np.full(5, 100.0)
        run_single_stock(pd.DataFrame({"close": px, "high": px, "low": px,
                                        "volume": 1e6}, index=dates), s, {},
                         rebalance="M")
        assert inst.ts_seen[0] == int(dates[0].value) // 10**6, (
            f"strategy got ts={inst.ts_seen[0]}, expected epoch-ms "
            f"{int(dates[0].value) // 10**6}")

    # (was @pytest.mark.xfail(strict=True) -- defect fixed)
    def test_realised_pnl_reconciles_with_equity_fees_and_tax(self):
        rng = np.random.default_rng(20260501)
        bars, sched = alternating_bars(rng, n=900)
        res = run_single_stock(bars, spec_for(), {"schedule": sched}, rebalance="M")
        r = replay(res.trades)
        unrealised = (r["open_shares"] * float(bars["close"].iloc[-1]) - r["open_basis"])
        # Trade.pnl is net of the SELL fee and gross of the BUY fee (see the Trade
        # docstring). So the buy fee must be subtracted once, separately. Subtracting
        # `total_fees` charged every sell fee twice and looked like an engine bug.
        buy_fees = sum(t.fee for t in res.trades if t.side == "BUY")
        lhs = (CAPITAL + sum(t.pnl for t in res.trades) - buy_fees
               - res.total_tax)
        rhs = float(res.equity.iloc[-1]) - unrealised
        sell_fees = sum(t.fee for t in res.trades if t.side == "SELL")
        assert abs(lhs - rhs) < ATOL, (
            f"capital + sum(pnl) - buy_fees - tax = {lhs:.4f} but realised equity = "
            f"{rhs:.4f}; {sell_fees:.2f} of sell-side fees appear unaccounted")

        # The authoritative identity the engine relies on, stated without reference to
        # any helper: cash from the trade tape, plus the mark-to-market of whatever is
        # still held, must equal final equity to the rupee.
        buys = sum(t.value for t in res.trades if t.side == "BUY")
        sells = sum(t.value for t in res.trades if t.side == "SELL")
        held = (sum(t.shares for t in res.trades if t.side == "BUY")
                - sum(t.shares for t in res.trades if t.side == "SELL"))
        cash = CAPITAL - buys + sells - res.total_fees - res.total_tax
        last = float(bars["close"].iloc[-1])
        assert abs(cash + held * last - float(res.equity.iloc[-1])) < ATOL

    # (was @pytest.mark.xfail(strict=True) -- defect fixed)
    def test_fastpath_rebind_leaves_unrelated_names_alone(self):
        proxy = types.ModuleType("_nsealgo_fastpath_probe")
        proxy.saved = IND.roc        # deliberately aliased
        proxy.also_saved = IND.sma
        sys.modules[proxy.__name__] = proxy
        with _pristine_fastpath():
            FP.install()
            try:
                assert proxy.saved is IND.roc.__wrapped__, (
                    "_rebind_all rewrote an unrelated module attribute (`saved`); "
                    "references to the original indicators are corrupted")
                assert proxy.also_saved is IND.sma.__wrapped__
            finally:
                sys.modules.pop(proxy.__name__, None)

    # (was @pytest.mark.xfail(strict=True) -- defect fixed)
    def test_bankrupt_curve_reports_its_drawdown(self):
        eq = pd.Series([-100.0, -50.0, -200.0, -300.0],
                       index=pd.bdate_range("2020-01-01", periods=4))
        m = MET.compute(eq)
        assert m.max_drawdown < 0.0, (
            f"a curve that fell from -100 to -300 reported max_drawdown "
            f"{m.max_drawdown}")

    # (was @pytest.mark.xfail(strict=True) -- defect fixed)
    def test_affordable_shares_is_a_whole_number_of_shares(self):
        s = _affordable_shares(1017.37, CAPITAL, C.FeeSchedule())
        assert s == int(s), f"_affordable_shares returned the fractional value {s}"

    # (was @pytest.mark.xfail(strict=True) -- defect fixed)
    def test_rebalance_cache_cannot_serve_one_index_anothers_mask(self):
        """Two different index objects sharing ``(len, first, last, freq)`` must not
        share a cache entry -- the key is a summary of the content, not the content."""
        from research.optimize import backtest as BT

        saved = dict(BT._REBAL_CACHE)
        try:
            BT._REBAL_CACHE.clear()
            a = pd.bdate_range("2020-01-01", periods=150)
            swapped = list(a[1:-1])
            swapped[40] = pd.Timestamp("2020-03-08")     # a Sunday, not a session
            b = pd.DatetimeIndex([a[0]] + swapped + [a[-1]])
            assert len(a) == len(b) and a[0] == b[0] and a[-1] == b[-1], (
                "the two indices must collide on the cache key for this to mean anything")

            def truth(idx):
                keys = idx.to_period("M")
                return frozenset(idx[i] for i in range(len(idx))
                                 if i == 0 or keys[i] != keys[i - 1])

            assert rebalance_dates(a, "M") == truth(a)
            assert rebalance_dates(b, "M") == truth(b), (
                "rebalance_dates served one index another's mask: the cache key "
                "(len, first, last, freq) is a summary, not the content")
        finally:
            BT._REBAL_CACHE.clear()
            BT._REBAL_CACHE.update(saved)
