"""Harness for agent_regression: SMA-distance trend filter on NSE NIFTY-50 daily bars.

Protocol fixed in ../AGENT_BRIEF.md; 5-variant budget declared in ../REPORT.md §4.

What the catalog strategy actually computes (see REPORT.md §1 / finding F1):
    signal = +1 if close > SMA(period) else -1,  0 only during warm-up
There is no regression in it. `period` is the only parameter.

Usage:
    .venv/bin/python research/agent_regression/harness.py train   # TRAIN only
    .venv/bin/python research/agent_regression/harness.py test    # TEST, once
    .venv/bin/python research/agent_regression/harness.py controls <variant>
"""

from __future__ import annotations

import json
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
from nsealgo.factors.core import build_composite_score, zscore_cross_sectional  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

HERE = Path("research/agent_regression")

COSTS = CostModel(segment="delivery", slippage_bps=5)
ZERO_COST = CostModel(segment="delivery", slippage_bps=0.0)
CFG = PortfolioConfig()

TRAIN = (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"),
         pd.Timestamp("2023-12-31", tz="Asia/Kolkata"))
TEST = (pd.Timestamp("2024-01-01", tz="Asia/Kolkata"),
        pd.Timestamp("2026-10-01", tz="Asia/Kolkata"))

# Declared in REPORT.md section 4, in declaration order. Do not add entries.
VARIANTS = {
    "V1_p20_flag":     (20,  "flag"),
    "V2_p50_flag":     (50,  "flag"),
    "V3_p200_flag":    (200, "flag"),
    "V4_p50_momrank":  (50,  "momrank"),
    "V5_p20_strength": (20,  "strength"),
}


# --------------------------------------------------------------------------- #
# Signal -> cross-sectional score. Every input is trailing; no lookahead.
# --------------------------------------------------------------------------- #

