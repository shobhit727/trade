"""Shared harness for the dual-momentum NSE study.

Every function here is point-in-time: a signal at date *t* uses closes up to and
including *t* only. Signals are built on the FULL panel and then sliced to the
window, so the EMA/rolling warm-up is satisfied by pre-window history (which a live
system would also have) rather than by eating into the evaluation window.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    BacktestResult,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import Metrics, compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

DATA_DIR = str(ROOT / "data" / "nse")

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

#: Ranking horizon for the cross-sectional score. Fixed by the AGENT_BRIEF recipe
#: (6-month trailing momentum), never tuned -- see the declared budget in the report.
RANK_DAYS = 126

COST = CostModel(segment="delivery", slippage_bps=5)
CONFIG = PortfolioConfig()

_PANEL: pd.DataFrame | None = None
_SYMBOLS: list[str] = []


def panel() -> pd.DataFrame:
    """Cleaned daily close panel (cached)."""
    global _PANEL, _SYMBOLS
    if _PANEL is None:
        p, s, _rep = load_universe(DATA_DIR)
        _PANEL, _SYMBOLS = p, s
    return _PANEL


def symbols() -> list[str]:
    panel()
    return list(_SYMBOLS)


# --------------------------------------------------------------------------- #
# The strategy: EMA(fast) vs EMA(slow), lifted verbatim from the catalog
# --------------------------------------------------------------------------- #


def ema_panel(px: pd.DataFrame, period: int) -> pd.DataFrame:
    """Recursive EMA seeded on the first observation.

    ``ewm(span=p, adjust=False)`` applies exactly the recursion the catalog uses
    (``out = k*x + (1-k)*out`` with ``k = 2/(p+1)``) and seeds on the first value,
    so this is numerically the catalog's ``ema`` rather than a lookalike.
    """
    return px.ewm(span=period, adjust=False).mean()


def build_signal(px: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """1.0 where the fast EMA is above the slow EMA, 0.0 otherwise.

    NaN for the first ``slow`` bars: the catalog's ``warmup`` returns ``slow`` and its
    ``ema`` returns NaN on a short window, so no signal exists there and the name is
    untradeable rather than falsely flat.
    """
    f = ema_panel(px, fast)
    s = ema_panel(px, slow)
    sig = (f > s).astype(float)
    sig.iloc[:slow] = np.nan
    return sig


def build_score(px: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional score: 6m trailing momentum, ranked among flagged names only.

    This is the AGENT_BRIEF sec.5 recipe verbatim. ``na_option="keep"`` means the
    percentile is computed inside the signalled subset, so a name that is not flagged
    can never win the ranking.
    """
    mom = px / px.shift(RANK_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True, na_option="keep")


def signal_liveness(sig: pd.DataFrame) -> dict[str, float]:
    """Fraction of symbol-bars flagged long, and the flagged count per day."""
    v = sig.to_numpy(dtype=float)
    ok = np.isfinite(v)
    return {
        "frac_bars_long": float((v[ok] > 0).mean()),
        "mean_flagged_per_day": float(np.nansum(v > 0, axis=1).mean()),
        "min_flagged_per_day": float(np.nansum(v > 0, axis=1).min()),
    }


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


def win_mask(frame: pd.DataFrame, window: tuple[str, str]) -> pd.Series:
    """Boolean mask selecting ``window`` from any frame sharing the panel's index."""
    lo = pd.Timestamp(window[0], tz=frame.index.tz)
    hi = pd.Timestamp(window[1], tz=frame.index.tz)
    return (frame.index >= lo) & (frame.index <= hi)


def slice_w(frame: pd.DataFrame, window: tuple[str, str]) -> pd.DataFrame:
    return frame.loc[win_mask(frame, window)]


def run(
    px: pd.DataFrame,
    score: pd.DataFrame,
    window: tuple[str, str],
    cost_model: CostModel = COST,
    config: PortfolioConfig = CONFIG,
    rebalance: str = "M",
) -> BacktestResult:
    return run_backtest(
        slice_w(px, window),
        slice_w(score, window),
        cost_model,
        config,
        rebalance=rebalance,
    )


def buy_and_hold(px: pd.DataFrame, window: tuple[str, str]) -> Metrics:
    """Equal-weight universe, one round trip in and out, net of the same costs.

    AGENT_BRIEF sec.4 rule 5 specifies ``panel.pct_change().mean(axis=1)``. One buy at
    the start and one sell at the end is exactly one complete rotation, so the charge
    is ``all_in_round_trip_bps`` -- the same number the engine charges per rotation.
    """
    p = slice_w(px, window)
    r = p.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    # Same per-position notional the engine uses (REF_POSITION_NOTIONAL = Rs 1,00,000),
    # so the flat DP charge bites identically on both sides of the comparison.
    rate = float(COST.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    equity = (1.0 + r).cumprod() * (1.0 - rate)
    daily = equity.pct_change(fill_method=None).fillna(0.0)
    daily.iloc[0] = equity.iloc[0] - 1.0
    return compute_metrics(daily, equity)


def composite_score(px: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(px)


def random_control(
    px: pd.DataFrame,
    liveness: float,
    window: tuple[str, str],
    seed: int,
    mode: str = "gate",
) -> BacktestResult:
    """Negative control: a coin flip with the same fraction of bars long.

    ``gate`` -- random 0/1 gate on the *same* 6m-momentum score, i.e. the honest
    version of "replace my EMA signal with noise". ``score`` -- a fully random score
    with no momentum in it at all, which is the stricter floor.
    """
    rng = np.random.default_rng(seed)
    shape = px.shape
    draw = rng.random(shape) < liveness
    if mode == "gate":
        fake_sig = pd.DataFrame(
            np.where(draw, 1.0, np.nan), index=px.index, columns=px.columns
        )
        score = build_score(px, fake_sig)
    elif mode == "score":
        score = pd.DataFrame(
            np.where(draw, rng.random(shape), np.nan), index=px.index, columns=px.columns
        )
    else:  # pragma: no cover
        raise ValueError(mode)
    return run(px, score, window)


def row(name: str, m: Metrics, res: BacktestResult | None = None, extra: str = "") -> dict:
    d = {
        "name": name,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "vol": m.volatility,
        "total": m.total_return,
        "winrate": m.win_rate,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "trades_y": m.trades_per_year,
        "avg_names": res.diag["avg_names"] if res is not None else float("nan"),
        "extra": extra,
    }
    return d


def table(rows: list[dict]) -> str:
    hdr = (
        f"{'name':<26}{'CAGR':>9}{'Sharpe':>8}{'Sortino':>8}{'MaxDD':>9}"
        f"{'Calmar':>8}{'Turn':>7}{'CostDrag':>10}{'Names':>7}"
    )
    lines = [hdr, "-" * len(hdr)]
    for r in rows:
        lines.append(
            f"{r['name']:<26}{r['cagr'] * 100:>8.2f}%{r['sharpe']:>8.2f}"
            f"{r['sortino']:>8.2f}{r['maxdd'] * 100:>8.2f}%{r['calmar']:>8.2f}"
            f"{r['turnover']:>7.2f}{r['cost_drag'] * 100:>9.2f}%{r['avg_names']:>7.1f}"
        )
    return "\n".join(lines)


def yearly(returns: pd.Series) -> str:
    yr = yearly_returns(returns)
    return "  ".join(f"{int(y)}:{v * 100:>7.2f}%" for y, v in yr.items())
