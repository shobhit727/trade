"""Web-triggered strategy sweeps (run every registered algo from /dashboard).

A tiny job manager: one background worker thread runs each registered
strategy through ``run_backtest`` on the requested bars, collecting return /
Sharpe / max-drawdown per algorithm. The health server exposes:

- ``POST /api/backtest/start?symbol=BTCUSDT&timeframe=1d&capital=10000``
- ``GET  /api/backtest/status``

Bars come from ``data/{symbol}_{timeframe}.csv`` when present (Binance kline
export), otherwise a deterministic synthetic series is generated so the sweep
always has something honest to chew on.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from cryptobot.backtest.metrics import PerformanceMetrics
from cryptobot.backtest.runner import generate_synthetic_ohlcv, make_strategy, run_backtest
from cryptobot.strategies.registry import _STRATEGY_REGISTRY_MAP

logger = logging.getLogger(__name__)

_SLIPPAGE_BPS = 3
_COMMISSION_BPS = 5


def list_strategy_names() -> list[str]:
    """Every registry algorithm, sorted (ml_strategy excluded: needs training)."""
    return sorted(n for n in _STRATEGY_REGISTRY_MAP if n != "ml_strategy")


def load_bars(symbol: str, timeframe: str, fallback_bars: int = 400):
    """Real CSV bars when available, else synthetic random-walk."""
    path = Path(f"data/{symbol.lower()}_{timeframe}.csv")
    if path.exists():
        df = pd.read_csv(path)
        from datetime import UTC, datetime

        return [
            OhlcvBar_(datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                      float(r.open), float(r.high), float(r.low),
                      float(r.close), float(r.vol))
            for r in df.itertuples(index=False)
        ]
    from datetime import UTC, datetime

    logger.warning("no data/%s_%s.csv; generating %d synthetic bars",
                   symbol.lower(), timeframe, fallback_bars)
    return generate_synthetic_ohlcv(
        n_bars=fallback_bars,
        start=datetime(2025, 1, 1, tzinfo=UTC),
        freq_minutes=1440 if timeframe.endswith("d") else 60,
    )


# Local alias to avoid importing OhlcvBar twice under different names.
from cryptobot.backtest.runner import OhlcvBar as OhlcvBar_  # noqa: E402


def _curve_metrics(curve) -> dict[str, float]:
    values = [float(v) for _t, v in curve]
    if len(values) < 2:
        return {"ret": 0.0, "sharpe": 0.0, "mdd": 0.0}
    pm = PerformanceMetrics()
    pm.add_value(values[0])
    for v in values[1:]:
        pm.add_value(v)
    rets = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    return {
        "ret": values[-1] / values[0] - 1.0,
        "sharpe": float(pm.calculate_sharpe_ratio(rets)),
        "mdd": float(pm.calculate_drawdown(pd.Series(values))) / 100.0,
    }


@dataclass
class SweepJob:
    symbol: str
    timeframe: str
    capital: str
    running: bool = True
    started_at: float = field(default_factory=time.time)
    done: int = 0
    total: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    trades: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    max_trades_stored: int = 500
    error: str = ""

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "capital": self.capital,
            "done": self.done,
            "total": self.total,
            "elapsed_s": round(time.time() - self.started_at, 1),
            "error": self.error,
            "results": self.results,
        }


class BacktestJobManager:
    """Runs at most one sweep at a time; results are replaceable."""

    def __init__(self):
        self._lock = threading.Lock()
        self._job: SweepJob | None = None
        self._thread: threading.Thread | None = None

    def start(self, symbol: str, timeframe: str, capital: str) -> tuple[bool, str]:
        with self._lock:
            if self._job is not None and self._job.running:
                return False, "a sweep is already running"
            job = SweepJob(symbol=symbol.upper(), timeframe=timeframe,
                           capital=capital)
            job.total = len(list_strategy_names())
            self._job = job
            self._thread = threading.Thread(
                target=self._worker, args=(job,), name="backtest-sweep", daemon=True)
            self._thread.start()
            return True, f"sweep started: {job.total} algorithms on {job.symbol} {job.timeframe}"

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._job is None:
                return {"running": False, "results": [], "total": 0, "done": 0}
            return self._job.status()

    def trades_for(self, name: str) -> dict[str, Any]:
        with self._lock:
            if self._job is None:
                return {"name": name, "trades": [], "total": 0}
            return {
                "name": name,
                "trades": self._job.trades.get(name, []),
                "total": len(self._job.trades.get(name, [])),
            }

    # ------------------------------------------------------------------ worker

    def _worker(self, job: SweepJob) -> None:
        try:
            bars = load_bars(job.symbol, job.timeframe)
            capital = Decimal(job.capital)
        except Exception as exc:  # noqa: BLE001
            job.error = f"bar load failed: {exc}"
            job.running = False
            return

        for name in list_strategy_names():
            entry: dict[str, Any] = {"name": name}
            try:
                strategy = make_strategy(name)
                result = asyncio.run(run_backtest(
                    bars, strategy, symbol=job.symbol,
                    initial_capital=capital, risk_fraction=1.0,
                    slippage_bps=_SLIPPAGE_BPS, commission_bps=_COMMISSION_BPS,
                    collect_trades=True,
                ))
                m = _curve_metrics(result.equity_curve)
                entry.update(ret=m["ret"], sharpe=m["sharpe"], mdd=m["mdd"],
                             n_trades=len(result.trades))
                job.trades[name] = [
                    {
                        "entry_time": str(tr.get("entry_time", "")),
                        "exit_time": str(tr.get("exit_time", "")),
                        "side": tr.get("side", ""),
                        "qty": float(tr.get("quantity", 0)),
                        "entry_price": float(tr.get("entry_price", 0)),
                        "exit_price": float(tr.get("exit_price", 0)),
                        "pnl": float(tr.get("pnl", 0)),
                        "pnl_pct": float(tr.get("pnl_pct", 0)),
                        "fees": float(tr.get("fees", 0)),
                    }
                    for tr in result.trades[:job.max_trades_stored]
                ]
            except Exception as exc:  # noqa: BLE001 - one bad algo must not kill the sweep
                entry.update(error=str(exc)[:120])
            job.results.append(entry)
            job.done += 1

        job.results.sort(key=lambda r: r.get("sharpe", -1e9), reverse=True)
        job.running = False
        logger.info("sweep finished: %d algos on %s %s", job.done, job.symbol, job.timeframe)


_MANAGER: BacktestJobManager | None = None


def get_backtest_manager() -> BacktestJobManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = BacktestJobManager()
    return _MANAGER


__all__ = [
    "BacktestJobManager",
    "SweepJob",
    "get_backtest_manager",
    "list_strategy_names",
    "load_bars",
]
