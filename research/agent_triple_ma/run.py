"""triple_moving_average (SMA fast>mid>slow) on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31 (all tuning/selection)
  TEST  2024-01-01 -> 2026-10-01 (touched once, after selection was frozen)

Declared parameter budget (5 variants; rebalance fixed at monthly and is NOT a variant):

  V1  5/15/30   catalog default
  V2 10/30/60
  V3 20/50/100  canonical daily triple MA
  V4 20/60/120
  V5 10/20/50

Signal: SMA(fast) > SMA(mid) > SMA(slow) -> +1 (holdable);  SMA(fast) < SMA(mid) <
SMA(slow) -> -1 (discarded: the book is long-only, GOAL.md 3.1);  every mixed ordering
-> 0. `cryptobot.strategies.indicators.sma` is `np.mean(values[-period:])`, so the panel
implementation is `rolling(period, min_periods=period).mean()` -- an exact match, not an
EMA substitution.

Cross-sectional score (brief section 5): 126d trailing momentum ranked ONLY among names
in the +1 state that day.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import (  # noqa: E402
    ENGINE_SHA,
    PortfolioConfig,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
MOM_DAYS = 126
REBALANCE = "M"
REF_NOTIONAL = 100_000

VARIANTS = {
    "V1_5_15_30": (5, 15, 30),
    "V2_10_30_60": (10, 30, 60),
    "V3_20_50_100": (20, 50, 100),
    "V4_20_60_120": (20, 60, 120),
    "V5_10_20_50": (10, 20, 50),
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)


# --------------------------------------------------------------------------- #
# Signal + score construction
# --------------------------------------------------------------------------- #


def sma_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Simple moving average over the last `period` bars -- matches indicators.sma()."""
    return panel.rolling(period, min_periods=period).mean()


def tma_signal(panel: pd.DataFrame, fast: int, mid: int, slow: int) -> pd.DataFrame:
    """+1 fully-bullish alignment, -1 fully-bearish, 0 every mixed ordering/warmup."""
    f = sma_panel(panel, fast)
    m = sma_panel(panel, mid)
    s = sma_panel(panel, slow)
    sig = np.zeros(panel.shape)
    ok = f.notna() & m.notna() & s.notna()
    sig[ok & (f > m).values & (m > s).values] = 1.0
    sig[ok & (f < m).values & (m < s).values] = -1.0
    return pd.DataFrame(sig, index=panel.index, columns=panel.columns)


def tma_score(panel: pd.DataFrame, fast: int, mid: int, slow: int) -> pd.DataFrame:
    """126d trailing momentum ranked only among names the strategy flags long."""
    sig = tma_signal(panel, fast, mid, slow)
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def state_fracs(sig: pd.DataFrame, window: tuple[str, str]) -> dict[str, float]:
    """Share of (day, symbol) cells in each of the three states, inside `window`."""
    v = sig.loc[window[0]:window[1]].to_numpy()
    n = v.size
    return {
        "long": round(float((v > 0).sum() / n), 4),
        "short": round(float((v < 0).sum() / n), 4),
        "neutral": round(float((v == 0).sum() / n), 4),
    }


# --------------------------------------------------------------------------- #
# Controls
# --------------------------------------------------------------------------- #


def random_score(panel: pd.DataFrame, long_frac: float, seed: int) -> pd.DataFrame:
    """Negative control: same % of cells long, membership chosen by a coin flip."""
    rng = np.random.default_rng(seed)
    mask = rng.random(panel.shape) < long_frac
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(pd.DataFrame(mask, index=panel.index, columns=panel.columns)).rank(
        axis=1, pct=True
    )


