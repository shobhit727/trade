"""dual_moving_average (EMA fast>slow) on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31 (all tuning)
  TEST  2024-01-01 -> 2026-10-01 (touched once)

Declared parameter budget (5 variants, (fast, slow) EMA spans; rebalance fixed at
monthly, monthly is what the engine's evidence note supports):

  V1 20/50   (catalog default)
  V2 10/30
  V3 50/200
  V4 20/100
  V5 5/20

Signal: ema_fast > ema_slow -> +1 (long), else -1. Long-only book, so only the +1
state can be held; the cross-sectional score is 126d trailing momentum ranked among
names flagged long that day (brief section 5).
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
MOM_DAYS = 126
REBALANCE = "M"

VARIANTS = {
    "V1_20_50": (20, 50),
    "V2_10_30": (10, 30),
    "V3_50_200": (50, 200),
    "V4_20_100": (20, 100),
    "V5_5_20": (5, 20),
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)


def ema_panel(panel: pd.DataFrame, span: int) -> pd.DataFrame:
    """Recursive EMA seeded at the first bar -- matches cryptobot's `ema()` exactly."""
    return panel.ewm(span=span, adjust=False).mean()


def dma_signal(panel: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    f = ema_panel(panel, fast)
    s = ema_panel(panel, slow)
    sig = pd.DataFrame(np.where(f > s, 1, -1), index=panel.index, columns=panel.columns)
    # Warmup: the slow EMA is meaningless until it has seen `slow` bars.
    sig.iloc[: max(fast, slow) - 1] = 0
    sig.iloc[: slow] = sig.iloc[:slow].where(
        f.iloc[:slow].notna() & s.iloc[:slow].notna(), 0
    )
    return sig


def dma_score(panel: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """126d trailing momentum, ranked, but only among names the DMA flags long."""
    sig = dma_signal(panel, fast, slow)
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def random_score(panel: pd.DataFrame, sig: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: same % of bars long, entries chosen by a coin flip."""
    rng = np.random.default_rng(seed)
    long_frac = float((sig > 0).to_numpy().mean())
    mask = rng.random(sig.shape) < long_frac
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(pd.DataFrame(mask, index=panel.index, columns=panel.columns)).rank(
        axis=1, pct=True
    )


def bh_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight buy-and-hold of the universe (brief section 4 rule 5)."""
    return (panel / panel.shift(MOM_DAYS) - 1.0).rank(axis=1, pct=True)


def slice_panel(panel: pd.DataFrame, window: tuple[str, str]) -> pd.DataFrame:
    return panel.loc[window[0]:window[1]]


def run(panel, score, window, cfg=CFG, cost=COST):
    p = slice_panel(panel, window)
    s = score.loc[p.index]
    return run_backtest(p, s, cost, cfg, rebalance=REBALANCE)


def row(label, res):
    m = res.metrics
    return {
        "label": label,
        "cagr": round(m.cagr * 100, 2),
        "sharpe": round(m.sharpe, 2),
        "maxdd": round(m.max_drawdown * 100, 2),
        "calmar": round(m.calmar, 2),
        "turnover_x_y": round(m.annual_turnover, 2),
        "cost_drag_pct_y": round(m.cost_drag_annual * 100, 2),
        "avg_names": round(res.diag["avg_names"], 1),
        "trades_y": round(m.trades_per_year, 1),
        "total_ret_pct": round(m.total_return * 100, 1),
        "n_days": m.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(res.returns) > 0).mean()), 2),
    }


