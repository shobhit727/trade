"""Point-in-time universe tests against the REAL membership CSV.

No mocks: every assertion reads the same gitignored CSV the loader consumes
(``data/nse_membership/nifty50_monthly_membership.csv``). Member sets quoted in
this file were read from the CSV by hand (awk over ``date`` rows) before being
asserted.
"""

from __future__ import annotations

import csv
from collections import defaultdict

import pandas as pd
import pytest

from research.platform.universe import (
    PITUniverse,
    membership_csv_path,
    members_range,
    universe_at,
)


@pytest.fixture(scope="module")
def universe() -> PITUniverse:
    return PITUniverse()


@pytest.fixture(scope="module")
def raw_rows() -> dict[str, set[str]]:
    """date -> member symbols, read straight from the CSV with the stdlib."""
    path = membership_csv_path()
    grouped: dict[str, set[str]] = defaultdict(set)
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            grouped[row["date"]].add(row["symbol"].strip().upper())
    return grouped


# --------------------------------------------------------------------------- #
# (a) exact member sets at known historical dates (hand-read from the CSV)
# --------------------------------------------------------------------------- #

KNOWN_SETS = {
    # 2008-01-31: first month-end of the reconstruction (50 names, pre-crisis)
    "2008-01-31": (
        "ABB ACC AMBUJACEM BAJAJAUTO BHARTIARTL BHEL BPCL CAIRN CIPLA DRREDDY "
        "GAIL GLAXO GRASIM HCLTECH HDFC HDFCBANK HEROMOTOCO HINDALCO HINDUNILVR "
        "ICICIBANK IDEA INFY ITC LT MARUTI MM NATIONALUM NTPC ONGC PNB RANBAXY "
        "RCOM RELIANCE RELINFRA RPL SAIL SATYAMCOMP SBIN SIEMENS STER SUNPHARMA "
        "SUZLON TATAMOTORS TATAPOWER TATASTEEL TCS UNITECH VSNL WIPRO ZEEL"
    ).split(),
    # 2017-04-30: verified against the wayback_20180929103632 snapshot source
    "2017-04-30": (
        "ACC ADANIPORTS AMBUJACEM ASIANPAINT AUROPHARMA AXISBANK BAJAJAUTO "
        "BANKBARODA BHARTIARTL BOSCHLTD BPCL CIPLA COALINDIA DRREDDY EICHERMOT "
        "GAIL GRASIM HCLTECH HDFC HDFCBANK HEROMOTOCO HINDALCO HINDUNILVR "
        "IBULHSGFIN ICICIBANK INDUSINDBK INFRATEL INFY IOC ITC KOTAKBANK LT "
        "LUPIN MARUTI MM NTPC ONGC POWERGRID RELIANCE SBIN SUNPHARMA TATAMOTORS "
        "TATAPOWER TATASTEEL TCS TECHM ULTRACEMCO WIPRO YESBANK ZEEL"
    ).split(),
    # 2023-07-31: post HDFC->LTIM rebalance, all sources modern
    "2023-07-31": (
        "ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJAUTO BAJAJFINSV "
        "BAJFINANCE BHARTIARTL BPCL BRITANNIA CIPLA COALINDIA DIVISLAB DRREDDY "
        "EICHERMOT GRASIM HCLTECH HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO "
        "HINDUNILVR ICICIBANK INDUSINDBK INFY ITC JSWSTEEL KOTAKBANK LT LTIM "
        "MARUTI MM NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE SBIN SUNPHARMA "
        "TATACONSUM TATAMOTORS TATASTEEL TCS TECHM TITAN ULTRACEMCO UPL WIPRO"
    ).split(),
}


@pytest.mark.parametrize(("day", "expected"), sorted(KNOWN_SETS.items()))
def test_universe_at_matches_hand_read_csv_sets(
    universe: PITUniverse, raw_rows: dict[str, set[str]], day: str, expected: list[str]
) -> None:
    assert day in raw_rows, f"{day} is not a recorded month-end in the CSV"
    assert universe.universe_at(day) == frozenset(expected)
    # and the quoted set is itself the CSV truth for that date
    assert frozenset(expected) == raw_rows[day]


def test_universe_at_returns_frozenset_of_symbols(universe: PITUniverse) -> None:
    result = universe.universe_at("2023-07-31")
    assert isinstance(result, frozenset)
    assert len(result) == 50


def test_module_level_entry_points_share_behaviour() -> None:
    assert universe_at("2023-07-31") == universe_at("2023-07-31")
    assert len(universe_at("2023-07-31")) == 50
    pairs = members_range("2023-07-31", "2023-07-31")
    assert [d for d, _ in pairs] == [pd.Timestamp("2023-07-31")]


# --------------------------------------------------------------------------- #
# (b) no look-ahead: first membership month-end gates first query date
# --------------------------------------------------------------------------- #

def test_universe_at_never_precedes_first_membership_month_end(universe: PITUniverse) -> None:
    """A symbol absent from every query strictly before its first recorded
    month-end has no time-travel entry point."""
    checked = 0
    for symbol in universe._membership.symbols:
        column = universe._membership.table[symbol]
        if not column.any():
            continue
        first = universe._membership.table.index[column][0]
        if first > universe.coverage[0]:
            before = universe.universe_at(first - pd.Timedelta(days=1))
            assert symbol not in before, (
                f"{symbol} leaked into {before} before its first month-end {first.date()}"
            )
        assert symbol in universe.universe_at(first)
        checked += 1
    assert checked >= 100  # the CSV carries 104 distinct symbols


