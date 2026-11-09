"""Core library for the `cross_sectional_strategy` agent.

The catalog strategy (src/cryptobot/strategies/catalog/cross_sectional_strategy.py):

    m = roc(closes, period)                      # = close[t]/close[t-period] - 1
    return 1 if m > thr else (-1 if m < -thr else 0)

`roc()` is a pure trailing return, so the signal is exactly **the sign of the
`period`-bar return, gated by a symmetric `threshold` deadband**. That is all it
is — there is no cross-sectional information in it at all, despite the name.
The name is a misnomer: nothing in this file compares one symbol to another.

Because the NSE book is long-only, the -1 leg is unusable, so the long-only
interpretation is "be long a name on the days its `period`-bar return is
outside the deadband". §5 of AGENT_BRIEF.md then tells us how to build the book:
rank the signalled names cross-sectionally and let `run_backtest` apply the
portfolio constraints.

Every function here is strictly trailing: a value stamped at date *t* uses only
closes up to and including *t*, and `run_backtest` itself lags weights by one
bar (weights from *t* earn returns from *t+1*). No forward-fill from the future.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

sys.path.insert(0, "src")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nsealgo.backtest.engine import (  # noqa: E402
    BacktestResult,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402

COST = CostModel(segment="delivery", slippage_bps=5)

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

PORTFOLIO = PortfolioConfig()  # GOAL.md §3.2 defaults: 22 names, 12%, 25%, 10% cash


# --------------------------------------------------------------------------- #
# The strategy signal, vectorised but semantically identical to the catalog class
# --------------------------------------------------------------------------- #


def strategy_signal(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """+1 / 0 / -1 exactly as `CrossSectionalStrategy.signal` returns it.

    Verified against the catalog implementation in `10_verify_signal.py`.
    """
    m = panel / panel.shift(period) - 1.0
    sig = pd.DataFrame(
        np.select([m > threshold, m < -threshold], [1.0, -1.0], default=0.0),
        index=panel.index,
        columns=panel.columns,
    )
    # warmup(period): the first `period` bars have no defined ROC -> signal 0.
    sig.iloc[:period] = 0.0
    return sig


def trailing_return(panel: pd.DataFrame, days: int) -> pd.DataFrame:
    """Cumulative return over the last `days` bars. `nsealgo.factors.core` export."""
    return panel / panel.shift(days) - 1.0


def build_score(
    panel: pd.DataFrame, period: int, threshold: float, rank_days: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Long-only cross-sectional score: rank the signalled names by trailing return.

    `rank_days` is the horizon used to *rank* the names the strategy flags; the
    strategy's own `period` decides *which* names are flagged. `rank_days == period`
    means "buy the strongest of my own signalled names", which is the pure
    reading of the catalog strategy. `rank_days > period` is AGENT_BRIEF §5's
    suggested construction (rank the flagged names by longer trailing momentum).

    Non-eligible names are NaN, so `build_rebalance_weights` never selects them.
    """
    sig = strategy_signal(panel, period, threshold)
    mom = trailing_return(panel, rank_days)
    score = mom.where(sig > 0)
    return score, sig


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #

METRIC_ROWS = [
    ("CAGR %", lambda m: m.cagr * 100),
    ("Sharpe", lambda m: m.sharpe),
    ("MaxDD %", lambda m: m.max_drawdown * 100),
    ("Calmar", lambda m: m.calmar),
    ("Sortino", lambda m: m.sortino),
    ("Vol %", lambda m: m.volatility * 100),
    ("Total %", lambda m: m.total_return * 100),
    ("Turnover x/y", lambda m: m.annual_turnover),
    ("CostDrag %/y", lambda m: m.cost_drag_annual * 100),
    ("Trades /y", lambda m: m.trades_per_year),
    ("WinRate %", lambda m: m.win_rate * 100),
]


def metrics_table(rows: list[tuple[str, object]]) -> str:
    """Format a metrics comparison table. `rows` is [(label, Metrics)]."""
    w = max(len(lbl) for lbl, _ in rows) + 2
    head = "metric".ljust(w) + "".join(lbl.rjust(15) for lbl, _ in rows)
    out = [head, "-" * len(head)]
    for label, fn in METRIC_ROWS:
        cells = []
        for _, m in rows:
            v = fn(m)
            cells.append(f"{v:>15.2f}" if isinstance(v, float) else f"{v:>15}")
        out.append(label.ljust(w) + "".join(cells))
    return "\n".join(out)


def diagnostics(res: BacktestResult) -> str:
    w = res.weights
    return (
        f"    avg names held      : {res.diag['avg_names']:.2f}  "
        f"(config cap {PORTFOLIO.n_positions} picks / {PORTFOLIO.max_names} max)\n"
        f"    avg top weight      : {res.diag['avg_top_weight'] * 100:.2f}%  "
        f"(cap {PORTFOLIO.max_weight * 100:.0f}%)\n"
        f"    max weight seen     : {(w.max(axis=1)).max() * 100:.2f}%\n"
        f"    invested weight     : {w.sum(axis=1).mean() * 100:.2f}%  "
        f"(target {(1 - PORTFOLIO.cash_buffer) * 100:.0f}%)\n"
        f"    rebalances          : {int(res.diag['n_rebalances'])}\n"
        f"    round-trip bps      : {res.diag['round_trip_bps']:.2f}"
    )


