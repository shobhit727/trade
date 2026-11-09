"""Shared helpers for the keltner_channel NSE study.

Signal is a faithful vectorised port of
`src/cryptobot/strategies/catalog/keltner_channel.py`:

    mid = ema(closes, period)                       # indicators.ema -> prefix recursion
    b   = atr(highs, lows, closes, period)          # indicators.atr -> mean of last N TRs
    +1  if close < mid - multiplier * b             # below lower band -> LONG
    -1  if close > mid + multiplier * b             # above upper band -> SHORT
     0  otherwise

The SHORT leg has no meaning in an Indian delivery account (brief section 5: long-only,
never short), so the NSE-adapted strategy is the LONG leg only:

    "hold names whose close is below their `period`-day EMA by more than
     `multiplier x ATR(period)`."

Two score constructions are tested so the result can be decomposed:
  * ``pure``   - rank gated names by band depth ((mid - close) / ATR, in ATR units).
                 Isolates the Keltner signal.
  * ``hybrid`` - rank gated names by 126d momentum (brief section 5 recipe).
                 This is a Keltner+momentum HYBRID; its performance is NOT attributable
                 to Keltner alone.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import yearly_returns
from nsealgo.costs import CostModel
from nsealgo.factors.core import momentum_6m

SCRATCH = "research/agent_keltner"

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

#: Brief section 3 mandate: full Indian delivery cost stack, 5 bps slippage.
COST = CostModel(segment="delivery", slippage_bps=5)

#: Brief section 5 / GOAL.md section 3.2 defaults. Never bypassed.
PORT = PortfolioConfig()

#: The declared variant budget (research/agent_keltner/DECLARED_BUDGET.md). Closed list.
VARIANTS: dict[str, dict] = {
    "kelt_pure_p20_m2":    {"period": 20, "multiplier": 2.0, "construction": "pure"},
    "kelt_hybrid_p20_m2":  {"period": 20, "multiplier": 2.0, "construction": "hybrid"},
    "kelt_pure_p20_m25":   {"period": 20, "multiplier": 2.5, "construction": "pure"},
    "kelt_pure_p40_m2":    {"period": 40, "multiplier": 2.0, "construction": "pure"},
    "kelt_hybrid_p20_m25": {"period": 20, "multiplier": 2.5, "construction": "hybrid"},
}


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def load_panel() -> pd.DataFrame:
    return pd.read_pickle(f"{SCRATCH}/panel.pkl")


def load_ohlc() -> dict[str, pd.DataFrame]:
    """OHLC panels on exactly the index/columns of the close panel.

    `nsealgo.data.loader.load_universe` returns closes only, but Keltner needs highs
    and lows for the true range. Rather than re-implement cleaning, each symbol is run
    through the SAME `load_symbol` (C1-C7) and then reindexed onto the close panel's
    index, so the score and the price panel can never drift apart.
    """
    import os

    from nsealgo.data.loader import load_symbol

    panel = load_panel()
    idx, cols = panel.index, list(panel.columns)
    out = {k: pd.DataFrame(np.nan, index=idx, columns=cols) for k in ("high", "low", "open")}
    for sym in cols:
        df = load_symbol(os.path.join("data/nse", f"{sym}_1d.csv"), sym)
        df = df.reindex(idx)
        # The close from load_symbol must be identical to the panel close; assert it so
        # a silent cleaning divergence cannot slip through.
        both = df["close"].notna() & panel[sym].notna()
        if not np.allclose(df.loc[both, "close"], panel.loc[both, sym]):
            raise AssertionError(f"{sym}: load_symbol close != load_universe close")
        out["open"][sym] = df["open"]
        out["high"][sym] = df["high"]
        out["low"][sym] = df["low"]
    return out


# --------------------------------------------------------------------------- #
# Indicator port
# --------------------------------------------------------------------------- #
def _ema_col(s: pd.Series, period: int) -> pd.Series:
    """Exact vectorised `cryptobot.strategies.indicators.ema` over the valid history.

    The catalog seeds the recursion at `values[0]` and is not a windowed function, so
    the value at bar t equals `ewm(span=period, adjust=False)` read at t, provided the
    recursion starts at the first *valid* bar. Computed on the de-NaN'd series and
    reindexed back, which is what the catalog sees: only that symbol's own bars.
    """
    valid = s.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=s.index)
    k = 2.0 / (period + 1)
    out = pd.Series(np.empty(len(valid)), index=valid.index)
    out.iloc[0] = valid.iloc[0]
    prev = float(valid.iloc[0])
    a = valid.to_numpy(dtype=float)
    for i in range(1, len(a)):
        prev = k * a[i] + (1.0 - k) * prev
        out.iloc[i] = prev
    return out.reindex(s.index)


def keltner_depth(
    close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, period: int
) -> pd.DataFrame:
    """``(mid - close) / atr`` in ATR units. Positive = close is BELOW the mid line.

    `atr` in the catalog is `np.mean` of the last `period` true ranges, and returns NaN
    unless there are `period + 1` closes -- i.e. TR[0] is undefined and the first valid
    ATR sits at bar index `period`. `rolling(period, min_periods=period)` over a TR
    series whose first entry is NaN reproduces exactly that first-valid-bar.
    """
    mid = pd.DataFrame(
        {c: _ema_col(close[c], period) for c in close.columns}, index=close.index
    )
    prev = close.shift(1)
    # np.maximum (NOT np.fmax / .max(axis=1)): true range must be NaN whenever any term
    # is NaN, so TR[0] -- which has no previous close -- is undefined, as in the catalog.
    # Also built as an explicit frame rather than by concat: concatenating frames that
    # share column labels produces DUPLICATE column labels, and the later `/ b` then
    # aligns 48 columns against 144 and silently yields an all-NaN panel.
    tr = pd.DataFrame(
        np.maximum(
            np.maximum((high - low).to_numpy(), (high - prev).abs().to_numpy()),
            (low - prev).abs().to_numpy(),
        ),
        index=close.index,
        columns=close.columns,
    )
    b = tr.rolling(period, min_periods=period).mean()
    out = (mid - close) / b.replace(0.0, np.nan)
    assert out.notna().to_numpy().any(), "keltner_depth produced an all-NaN panel"
    return out


def make_score(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    period: int,
    multiplier: float,
    construction: str,
) -> pd.DataFrame:
    """Cross-sectional score panel. NaN = not investable that day."""
    depth = keltner_depth(close, high, low, period)
    g = depth > multiplier           # catalog LONG condition: close < mid - mult * b
    if construction == "pure":
        # Deeper below the lower band = higher score. NaN elsewhere -> excluded.
        return depth.where(g)
    if construction == "hybrid":
        # brief section 5: rank the gated names by trailing 6m momentum.
        return momentum_6m(close).where(g).rank(axis=1, pct=True, na_option="keep")
    raise ValueError(f"unknown construction {construction!r}")


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #
def run(panel: pd.DataFrame, score: pd.DataFrame, port: PortfolioConfig | None = None,
        cost: CostModel | None = None):
    """Net-of-cost backtest. The default cost is the mandated 21.92 bps delivery stack.

    `cost` is exposed ONLY to produce the brief section 6.4 cost-drag decomposition.
    A costless run is a diagnostic, never a reported result.
    """
    return run_backtest(panel, score, cost or COST, port or PORT, rebalance="M")


def bh_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Buy-and-hold equal-weight universe as a score panel (brief section 4.5).

    Every name scores 1.0, so the engine holds the whole universe equally weighted,
    subject to the same caps, the same monthly rebalance and the same costs.
    """
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns)


