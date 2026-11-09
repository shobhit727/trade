"""Data load + stochastic signal construction + TRAIN sweep.

Everything here is TRAIN-only. TEST is not touched by this script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import (  # noqa: E402
    ENGINE_SHA,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

OUT = Path(__file__).resolve().parent

TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"


# --------------------------------------------------------------------------- #
# Stochastic %K, vectorised, point-in-time
# --------------------------------------------------------------------------- #


def stoch_k_panel(
    high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, period: int
) -> pd.DataFrame:
    """%K = (close - LL_period) / (HH_period - LL_period) * 100, per column.

    Trailing window includes day *t*. Matches `indicators.stochastic` exactly
    (which takes max/min of the last `period` values, i.e. including today).
    """
    hh = high.rolling(period, min_periods=period).max()
    ll = low.rolling(period, min_periods=period).min()
    rng = (hh - ll).replace(0.0, np.nan)
    k = (close - ll) / rng * 100.0
    # indicators.stochastic returns 50.0 when hh == ll; reproduce that.
    return k.where(~((hh - ll) == 0.0) | hh.isna(), 50.0)


def signal_panel(k: pd.DataFrame, lower: float, upper: float) -> pd.DataFrame:
    """The catalog's +1/-1/0 state, exactly as `StochasticStrategy.signal` emits.

    `StochasticStrategy.signal` is an ``if / if`` chain, so the FIRST matching
    branch wins: ``k <= lower`` returns +1 even when the same bar would also
    satisfy ``k >= upper`` (which happens only in the degenerate ``upper <= lower``
    configuration). A chained ``.mask`` gets this backwards -- the second mask
    overwrites the first -- so the branches are applied in order and earlier ones
    are re-stamped afterwards.
    """
    sig = pd.DataFrame(0.0, index=k.index, columns=k.columns)
    sig = sig.mask(k.isna(), 0.0)
    # Order matters: `if k <= lower: return 1` is checked FIRST in the catalog.
    sig = sig.mask(k >= upper, -1.0)
    sig = sig.mask(k <= lower, 1.0)
    return sig


def build_score(raw: pd.DataFrame) -> pd.DataFrame:
    """Rank a raw panel cross-sectionally, NaN-preserving.

    Callers pass a panel that is already NaN on non-signalled names, so the
    rank is computed *among signalled names only* and un-signalled stay NaN,
    which `build_rebalance_weights` treats as ineligible.
    """
    return raw.rank(axis=1, pct=True, na_option="keep")


def main() -> None:
    print(f"[engine_sha] {ENGINE_SHA}")

    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"symbols={len(symbols)}  bars={len(panel)}")
    print(f"span {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"NaN close cells: {int(panel.isna().sum().sum())}")

    # --- high/low panels, aligned to the close panel exactly ------------------
    # Reuse the loader per symbol so high/low get the SAME cleaning (C1-C8).
    from nsealgo.data.loader import load_symbol

    highs, lows = {}, {}
    for s in symbols:
        df = load_symbol(f"data/nse/{s}_1d.csv", s)
        highs[s] = df["high"].rename(s)
        lows[s] = df["low"].rename(s)
    high = pd.DataFrame(highs).reindex(index=panel.index, columns=panel.columns)
    low = pd.DataFrame(lows).reindex(index=panel.index, columns=panel.columns)
    print(f"high NaN: {int(high.isna().sum().sum())}  low NaN: {int(low.isna().sum().sum())}")

    cm = CostModel(segment="delivery", slippage_bps=5)
    from decimal import Decimal

    rt = float(cm.round_trip_bps(Decimal("100000")))
    rt_all = float(cm.all_in_round_trip_bps(Decimal("100000")))
    print(f"round_trip_bps={rt}  all_in_round_trip_bps={rt_all}")

    cfg = PortfolioConfig()

    tr = panel.loc[TRAIN_START:TRAIN_END]
    print(f"\nTRAIN bars={len(tr)} {tr.index[0].date()} -> {tr.index[-1].date()}")

    variants = {
        "V1": dict(period=14, lower=20.0, upper=80.0),
        "V2": dict(period=5, lower=20.0, upper=80.0),
        "V3": dict(period=21, lower=20.0, upper=80.0),
        "V4": dict(period=14, lower=10.0, upper=80.0),
        "V5": dict(period=14, lower=30.0, upper=70.0),
    }

    results = {}
    for name, p in variants.items():
        k = stoch_k_panel(high, low, panel, p["period"])
        sig = signal_panel(k, p["lower"], p["upper"])
        depth = (p["lower"] - k).where(sig > 0)
        mom = (panel / panel.shift(126) - 1.0).where(sig > 0)
        for ctor, raw in (("depth", depth), ("momentum", mom)):
            score = build_score(raw)
            res = run_backtest(tr, score.loc[tr.index], cm, cfg, rebalance="M")
            m = res.metrics
            live = float((sig > 0).sum(axis=1).mean() / len(symbols))
            rec = dict(
                variant=name,
                params=p,
                construction=ctor,
                cagr=m.cagr,
                sharpe=m.sharpe,
                maxdd=m.max_drawdown,
                calmar=m.calmar,
                turnover=m.annual_turnover,
                cost_drag=m.cost_drag_annual,
                avg_names=res.diag["avg_names"],
                total_return=m.total_return,
                signal_liveness=live,
                engine_sha=res.engine_sha,
            )
            results[f"{name}:{ctor}"] = rec
            print(
                f"{name} {ctor:9s} CAGR {m.cagr*100:7.2f}%  Sh {m.sharpe:6.2f}  "
                f"DD {m.max_drawdown*100:7.2f}%  Cal {m.calmar:6.2f}  "
                f"TO {m.annual_turnover:4.2f}  drag {m.cost_drag_annual*100:5.2f}%  "
                f"names {res.diag['avg_names']:4.1f}  live {live*100:4.1f}%"
            )

    (OUT / "train_sweep.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
