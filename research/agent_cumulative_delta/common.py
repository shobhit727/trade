"""Shared harness for the `cumulative_delta` NSE agent run.

Signal definition comes verbatim from
`src/cryptobot/strategies/catalog/cumulative_delta_strategy.py`:

    d = cumulative_delta(closes, volumes, window)
    return 1 if d > 0 else (-1 if d < 0 else 0)

and `cumulative_delta` (src/cryptobot/strategies/indicators.py:375) is

    sum over the last `window` bars of  +volume if close[i] > close[i-1]
                                       -volume if close[i] < close[i-1]
                                        0        if close[i] == close[i-1]

i.e. a net buy-pressure proxy: signed (tick-rule) volume accumulated over a window.
It is NOT crypto-specific — no funding, no liquidations, no peg, no IV, no basis.
It is the daily-bar cousin of Chaikin Money Flow / OBV slope, so it has NSE meaning
and this run is legitimate.

Shorting is unavailable in an Indian delivery account, so the `-1` branch maps to
"not held". The book is long-only and cross-sectional, so the signal is turned into a
cross-sectional score (brief section 5).

No lookahead: the delta on day t uses closes/volumes through t only, and
`run_backtest` applies weights decided at t from t+1 onward.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    _rebalance_dates,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score, rank_cross_sectional  # noqa: E402

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

DATA_DIR = "data/nse"
CACHE = Path(__file__).resolve().parent / "panel.pkl"
SLIPPAGE_BPS = 5
N_POSITIONS = 22
MOM_DAYS = 126  # brief section 5's trailing-momentum ranking horizon (6 months)


def cost_model(slippage_bps: int = SLIPPAGE_BPS) -> CostModel:
    return CostModel(segment="delivery", slippage_bps=Decimal(str(slippage_bps)))


def portfolio_config() -> PortfolioConfig:
    return PortfolioConfig(n_positions=N_POSITIONS)


def window(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    idx = panel.index
    lo = idx.searchsorted(start)
    hi = idx.searchsorted(end, side="right")
    return panel.iloc[lo:hi]


# --------------------------------------------------------------------------- #
# Data — close panel (mandatory loader) + volume panel (same cleaning rules)
# --------------------------------------------------------------------------- #


def load_panels(data_dir: str = DATA_DIR, use_cache: bool = True):
    """Return (close_panel, volume_panel, symbols, cleaning_report).

    The close panel comes from `load_universe`, which is the binding loader. Volume is
    rebuilt per symbol through the *same* `load_symbol` cleaning rules (C1-C7), so the
    volume panel and the close panel share one index and one cleaning history — no
    second, divergent cleaning path.
    """
    if use_cache and CACHE.exists():
        cached = pd.read_pickle(CACHE)
        return cached["close"], cached["vol"], cached["symbols"], cached["report"]

    panel, symbols, report = load_universe(data_dir)

    vols: dict[str, pd.Series] = {}
    for sym in symbols:
        df = load_symbol(os.path.join(data_dir, f"{sym}_1d.csv"), sym)
        vols[sym] = df["vol"].rename(sym)
    vol = pd.DataFrame(vols).reindex(panel.index)

    out = {"close": panel, "vol": vol, "symbols": symbols, "report": report}
    pd.to_pickle(out, CACHE)
    return panel, vol, symbols, report


# --------------------------------------------------------------------------- #
# The strategy
# --------------------------------------------------------------------------- #


def delta_panel(close: pd.DataFrame, vol: pd.DataFrame, window: int) -> pd.DataFrame:
    """Vectorised `cumulative_delta` — verified equal to the catalog function.

    Per-bar signed volume is `sign(close.diff()) * volume` (flat days contribute 0,
    exactly as the loop does), summed over the trailing `window` bars.
    `min_periods=window` mirrors `len(closes) < window + 1 -> NaN` warmup.

    Computed **per symbol on that symbol's own bars**, then aligned to the panel
    index. This is not cosmetic: the wide panel index is the *union* of all symbols'
    dates, so a symbol that did not trade on a given date (TCS has no 2010-02-06
    bar) gets a NaN volume row. Rolling over the union index would then wipe out
    `window` bars of a symbol's history for every such day, whereas the catalog loop
    — which walks one symbol's own sequence — sees nothing. Doing it per symbol
    reproduces the catalog exactly; `verify` asserts it.
    """
    out: dict[str, pd.Series] = {}
    for sym in close.columns:
        c = close[sym].dropna()
        v = vol[sym].reindex(c.index)
        signed = np.sign(c.diff()) * v
        out[sym] = signed.rolling(window, min_periods=window).sum().reindex(close.index)
    return pd.DataFrame(out, index=close.index, columns=close.columns)


def signal_panel(delta: pd.DataFrame) -> pd.DataFrame:
    """+1 where delta > 0, NaN elsewhere (the -1 branch == not held in delivery)."""
    return delta.where(delta > 0.0)


def momentum_panel(close: pd.DataFrame, days: int = MOM_DAYS) -> pd.DataFrame:
    return close / close.shift(days) - 1.0


@dataclass(frozen=True)
class Variant:
    name: str
    window: int
    construction: str


#: DECLARED PARAMETER BUDGET — 5 variants, fixed before any run.
#: Three windows on the faithful translation of the strategy (pure delta ranking among
#: delta>0 names), and two alternative constructions at the catalog's default window
#: so that "is it the window or the construction?" is answerable on TRAIN.
CONSTRUCTIONS = ("delta_rank", "momentum_rank", "delta_mom_blend")

VARIANTS: tuple[Variant, ...] = (
    Variant("V1_w20_delta_rank", 20, "delta_rank"),
    Variant("V2_w30_delta_rank", 30, "delta_rank"),
    Variant("V3_w60_delta_rank", 60, "delta_rank"),
    Variant("V4_w30_mom_rank", 30, "momentum_rank"),
    Variant("V5_w30_blend", 30, "delta_mom_blend"),
)


def strategy_score(close: pd.DataFrame, vol: pd.DataFrame, v: Variant) -> pd.DataFrame:
    """Cross-sectional score for one variant. Higher = more attractive."""
    delta = delta_panel(close, vol, v.window)
    sig = signal_panel(delta)
    mom = momentum_panel(close)

    if v.construction == "delta_rank":
        # Faithful translation: among names the strategy flags long, buy the ones
        # with the strongest net buy pressure.
        return sig.rank(axis=1, pct=True)
    if v.construction == "momentum_rank":
        # Brief section 5's canonical recipe: flag with the strategy, rank the
        # signalled names by trailing momentum.
        return sig.notna().mul(0.0).add(mom.where(sig.notna())).rank(axis=1, pct=True)
    if v.construction == "delta_mom_blend":
        a = sig.rank(axis=1, pct=True)
        b = mom.where(sig.notna()).rank(axis=1, pct=True)
        return a.add(b, fill_value=np.nan).div(2.0).where(sig.notna())
    raise ValueError(f"unknown construction {v.construction!r}")


def liveness(delta: pd.DataFrame, start: pd.Timestamp,
             end: pd.Timestamp) -> dict[str, float]:
    sig = signal_panel(delta).loc[start:end]
    n_flagged = sig.notna().sum(axis=1)
    return {
        "long_frac": float(sig.notna().to_numpy().mean()),
        "avg_flagged_names": float(n_flagged.mean()),
        "days_below_n_positions": float((n_flagged < N_POSITIONS).mean()),
    }


def avg_names_held(result) -> float:
    w = result.weights
    return float((w > 1e-9).sum(axis=1).mean())


# --------------------------------------------------------------------------- #
# Benchmarks & controls
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, cm: CostModel,
                 start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Equal-weight buy-and-hold over the window, net of the same cost stack.

    Mirrors `run_backtest`'s accounting: cost is charged on the compounding
    normalised equity, and 100% in + 100% out is one full round trip.
    """
    px = window(panel, start, end)
    daily_gross = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0

    daily = pd.Series(0.0, index=px.index)
    eq, costs = 1.0, 0.0
    for i, dt in enumerate(px.index):
        prev = eq
        eq *= 1.0 + float(daily_gross.loc[dt])
        if i == 0 or i == len(px.index) - 1:
            eq -= 0.5 * eq * rate  # 50% of book traded on each leg
            costs += 0.5 * eq * rate
        daily.loc[dt] = eq / prev - 1.0
    equity = (1.0 + daily).cumprod()
    years = len(equity) / 244
    m = compute_metrics(daily, equity, annual_turnover=1.0 / years,
                        cost_drag_annual=costs / years)
    return {"returns": daily, "equity": equity, "metrics": m}