def liveness(depth: pd.DataFrame, multiplier: float, lo: str, hi: str) -> dict:
    """Brief section 6.3 - what fraction of (symbol, bar) cells the gate fires on."""
    g = depth > multiplier
    sub = g.loc[lo:hi]
    per_bar = sub.sum(axis=1)
    return {
        "cell_frac": float(sub.to_numpy().mean()),
        "mean_names_flagged": float(per_bar.mean()),
        "median_names_flagged": float(per_bar.median()),
        "p90_names_flagged": float(per_bar.quantile(0.90)),
        "frac_bars_zero": float((per_bar == 0).mean()),
    }


def slice_metrics(res, lo: str, hi: str):
    """Metrics for a date window of an ALREADY-RUN backtest. Nothing is refitted.

    Turnover and cost drag are both recomputed over the window from the held-weight
    path, because `held` is forward-filled between rebalances: every bar where it
    changes IS a rebalance, and sum|dW|/2 there is exactly the engine's one-way
    convention.

    Cost drag is reconstructed as a FRACTION of equity. The engine charges
    ``2 * one_way_turnover * equity * rt_rate`` in absolute equity units, so the
    fractional drag at each rebalance is ``2 * one_way_turnover * rt_rate`` and the
    annual drag is ``2 * annual_turnover * rt_rate``. Two traps are avoided here:
    ``res.costs_paid`` is a whole-run scalar (attributing 18 years of cost to a 2.75
    year window overstates ~6.8x), and multiplying by the *absolute* equity level
    (which compounds from 2008) inflates the figure by the equity level again.
    """
    from nsealgo.backtest.metrics import compute_metrics

    idx = res.returns.index
    w = (idx >= lo) & (idx <= hi)
    r = res.returns[idx][w]
    held = res.weights.loc[idx]
    dw = held.diff().abs().sum(axis=1) / 2.0
    eq = (1.0 + r).cumprod()
    years = max(len(eq) / 244, 1e-9)

    rate = res.diag["round_trip_bps"] / 10_000.0
    turnover = float(dw.loc[idx][w].sum() / years)

    return compute_metrics(
        r,
        eq,
        annual_turnover=turnover,
        cost_drag_annual=2.0 * turnover * rate,
        trades_per_year=float((dw.loc[idx][w] > 0).sum() / years),
    ), {"avg_names": float((held.loc[idx][w] > 0).sum(axis=1).mean())}


