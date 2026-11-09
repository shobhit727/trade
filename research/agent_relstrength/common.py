"""Shared harness for the relative_strength NSE study.

Point-in-time by construction: a signal at date *t* uses closes up to and including
*t* only. Signals are built on the FULL panel and then sliced to the window, so the
rolling warm-up is satisfied by pre-window history (which a live system would also
have) rather than by eating into the evaluation window.
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

#: Ranking horizon for the cross-sectional score. Fixed by the AGENT_BRIEF sec.5
#: recipe (6-month trailing momentum), never tuned -- see the declared budget.
RANK_DAYS = 126

COST = CostModel(segment="delivery", slippage_bps=5)
CONFIG = PortfolioConfig()

#: The five declared variants. Committed in REPORT.md section 1 before any run.
VARIANTS: list[dict] = [
    {"name": "V1 roc20 t0.5%", "period": 20, "threshold": 0.005},
    {"name": "V2 roc20 t3%", "period": 20, "threshold": 0.030},
    {"name": "V3 roc60 t3%", "period": 60, "threshold": 0.030},
    {"name": "V4 roc126 t8%", "period": 126, "threshold": 0.080},
    {"name": "V5 roc5 t0.5%", "period": 5, "threshold": 0.005},
]

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
# The strategy: roc(closes, period) vs threshold, lifted verbatim from the catalog
# --------------------------------------------------------------------------- #


def roc_panel(px: pd.DataFrame, period: int) -> pd.DataFrame:
    """``roc()`` from ``cryptobot.strategies.indicators``, vectorised.

    The catalog function is ``(closes[-1] - closes[-period-1]) / closes[-period-1]``,
    i.e. exactly ``px / px.shift(period) - 1``. It returns NaN when the history is
    shorter than ``period``, which vectorises to a NaN in the shifted base.
    """
    return px / px.shift(period) - 1.0


def build_signal(px: pd.DataFrame, period: int, threshold: float) -> pd.DataFrame:
    """1.0 where the ROC clears ``+threshold``; NaN everywhere else.

    Long-only translation of the catalog's +1/0/-1: both 0 (inside the band) and -1
    (below ``-threshold``) mean *not held*, which is a NaN in the score panel and
    therefore excluded from the book. NaN is not 0 -- a name the strategy did not
    choose and a name with no data are different things, and collapsing them is
    exactly how a residual-weight bug hides.
    """
    m = roc_panel(px, period)
    return m.where(m > threshold, other=np.nan)


def build_score(px: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional score: 6m trailing momentum, ranked among flagged names only.

    AGENT_BRIEF sec.5 recipe verbatim. ``na_option="keep"`` means the percentile is
    computed inside the signalled subset, so a name that is not flagged can never
    win the ranking.
    """
    mom = px / px.shift(RANK_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True, na_option="keep")


def signal_liveness(sig: pd.DataFrame, roc: pd.DataFrame, threshold: float) -> dict:
    """Liveness diagnostics straight off the catalog's own three-way branch."""
    s = sig.to_numpy(dtype=float)
    r = roc.to_numpy(dtype=float)
    ok = np.isfinite(r)
    return {
        "frac_bars_long": float((s[ok] > 0).mean()),
        "frac_bars_flat": float((np.abs(r[ok]) <= threshold).mean()),
        "frac_bars_short": float((r[ok] < -threshold).mean()),
        "mean_flagged_per_day": float(np.nansum(s > 0, axis=1).mean()),
        "min_flagged_per_day": float(np.nansum(s > 0, axis=1).min()),
        "days_zero_flagged": int((np.nansum(s > 0, axis=1) == 0).sum()),
    }


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


def win_mask(frame: pd.DataFrame, window: tuple[str, str]) -> pd.Series:
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
    """Equal-weight universe, one buy at the start and one sell at the end.

    AGENT_BRIEF sec.4 rule 5 specifies ``panel.pct_change().mean(axis=1)``. One buy
    at the start and one sell at the end is exactly one complete rotation, so the
    charge is ``all_in_round_trip_bps`` -- the same number the engine charges per
    rotation. (agent_cross_sectional BUGS.md B2 double-charged this; fixed there and
    not repeated here.)
    """
    p = slice_w(px, window)
    r = p.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
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

    ``gate``  -- random 0/1 gate on the *same* 6m-momentum score, i.e. the honest
    version of "replace my ROC signal with noise".
    ``score`` -- a fully random score with no momentum in it at all (stricter floor).
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


def row(name: str, m: Metrics, res: BacktestResult | None = None) -> dict:
    return {
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
        "maxdd_days": m.max_drawdown_days,
        "avg_names": res.diag["avg_names"] if res is not None else float("nan"),
        "max_top_weight": res.diag["avg_top_weight"] if res is not None else float("nan"),
        "n_rebalances": res.diag["n_rebalances"] if res is not None else float("nan"),
        "cost_paid": res.costs_paid if res is not None else float("nan"),
    }


def table(rows: list[dict]) -> str:
    hdr = (
        f"{'name':<24}{'CAGR':>9}{'Sharpe':>8}{'Sortino':>8}{'MaxDD':>9}"
        f"{'Calmar':>8}{'Turn':>7}{'Cost/y':>8}{'Names':>7}{'TopW':>7}"
    )
    lines = [hdr, "-" * len(hdr)]
    for r in rows:
        lines.append(
            f"{r['name']:<24}{r['cagr'] * 100:>8.2f}%{r['sharpe']:>8.2f}"
            f"{r['sortino']:>8.2f}{r['maxdd'] * 100:>8.2f}%{r['calmar']:>8.2f}"
            f"{r['turnover']:>7.2f}{r['cost_drag'] * 100:>7.2f}%{r['avg_names']:>7.1f}"
            f"{r['max_top_weight'] * 100:>6.2f}%"
        )
    return "\n".join(lines)


def yearly_series(returns: pd.Series) -> pd.Series:
    return yearly_returns(returns)


def yearly(returns: pd.Series) -> str:
    yr = yearly_returns(returns)
    return "  ".join(f"{int(y)}:{v * 100:>7.2f}%" for y, v in yr.items())


def variant(name: str) -> dict:
    for v in VARIANTS:
        if v["name"] == name:
            return v
    raise KeyError(name)
