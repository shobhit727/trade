from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cryptobot.backtest.funding_sim import _price_at, run_funding_backtest
from cryptobot.strategies.funding_arb import FundingArbConfig


def _make_data():
    base = datetime(2024, 1, 1, tzinfo=UTC)
    f_ts = [base + timedelta(hours=8 * i) for i in range(6)]
    f_rates = [0.0005, 0.0004, -0.0002, 0.0006, 0.0003, 0.0001]
    p_ts = [base + timedelta(hours=2 * i) for i in range(30)]
    s_cl = [100.0 + 0.001 * i for i in range(30)]
    # Perp carries a wide premium (~100bps) decaying to par over ~12 bars, so a
    # causal decision (previous bar's close — see issue #31) still sees an
    # entry-grade basis and the subsequent negative-funding decision exits.
    p_cl = (
        [101.0 - 0.1 * i for i in range(12)]
        + [100.0] * 18
    )
    return f_ts, f_rates, p_ts, s_cl, p_ts, p_cl


def test_funding_backtest_rejects_empty():
    with pytest.raises(ValueError):
        run_funding_backtest([], [], [], [], [], [])


def test_price_at_uses_previous_closed_bar_no_lookahead():
    """Issue #31: a decision at ts must use the previous bar's close, never the
    in-progress bar's future close."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = [base + timedelta(hours=i) for i in range(5)]
    closes = [100.0, 101.0, 102.0, 999.0, 1000.0]
    # At ts[3] (open of the 4th bar) the in-progress bar's close is 999.0, but
    # the previous closed bar's close is 102.0. Lookahead would return 999.0.
    assert _price_at(ts, closes, ts[3]) == 102.0
    # Exactly at the first bar's open, no previous bar exists -> None.
    assert _price_at(ts, closes, ts[0]) is None
    # Mid-interval still uses the previous closed bar.
    assert _price_at(ts, closes, base + timedelta(hours=2, minutes=30)) == 102.0


def test_funding_backtest_opens_closes_and_collects_carry():
    f_ts, f_rates, p_ts, s_cl, just_used_pp_ts, p_cl = _make_data()
    strat = FundingArbStrategy()
    res = run_funding_backtest(
        f_ts, f_rates, p_ts, s_cl, just_used_pp_ts, p_cl,
        strategy=strat, spot_maker_bps=7.5, spot_taker_bps=7.5,
        perp_maker_bps=1.8, perp_taker_bps=4.5,
    )
    assert res.n_roundtrips >= 1
    assert res.intervals_held >= 2
    assert res.years > 0.0


def test_funding_settled_when_price_grid_has_gap_at_boundary():
    """Issue #30: a carried position must still collect funding at an 8h
    boundary even when the spot/perp bar grid has no bar at that exact ts."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    f_ts = [base + timedelta(hours=8 * i) for i in range(6)]
    f_rates = [0.0005, 0.0004, -0.0002, 0.0006, 0.0003, 0.0001]
    # Price grid starts AFTER funding_ts[0] and ends BEFORE funding_ts[5], so
    # the first and last funding intervals have no price quote available.
    p_ts = [base + timedelta(hours=2 * i) for i in range(2, 18)]
    s_cl = [100.0 + 0.001 * i for i in range(16)]
    p_cl = [101.0 - 0.1 * i for i in range(12)] + [100.0] * 4
    strat = FundingArbStrategy()
    res = run_funding_backtest(
        f_ts, f_rates, p_ts, s_cl, p_ts, p_cl,
        strategy=strat, spot_maker_bps=7.5, spot_taker_bps=7.5,
        perp_maker_bps=1.8, perp_taker_bps=4.5,
    )
    # Position opens at funding_ts[1] (price available) and is carried across
    # funding_ts[2..4]; funding_ts[5] has no price but the position is still
    # open, so its rate must still be credited (no settlement skipped).
    assert res.intervals_held >= 3
    # carry must include the rate at the no-price boundary (funding_ts[5] = 0.0001)
    assert res.carry_bps > 0.0
    # The settlement at the gapped boundary is reflected in the final curve point.
    assert res.equity_curve[-1][1] > res.equity_curve[0][1]


def FundingArbStrategy(config=None):
    from cryptobot.strategies.funding_arb import FundingArbStrategy as _F
    return _F(config or FundingArbConfig(basis_entry_bps=5.0, basis_exit_bps=1.5))