def sma_flag(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """The catalog rule exactly: 1.0 where close > SMA(period), NaN elsewhere.

    `rolling(period).mean()` needs `period` bars, which is what `sma()`'s
    `len(values) < period -> nan` guard encodes, so the warm-up matches.
    """
    m = panel.rolling(period, min_periods=period).mean()
    flag = panel > m
    return flag.astype(float).where(flag)


def regression_score(panel: pd.DataFrame, period: int, kind: str) -> pd.DataFrame:
    """Turn the per-symbol +-1 flag into a cross-sectional score.

    ``flag``      constant 1.0 on flagged names. The engine breaks ties with a
                  stable argsort, i.e. column order, so this measures the filter
                  alone with a *neutral* (alphabetical) tie-break.
    ``momrank``   126d trailing return, percentile-ranked among flagged names.
    ``strength``  (close - SMA)/close, cross-sectionally z-scored, flagged only.
    """
    flag = sma_flag(panel, period)

    if kind == "flag":
        return flag

    if kind == "momrank":
        mom = panel / panel.shift(126) - 1.0
        # rank within the flagged subset only: mask first, then rank.
        ranked = mom.where(flag > 0)
        return ranked.rank(axis=1, pct=True, na_option="keep")

    if kind == "strength":
        m = panel.rolling(period, min_periods=period).mean()
        rel = (panel - m) / panel
        z = zscore_cross_sectional(rel.where(flag > 0))
        return z.where(flag > 0)

    raise ValueError(kind)


# --------------------------------------------------------------------------- #
# Controls
# --------------------------------------------------------------------------- #

def random_mask(panel: pd.DataFrame, target: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Brief 6.5: independent coin flip per name per day, matched to the target's
    fraction of bars long. `notna` cells = positions the strategy would hold."""
    rng = np.random.default_rng(seed)
    p = float(target.notna().to_numpy().mean())
    draw = rng.random(panel.shape) < p
    return pd.DataFrame(draw, index=panel.index, columns=panel.columns).astype(float)


def buy_and_hold(panel: pd.DataFrame, cost_model: CostModel = COSTS):
    """Equal-weight universe over the window, net of one all-in round trip.

    Brief 4.5 specifies `panel.pct_change().mean(axis=1)`. The single round trip
    is charged at the same all-in rate `run_backtest` uses, so it is like-for-like.
    """
    r = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rate = float(cost_model.all_in_round_trip_bps(100_000)) / 10_000.0
    net = r.copy()
    net.iloc[0] -= rate
    return net, (1.0 + net).cumprod()


def _m(net: pd.Series, eq: pd.Series) -> dict:
    mt = compute_metrics(net, eq)
    return {
        "cagr": mt.cagr, "sharpe": mt.sharpe, "maxdd": mt.max_drawdown,
        "calmar": mt.calmar, "vol": mt.volatility, "total": mt.total_return,
        "sortino": mt.sortino,
    }


def _row(name, res, live, cost_model=None):
    d = _m(res.returns, res.equity)
    d["variant"] = name
    d["live_frac"] = live
    d["avg_names"] = res.diag["avg_names"]
    d["turnover"] = res.metrics.annual_turnover
    d["cost_drag"] = res.metrics.cost_drag_annual
    d["trades_y"] = res.metrics.trades_per_year
    d["rt_bps"] = res.diag["round_trip_bps"]
    d["engine_sha"] = res.engine_sha
    return d


def _print(name, r):
    print(f"  {name:<22} CAGR {r['cagr']*100:7.2f}%  Sh {r['sharpe']:6.2f}  "
          f"MaxDD {r['maxdd']*100:7.2f}%  Calmar {r['calmar']:6.2f}  "
          f"live {r['live_frac']*100:5.1f}%  names {r.get('avg_names', float('nan')):4.1f}  "
          f"turn {r.get('turnover', float('nan')):5.2f}x")


# --------------------------------------------------------------------------- #

def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "train"
    if stage not in ("train", "test"):
        raise SystemExit("stage must be train|test")

    panel, _symbols, _rep = load_universe("data/nse")
    lo, hi = TRAIN if stage == "train" else TEST
    p = panel.loc[lo:hi]
    print(f"[{stage}] {lo.date()} -> {hi.date()}  bars={len(p)}  syms={p.shape[1]}")
    print(f"[{stage}] engine_sha={ENGINE_SHA}  prov={json.dumps(provenance())}")
    print(f"[{stage}] rt_bps(1e5) all_in={float(COSTS.all_in_round_trip_bps(100_000)):.2f}"
          f"  zero={float(ZERO_COST.all_in_round_trip_bps(100_000)):.2f}")

    rows = []
    for name, (period, kind) in VARIANTS.items():
        sc = regression_score(panel, period, kind).loc[lo:hi]
        live = float(sc.notna().to_numpy().mean())
        res = run_backtest(p, sc, COSTS, CFG, rebalance="M")
        r = _row(name, res, live)
        rows.append(r)
        _print(name, r)

    bh_r, bh_eq = buy_and_hold(p)
    bh = _m(bh_r, bh_eq)
    bh["variant"] = "BUY_AND_HOLD"
    print(f"  {'BUY_AND_HOLD':<22} CAGR {bh['cagr']*100:7.2f}%  Sh {bh['sharpe']:6.2f}  "
          f"MaxDD {bh['maxdd']*100:7.2f}%  Calmar {bh['calmar']:6.2f}")

    comp = build_composite_score(panel).loc[lo:hi]
    cres = run_backtest(p, comp, COSTS, CFG, rebalance="M")
    cm = _row("COMPOSITE", cres, float(comp.notna().to_numpy().mean()))
    print(f"  {'COMPOSITE':<22} CAGR {cm['cagr']*100:7.2f}%  Sh {cm['sharpe']:6.2f}  "
          f"MaxDD {cm['maxdd']*100:7.2f}%  Calmar {cm['calmar']:6.2f}  "
          f"names {cm['avg_names']:4.1f}")

    # --- sanity: avg names held. 48 means residuals are accumulating.
    print("\n  [sanity] avg names held per variant (target ~22, max_names 30):")
    for r in rows:
        flag = "  <-- TOO MANY" if r["avg_names"] > 26 else ""
        print(f"    {r['variant']:<22} {r['avg_names']:5.1f}{flag}")

    out = pd.DataFrame(rows)
    out.to_csv(HERE / f"results_{stage}.csv", index=False)

    payload = {
        "stage": stage, "window": [str(lo.date()), str(hi.date())],
        "variants": rows, "buy_and_hold": bh, "composite": cm,
        "provenance": provenance(), "engine_sha": ENGINE_SHA,
    }
    (HERE / f"results_{stage}.json").write_text(json.dumps(payload, indent=2, default=str))

    # --- yearly returns for the leading TRAIN variant (informational only)
    lead = max(rows, key=lambda r: r["sharpe"])["variant"] if stage == "train" else None
    if lead:
        period, kind = VARIANTS[lead]
        sc = regression_score(panel, period, kind).loc[lo:hi]
        res = run_backtest(p, sc, COSTS, CFG, rebalance="M")
        yr = yearly_returns(res.returns) * 100
        print(f"\n  yearly returns, TRAIN leader {lead}:")
        print("    " + "  ".join(f"{i}:{v:+.1f}" for i, v in yr.items()))
        print("    % of years positive: "
              f"{float((yr > 0).mean())*100:.0f}%  ({int((yr>0).sum())}/{len(yr)})")
        print("  yearly returns, buy&hold:")
        yrb = yearly_returns(bh_r) * 100
        print("    " + "  ".join(f"{i}:{v:+.1f}" for i, v in yrb.items()))

    print(f"\n  wrote {HERE}/results_{stage}.csv and .json")


if __name__ == "__main__":
    main()
