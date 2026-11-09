"""Run the 5 declared MFI variants on TRAIN and TEST, plus every control.

No variant may be added here — the budget was declared in REPORT.md §3.1 before any of
this ran. Every result carries the engine SHA it was produced under.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_mfi")

from data_prep import TEST_END, TEST_START, TRAIN_END, TRAIN_START, load_all  # noqa: E402
from mfi_lib import mfi_panel, signal_panel  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

#: Declared in REPORT.md §3.1. Exactly five. Do not add a sixth.
VARIANTS: dict[str, tuple[int, float]] = {
    "V1_mfi_p14_l20": (14, 20.0),   # shipped
    "V2_mfi_p14_l30": (14, 30.0),
    "V3_mfi_p14_l40": (14, 40.0),
    "V4_mfi_p28_l30": (28, 30.0),
    "V5_mfi_p9_l30": (9, 30.0),
}

MOM_LOOKBACK = 126  # brief §5, trailing momentum used to rank the signalled names
BASE_COST = CostModel(segment="delivery", slippage_bps=5)
ZERO_COST = CostModel(segment="delivery", slippage_bps=0.0)


def build_score(panel: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Brief §5 construction, verbatim: rank the signalled names by trailing momentum.

    `panel.shift(126)` is a *past* value, so the score on day t uses data through t only.
    Names not flagged get NaN and are dropped from the book.
    """
    mom = panel / panel.shift(MOM_LOOKBACK) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def build_random_score(panel: pd.DataFrame, sig: pd.DataFrame, seed: int,
                       dates: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Random book matching `sig`'s count of long names on each rebalance date.

    `run_backtest` reads the score **only** at rebalance dates (`build_rebalance_weights`
    is called on `sc.loc[rb]`), so scores elsewhere are never observed. Populating only
    those dates is therefore exactly equivalent to populating every date, and is ~50x
    cheaper — which is what makes 50 random draws per variant affordable.

    The count is matched **on the rebalance dates**, not on all days, because that is
    where the real strategy's book is actually decided. Matching on all days would
    control for something the engine never reads.

    Guarded against the silent-failure mode recorded as bug B2 in `agent_obv`: the frame
    is built on `panel.index` (never a bare ndarray's RangeIndex) and `run_backtest` is
    asserted to have produced a non-zero number of rebalances.
    """
    rng = np.random.default_rng(seed)
    if dates is None:
        from nsealgo.backtest.engine import _rebalance_dates

        dates = pd.DatetimeIndex(
            [d for d in _rebalance_dates(panel.index, "M") if d in sig.index][1:]
        )
    counts = sig.sum(axis=1)
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    n_cols = len(panel.columns)
    for dt in dates:
        k = int(counts.loc[dt])
        if k <= 0:
            continue
        cols = rng.choice(n_cols, size=min(k, n_cols), replace=False)
        out.loc[dt, panel.columns[cols]] = rng.permutation(np.linspace(0.01, 1.0, len(cols)))
    return out


def buy_and_hold(panel: pd.DataFrame, index: pd.DatetimeIndex) -> dict:
    """Brief §5 buy-and-hold: equal-weight universe return, net of one round trip.

    The engine charges `sum|dW| * rate`, so a full buy plus a full sell is
    `2 * 21.92bps = 43.84bps` of total turnover. Buy-and-hold pays that once, at the two
    ends of the window; it is deducted as a single multiplicative haircut so no day is
    penalised for a cost that was paid only at entry and exit.
    """
    sub = panel.loc[index]
    r = sub.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    r = r.iloc[1:]
    rt = float(BASE_COST.all_in_round_trip_bps(100_000))
    haircut = 2.0 * rt / 10_000.0
    eq = (1.0 + r).cumprod() * (1.0 - haircut)
    eq = eq / eq.iloc[0]
    years = len(eq) / 244.0
    return {
        "cagr": float(eq.iloc[-1] ** (1.0 / years) - 1.0),
        "metrics": compute_metrics(r, eq),
        "returns": r,
        "equity": eq,
        "cost_haircut": haircut,
    }


def bh_through_engine(panel: pd.DataFrame, index: pd.DatetimeIndex) -> dict:
    """Buy-and-hold through `run_backtest`, same machinery as the strategy rows.

    All 48 names, inverse-vol scaled, 10% cash, caps relaxed so nothing is clipped. This
    isolates *selection* from *weighting*: every strategy row uses the same inverse-vol
    scheme, so any difference is attributable to which names were chosen.
    """
    cfg = PortfolioConfig(
        n_positions=len(panel.columns), max_weight=0.90, max_sector_weight=1.0,
        cash_buffer=0.10, turnover_budget=1.0, max_names=len(panel.columns),
    )
    score = pd.DataFrame(1.0, index=index, columns=panel.columns)
    res = run_backtest(panel.loc[index], score, BASE_COST, config=cfg, rebalance="M")
    if res.diag["n_rebalances"] == 0:
        raise RuntimeError("buy-and-hold produced zero rebalances — index mismatch")
    return res


def run_one(panel, index, score, cost=BASE_COST, config=None):
    cfg = config or PortfolioConfig()
    res = run_backtest(panel.loc[index], score, cost, config=cfg, rebalance="M")
    if res.diag["n_rebalances"] == 0:
        raise RuntimeError("zero rebalances — score index did not intersect panel index")
    return res


def summarise(name, res) -> dict:
    m = res.metrics
    return {
        "name": name,
        "engine_sha": res.engine_sha,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "max_drawdown": m.max_drawdown,
        "calmar": m.calmar,
        "total_return": m.total_return,
        "vol": m.volatility,
        "win_rate": m.win_rate,
        "turnover": m.annual_turnover,
        "cost_drag": m.cost_drag_annual,
        "avg_names": res.diag["avg_names"],
        "rt_bps": res.diag["round_trip_bps"],
        "n_rebalances": res.diag["n_rebalances"],
    }


def main() -> None:
    panel, syms, rep, close, high, low, vol, _ = load_all()
    out: dict = {"variants": {}, "index": {}}

    windows = {
        "TRAIN": (panel.loc[TRAIN_START:TRAIN_END].index),
        "TEST": (panel.loc[TEST_START:TEST_END].index),
    }

    # ---- MFI panels (one per declared lookback) ----
    mfi = {}
    for p in sorted({p for p, _ in VARIANTS.values()}):
        mfi[p] = mfi_panel(high, low, close, vol, p)
    out["index"] = {"train_start": str(windows["TRAIN"][0].date()),
                    "train_end": str(windows["TRAIN"][-1].date()),
                    "train_bars": len(windows["TRAIN"]),
                    "test_start": str(windows["TEST"][0].date()),
                    "test_end": str(windows["TEST"][-1].date()),
                    "test_bars": len(windows["TEST"])}

    for wname, index in windows.items():
        rows = {}
        for vname, (p, lo) in VARIANTS.items():
            sig = signal_panel(mfi[p], lo)
            score = build_score(panel, sig)
            res = run_one(panel, index, score)
            rows[vname] = summarise(vname, res)
            rows[vname]["yearly"] = {
                str(k): float(v) for k, v in yearly_returns(res.returns).items()}

        # ---- controls ----
        bh = buy_and_hold(panel, index)
        rows["BH_equalwt_brief"] = {
            "name": "BH_equalwt_brief", "engine_sha": "n/a",
            "cagr": bh["cagr"], "sharpe": bh["metrics"].sharpe,
            "sortino": bh["metrics"].sortino,
            "max_drawdown": bh["metrics"].max_drawdown,
            "calmar": bh["metrics"].calmar,
            "total_return": bh["metrics"].total_return,
            "vol": bh["metrics"].volatility, "win_rate": bh["metrics"].win_rate,
            "turnover": 0.0, "cost_drag": bh["cost_haircut"] / max(bh["metrics"].n_periods / 244.0, 1e-9),
            "bh_total_cost_haircut": bh["cost_haircut"],
            "avg_names": float(len(panel.columns)),
            "rt_bps": float(BASE_COST.all_in_round_trip_bps(100_000)),
            "n_rebalances": 0,
            "yearly": {str(k): float(v) for k, v in yearly_returns(bh["returns"]).items()},
        }
        bhe = bh_through_engine(panel, index)
        rows["BH_engine_parity"] = summarise("BH_engine_parity", bhe)
        rows["BH_engine_parity"]["yearly"] = {
            str(k): float(v) for k, v in yearly_returns(bhe.returns).items()}

        comp = build_composite_score(panel.loc[index])
        resc = run_one(panel.loc[index], index, comp)
        rows["nsealgo_composite"] = summarise("nsealgo_composite", resc)
        rows["nsealgo_composite"]["yearly"] = {
            str(k): float(v) for k, v in yearly_returns(resc.returns).items()}

        out["variants"][wname] = rows

    with open("research/agent_mfi/results_main.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    for wname in ("TRAIN", "TEST"):
        print(f"\n===== {wname} =====")
        print(f"{'run':22s} {'CAGR%':>7s} {'Sharpe':>7s} {'MaxDD%':>8s} {'Calmar':>7s} "
              f"{'Turn/y':>7s} {'Cost/y%':>8s} {'Names':>6s} {'TotRet%':>8s}")
        for k, r in out["variants"][wname].items():
            print(f"{k:22s} {r['cagr']*100:7.2f} {r['sharpe']:7.2f} "
                  f"{r['max_drawdown']*100:8.2f} {r['calmar']:7.2f} {r['turnover']:7.2f} "
                  f"{r['cost_drag']*100:8.2f} {r['avg_names']:6.1f} {r['total_return']*100:8.1f}")


if __name__ == "__main__":
    main()
