"""Response-shape validation for Binance public market-data endpoints.

Shared by the client's fetch methods. Each validator enforces the documented
provider schema (field names, field order where the API fixes it, integer
epoch-millisecond timestamps) and rejects non-monotonic timestamps before any
frame is built. Validation is by concrete value checks only; nothing here
infers data quality beyond the recorded facts.
"""

from __future__ import annotations

from typing import Any

from .binance import AcquisitionError, _checked_millisecond_timestamps


def _finite_float(value: Any, *, label: str, url: str, index: int) -> float:
    """Coerce a provider numeric that may arrive as a JSON string.

    Binance encodes kline prices/volumes as decimal strings while funding and
    open-interest objects carry JSON numbers; both forms are accepted, bools
    and everything else are rejected.
    """
    if isinstance(value, bool):
        raise AcquisitionError(f"{url} row {index} {label} is not a number")
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError as exc:
            raise AcquisitionError(f"{url} row {index} {label} is not a number") from exc
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        raise AcquisitionError(f"{url} row {index} {label} is not a number")
    if number != number or number in (float("inf"), float("-inf")):
        raise AcquisitionError(f"{url} row {index} {label} is not finite")
    return number


def _positive_float(value: Any, *, label: str, url: str, index: int) -> float:
    number = _finite_float(value, label=label, url=url, index=index)
    if number <= 0:
        raise AcquisitionError(f"{url} row {index} {label} must be positive")
    return number


def _non_negative_float(value: Any, *, label: str, url: str, index: int) -> float:
    number = _finite_float(value, label=label, url=url, index=index)
    if number < 0:
        raise AcquisitionError(f"{url} row {index} {label} must not be negative")
    return number


def validate_kline_rows(rows: list[Any], url: str) -> list[dict[str, Any]]:
    """Validate Binance spot kline arrays: 12 fields in documented order.

    Documented layout: open_time, open, high, low, close, volume, close_time,
    quote_volume, trades, taker_buy_base, taker_buy_quote, ignore.
    """
    KLINE_FIELD_COUNT = 12
    OPEN_TIME = 0
    OPEN = 1
    HIGH = 2
    LOW = 3
    CLOSE = 4
    VOLUME = 5

    validated: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != KLINE_FIELD_COUNT:
            raise AcquisitionError(
                f"{url} row {index} is not a {KLINE_FIELD_COUNT}-field kline array"
            )
        open_time = row[OPEN_TIME]
        if isinstance(open_time, bool) or not isinstance(open_time, int):
            raise AcquisitionError(
                f"{url} row {index} open_time is not an integer epoch millisecond"
            )
        open_price = _positive_float(row[OPEN], label="open", url=url, index=index)
        high_price = _positive_float(row[HIGH], label="high", url=url, index=index)
        low_price = _positive_float(row[LOW], label="low", url=url, index=index)
        close_price = _positive_float(row[CLOSE], label="close", url=url, index=index)
        volume = _non_negative_float(row[VOLUME], label="volume", url=url, index=index)
        if not (low_price <= open_price <= high_price and low_price <= close_price <= high_price):
            raise AcquisitionError(f"{url} row {index} OHLC values are internally inconsistent")
        validated.append({
            "open_time": open_time,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
        })

    timestamps = [row["open_time"] for row in validated]
    _checked_millisecond_timestamps(timestamps, url)
    return validated


def _validate_timestamped_rows(
    rows: list[Any],
    url: str,
    timestamp_field: str,
    extra_fields: tuple[tuple[str, str], ...],
) -> list[dict[str, Any]]:
    """Validate object rows with a millisecond timestamp field plus extras.

    ``extra_fields`` entries are ``(field_name, kind)`` where ``kind`` is
    ``"number"`` or ``"text"``. Rows are returned in provider order, sorted
    by timestamp ascending after the monotonic check passes.
    """
    validated: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise AcquisitionError(f"{url} row {index} is not a JSON object")
        for field_name, _ in extra_fields:
            if field_name not in row:
                raise AcquisitionError(f"{url} row {index} missing field: {field_name}")
        timestamp = row.get(timestamp_field)
        if isinstance(timestamp, bool) or not isinstance(timestamp, int):
            raise AcquisitionError(
                f"{url} row {index} {timestamp_field} is not an integer epoch millisecond"
            )
        record: dict[str, Any] = {timestamp_field: timestamp}
        for field_name, kind in extra_fields:
            value = row[field_name]
            if kind == "number":
                record[field_name] = _finite_float(value, label=field_name, url=url, index=index)
            else:
                if not isinstance(value, str) or not value:
                    raise AcquisitionError(f"{url} row {index} {field_name} must be a non-empty string")
                record[field_name] = value
        validated.append(record)

    timestamps = [row[timestamp_field] for row in validated]
    _checked_millisecond_timestamps(timestamps, url)
    return sorted(validated, key=lambda row: row[timestamp_field])


def validate_funding_rows(rows: list[Any], url: str) -> list[dict[str, Any]]:
    """Validate funding-rate rows: symbol, fundingTime, fundingRate (and markup)."""
    return _validate_timestamped_rows(
        rows,
        url,
        "fundingTime",
        (
            ("symbol", "text"),
            ("fundingRate", "number"),
            ("markupRate", "number"),
        ),
    )


def validate_open_interest_rows(rows: list[Any], url: str) -> list[dict[str, Any]]:
    """Validate open-interest statistic rows for the requested symbol/period."""
    return _validate_timestamped_rows(
        rows,
        url,
        "timestamp",
        (
            ("symbol", "text"),
            ("sumOpenInterest", "number"),
            ("sumOpenInterestValue", "number"),
        ),
    )