def series_metrics(ret: pd.Series, lo: str, hi: str, annual_turnover: float = 0.0,
                   cost_drag: float = 0.0, trades: float = 12.0):
    """Metrics for a bare return series (benchmarks have no weight path)."""
    from nsealgo.backtest.metrics import compute_metrics

    r = ret.loc[lo:hi].dropna()
    eq = (1.0 + r).cumprod()
    return compute_metrics(
        r, eq, annual_turnover=annual_turnover, cost_drag_annual=cost_drag,
        trades_per_year=trades,
    ), {}


def random_score(gate: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Negative control: a RANDOM score on the SAME gate the strategy used.

    Brief section 6.5 -- "beat a random signal with the same % of bars long" is the
    minimum bar. Holding the gate fixed and randomising only the *ranking* isolates
    "was the Keltner band depth informative?" from "was being in the market at all?".
    """
    rng = np.random.default_rng(seed)
    noise = pd.DataFrame(
        rng.random(gate.shape), index=gate.index, columns=gate.columns
    )
    return noise.where(gate.to_numpy())


def fmt(name: str, m, extra: dict | None = None) -> str:
    base = (
        f"{name:<26} CAGR {m.cagr*100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown*100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x  Drag {m.cost_drag_annual*100:>5.2f}%/y"
    )
    if extra:
        base += "  " + "  ".join(f"{k}={v}" for k, v in extra.items())
    return base


def metrics_table(rows: list[tuple[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": n,
                "CAGR%": m.cagr * 100,
                "Sharpe": m.sharpe,
                "MaxDD%": m.max_drawdown * 100,
                "Calmar": m.calmar,
                "Turnover/y": m.annual_turnover,
                "CostDrag%/y": m.cost_drag_annual * 100,
                "AvgNames": d.get("avg_names", np.nan),
                "Total%": m.total_return * 100,
                "Win%": m.win_rate * 100,
            }
            for n, (m, d) in rows
        ]
    )


def yr(ret: pd.Series) -> pd.Series:
    return yearly_returns(ret)
