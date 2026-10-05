from __future__ import annotations

from cryptobot.live.paper_harness import FundingPaperHarness
from cryptobot.strategies.funding_arb import FundingArbConfig, FundingArbStrategy


def _harness(symbols=("BTCUSDT",), tmp_path=None):
    strat = FundingArbStrategy(FundingArbConfig(
        min_funding_rate=0.0001,
        max_funding_rate=0.005,
        basis_entry_bps=5.0,
        basis_exit_bps=1.5,
    ))
    log = (tmp_path / "paper.csv") if tmp_path else "paper_funding.csv"
    return FundingPaperHarness(symbols=symbols, strategy=strat, log_path=log)


def _spot_msg(sym="BTCUSDT", bid="100", ask="100.01"):
    return {"b": bid, "a": ask}


def _perp_msg(sym="BTCUSDT", mark="100.07", rate="0.0008"):
    return {"p": mark, "r": rate, "e": "markPriceUpdate"}


def test_no_signal_before_both_legs():
    h = _harness()
    h.process_spot_message("BTCUSDT", _spot_msg())
    assert h.states["BTCUSDT"].in_position is False


def test_enter_then_exit_cycles(tmp_path):
    h = _harness(tmp_path=tmp_path)
    # spot 100, perp 100.07 -> basis 7bps >= 5 entry, funding 0.08% >= 0.01%
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg())
    st = h.states["BTCUSDT"]
    assert st.in_position is True
    assert st.entry_basis_bps > 5.0
    # basis converges to 1bp -> exit
    h.process_spot_message("BTCUSDT", _spot_msg(bid="100.06", ask="100.07"))
    h.process_perp_message("BTCUSDT", _perp_msg(mark="100.07"))
    assert st.in_position is False
    assert st.n_trips == 1


def test_carry_accumulates_while_in_position(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg())  # enter
    h.process_spot_message("BTCUSDT", _spot_msg(bid="100.03", ask="100.04"))
    h.process_perp_message("BTCUSDT", _perp_msg(mark="100.075", rate="0.0008"))
    assert h.states["BTCUSDT"].carry_bps > 0


def test_low_funding_blocks_entry(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg(rate="0.00001"))
    assert h.states["BTCUSDT"].in_position is False


def test_combined_json_dispatch(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.process_json_message({
        "stream": "btcusdt@bookTicker",
        "data": {"b": "100", "a": "100.01"},
    })
    h.process_json_message({
        "stream": "btcusdt@markPrice@1m",
        "data": {"p": "100.07", "r": "0.0008"},
    })
    assert h.states["BTCUSDT"].in_position is True


def test_csv_log_rows_written_on_signals(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg())
    lines = (tmp_path / "paper.csv").read_text().strip().splitlines()
    assert len(lines) == 3  # header + ENTER + SAMPLE
    assert "ENTER" in lines[1]


def test_ignores_garbage_messages():
    h = _harness()
    h.process_spot_message("BTCUSDT", {"b": "abc", "a": "xyz"})
    h.process_perp_message("BTCUSDT", {"p": None})
    assert h.states["BTCUSDT"].in_position is False


def test_basis_gate_uses_strategy_config(tmp_path):
    h = _harness(tmp_path=tmp_path)
    # basis 5.5bps but entry threshold is 5.0 -> enters
    h.process_spot_message("BTCUSDT", _spot_msg(bid="100", ask="100.001"))
    h.process_perp_message("BTCUSDT", _perp_msg(mark="100.056", rate="0.0005"))
    assert h.states["BTCUSDT"].in_position is True


def test_sample_rows_written_without_signals(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg(rate="0.00001"))  # low funding -> no enter
    lines = (tmp_path / "paper.csv").read_text().strip().splitlines()
    assert len(lines) == 2  # header + one SAMPLE row
    assert "SAMPLE" in lines[1]
    assert h._sample_count == 1


def test_sample_throttled_by_interval(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.sample_interval_s = 3600.0
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg(rate="0.00001"))  # first eval -> sample
    h.process_spot_message("BTCUSDT", _spot_msg(bid="100.02", ask="100.03"))
    h.process_perp_message("BTCUSDT", _perp_msg(mark="100.07", rate="0.00001"))  # throttled
    lines = (tmp_path / "paper.csv").read_text().strip().splitlines()
    assert len(lines) == 2  # header + one SAMPLE row (second eval suppressed)
    assert h._sample_count == 1


def test_sample_and_signal_rows_coexist(tmp_path):
    h = _harness(tmp_path=tmp_path)
    h.process_spot_message("BTCUSDT", _spot_msg())
    h.process_perp_message("BTCUSDT", _perp_msg())  # enter -> ENTER row
    lines = (tmp_path / "paper.csv").read_text().strip().splitlines()
    assert len(lines) == 3  # header + ENTER + SAMPLE
    assert "ENTER" in lines[1]
    assert "SAMPLE" in lines[2]


def test_to_live_row_includes_basis_and_funding():
    from decimal import Decimal

    from cryptobot.live.paper_harness import PaperState

    st = PaperState(symbol="BTCUSDT")
    row = st.to_live_row(spot=Decimal("100"), perp=Decimal("100.06"), rate=0.0008)
    assert row["basis_bps"] == 6.0
    assert row["funding_pct"] == 0.08


def test_no_signal_basis_when_leg_missing():
    from cryptobot.live.paper_harness import PaperState

    st = PaperState(symbol="BTCUSDT")
    row = st.to_live_row(spot=None, perp=None, rate=None)
    assert "basis_bps" not in row
    assert "funding_pct" not in row
