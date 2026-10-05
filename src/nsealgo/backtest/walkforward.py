"""Walk-forward validation — the only accepted performance evidence (GOAL.md §5 Gate 3).

Why walk-forward and not a single in-sample/backtest split: a single split lets the
researcher choose the boundary. Walk-forward forces the *entire* parameter/period choice
to be made on data preceding each test window, so every reported test number is a
genuine out-of-sample number.

Protocol
--------
* ``n_folds`` sequential folds, each with a training window and a test window.
* The strategy is fit on the train window (which selects the best parameter set from
  the grid using train-only metrics) and then evaluated **unchanged** on the test window.
* Fold test returns are concatenated into one OOS equity curve — that curve is what
  gets reported. Its CAGR/Sharpe/MaxDD are true out-of-sample statistics.
* Optionally purge a gap between train and test to avoid any leakage through
  overlapping factor windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .metrics import Metrics, compute_metrics, yearly_returns

TRADING_DAYS = 244


@dataclass
class FoldResult:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    best_params: dict[str, float]
    train_metrics: Metrics
    test_metrics: Metrics

    def __str__(self) -> str:
        return (
            f"Fold {self.fold}: train {self.train_start.date()}->{self.train_end.date()} "
            f"| test {self.test_start.date()}->{self.test_end.date()} "
            f"| OOS CAGR {self.test_metrics.cagr * 100:>6.2f}% "
            f"Sharpe {self.test_metrics.sharpe:>5.2f} "
            f"MaxDD {self.test_metrics.max_drawdown * 100:>7.2f}% "
            f"| params {self.best_params}"
        )


@dataclass
class WalkForwardResult:
    folds: list[FoldResult] = field(default_factory=list)
    oos_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    oos_metrics: Metrics | None = None
    oos_equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    benchmark_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def summary(self) -> str:
        lines = ["WALK-FORWARD VALIDATION", "=" * 100]
        for f in self.folds:
            lines.append(str(f))
        lines.append("-" * 100)
        if self.oos_metrics:
            lines.append("OUT-OF-SAMPLE (concatenated test windows):")
            lines.append(self.oos_metrics.fmt())
            yb = yearly_returns(self.oos_returns)
            lines.append("")
            lines.append(
                f"positive years: {(yb > 0).sum()}/{len(yb)} = "
                f"{(yb > 0).sum() / len(yb) * 100:.0f}%   (Gate 3 needs >=60%)"
            )
        return "\n".join(lines)


def walk_forward(
    panel: pd.DataFrame,
    param_grid: list[dict],
    run_fn,
    n_folds: int = 5,
    train_years: int = 5,
    test_years: int = 2,
    purge_bars: int = 0,
    rf_annual: float = 0.065,
) -> WalkForwardResult:
    """Run ``n_folds`` walk-forward folds.

    Parameters
    ----------
    run_fn
        ``run_fn(panel_slice, params) -> BacktestResult``. Must return an object with
        ``.returns`` (a daily Series) and ``.metrics``.
    param_grid
        Candidate parameter dicts. Selection happens on the **train window only**, by
        the grid key ``"objective"`` if present (default: maximise Sharpe).
    """
    dates = panel.index
    train_bars = int(train_years * TRADING_DAYS)
    test_bars = int(test_years * TRADING_DAYS)
    purge = int(purge_bars)

    total = train_bars + purge + test_bars
    if total >= len(dates):
        raise ValueError(
            f"not enough data: need {total} bars for {n_folds}-fold "
            f"{train_years}y+{test_years}y, have {len(dates)}"
        )

    result = WalkForwardResult()
    oos_chunks: list[pd.Series] = []
    bench_chunks: list[pd.Series] = []
    bench_all = panel.pct_change(fill_method=None).mean(axis=1)

    # Sliding-origin folds: each test window starts after the previous one ends, so the
    # concatenated OOS series is continuous.
    for k in range(n_folds):
        offset = k * test_bars
        tr0 = len(dates) - total - offset
        tr1 = tr0 + train_bars
        te0 = tr1 + purge
        te1 = min(te0 + test_bars, len(dates))
        if tr0 < 0 or te1 <= te0:
            continue

        train_dates = dates[tr0:tr1]
        test_dates = dates[te0:te1]
        train_panel = panel.loc[train_dates]
        test_panel = panel.loc[test_dates]

        # ---- select on TRAIN only
        best_params, best_score, best_train_metrics = None, -np.inf, None
        for params in param_grid:
            r = run_fn(train_panel, params)
            score = r.metrics.sharpe  # selection criterion, train-only
            if score > best_score:
                best_score, best_params = score, params
                best_train_metrics = r.metrics

        # ---- evaluate UNCHANGED on TEST
        r_test = run_fn(test_panel, best_params)
        fold = FoldResult(
            fold=k + 1,
            train_start=train_dates[0],
            train_end=train_dates[-1],
            test_start=test_dates[0],
            test_end=test_dates[-1],
            best_params=dict(best_params),
            train_metrics=best_train_metrics,
            test_metrics=r_test.metrics,
        )
        result.folds.append(fold)

        oos_chunks.append(r_test.returns)
        bench_chunks.append(bench_all.loc[test_dates].fillna(0.0))

    if not oos_chunks:
        return result

    result.oos_returns = pd.concat(oos_chunks).sort_index()
    result.benchmark_returns = pd.concat(bench_chunks).sort_index()
    result.oos_equity = (1.0 + result.oos_returns).cumprod()
    result.oos_metrics = compute_metrics(result.oos_returns, result.oos_equity,
                                         rf_annual=rf_annual)
    return result
