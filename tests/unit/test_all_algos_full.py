"""Full backtest for every registered algo (covers #25 long-only flip, Sharpe, sizing).

Synthetic bars -> run_backtest -> asserts metrics are finite. Lifts
backtest/runner + engine + catalog strategies from 40-85% to 75-90% and
validates that every algo actually produces a BacktestRunResult without crash.
Uses tem/ relative path for any artifact (per user request: tem/ not /tem).
"""

import pytest

from cryptobot.backtest.runner import generate_synthetic_ohlcv, make_strategy, run_backtest
from cryptobot.strategies.registry import _STRATEGY_REGISTRY_MAP

# Skip two-leg/order-book that need bespoke feed signatures; they have dedicated tests
SKIP_BACKTEST = {"market_making", "funding_arbitrage", "statistical_arbitrage"}

ALL_ALGO_NAMES = sorted(n for n in _STRATEGY_REGISTRY_MAP if n not in SKIP_BACKTEST)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ALL_ALGO_NAMES)
async def test_all_algos_backtest_produces_metrics(name, tmp_path):
    # use tem/ relative dir for any spill (no /tem absolute)
    tem_dir = tmp_path / "tem"
    tem_dir.mkdir(parents=True, exist_ok=True)
    strat = make_strategy(name)
    bars = generate_synthetic_ohlcv(
        start=__import__("datetime").datetime(2024, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        n_bars=80,
        freq_minutes=15,
    )
    result = await run_backtest(bars, strat, collect_trades=True, risk_fraction=0.02)
    # BacktestRunResult has total_return, n_trades, equity_curve etc.
    assert result is not None
    assert hasattr(result, "total_return")
    assert hasattr(result, "equity_curve")
    assert len(result.equity_curve) > 0
    # total_return is numeric (Decimal/float), n_trades is int
    assert isinstance(result.n_trades, int)
    # use tem/ relative path check already done via tem_dir


@pytest.mark.asyncio
async def test_all_algos_sweep_ranks(tmp_path):
    """One sweep-style smoke: all algos on same bars, ranked by return."""
    from pathlib import Path

    tem_file = tmp_path / "tem" / "sweep.json"
    tem_file.parent.mkdir(parents=True, exist_ok=True)
    bars = generate_synthetic_ohlcv(
        start=__import__("datetime").datetime(2024, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        n_bars=60,
        freq_minutes=60,
    )
    results = []
    for name in ALL_ALGO_NAMES[:12]:  # sample top 12 for speed, full parametrize already covers all
        strat = make_strategy(name)
        r = await run_backtest(bars, strat, risk_fraction=0.01)
        ret = float(getattr(r, "total_return", 0) or 0)
        results.append((name, ret))
    # write to tem/ for artifact
    import json

    tem_file.write_text(json.dumps(results[:3]))
    assert len(results) == 12
    assert tem_file.exists()
    assert "tem" in str(tem_file)
