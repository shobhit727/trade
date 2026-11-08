"""Tests connecting existing registered strategies to the next-open simulator."""


import numpy as np
import pandas as pd
import pytest

from research.platform.strategy_signals import ExistingStrategySignalAdapter


def _bars(close: np.ndarray, *, volume: float = 10000.0) -> pd.DataFrame:
    # Construct internally consistent OHLCV rows with UTC bar-close timestamps.
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(close), volume, dtype=np.float64),
        },
        index=pd.date_range("2024-01-01", periods=len(close), freq="D", tz="UTC"),
    )


def test_existing_strategy_adapter_generates_close_time_long_flat_signals() -> None:
    # The original absolute momentum class is used with a short test lookback.
    adapter = ExistingStrategySignalAdapter()
    prices = np.linspace(100.0, 120.0, 20)
    bars = {"AAA": _bars(prices)}
    result = adapter.build_signals(
        "absolute_momentum",
        bars,
        parameters={"period": 3, "threshold": 0.0},
    )
    assert result.decision_time == "bar_close"
    assert result.signals.index.equals(bars["AAA"].index)
    assert result.signals["AAA"].iloc[:2].eq(0.0).all()
    assert result.signals["AAA"].iloc[-1] == 1.0
    targets = adapter.individual_asset_targets(result, "AAA")
    assert targets.columns.tolist() == ["AAA"]
    assert set(targets["AAA"].unique()).issubset({0.0, 1.0})


def test_existing_strategy_signals_are_invariant_to_future_bar_changes() -> None:
    # Changing future observations cannot alter earlier streaming strategy decisions.
    adapter = ExistingStrategySignalAdapter()
    prices = np.linspace(100.0, 120.0, 30)
    original = _bars(prices)
    changed = original.copy()
    changed.loc[changed.index[20]:, ["open", "high", "low", "close"]] *= 0.5
    original_signals = adapter.build_signals(
        "absolute_momentum", {"AAA": original}, parameters={"period": 4}
    )
    changed_signals = adapter.build_signals(
        "absolute_momentum", {"AAA": changed}, parameters={"period": 4}
    )
    pd.testing.assert_series_equal(
        original_signals.signals.loc[:original.index[19], "AAA"],
        changed_signals.signals.loc[:original.index[19], "AAA"],
    )


def test_equal_weight_signal_targets_remain_market_neutral_to_inactive_assets() -> None:
    # The portfolio allocation divides only among assets with active long signals.
    adapter = ExistingStrategySignalAdapter()
    dates = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
    rising = _bars(np.linspace(100.0, 120.0, len(dates)))
    falling = _bars(np.linspace(120.0, 100.0, len(dates)))
    signals = adapter.build_signals(
        "absolute_momentum",
        {"AAA": rising, "BBB": falling},
        parameters={"period": 3, "threshold": 0.0},
    )
    targets = adapter.equal_weight_targets(signals)
    assert (targets.to_numpy() >= 0.0).all()
    assert (targets.sum(axis=1) <= 1.0 + 1e-12).all()
    assert targets.loc[dates[-1], "AAA"] > 0.0
    assert targets.loc[dates[-1], "BBB"] == 0.0


def test_strategy_signal_adapter_rejects_unknown_config_fields() -> None:
    # Invalid parameter names must not be ignored by the underlying Config constructor.
    adapter = ExistingStrategySignalAdapter()
    with pytest.raises(ValueError, match="unknown config fields"):
        adapter.build_signals(
            "absolute_momentum",
            {"AAA": _bars(np.linspace(100.0, 110.0, 10))},
            parameters={"not_a_config_field": 10},
        )
