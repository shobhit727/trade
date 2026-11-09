"""Shared helpers for the bollinger_bands NSE study.

Signal is a faithful port of the catalog strategy
`src/cryptobot/strategies/catalog/bollinger_bands.py`:

    sig = bollinger_position(closes, period, n_std)      # (last - mean) / (n_std*sd)
    +1 (long)  if sig < -entry                          # close below lower band
    -1 (short) if sig > +entry                          # close above upper band
     0         otherwise

The SHORT leg has no meaning in an Indian delivery account (brief section 5:
long-only, never short), so the NSE-adapted strategy is the LONG leg only:
"hold names whose close is more than `entry * n_std` population-sd below their
`period`-day mean."

Two score constructions are tested so the result can be decomposed:
  * ``pure``   — rank gated names by oversold depth. Isolates the Bollinger signal.
  * ``hybrid`` — rank gated names by 126d momentum (brief section 5 recipe).
                 This is a Bollinger+momentum HYBRID; its performance is not
                 attributable to Bollinger alone.
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

SCRATCH = "research/agent_bollinger_bands"

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

#: Brief section 3 mandate: full Indian delivery cost stack, 5 bps slippage.
COST = CostModel(segment="delivery", slippage_bps=5)

#: Brief section 5 / GOAL.md section 3.2 defaults. Never bypassed.
PORT = PortfolioConfig()


def load_panel() -> pd.DataFrame:
    return pd.read_pickle(f"{SCRATCH}/panel.pkl")


def bollinger_position(panel: pd.DataFrame, period: int, n_std: float) -> pd.DataFrame:
    """Exact vectorised port of ``cryptobot.strategies.indicators.bollinger_position``.

    ddof=0 to match ``np.std`` default. Window includes day t (same as the catalog
    implementation, which slices ``closes[-period:]`` and reads ``a[-1]``), so the
    value at t uses data up to and including t — no look-ahead. The backtest engine
    additionally lags weights by one bar.
    """
    n = len(panel)
    if n < period:
        return pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    r = panel.rolling(period, min_periods=period)
    mid = r.mean()
    sd = r.std(ddof=0)
    sd = sd.mask(sd == 0.0)
    return (panel - mid) / (n_std * sd)


def gate(sig: pd.DataFrame, entry: float) -> pd.DataFrame:
    """Catalog LONG condition, as a boolean panel: ``sig < -entry``."""
    return sig < -entry


def make_score(
    panel: pd.DataFrame,
    period: int,
    n_std: float,
    entry: float,
    construction: str,
) -> pd.DataFrame:
    """Build a cross-sectional score panel. NaN = not investable that day."""
    sig = bollinger_position(panel, period, n_std)
    g = gate(sig, entry)
    if construction == "pure":
        # Deeper oversold = higher score. NaN everywhere else -> excluded from the book.
        return (-sig).where(g)
    if construction == "hybrid":
        # brief section 5: rank the gated names by trailing 6m momentum.
        return momentum_6m(panel).where(g).rank(axis=1, pct=True, na_option="keep")
    raise ValueError(f"unknown construction {construction!r}")


def run(panel: pd.DataFrame, score: pd.DataFrame, port: PortfolioConfig | None = None):
    return run_backtest(panel, score, COST, port or PORT, rebalance="M")


def bh_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Buy-and-hold equal-weight universe as a score panel (brief section 4.5).

    Every name scores 1.0 so the engine holds the whole universe equally weighted,
    subject to the same caps, the same monthly rebalance and the same costs.
    """
    return pd.DataFrame(1.0, index=panel.index, columns=panel.columns)


def fmt(name: str, m, extra: dict | None = None) -> str:
    base = (
        f"{name:<26} CAGR {m.cagr*100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown*100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x  Drag {m.cost_drag_annual*100:>5.2f}%/y"
    )
    if extra:
        base += "  " + "  ".join(f"{k}={v}" for k, v in extra.items())
    return base


def yr(ret: pd.Series) -> pd.Series:
    return yearly_returns(ret)


def metrics_table(rows: list[tuple[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(
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
    return df
