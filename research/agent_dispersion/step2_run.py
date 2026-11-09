"""Step 2: declared parameter budget + TRAIN-then-TEST evaluation harness.

## PARAMETER BUDGET (declared BEFORE running, AGENT_BRIEF §4)

At most 5 distinct variants of the strategy. This is the complete list. Selection is
on TRAIN only; TEST is touched exactly once, at the end, with the selected variant
unchanged. `RESELECT_ON_TEST` is not implemented anywhere in this file by design.

| id | period | entry | rationale (all a priori, not fitted) |
|----|--------|-------|--------------------------------------|
| V1 |   30  | 1.00 | catalog default (DispersionConfig) |
| V2 |   20  | 2.00 | 2-sigma classic threshold, ~1 trading month |
| V3 |   60  | 0.50 | slower + much looser: longer trend, weaker gate |
| V4 |  120  | 0.25 | ~6 months, very loose gate |
| V5 |  250  | 1.00 | exactly one trading year of history in the SMA |

Deliberately NOT in the budget: any `(period, entry)` pair discovered by looking at
TEST performance, and any momentum-ranking window other than the brief's 126d.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_dispersion")

from signal import dispersion_score, dispersion_signal  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score, equal_weight_market  # noqa: E402

# --------------------------------------------------------------------------- #

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

MOM_DAYS = 126  # fixed by AGENT_BRIEF §5, not tuned

VARIANTS: list[dict] = [
    {"id": "V1", "period": 30, "entry": 1.00},
    {"id": "V2", "period": 20, "entry": 2.00},
    {"id": "V3", "period": 60, "entry": 0.50},
    {"id": "V4", "period": 120, "entry": 0.25},
    {"id": "V5", "period": 250, "entry": 1.00},
]

COST = CostModel(segment="delivery", slippage_bps=5)


def slice_window(panel: pd.DataFrame, start, end) -> pd.DataFrame:
    return panel.loc[(panel.index >= start) & (panel.index <= end)]


def build_score(panel: pd.DataFrame, period: int, entry: float) -> pd.DataFrame:
    """Score over the FULL history, then sliced.

    Expanding z-score is a path-dependent statistic, so it must be computed once
    over the whole panel (from 2008) and then windowed. Computing it inside the
    window would silently change the signal at the TRAIN/TEST boundary.
    """
    long_sig, _ = dispersion_signal(panel, period=period, entry=entry)
    return dispersion_score(panel, long_sig, mom_days=MOM_DAYS)


def run_variant(panel: pd.DataFrame, period: int, entry: float, lo, hi) -> dict:
    score_full = build_score(panel, period, entry)
    win = slice_window(panel, lo, hi)
    score = slice_window(score_full, lo, hi)

    res = run_backtest(win, score, COST, config=PortfolioConfig())
    m = res.metrics

    avg_names = float((res.weights > 1e-6).sum(axis=1).mean())
    years = len(res.returns) / 244

    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "turnover_yr": m.annual_turnover / years if years > 0 else 0.0,
        "cost_drag_annual": m.cost_drag_annual,
        "costs_paid": res.costs_paid,
        "avg_names": avg_names,
        "vol": m.volatility,
        "total_return": m.total_return,
        "_returns": res.returns,
        "_equity": res.equity,
    }


def buy_and_hold(panel: pd.DataFrame, lo, hi) -> dict:
    """Equal-weight buy-and-hold over the identical window, net of the same costs.

    One-time entry cost on the full book plus one-time exit cost, charged on
    compounding equity, using the same round-trip rate the engine uses.
    """
    win = slice_window(panel, lo, hi)
    r = equal_weight_market(win)
    eq = (1.0 + r.fillna(0.0)).cumprod()
    # charges: half the round trip on entry, half on exit
    rt = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0
    eq_net = eq * (1.0 - rt / 2.0) * (1.0 - rt / 2.0)
    m = compute_metrics(r, equity=eq_net)
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "turnover_yr": 0.0,
        "cost_drag_annual": 0.0,
        "costs_paid": 0.0,
        "avg_names": float(win.notna().sum(axis=1).mean()),
        "vol": m.volatility,
        "total_return": m.total_return,
        "_returns": r,
        "_equity": eq_net,
    }


def composite_bench(panel: pd.DataFrame, lo, hi) -> dict:
    score_full = build_composite_score(panel)
    win = slice_window(panel, lo, hi)
    score = slice_window(score_full, lo, hi)
    res = run_backtest(win, score, COST, config=PortfolioConfig())
    m = res.metrics
    years = len(res.returns) / 244
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "turnover_yr": m.annual_turnover / years if years > 0 else 0.0,
        "cost_drag_annual": m.cost_drag_annual,
        "costs_paid": res.costs_paid,
        "avg_names": float((res.weights > 1e-6).sum(axis=1).mean()),
        "vol": m.volatility,
        "total_return": m.total_return,
        "_returns": res.returns,
        "_equity": res.equity,
    }


def random_control(panel: pd.DataFrame, long_frac: float, lo, hi, seed: int) -> dict:
    """Negative control: random Bernoulli(long_frac) gate, same ranking recipe.

    Same fraction of names eligible, same momentum ranking, same cost model, same
    portfolio constraints. Only the signal is replaced by a coin.
    """
    rng = np.random.default_rng(seed)
    mask = rng.random(panel.shape) < long_frac
    long_sig = pd.DataFrame(mask, index=panel.index, columns=panel.columns)
    score_full = dispersion_score(panel, long_sig, mom_days=MOM_DAYS)
    win = slice_window(panel, lo, hi)
    score = slice_window(score_full, lo, hi)
    res = run_backtest(win, score, COST, config=PortfolioConfig())
    m = res.metrics
    years = len(res.returns) / 244
    return {
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "calmar": m.calmar,
        "turnover_yr": m.annual_turnover / years if years > 0 else 0.0,
        "cost_drag_annual": m.cost_drag_annual,
        "costs_paid": res.costs_paid,
        "avg_names": float((res.weights > 1e-6).sum(axis=1).mean()),
        "vol": m.volatility,
        "total_return": m.total_return,
        "_returns": res.returns,
    }


HDR = (
    f"{'label':<16}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}{'Calmar':>8}"
    f"{'Turn/yr':>9}{'CostD':>8}{'Names':>7}{'Vol':>7}"
)


def fmt(label: str, d: dict) -> str:
    return (
        f"{label:<16}{d['cagr']:>8.2%}{d['sharpe']:>9.2f}{d['maxdd']:>9.2%}"
        f"{d['calmar']:>8.2f}{d.get('turnover_yr', 0):>9.2f}"
        f"{d.get('cost_drag_annual', 0):>8.2%}{d['avg_names']:>7.1f}{d['vol']:>7.1%}"
    )


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    print(f"universe: {len(symbols)} symbols, {panel.index[0].date()} -> "
          f"{panel.index[-1].date()}")
    print(f"cost: {float(COST.all_in_round_trip_bps(100_000)):.2f} bps round-trip "
          f"at Rs 1L/side "
          f"({float(COST.round_trip_bps(100_000)):.2f} statutory + "
          f"{2 * float(COST.slippage_bps):.0f} slippage)\n")

    # ---------------- TRAIN: all 5 variants, selection happens here ----------
    print("=" * 92)
    print("TRAIN 2016-01-01 -> 2023-12-31   (selection window)")
    print("=" * 92)
    print(HDR)
    train_rows = {}
    for v in VARIANTS:
        d = run_variant(panel, v["period"], v["entry"], TRAIN_START, TRAIN_END)
        train_rows[v["id"]] = d
        print(fmt(f"{v['id']} p{v['period']} e{v['entry']}", d))

    # Select on TRAIN only. Primary = Sharpe (risk-adjusted, the mission metric);
    # CAGR and MaxDD printed alongside so the choice is inspectable.
    best = max(train_rows.items(), key=lambda kv: kv[1]["sharpe"])
    best_id = best[0]
    best_cfg = next(v for v in VARIANTS if v["id"] == best_id)
    print(f"\nSELECTED ON TRAIN (max Sharpe): {best_id} "
          f"period={best_cfg['period']} entry={best_cfg['entry']}")

    # Liveness of the signal itself (TRAIN), fraction of (name, day) long.
    long_sig, short_sig = dispersion_signal(
        panel, period=best_cfg["period"], entry=best_cfg["entry"]
    )
    tr_sig = slice_window(long_sig.astype(float), TRAIN_START, TRAIN_END)
    tr_short = slice_window(short_sig.astype(float), TRAIN_START, TRAIN_END)
    print(f"signal liveness TRAIN : long {tr_sig.mean().mean():.2%} of cells, "
          f"short {tr_short.mean().mean():.2%} (not tradable long-only)")

    # ---------------- TEST: selected variant, unchanged ---------------------
    print()
    print("=" * 92)
    print("TEST 2024-01-01 -> 2026-10-01   (touched once, with the TRAIN-selected "
          "variant unchanged)")
    print("=" * 92)
    print(HDR)
    test_sel = run_variant(
        panel, best_cfg["period"], best_cfg["entry"], TEST_START, TEST_END
    )
    print(fmt("SELECTED", test_sel))

    test_bh = buy_and_hold(panel, TEST_START, TEST_END)
    print(fmt("buy&hold", test_bh))

    test_comp = composite_bench(panel, TEST_START, TEST_END)
    print(fmt("nse composite", test_comp))

    te_sig = slice_window(long_sig.astype(float), TEST_START, TEST_END)
    te_short = slice_window(short_sig.astype(float), TEST_START, TEST_END)
    print(f"\nsignal liveness TEST  : long {te_sig.mean().mean():.2%} of cells, "
          f"short {te_short.mean().mean():.2%}")

    # --- sanity checks from AGENT_BRIEF §6 --------------------------------
    print()
    print("--- sanity checks ---")
    print(f"1. plausibility : CAGR {test_sel['cagr']:.2%} "
          f"(long-only NIFTY-50 ceiling ~40-50%) -> "
          f"{'OK' if test_sel['cagr'] < 0.50 else 'SUSPECT BUG'}")
    print(f"2. weight count : {test_sel['avg_names']:.1f} names avg "
          f"(target ~22) -> {'OK' if 10 <= test_sel['avg_names'] <= 30 else 'SUSPECT'}")
    print(f"3. liveness     : {te_sig.mean().mean():.2%} of cells flagged "
          f"(>5% -> {'OK' if te_sig.mean().mean() > 0.05 else 'ALWAYS-FLAT'})")
    print(f"4. cost drag    : {test_sel['cost_drag_annual']:.2%}/yr, "
          f"Rs {test_sel['costs_paid']:,.0f} total "
          f"(net terminal equity {test_sel['_equity'].iloc[-1]:.3f} vs "
          f"buy&hold {test_bh['_equity'].iloc[-1]:.3f})")

    # --- negative control: random gate at the same liveness ----------------
    print()
    print("--- negative control (random gate, same % of cells long) ---")
    print(HDR)
    lf = float(te_sig.mean().mean())
    ctrl = []
    for seed in (11, 22, 33):
        d = random_control(panel, lf, TEST_START, TEST_END, seed)
        ctrl.append(d)
        print(fmt(f"random s{seed}", d))
    c_cagr = np.mean([d["cagr"] for d in ctrl])
    c_sharpe = np.mean([d["sharpe"] for d in ctrl])
    print(f"random mean   : CAGR {c_cagr:.2%}  Sharpe {c_sharpe:.2f}")
    print(f"strategy TEST : CAGR {test_sel['cagr']:.2%}  Sharpe {test_sel['sharpe']:.2f}")
    print(f"beats random? : return {'YES' if test_sel['cagr'] > c_cagr else 'NO'} "
          f"({(test_sel['cagr'] - c_cagr) * 100:+.2f}pp), "
          f"risk-adj {'YES' if test_sel['sharpe'] > c_sharpe else 'NO'} "
          f"({test_sel['sharpe'] - c_sharpe:+.2f})")

    # --- yearly returns, TEST ---------------------------------------------
    print()
    print("--- calendar-year returns, TEST ---")
    yr_sel = yearly_returns(test_sel["_returns"])
    yr_bh = yearly_returns(test_bh["_returns"])
    yr_cp = yearly_returns(test_comp["_returns"])
    for y in yr_sel.index:
        print(f"  {y}  strategy {yr_sel[y]:>7.2%}   "
              f"buy&hold {yr_bh.get(y, float('nan')):>7.2%}   "
              f"composite {yr_cp.get(y, float('nan')):>7.2%}")

    out = {
        "selected": best_cfg,
        "train": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                  for k, v in train_rows.items()},
        "test_selected": {k: v for k, v in test_sel.items() if not k.startswith("_")},
        "test_buyhold": {k: v for k, v in test_bh.items() if not k.startswith("_")},
        "test_composite": {k: v for k, v in test_comp.items() if not k.startswith("_")},
        "random_control_mean_cagr": float(c_cagr),
        "random_control_mean_sharpe": float(c_sharpe),
        "test_liveness_long": float(te_sig.mean().mean()),
        "train_liveness_long": float(tr_sig.mean().mean()),
    }
    with open("research/agent_dispersion/results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("\nwrote research/agent_dispersion/results.json")


if __name__ == "__main__":
    main()
