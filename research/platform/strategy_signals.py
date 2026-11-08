"""Causal adapters from existing streaming strategy signals to portfolio targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .strategy_catalog import ExistingStrategyRegistry


@dataclass(frozen=True, slots=True)
class SignalGenerationResult:
    """Close-time long/flat signals and their declared strategy provenance."""

    signals: pd.DataFrame
    strategy_name: str
    parameters: dict[str, Any]
    decision_time: str
    direction_policy: str = "long_flat"


class SignalGenerationError(RuntimeError):
    """Raised when an existing strategy cannot produce a trustworthy signal stream."""


class ExistingStrategySignalAdapter:
    """Generate point-in-time signals using the repository's original strategy classes."""

    REQUIRED_COLUMNS = frozenset({"close", "high", "low", "volume"})

    def __init__(self, registry: ExistingStrategyRegistry | None = None) -> None:
        # Reuse the existing strategy catalogue and its typed Config constructors.
        self.registry = registry or ExistingStrategyRegistry()

    def build_signals(
        self,
        strategy_name: str,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        *,
        parameters: dict[str, Any] | None = None,
    ) -> SignalGenerationResult:
        """Evaluate one strategy independently on each symbol's historical OHLCV stream.

        Signals are stamped at each bar close. They are not fills. Pass the resulting
        target weights to PortfolioSimulator, which executes the preceding close's
        decision on the following bar's open.
        """
        # Refuse empty/unordered panels because signal timing would be ambiguous.
        if not bars_by_symbol:
            raise ValueError("bars_by_symbol cannot be empty")
        parameters = dict(parameters or {})
        self.registry.validate_parameter_payload(strategy_name, parameters)
        signals: dict[str, pd.Series] = {}

        for symbol in sorted(bars_by_symbol):
            frame = bars_by_symbol[symbol]
            if not self.REQUIRED_COLUMNS.issubset(frame.columns):
                raise ValueError(f"{symbol}: bars require close, high, low and volume")
            index = pd.DatetimeIndex(frame.index)
            if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
                raise ValueError(f"{symbol}: bar index must be timezone-aware, unique and increasing")
            values = frame[["close", "high", "low", "volume"]].to_numpy(dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError(f"{symbol}: OHLCV contains missing or non-finite values")
            if (values[:, :3] <= 0).any() or (values[:, 3] < 0).any():
                raise ValueError(f"{symbol}: prices must be positive and volume non-negative")

            # Each symbol gets an independent strategy instance and indicator state.
            strategy = self.registry.instantiate(strategy_name, parameters)
            if not callable(getattr(strategy, "feed", None)):
                raise TypeError(f"{strategy_name}: strategy does not implement streaming feed()")
            raw_positions = np.zeros(len(frame), dtype=np.float64)
            utc_naive = index.tz_convert("UTC").tz_localize(None)
            timestamps_ms = utc_naive.to_numpy(dtype="datetime64[ms]").astype("int64")

            for position, row in enumerate(frame.itertuples(index=False)):
                # Only this and previous bars are passed to the original streaming strategy.
                close = float(getattr(row, "close"))
                high = float(getattr(row, "high"))
                low = float(getattr(row, "low"))
                volume = float(getattr(row, "volume"))
                try:
                    strategy.feed(
                        symbol,
                        close,
                        high,
                        low,
                        volume,
                        ts=int(timestamps_ms[position]),
                    )
                except Exception as exc:  # noqa: BLE001 - retain the exact failing point.
                    raise SignalGenerationError(
                        f"{strategy_name} failed for {symbol} at {index[position].isoformat()}: {exc}"
                    ) from exc
                # The existing SignalStrategy owns its streaming position state.
                signal_position = int(strategy._pos.get(symbol, 0))
                raw_positions[position] = 1.0 if signal_position > 0 else 0.0

            signals[symbol] = pd.Series(raw_positions, index=index, name=symbol)

        # A portfolio target matrix requires one shared chronological calendar.
        first_index = next(iter(signals.values())).index
        for symbol, series in signals.items():
            if not series.index.equals(first_index):
                raise ValueError(f"{symbol}: signal calendar differs from the other assets")
        signal_frame = pd.DataFrame(signals, index=first_index)
        return SignalGenerationResult(
            signals=signal_frame,
            strategy_name=strategy_name,
            parameters=parameters,
            decision_time="bar_close",
        )

    @staticmethod
    def equal_weight_targets(signals: SignalGenerationResult) -> pd.DataFrame:
        """Convert active long/flat signals into equal-weight cash portfolio targets."""
        # Only signaled assets share the declared gross exposure; all-inactive rows stay cash.
        matrix = signals.signals.astype("float64")
        active_count = matrix.sum(axis=1).replace(0.0, np.nan)
        targets = matrix.div(active_count, axis=0).fillna(0.0)
        targets.attrs["strategy_name"] = signals.strategy_name
        targets.attrs["parameters"] = dict(signals.parameters)
        targets.attrs["allocation_policy"] = "equal_weight_active_signals"
        targets.attrs["decision_time"] = signals.decision_time
        return targets

    @staticmethod
    def individual_asset_targets(signals: SignalGenerationResult, symbol: str) -> pd.DataFrame:
        """Return a one-asset 0/1 target-weight frame for an individual-asset track."""
        # Validate exact symbol selection so a caller cannot accidentally pool assets.
        if symbol not in signals.signals.columns:
            raise KeyError(f"symbol not present in signal matrix: {symbol}")
        target = signals.signals[[symbol]].copy()
        target.attrs["strategy_name"] = signals.strategy_name
        target.attrs["parameters"] = dict(signals.parameters)
        target.attrs["allocation_policy"] = "single_asset_long_flat"
        target.attrs["decision_time"] = signals.decision_time
        return target
