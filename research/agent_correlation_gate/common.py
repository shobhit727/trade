"""Shared plumbing for the correlation_gate NSE validation run.

Strategy under test (src/cryptobot/strategies/catalog/correlation_gate.py):

    m = sma(closes, period);  r = roc(closes, period)
    +1 if r >  threshold and close > m
    -1 if r < -threshold and close < m
     0 otherwise

i.e. a trend-following crossover whose ROC deadband `threshold` gates it. Despite
the catalog name there is no correlation statistic in it -- the "gate" is the
ROC threshold. Long/short are per-symbol time-series; the NSE book is long-only
and cross-sectional, so the signal is mapped to a score (see `score_from_signal`).
"""

from __future__ import annotations

import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

# ---- protocol windows (brief section 4) ------------------------------------
TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

COST = CostModel(segment="delivery", slippage_bps=5)
PCFG = PortfolioConfig()


def load():
    return load_universe("data/nse")


# ---- strategy, vectorised ---------------------------------------------------


def signal_panel(panel: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """Vectorised equivalent of CorrGateStrategy.signal. No lookahead: uses c[:t+1]."""
    sma_ = panel.rolling(period, min_periods=period).mean()
    roc_ = panel / panel.shift(period) - 1.0
    long_ = (roc_ > threshold) & (panel > sma_)
    short_ = (roc_ < -threshold) & (panel < sma_)
    sig = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    sig = sig.mask(long_, 1.0)
    sig = sig.mask(short_, -1.0)
    # bars where sma/roc are not yet defined
    sig[sma_.isna() | roc_.isna()] = 0.0
    return sig


def score_from_signal(sig: pd.DataFrame, panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Map the long/short time-series signal to a long-only cross-sectional score.

    DECLARED UP FRONT, fixed for every variant:
      * score = cross-sectional rank of the strategy's OWN ROC(period), taken only
        over names it flags +1.  Ranking on its own conviction measure keeps the
        alpha attributable to correlation_gate rather than smuggled in from
        nsealgo's momentum factor.
      * names flagged -1 or 0 -> NaN.  NaN is *excluded* from the book, never
        shorted (Indian delivery accounts are long-only) and never ranked at the
        bottom: the strategy says "flat" on those names, so the book is flat too.
      * if fewer than n_positions names are flagged, the book simply holds fewer.
    """
    roc_ = panel / panel.shift(period) - 1.0
    live = sig > 0
    return roc_.where(live).rank(axis=1, pct=True)


# ---- reporting --------------------------------------------------------------


def fmt_metrics(tag: str, m, extra: str = "") -> str:
    return (
        f"{tag:<34} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>5.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>5.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x/y  Drag {m.cost_drag_annual * 100:>5.2f}%/y"
        + (f"  {extra}" if extra else "")
    )


def live_frac(sig: pd.DataFrame) -> float:
    """Fraction of symbol-days where the strategy is long (sanity check 3)."""
    return float((sig > 0).to_numpy().mean())


def slice_window(panel: pd.DataFrame, score: pd.DataFrame, start, end):
    p = panel.loc[start:end]
    s = score.reindex(p.index)
    return p, s


def backtest(panel, score, start, end, rebalance="M"):
    p, s = slice_window(panel, score, start, end)
    return run_backtest(p, s, COST, PCFG, rebalance=rebalance)
