from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cryptobot.backtest.funding_sim import run_funding_backtest
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


def FundingArbStrategy(config=None):
    from cryptobot.strategies.funding_arb import FundingArbStrategy as _F
    return _F(config or FundingArbConfig(basis_entry_bps=5.0, basis_exit_bps=1.5))
