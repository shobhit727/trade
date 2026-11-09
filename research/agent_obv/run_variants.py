"""Walk the 5 declared variants over TRAIN, then TEST once.

Construction (declared, identical for every variant):
  * `obv_chg_n(t) = OBV(t) - OBV(t - n)`  -- trailing OBV change, point-in-time
  * long where `obv_chg_n > 0`; rank the long names by `obv_chg_n` (cross-sectional
    percentile); NaN elsewhere so the book never holds a name the variant says no to.
  * monthly rebalance, default PortfolioConfig. `run_backtest` holds weights from t+1.

Mode `--split train` runs TRAIN only. `--split test` runs TEST only. They are separate
invocations so that TEST is genuinely touched once, after TRAIN is frozen to disk.
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_obv")

from data_prep import load, obv_matrix, split_test, split_train  # noqa: E402

from nsealgo.backtest.engine import (  # noqa: E402
    ENGINE_SHA,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

VARIANTS = {
    "V1_obv_n1_shipped": 1,
    "V2_obv_n5": 5,
    "V3_obv_n20": 20,
    "V4_obv_n63": 63,
    "V5_obv_n126": 126,
}

OUT = "research/agent_obv"


def build_score(panel: pd.DataFrame, vol_panel: pd.DataFrame, n: int) -> pd.DataFrame:
    """Point-in-time cross-sectional score from the OBV change over `n` bars."""
    obv = obv_matrix(panel, vol_panel)
    chg = obv - obv.shift(n)
    long_mask = chg > 0
    score = chg.where(long_mask)
    return score.rank(axis=1, pct=True, na_option="keep")


def run(panel, score, label, model=None, rebalance="M"):
    cfg = PortfolioConfig()
    model = model or CostModel(segment="delivery", slippage_bps=5)
    res = run_backtest(panel, score, model, cfg, rebalance=rebalance)
    m = res.metrics
    return {
        "label": label,
        "engine_sha": res.engine_sha,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "calmar": m.calmar,
        "max_drawdown": m.max_drawdown,
        "max_drawdown_days": m.max_drawdown_days,
        "volatility": m.volatility,
        "total_return": m.total_return,
        "win_rate": m.win_rate,
        "annual_turnover": m.annual_turnover,
        "cost_drag_annual": m.cost_drag_annual,
        "trades_per_year": m.trades_per_year,
        "avg_names": res.diag["avg_names"],
        "avg_top_weight": res.diag["avg_top_weight"],
        "n_rebalances": res.diag["n_rebalances"],
        "n_periods": m.n_periods,
        "costs_paid_rupees": res.costs_paid,
    }


def buy_and_hold(panel: pd.DataFrame) -> dict:
    """Equal-weight universe hold, net of one full round trip (in + out)."""
    r = panel.pct_change(fill_method=None).fillna(0.0)
    r = r.iloc[1:]
    model = CostModel(segment="delivery", slippage_bps=5)
    rt = float(model.all_in_round_trip_bps(__import__("decimal").Decimal("100000"))) / 10_000.0
    from nsealgo.backtest.metrics import compute_metrics, yearly_returns

    daily = r.mean(axis=1)
    eq_gross = (1 + daily).cumprod()
    # charge the round trip once, at the start (buy) and once at the end (sell)
    eq = eq_gross * (1 - rt) ** 2
    m = compute_metrics(eq.pct_change(fill_method=None).fillna(0.0), eq,
                        annual_turnover=0.0, cost_drag_annual=2 * rt * 244 / len(eq),
                        trades_per_year=0.0)
    yr = yearly_returns(eq.pct_change(fill_method=None).fillna(0.0))
    return {
        "label": "buy_and_hold_equal_weight",
        "engine_sha": "n/a (not run_backtest)",
        "cagr": m.cagr, "sharpe": m.sharpe, "sortino": m.sortino, "calmar": m.calmar,
        "max_drawdown": m.max_drawdown, "max_drawdown_days": m.max_drawdown_days,
        "volatility": m.volatility, "total_return": m.total_return,
        "win_rate": m.win_rate, "annual_turnover": 0.0,
        "cost_drag_annual": m.cost_drag_annual, "trades_per_year": 0.0,
        "avg_names": float((panel.iloc[1:].notna()).sum(axis=1).mean()),
        "avg_top_weight": float(1.0 / panel.shape[1]),
        "n_rebalances": 1, "n_periods": m.n_periods, "costs_paid_rupees": float("nan"),
        "yearly": {str(k): float(v) for k, v in yr.items()},
    }


def composite_bench(panel: pd.DataFrame) -> dict:
    sc = build_composite_score(panel)
    return run(panel, sc, "nsealgo_composite")


def fmt(rows: list[dict]) -> str:
    hdr = (f"{'label':<26}{'CAGR%':>9}{'Sharpe':>8}{'MaxDD%':>9}{'Calmar':>8}"
           f"{'Turn/y':>8}{'Cost/y%':>9}{'Names':>7}{'TotRet%':>9}")
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        out.append(
            f"{r['label']:<26}{r['cagr'] * 100:>9.2f}{r['sharpe']:>8.2f}"
            f"{r['max_drawdown'] * 100:>9.2f}{r['calmar']:>8.2f}"
            f"{r['annual_turnover']:>8.2f}{r['cost_drag_annual'] * 100:>9.2f}"
            f"{r['avg_names']:>7.1f}{r['total_return'] * 100:>9.1f}"
        )
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "test"], required=True)
    args = ap.parse_args()

    panel, vol_panel = load()
    split = split_train if args.split == "train" else split_test
    p = split(panel)
    vp = split(vol_panel)

    print(f"=== {args.split.upper()}  {p.index[0].date()} -> {p.index[-1].date()}  "
          f"({len(p)} bars, {p.shape[1]} symbols) ===")
    print(f"engine_sha = {ENGINE_SHA}\n")

    rows = []
    for label, n in VARIANTS.items():
        sc = build_score(p, vp, n)
        live = float((sc.notna()).sum(axis=1).mean())
        rows.append(run(p, sc, f"{label}[live={live:.1f}]"))

    rows.append(buy_and_hold(p))
    rows.append(composite_bench(p))

    print(fmt(rows))

    # cost sensitivity, reported for the TRAIN-frozen best variant only if given
    tag = f"{args.split}"
    with open(f"{OUT}/results_{tag}.json", "w") as fh:
        json.dump({"engine_sha": ENGINE_SHA, "split": tag,
                   "span": [str(p.index[0].date()), str(p.index[-1].date())],
                   "rows": rows}, fh, indent=2)
    print(f"\nwrote {OUT}/results_{tag}.json")


if __name__ == "__main__":
    main()