def liveness(sig: pd.DataFrame, name: str) -> str:
    frac = (sig > 0).to_numpy().mean()
    flat = (sig == 0).to_numpy().mean()
    neg = (sig < 0).to_numpy().mean()
    return (
        f"    {name:<22} long {frac * 100:5.1f}% | flat {flat * 100:5.1f}% | "
        f"short {neg * 100:5.1f}%"
    )


def buy_and_hold(
    panel: pd.DataFrame, cost_model: CostModel = COST
) -> BacktestResult:
    """AGENT_BRIEF §4.5 benchmark: equal-weight buy-and-hold over the window.

    `panel.pct_change().mean(axis=1)` is the return series. The book is entered
    once at full weight at the start of the window and never touched again, so the
    only cost is a single one-way deployment: one-way turnover of exactly 1.0,
    charged at HALF the all-in round-trip rate (the engine's
    `all_in_round_trip_bps` is a *round-trip* rate; deploying once and never
    touching the book pays one side of it). `annual_turnover` is one-way turnover
    per year, matching the engine's own definition. Charged properly, so "beating
    nothing" is a fair fight and the benchmark is not handicapped.
    """
    rets = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rets.iloc[0] = 0.0
    rate = float(cost_model.all_in_round_trip_bps(_dec(100_000))) / 10_000.0
    one_way = rate / 2.0
    eq = 1.0
    daily = pd.Series(0.0, index=rets.index)
    for i, dt in enumerate(rets.index):
        prev = eq
        eq *= 1.0 + float(rets.loc[dt])
        if i == 0:
            eq -= one_way  # single one-way deployment of the whole book
        daily.loc[dt] = eq / prev - 1.0
    equity = (1.0 + daily).cumprod()
    years = len(equity) / 244
    m = compute_metrics(daily, equity, annual_turnover=1.0 / years,
                         cost_drag_annual=one_way / years, trades_per_year=1.0 / years)
    n = len(panel.columns)
    w = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    w.iloc[0:] = 1.0 / n
    return BacktestResult(
        returns=daily, equity=equity, weights=w, metrics=m,
        costs_paid=one_way * 2_100_000.0,
        diag={"avg_names": float(n), "n_rebalances": 1, "round_trip_bps": rate * 10_000},
    )


def _dec(x) -> object:
    from decimal import Decimal

    return Decimal(str(x))


def random_control(
    panel: pd.DataFrame,
    eligible_counts: pd.Series,
    seed: int,
    config: PortfolioConfig = PORTFOLIO,
    rebalance: str = "M",
) -> BacktestResult:
    """Negative control: pick `eligible_counts` random names on each rebalance date.

    Matches the strategy's cross-sectional *selectivity* on each date (hence a
    comparable turnover profile and a comparable cost drag) but carries zero
    signal. Any excess return is what diversification + beta alone buys.
    """
    rng = np.random.default_rng(seed)
    n = len(panel.columns)
    from nsealgo.backtest.engine import _rebalance_dates  # noqa: PLC0415

    arr = np.full((len(panel.index), n), np.nan)

    rb = _rebalance_dates(panel.index, rebalance)
    pos = {dt: i for i, dt in enumerate(panel.index)}
    for dt in rb:
        if dt not in pos:
            continue
        k = int(
            eligible_counts.reindex([dt], method="ffill")
            .fillna(config.n_positions).iloc[0]
        )
        k = max(1, min(k, n))
        # Positional (numpy) assignment: the column index is string labels, so
        # `.loc[row, [ints]]` would *append* integer-labelled columns instead of
        # setting existing ones.
        arr[pos[dt], rng.choice(n, size=k, replace=False)] = 1.0
    score = pd.DataFrame(arr, index=panel.index, columns=panel.columns)
    return run_backtest(panel, score, COST, config, rebalance)


def yearly(returns: pd.Series) -> str:
    yr = yearly_returns(returns) * 100
    return "  ".join(f"{int(y)}:{v:+.1f}%" for y, v in yr.items())


@dataclass
class Variant:
    """One declared parameter variant."""

    tag: str
    period: int
    threshold: float
    rank_days: int
    rebalance: str = "M"
    note: str = ""

    def __str__(self) -> str:
        return (
            f"{self.tag}: period={self.period} threshold={self.threshold:.3f} "
            f"rank_days={self.rank_days} rebalance={self.rebalance}"
        )


#: ---- DECLARED PARAMETER BUDGET: exactly 5 variants, written down BEFORE any
#: ---- backtest was run. Selection rule: highest TRAIN Sharpe, tie-break lower
#: ---- TRAIN MaxDD. No sixth variant is permitted.
VARIANTS: list[Variant] = [
    Variant("V1", 20, 0.015, 20, "M", "catalog defaults, ranked by its own 20d ROC"),
    Variant("V2", 20, 0.015, 126, "M", "same flag, ranked by 6m momentum (brief §5)"),
    Variant("V3", 60, 0.05, 60, "M", "slower signal, wider deadband"),
    Variant("V4", 126, 0.08, 126, "M", "6m signal — the evidence-backed horizon"),
    Variant("V5", 20, 0.015, 20, "W", "catalog defaults but weekly rebalance"),
]


def yearly_returns_safe(returns: pd.Series) -> pd.Series:
    """Calendar-year returns as a plain float mapping (used for the JSON dump)."""
    return yearly_returns(returns)
