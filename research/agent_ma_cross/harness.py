"""Harness for agent_ma_cross: MA-crossover on NSE NIFTY-50 daily bars.

Protocol is fixed in ../AGENT_BRIEF.md and declared in REPORT.md section 4.
Nothing here modifies src/.

Usage:
    .venv/bin/python research/agent_ma_cross/harness.py train     # TRAIN only
    .venv/bin/python research/agent_ma_cross/harness.py test      # TEST, once
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nsealgo.backtest.engine import (  # noqa: E402
    ENGINE_SHA,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import (  # noqa: E402
    build_composite_score,
    zscore_cross_sectional,
)

COSTS = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()

TRAIN = (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"),
         pd.Timestamp("2023-12-31", tz="Asia/Kolkata"))
TEST = (pd.Timestamp("2024-01-01", tz="Asia/Kolkata"),
        pd.Timestamp("2026-10-01", tz="Asia/Kolkata"))

# Declared in REPORT.md section 4. Order is the declaration order.
VARIANTS = ["V1_10_30_flag", "V2_20_60_flag", "V3_50_200_flag",
            "V4_20_60_strength", "V5_20_60_momrank"]
WINDOWS = {"V1_10_30_flag": (10, 30), "V2_20_60_flag": (20, 60),
           "V3_50_200_flag": (50, 200), "V4_20_60_strength": (20, 60),
           "V5_20_60_momrank": (20, 60)}


# --------------------------------------------------------------------------- #
# Signal construction -- all trailing, no lookahead
# --------------------------------------------------------------------------- #

def ma_cross_score(panel: pd.DataFrame, fast: int, slow: int, kind: str) -> pd.DataFrame:
    """Turn the per-symbol +1/0/-1 MA-cross signal into a cross-sectional score.

    The catalog signal is *binary*: it says whether a name is in an uptrend, and says
    nothing about which of the uptrending names to prefer. Three constructions:

    ``flag``      score 1.0 where the flag fires, NaN elsewhere. Ties are broken by the
                  engine's deterministic stable sort, i.e. column order -- a *neutral*
                  tie-break. Measures the uptrend filter in isolation.
    ``strength``  (SMA_fast - SMA_slow)/close, cross-sectionally z-scored and kept
                  only where the flag fires. Uses the magnitude of the cross.
    ``momrank``   trailing 126d return, percentile-ranked among the flagged names.
    """
    sma_f = panel.rolling(fast, min_periods=fast).mean()
    sma_s = panel.rolling(slow, min_periods=slow).mean()
    # Exactly the catalog rule: 0 when either SMA is undefined or the two are equal.
    both_defined = sma_f.notna() & sma_s.notna()
    flag = both_defined & (sma_f > sma_s)

    if kind == "flag":
        return flag.astype(float).where(flag)
    if kind == "strength":
        rel = (sma_f - sma_s) / panel
        z = zscore_cross_sectional(rel.where(flag))
        return z.where(flag)
    if kind == "momrank":
        mom = panel / panel.shift(126) - 1.0
        return mom.where(flag).rank(axis=1, pct=True, na_option="keep")
    raise ValueError(kind)


def random_among_flagged(panel: pd.DataFrame, score: pd.DataFrame,
                        seed: int) -> pd.DataFrame:
    """Control B: keep the *exact* same flagged names, break ties at random.

    This is the tightest control available -- it holds the strategy's uptrend filter
    fixed and randomises only the ranking, so any difference is attributable to the
    ranking alone.
    """
    rng = np.random.default_rng(seed)
    ranked = score.where(score.notna())
    noise = pd.DataFrame(rng.random(ranked.shape), index=ranked.index,
                         columns=ranked.columns)
    # High score wins, so invert: keep names whose random draw beats their own peers.
    out = noise.where(ranked.notna())
    return out


def random_mask(panel: pd.DataFrame, target: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Control A (brief 6.5): an independent coin flip per name per day, matched to
    the strategy's fraction of bars long."""
    rng = np.random.default_rng(seed)
    p = float(target.notna().to_numpy().mean())
    draw = rng.random(panel.shape) < p
    m = pd.DataFrame(draw, index=panel.index, columns=panel.columns)
    return m.astype(float)


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #

def buy_and_hold(panel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Equal-weight universe held for the whole window, net of one full round trip.

    Brief 4.5 specifies `panel.pct_change().mean(axis=1)`. The single round trip
    (buy at the open of the window, sell at its close) is charged at the same
    all-in rate `run_backtest` uses, so the comparison is like-for-like.
    """
    r = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rate = float(COSTS.all_in_round_trip_bps(100_000)) / 10_000.0
    net = r.copy()
    net.iloc[0] -= rate  # one round trip, paid once
    return net, (1.0 + net).cumprod()


def _m(net: pd.Series, eq: pd.Series) -> dict:
    mt = compute_metrics(net, eq)
    return {"cagr": mt.cagr, "sharpe": mt.sharpe, "maxdd": mt.max_drawdown,
            "calmar": mt.calmar, "vol": mt.volatility, "total": mt.total_return,
            "sortino": mt.sortino}


# --------------------------------------------------------------------------- #

def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "train"
    lo, hi = TRAIN if stage == "train" else TEST

    panel, symbols, _ = load_universe("data/nse")
    p = panel.loc[lo:hi]
    print(f"[{stage}] window {lo.date()} -> {hi.date()}   "
          f"bars={len(p)}  symbols={p.shape[1]}")
    print(f"[{stage}] engine_sha={ENGINE_SHA}")

    rows = []
    for name in VARIANTS:
        fast, slow = WINDOWS[name]
        kind = "flag" if name.endswith("_flag") else (
            "strength" if name.endswith("_strength") else "momrank")
        sc = ma_cross_score(panel, fast, slow, kind).loc[lo:hi]
        # Liveness = fraction of (bar, symbol) cells the strategy actually holds a
        # name in. `notna`, not `>0`: the strength score is a z-score and can be
        # negative while still being a live position.
        live = float(sc.notna().to_numpy().mean())
        res = run_backtest(p, sc, COSTS, CFG, rebalance="M")
        r = _m(res.returns, res.equity)
        r["variant"] = name
        r["live_frac"] = live
        r["avg_names"] = res.diag["avg_names"]
        r["turnover"] = res.metrics.annual_turnover
        r["cost_drag"] = res.metrics.cost_drag_annual
        r["trades_y"] = res.metrics.trades_per_year
        r["engine_sha"] = res.engine_sha
        rows.append(r)
        print(f"  {name:<20} CAGR {r['cagr']*100:7.2f}%  Sh {r['sharpe']:6.2f}  "
              f"MaxDD {r['maxdd']*100:7.2f}%  Calmar {r['calmar']:6.2f}  "
              f"live {live*100:5.1f}%  names {r['avg_names']:4.1f}  "
              f"turn {r['turnover']:5.2f}x")

    bh_r, bh_eq = buy_and_hold(p)
    bh = _m(bh_r, bh_eq)
    print(f"  {'BUY_AND_HOLD':<20} CAGR {bh['cagr']*100:7.2f}%  Sh {bh['sharpe']:6.2f}  "
          f"MaxDD {bh['maxdd']*100:7.2f}%  Calmar {bh['calmar']:6.2f}")

    comp = build_composite_score(panel).loc[lo:hi]
    cres = run_backtest(p, comp, COSTS, CFG, rebalance="M")
    cm = _m(cres.returns, cres.equity)
    print(f"  {'COMPOSITE':<20} CAGR {cm['cagr']*100:7.2f}%  Sh {cm['sharpe']:6.2f}  "
          f"MaxDD {cm['maxdd']*100:7.2f}%  Calmar {cm['calmar']:6.2f}")

    if stage == "train":
        print("\n  yearly returns, V2_20_60_flag:")
        sc2 = ma_cross_score(panel, 20, 60, "flag").loc[lo:hi]
        r2 = run_backtest(p, sc2, COSTS, CFG, rebalance="M")
        yr = yearly_returns(r2.returns) * 100
        print("   " + "  ".join(f"{i}:{v:+.1f}" for i, v in yr.items()))
        print("  yearly returns, buy&hold:")
        yrb = yearly_returns(bh_r) * 100
        print("   " + "  ".join(f"{i}:{v:+.1f}" for i, v in yrb.items()))

    out = pd.DataFrame(rows)
    Path(f"research/agent_ma_cross/results_{stage}.csv").write_text(
        out.to_csv(index=False))
    print(f"\n  wrote research/agent_ma_cross/results_{stage}.csv")


if __name__ == "__main__":
    main()
