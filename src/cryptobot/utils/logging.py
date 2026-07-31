"""
Structured logging configuration using structlog.

Provides JSON-formatted logs with context binding, correlation IDs,
and integration with Python's standard logging.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import structlog

from cryptobot.config import settings

# Context variables for request-scoped logging
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
strategy_name_var: ContextVar[str | None] = ContextVar("strategy_name", default=None)
symbol_var: ContextVar[str | None] = ContextVar("symbol", default=None)


def get_correlation_id() -> str:
    """Get or generate a correlation ID for the current context."""
    cid = correlation_id_var.get()
    if cid is None:
        cid = uuid4().hex[:12]
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context."""
    correlation_id_var.set(cid)


def clear_correlation_id() -> None:
    """Clear the correlation ID from the current context."""
    correlation_id_var.set(None)


def set_strategy_context(strategy: str) -> None:
    """Set the strategy name for the current context."""
    strategy_name_var.set(strategy)


def set_symbol_context(symbol: str) -> None:
    """Set the symbol for the current context."""
    symbol_var.set(symbol)


def clear_context() -> None:
    """Clear all context variables."""
    correlation_id_var.set(None)
    strategy_name_var.set(None)
    symbol_var.set(None)


class ContextFilter(logging.Filter):
    """Add context variables to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "-"
        record.strategy = strategy_name_var.get() or "-"
        record.symbol = symbol_var.get() or "-"
        return True


def add_context_to_event(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add context variables to structlog event dict."""
    cid = correlation_id_var.get()
    if cid:
        event_dict["correlation_id"] = cid

    strategy = strategy_name_var.get()
    if strategy:
        event_dict["strategy"] = strategy

    symbol = symbol_var.get()
    if symbol:
        event_dict["symbol"] = symbol

    return event_dict


def setup_logging(
    level: str = "INFO",
    json_output: bool = True,
    include_caller: bool = True,
) -> None:
    """
    Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Whether to output JSON (True) or human-readable (False)
        include_caller: Whether to include caller info in logs
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Processors for structlog
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        add_context_to_event,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]

    if json_output:
        # JSON output for production/log aggregation
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    if include_caller:
        shared_processors.append(structlog.processors.CallsiteParameterAdder([
            structlog.processors.CallsiteParameter.FUNC_NAME,
            structlog.processors.CallsiteParameter.LINENO,
            structlog.processors.CallsiteParameter.FILENAME,
        ]))

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, level.upper()))

    # Reduce noise from third-party libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Bound logger with context support
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin to add structured logging to a class."""

    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__module__ + "." + self.__class__.__name__)
        return self._logger

    def log_with_context(self, level: str, event: str, **kwargs: Any) -> None:
        """Log with automatic context binding."""
        getattr(self.logger, level.lower())(event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self.logger.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self.logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self.logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self.logger.error(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        self.logger.critical(event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        self.logger.exception(event, **kwargs)


def configure_logging_from_settings() -> None:
    """Configure logging from application settings."""
    setup_logging(
        level=settings.app.log_level,
        json_output=settings.app.env != "development",
        include_caller=settings.app.env == "development",
    )


# Initialize logging on import
configure_logging_from_settings()

# Export commonly used items
__all__ = [
    "get_logger",
    "setup_logging",
    "configure_logging_from_settings",
    "LoggerMixin",
    "get_correlation_id",
    "set_correlation_id",
    "clear_correlation_id",
    "set_strategy_context",
    "set_symbol_context",
    "clear_context",
    "ContextFilter",
]