def bh_eng_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Engine-side buy-and-hold: a rank that is flat in time, so the book simply
    holds the same names under the same caps, cash buffer and cost model."""
    n = panel.shape[1]
    return pd.DataFrame(
        np.tile(np.arange(1.0, n + 1.0), (len(panel), 1)),
        index=panel.index,
        columns=panel.columns,
    )


def bh_ew_series(panel: pd.DataFrame, window: tuple[str, str]) -> pd.Series:
    """Literal brief section 4 rule 5 buy-and-hold: equal-weight universe daily return."""
    return panel.pct_change(fill_method=None).fillna(0.0).loc[window[0]:window[1]].mean(
        axis=1
    )


# --------------------------------------------------------------------------- #
# Plumbing
# --------------------------------------------------------------------------- #


def slice_panel(panel: pd.DataFrame, window: tuple[str, str]) -> pd.DataFrame:
    return panel.loc[window[0]:window[1]]


def run(panel, score, window, cfg=CFG, cost=COST):
    p = slice_panel(panel, window)
    s = score.loc[p.index]
    return run_backtest(p, s, cost, cfg, rebalance=REBALANCE)


def row(label, res) -> dict:
    m = res.metrics
    return {
        "label": label,
        "engine_sha": res.engine_sha,
        "cagr": round(m.cagr * 100, 2),
        "sharpe": round(m.sharpe, 2),
        "sortino": round(m.sortino, 2),
        "maxdd": round(m.max_drawdown * 100, 2),
        "calmar": round(m.calmar, 2),
        "turnover_x_y": round(m.annual_turnover, 2),
        "cost_drag_pct_y": round(m.cost_drag_annual * 100, 2),
        "trades_y": round(m.trades_per_year, 1),
        "avg_names": round(res.diag["avg_names"], 1),
        "avg_top_weight_pct": round(res.diag["avg_top_weight"] * 100, 2),
        "total_ret_pct": round(m.total_return * 100, 1),
        "vol_pct": round(m.volatility * 100, 2),
        "n_days": m.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(res.returns) > 0).mean()), 2),
        "costs_paid_inr": round(res.costs_paid, 0),
    }


HDR = (f"{'variant':<14}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
       f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'TopWt%':>8}")


def show(label: str, r: dict) -> None:
    print(f"{label:<14}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
          f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}"
          f"{r['cost_drag_pct_y']:>7.2f}{r['avg_names']:>7.1f}"
          f"{r['avg_top_weight_pct']:>8.2f}")


def main() -> None:  # noqa: PLR0915
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"\npanel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"symbols ({len(symbols)}): {', '.join(sorted(symbols)[:12])} ...")
    rt = COST.round_trip_bps(REF_NOTIONAL)
    ain = COST.all_in_round_trip_bps(REF_NOTIONAL)
    print(f"cost: round_trip_bps={rt}  all_in_round_trip_bps={ain}")
    print(f"engine_sha = {ENGINE_SHA}")

    out: dict = {"engine_sha": ENGINE_SHA, "variants": {}, "states": {}}

    # ---------------- TRAIN: selection only ---------------- #
    print(f"\n=== TRAIN {TRAIN[0]} -> {TRAIN[1]} — selection only ===")
    print(HDR)
    for name, (f, m_, s_) in VARIANTS.items():
        res = run(panel, tma_score(panel, f, m_, s_), TRAIN)
        r = row(name, res)
        out["variants"][name] = {"fast": f, "mid": m_, "slow": s_, "train": r}
        out["states"][name] = state_fracs(tma_signal(panel, f, m_, s_), TRAIN)
        show(name, r)

    bh_tr = run(panel, bh_eng_score(panel), TRAIN)
    out["train_bh_eng"] = row("BH-ENG", bh_tr)
    show("BH-ENG", out["train_bh_eng"])

    comp_tr = run(panel, build_composite_score(panel), TRAIN)
    out["train_composite"] = row("COMPOSITE", comp_tr)
    show("COMPOSITE", out["train_composite"])

    # literal equal-weight buy-and-hold, TRAIN
    ew_tr = bh_ew_series(panel, TRAIN)
    ew_eq = (1.0 + ew_tr).cumprod()
    entry_cost = float(ain) / 10_000.0
    m_ew = compute_metrics(ew_tr - entry_cost * (ew_tr.index == ew_tr.index[0]).astype(float),
                           (1.0 - entry_cost) * ew_eq)
    out["train_bh_ew"] = {
        "label": "BH-EW", "engine_sha": "n/a (raw series)",
        "cagr": round(m_ew.cagr * 100, 2), "sharpe": round(m_ew.sharpe, 2),
        "maxdd": round(m_ew.max_drawdown * 100, 2), "calmar": round(m_ew.calmar, 2),
        "turnover_x_y": 0.0, "cost_drag_pct_y": round(entry_cost * 100 / (len(ew_tr) / 244), 3),
        "trades_y": 0.0, "avg_names": len(panel.columns), "avg_top_weight_pct": 100.0 / len(panel.columns),
        "total_ret_pct": round(m_ew.total_return * 100, 1), "vol_pct": round(m_ew.volatility * 100, 2),
        "n_days": m_ew.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(ew_tr) > 0).mean()), 2),
    }
    print("  (BH-EW = equal-weight universe, 1x entry cost only): "
          f"CAGR {out['train_bh_ew']['cagr']:.2f}%  Sharpe {out['train_bh_ew']['sharpe']:.2f}  "
          f"MaxDD {out['train_bh_ew']['maxdd']:.2f}%")

    best = max(VARIANTS, key=lambda k: out["variants"][k]["train"]["calmar"])
    f_sel, m_sel, s_sel = VARIANTS[best]
    out["selected_on_train"] = best
    print(f"\nselected on TRAIN (max Calmar): {best} = fast={f_sel} mid={m_sel} slow={s_sel}")
    print(f"  TRAIN signal states: {out['states'][best]}")

    sig_sel = tma_signal(panel, f_sel, m_sel, s_sel)
    long_frac_train = out["states"][best]["long"]

    # ---------------- controls on TRAIN (cheap, computed once) ---------------- #
    rng_scores = [random_score(panel, long_frac_train, seed) for seed in range(20)]
    out["train_random_cagr"] = [
        round(run(panel, sc, TRAIN).metrics.cagr * 100, 2) for sc in rng_scores
    ]
    print(f"random control (TRAIN, 20 seeds): median CAGR "
          f"{np.median(out['train_random_cagr']):.2f}%")

    # ---------------- TEST: evaluated ONCE, unchanged ---------------- #
    print(f"\n=== TEST {TEST[0]} -> {TEST[1]} — untouched until now ===")
    print(HDR)
    test_rows = {}
    for name, (vf, vm, vs) in VARIANTS.items():
        res = run(panel, tma_score(panel, vf, vm, vs), TEST)
        r = row(name, res)
        test_rows[name] = r
        show(name + (" *" if name == best else ""), r)
    out["test"] = test_rows

    sel_res = run(panel, tma_score(panel, f_sel, m_sel, s_sel), TEST)
    bh_res = run(panel, bh_eng_score(panel), TEST)
    comp_res = run(panel, build_composite_score(panel), TEST)
    out["test_bh_eng"] = row("BH-ENG", bh_res)
    out["test_composite"] = row("COMPOSITE", comp_res)
    show("BH-ENG", out["test_bh_eng"])
    show("COMPOSITE", out["test_composite"])

    ew_te = bh_ew_series(panel, TEST)
    ew_eq2 = (1.0 + ew_te).cumprod()
    m_ew2 = compute_metrics(
        ew_te - entry_cost * (ew_te.index == ew_te.index[0]).astype(float),
        (1.0 - entry_cost) * ew_eq2,
    )
    out["test_bh_ew"] = {
        "label": "BH-EW", "engine_sha": "n/a (raw series)",
        "cagr": round(m_ew2.cagr * 100, 2), "sharpe": round(m_ew2.sharpe, 2),
        "maxdd": round(m_ew2.max_drawdown * 100, 2), "calmar": round(m_ew2.calmar, 2),
        "turnover_x_y": 0.0, "cost_drag_pct_y": round(entry_cost * 100 / (len(ew_te) / 244), 3),
        "trades_y": 0.0, "avg_names": len(panel.columns),
        "avg_top_weight_pct": 100.0 / len(panel.columns),
        "total_ret_pct": round(m_ew2.total_return * 100, 1),
        "vol_pct": round(m_ew2.volatility * 100, 2), "n_days": m_ew2.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(ew_te) > 0).mean()), 2),
    }
    print(f"  (BH-EW): CAGR {out['test_bh_ew']['cagr']:.2f}%  "
          f"Sharpe {out['test_bh_ew']['sharpe']:.2f}  "
          f"MaxDD {out['test_bh_ew']['maxdd']:.2f}%  "
          f"Calmar {out['test_bh_ew']['calmar']:.2f}")

    out["test_states"] = state_fracs(sig_sel, TEST)
    print(f"  TEST signal states: {out['test_states']}")

    out["test_random_cagr"] = [
        round(run(panel, sc, TEST).metrics.cagr * 100, 2) for sc in rng_scores
    ]
    out["test_random_sharpe"] = [
        round(run(panel, sc, TEST).metrics.sharpe, 2) for sc in rng_scores
    ]
    rr = out["test_random_cagr"]
    sel_cagr = out["test"][best]["cagr"]
    out["test_random_beat_count"] = sum(1 for x in rr if x < sel_cagr)
    print("\nrandom control (TEST, 20 seeds, same long fraction):")
    print(f"  CAGR median {np.median(rr):.2f}%  min {min(rr):.2f}  max {max(rr):.2f}")
    print(f"  TMA beat {out['test_random_beat_count']}/20 random seeds")

    # ---------------- cost stress on the SELECTED variant only ---------------- #
    from decimal import Decimal as Dc  # noqa: PLC0415

    stress = {}
    for k, cm in (
        ("zero_cost", CostModel(segment="delivery", slippage_bps=Dc("0"))),
        ("double_slippage", CostModel(segment="delivery", slippage_bps=Dc("10"))),
        ("triple_slippage", CostModel(segment="delivery", slippage_bps=Dc("15"))),
    ):
        stress[k] = round(run(panel, tma_score(panel, f_sel, m_sel, s_sel), TEST,
                              cost=cm).metrics.cagr * 100, 2)
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (selected, TEST CAGR%): {stress}")

    print("\n--- TEST yearly returns (selected variant) ---")
    print((yearly_returns(sel_res.returns) * 100).round(2).to_string())
    print("--- TEST yearly returns (BH-ENG) ---")
    print((yearly_returns(bh_res.returns) * 100).round(2).to_string())
    print("--- TEST yearly returns (BH-EW) ---")
    print((yearly_returns(ew_te) * 100).round(2).to_string())

    # realised-cost reconciliation: engine drag vs engine-reported drag
    out["test_equity_end"] = round(float(sel_res.equity.iloc[-1]), 4)
    out["test_costs_paid_inr"] = round(sel_res.costs_paid, 0)
    out["test_capital_inr"] = 2_100_000

    with open("research/agent_triple_ma/results.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote research/agent_triple_ma/results.json")


if __name__ == "__main__":
    main()
