from __future__ import annotations

import io
import logging

from cryptobot.utils.logging import (
    ContextFilter,
    LoggerMixin,
    clear_context,
    clear_correlation_id,
    correlation_id_var,
    get_correlation_id,
    get_logger,
    set_correlation_id,
    set_strategy_context,
    set_symbol_context,
    setup_logging,
    strategy_name_var,
    symbol_var,
)


def test_correlation_id_generated():
    clear_correlation_id()
    cid = get_correlation_id()
    assert cid is not None
    assert len(cid) == 12


def test_correlation_id_persists_in_context():
    clear_correlation_id()
    set_correlation_id("test-cid-123")
    assert get_correlation_id() == "test-cid-123"


def test_correlation_id_clear():
    set_correlation_id("to-clear")
    clear_correlation_id()
    cid = get_correlation_id()
    assert cid != "to-clear"
    assert cid is not None


def test_strategy_context():
    clear_context()
    set_strategy_context("trend_following")
    assert strategy_name_var.get() == "trend_following"
    clear_context()


def test_symbol_context():
    clear_context()
    set_symbol_context("BTCUSDT")
    assert symbol_var.get() == "BTCUSDT"
    clear_context()


def test_clear_context():
    set_correlation_id("cid")
    set_strategy_context("strat")
    set_symbol_context("sym")
    clear_context()
    assert correlation_id_var.get() is None
    assert strategy_name_var.get() is None
    assert symbol_var.get() is None


def test_context_filter():
    clear_context()
    set_correlation_id("cid")
    set_strategy_context("strat")
    set_symbol_context("sym")
    flt = ContextFilter()
    record = logging.LogRecord("name", logging.INFO, "path", 1, "msg", (), None)
    assert flt.filter(record) is True
    assert record.correlation_id == "cid"
    assert record.strategy == "strat"
    assert record.symbol == "sym"
    clear_context()


def test_context_filter_no_context():
    clear_context()
    flt = ContextFilter()
    record = logging.LogRecord("name", logging.INFO, "path", 1, "msg", (), None)
    flt.filter(record)
    assert record.correlation_id == "-"
    assert record.strategy == "-"
    assert record.symbol == "-"


def test_get_logger_returns_logger():
    lg = get_logger("test_logger")
    assert lg is not None


def test_setup_logging_json():
    buf = io.StringIO()
    setup_logging(level="INFO", json_output=True, stream=buf)
    log = get_logger("test_setup_json")
    log.info("hello", key="value")
    output = buf.getvalue()
    assert "hello" in output


def test_setup_logging_console():
    buf = io.StringIO()
    setup_logging(level="INFO", json_output=False, stream=buf)
    log = get_logger("test_setup_console")
    log.info("hello_console")
    output = buf.getvalue()
    assert "hello_console" in output


def test_setup_logging_silences_third_party():
    buf = io.StringIO()
    setup_logging(level="DEBUG", stream=buf)
    assert logging.getLogger("aiohttp").level >= logging.WARNING
    assert logging.getLogger("websockets").level >= logging.WARNING
    assert logging.getLogger("asyncio").level >= logging.WARNING
    assert logging.getLogger("urllib3").level >= logging.WARNING
    assert logging.getLogger("ccxt").level >= logging.WARNING
    assert logging.getLogger("redis").level >= logging.WARNING


# --- LoggerMixin ---------------------------------------------------------

class _HasLogger(LoggerMixin):
    def do_log(self):
        self.info("test_event", count=1)


def test_logger_mixin_provides_logger():
    obj = _HasLogger()
    assert obj.logger is not None


def test_logger_mixin_logs():
    obj = _HasLogger()
    obj.do_log()


def test_logger_mixin_log_with_context():
    obj = _HasLogger()
    obj.log_with_context("warning", "watch_out", reason="test")


def test_logger_mixin_all_levels():
    obj = _HasLogger()
    obj.debug("d")
    obj.info("i")
    obj.warning("w")
    obj.error("e")


__all__ = []