def test_mid_month_rebalance_record_does_not_leak_early(universe: PITUniverse) -> None:
    # NESTLEIND was recorded on 2019-08-27 (a non-month-end day); it must first
    # appear at a month-end, never mid-quarter.
    assert "NESTLEIND" not in universe.universe_at("2019-08-27")
    assert "NESTLEIND" not in universe.universe_at("2019-09-30")
    assert "NESTLEIND" in universe.universe_at("2019-10-31")


# --------------------------------------------------------------------------- #
# (c) real delist / drop-and-relist behaviour per the recorded data
# --------------------------------------------------------------------------- #

def test_delisted_symbol_behaves_per_data(universe: PITUniverse) -> None:
    # SATYAMCOMP: member until the December 2008 snapshot; dropped from the
    # January 2009 set onward (the fraud-forced replacement by RELCAPITAL) and
    # never returns.
    assert "SATYAMCOMP" in universe.universe_at("2008-12-31")
    assert "SATYAMCOMP" not in universe.universe_at("2009-01-31")
    for symbol in universe.universe_at("2010-01-31"):
        assert symbol != "SATYAMCOMP"


def test_symbol_drop_and_relist_behaves_per_data(universe: PITUniverse) -> None:
    # WIPRO: removed at the 2013-04-30 rebalance, re-added from the
    # 2013-10-04 record onward (dense: 2013-10-31), stayed a member after.
    assert "WIPRO" in universe.universe_at("2013-03-31")
    assert "WIPRO" not in universe.universe_at("2013-04-30")
    assert "WIPRO" not in universe.universe_at("2013-09-30")
    assert "WIPRO" in universe.universe_at("2013-10-31")
    assert "WIPRO" in universe.universe_at("2014-06-30")


# --------------------------------------------------------------------------- #
# (d) before the first month-end -> explicit ValueError (documented policy)
# --------------------------------------------------------------------------- #

def test_query_before_first_month_end_raises(universe: PITUniverse) -> None:
    # Documented choice: explicit ValueError rather than an empty set. An empty
    # set would be indistinguishable from "index existed but had no members"
    # and would silently zero a backtest's tradable universe.
    with pytest.raises(ValueError, match="outside membership coverage"):
        universe.universe_at("2008-01-30")


def test_query_after_last_month_end_raises(universe: PITUniverse) -> None:
    with pytest.raises(ValueError, match="outside membership coverage"):
        universe.universe_at("2026-11-30")


# --------------------------------------------------------------------------- #
# (e) members_range: contiguous month-ends, transitions match the CSV
# --------------------------------------------------------------------------- #

def test_members_range_returns_contiguous_month_ends(
    universe: PITUniverse, raw_rows: dict[str, set[str]]
) -> None:
    pairs = universe.members_range("2017-04-01", "2017-12-31")
    dates = [d for d, _ in pairs]
    # first dense month-end on/after start, last on/before end, all ME.
    # The dense index spans every calendar month-end 2008-01..2026-10,
    # including the 45 carried ones, so 2017-11/12 are present too.
    assert dates[0] == pd.Timestamp("2017-04-30")
    assert dates[-1] == pd.Timestamp("2017-12-31")
    assert all(d.is_month_end for d in dates)
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    assert set(gaps) <= {28, 29, 30, 31}
    # forward-filled 2017-05-31 (absent from the source) equals 2017-04-30's set
    assert dict(pairs)[pd.Timestamp("2017-05-31")] == dict(pairs)[pd.Timestamp("2017-04-30")]
    # carried boundary month-end: 2017-03-31 is absent from the source, so the
    # dense row inherits 2017-02-28's recorded set
    carried = dict(universe.members_range("2017-03-01", "2017-03-31"))
    assert carried[pd.Timestamp("2017-03-31")] == frozenset(raw_rows["2017-02-28"])


def test_members_range_transition_matches_recorded_change(
    universe: PITUniverse, raw_rows: dict[str, set[str]]
) -> None:
    # GRASIM -> VEDL is recorded on 2017-05-29 in the CSV; 2017-05-31 is one of
    # the 45 missing month-ends, so the change becomes effective at 2017-06-30.
    pairs = dict(universe.members_range("2017-04-30", "2017-06-30"))
    before = pairs[pd.Timestamp("2017-05-31")]
    after = pairs[pd.Timestamp("2017-06-30")]
    assert after - before == frozenset({"VEDL"})
    assert before - after == frozenset({"GRASIM"})
    # ... and that is exactly what the CSV rows say
    assert raw_rows["2017-05-29"] - raw_rows["2017-04-30"] == {"VEDL"}
    assert raw_rows["2017-04-30"] - raw_rows["2017-05-29"] == {"GRASIM"}


def test_members_range_outside_coverage_raises(universe: PITUniverse) -> None:
    with pytest.raises(ValueError, match="outside membership coverage"):
        universe.members_range("2007-12-31", "2008-06-30")
    with pytest.raises(ValueError, match="is after end"):
        universe.members_range("2010-06-30", "2010-01-31")