def long_frac(panel, fast, slow) -> float:
    return float((dma_signal(panel, fast, slow) > 0).to_numpy().mean())


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"round-trip cost bps = {COST.all_in_round_trip_bps(100000)}")

    out: dict = {"variants": {}, "live_frac": {}}
    print("\n=== TRAIN (2016-01-01 -> 2023-12-31) — selection only ===")
    print(f"{'variant':<12}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
          f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'LongFrac':>9}")
    for name, (f, s) in VARIANTS.items():
        res = run(panel, dma_score(panel, f, s), TRAIN)
        out["variants"][name] = {"fast": f, "slow": s}
        r = row(name, res)
        out["variants"][name]["train"] = r
        out["live_frac"][name] = round(long_frac(panel, f, s), 4)
        print(f"{name:<12}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
              f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}"
              f"{r['cost_drag_pct_y']:>7.2f}{r['avg_names']:>7.1f}"
              f"{out['live_frac'][name]:>9.3f}")

    bh_tr = run(panel, bh_score(panel), TRAIN)
    out["train_bh"] = row("BH", bh_tr)
    print(f"{'BH':<12}{out['train_bh']['cagr']:>8.2f}{out['train_bh']['sharpe']:>8.2f}"
          f"{out['train_bh']['maxdd']:>8.2f}{out['train_bh']['calmar']:>7.2f}"
          f"{out['train_bh']['turnover_x_y']:>6.2f}"
          f"{out['train_bh']['cost_drag_pct_y']:>7.2f}"
          f"{out['train_bh']['avg_names']:>7.1f}")

    comp_tr = run(panel, build_composite_score(panel), TRAIN)
    out["train_composite"] = row("COMPOSITE", comp_tr)
    print(f"{'COMPOSITE':<12}{out['train_composite']['cagr']:>8.2f}"
          f"{out['train_composite']['sharpe']:>8.2f}"
          f"{out['train_composite']['maxdd']:>8.2f}"
          f"{out['train_composite']['calmar']:>7.2f}")

    # pick on TRAIN only
    best = max(VARIANTS, key=lambda k: out["variants"][k]["train"]["calmar"])
    f, s = VARIANTS[best]
    out["selected_on_train"] = best
    print(f"\nselected on TRAIN (max Calmar): {best} (fast={f}, slow={s})")

    sig = dma_signal(panel, f, s)
    rng_scores = [random_score(panel, sig, seed) for seed in range(20)]
    out["rng_train_cagr"] = [
        round(run(panel, sc, TRAIN).metrics.cagr * 100, 2) for sc in rng_scores
    ]
    out["selected_long_frac_train"] = round(
        float((sig.loc[TRAIN[0]:TRAIN[1]] > 0).to_numpy().mean()), 4
    )

    print("\n=== TEST (2024-01-01 -> 2026-10-01) — untouched until now ===")
    print(f"{'variant':<12}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
          f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'Live%':>7}{'YrPos':>6}")
    test_rows = {}
    for name, (vf, vs) in VARIANTS.items():
        sc = dma_score(panel, vf, vs)
        res = run(panel, sc, TEST)
        r = row(name, res)
        test_rows[name] = r
        sel = " *" if name == best else ""
        live = float((sig.loc[TEST[0]:TEST[1]] > 0).to_numpy().mean()) \
            if (vf, vs) == (f, s) else round(long_frac(panel, vf, vs), 3)
        print(f"{name:<12}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
              f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}"
              f"{r['cost_drag_pct_y']:>7.2f}{r['avg_names']:>7.1f}"
              f"{live * 100:>6.1f}%{r['yearly_pos_frac']:>6.2f}{sel}")
    out["test"] = test_rows

    sel_res = run(panel, dma_score(panel, f, s), TEST)
    bh_res = run(panel, bh_score(panel), TEST)
    comp_res = run(panel, build_composite_score(panel), TEST)
    out["test_bh"] = row("BH", bh_res)
    out["test_composite"] = row("COMPOSITE", comp_res)
    out["test_random_cagr"] = [
        round(run(panel, sc, TEST).metrics.cagr * 100, 2) for sc in rng_scores
    ]
    out["test_random_sharpe"] = [
        round(run(panel, sc, TEST).metrics.sharpe, 2) for sc in rng_scores
    ]

    print(f"{'BH':<12}{out['test_bh']['cagr']:>8.2f}{out['test_bh']['sharpe']:>8.2f}"
          f"{out['test_bh']['maxdd']:>8.2f}{out['test_bh']['calmar']:>7.2f}"
          f"{out['test_bh']['turnover_x_y']:>6.2f}"
          f"{out['test_bh']['cost_drag_pct_y']:>7.2f}"
          f"{out['test_bh']['avg_names']:>7.1f}")
    print(f"{'COMPOSITE':<12}{out['test_composite']['cagr']:>8.2f}"
          f"{out['test_composite']['sharpe']:>8.2f}"
          f"{out['test_composite']['maxdd']:>8.2f}"
          f"{out['test_composite']['calmar']:>7.2f}")

    rr = out["test_random_cagr"]
    print(f"\nrandom control (20 seeds, TEST): CAGR median {np.median(rr):.2f}%  "
          f"min {min(rr):.2f}  max {max(rr):.2f}  "
          f"| DMA beat {sum(1 for x in rr if x < out['test'][best]['cagr'])}/20")

    # cost stress on the selected variant only
    from decimal import Decimal as Dc

    stress = {}
    for k, cm in (
        ("double_slippage", CostModel(segment="delivery", slippage_bps=Dc("10"))),
        ("triple_slippage", CostModel(segment="delivery", slippage_bps=Dc("15"))),
        ("zero_cost", CostModel(segment="delivery", slippage_bps=Dc("0"))),
    ):
        r = run(panel, dma_score(panel, f, s), TEST, cost=cm)
        stress[k] = round(r.metrics.cagr * 100, 2)
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (TEST CAGR%): {stress}")

    # gross (pre-cost) return of the selected variant, to isolate cost drag
    res0 = run(panel, dma_score(panel, f, s), TEST,
               cost=CostModel(segment="delivery", slippage_bps=Dc("0")))
    out["test_zero_cost_cagr"] = round(res0.metrics.cagr * 100, 2)

    print("\n--- TEST yearly returns (selected variant) ---")
    print((yearly_returns(sel_res.returns) * 100).round(2).to_string())
    print("--- TEST yearly returns (buy & hold) ---")
    print((yearly_returns(bh_res.returns) * 100).round(2).to_string())

    with open("research/agent_dual_ma/results.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote research/agent_dual_ma/results.json")


if __name__ == "__main__":
    main()