def random_control_score(n_flagged: pd.Series, index: pd.DatetimeIndex,
                         cols: list[str], seed: int) -> pd.DataFrame:
    """Random names, random order, matched to the strategy's eligible count per day.

    Brief section 6.5: same number of names eligible each day, but no delta filter and
    no ranking. The long fraction is copied from the real signal's own daily count.
    """
    rng = np.random.default_rng(seed)
    noise = pd.DataFrame(rng.random((len(index), len(cols))),
                         index=index, columns=cols)
    keep = noise.rank(axis=1, ascending=False).le(n_flagged, axis=0)
    return (1.0 - noise).where(keep)


def composite_score(close: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(close)


def cost_drag_split(panel: pd.DataFrame, score: pd.DataFrame,
                    start: pd.Timestamp, end: pd.Timestamp):
    """Same book at base cost vs zero cost, over the window. Isolates viability."""
    px = window(panel, start, end)
    sc = score.reindex(px.index)
    cfg = portfolio_config()
    net = run_backtest(px, sc, cost_model(), cfg, rebalance="M")
    zero = CostModel(segment="delivery", slippage_bps=Decimal("0"))
    gross = run_backtest(px, sc, zero, cfg, rebalance="M")
    return net, gross


def row(label: str, m, extra: str = "") -> str:
    return (
        f"{label:<24} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
        f"MaxDD {m.max_drawdown * 100:>7.2f}%  Calmar {m.calmar:>6.2f}  "
        f"Turn {m.annual_turnover:>5.2f}x/y  Cost {m.cost_drag_annual * 100:>5.2f}%/y"
        f"{extra}"
    )


__all__ = [
    "CONSTRUCTIONS", "DATA_DIR", "MOM_DAYS", "TEST_END", "TEST_START",
    "TRAIN_END", "TRAIN_START", "VARIANTS", "Variant", "avg_names_held",
    "buy_and_hold", "composite_score", "cost_drag_split", "cost_model",
    "delta_panel", "liveness", "load_panels", "momentum_panel", "portfolio_config",
    "random_control_score", "rank_cross_sectional", "row", "run_backtest",
    "signal_panel", "strategy_score", "window", "yearly_returns",
    "_rebalance_dates", "compute_metrics",
]
