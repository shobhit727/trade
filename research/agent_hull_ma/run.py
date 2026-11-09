"""hull_moving_average on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31 (all tuning)
  TEST  2024-01-01 -> 2026-10-01 (touched once, at the end)

DECLARED parameter budget (5 variants, the only strategy parameter is `period`;
rebalance fixed at monthly throughout, not swept):

  V1 20  (catalog default)
  V2 10
  V3 15
  V4 30
  V5 55

Signal: close > HMA(period) -> +1 else -1, where HMA is reproduced EXACTLY as the
catalog library computes it (verified in verify_hull.py: note the library's
2*WMA(period) - WMA(half) term order, which is swapped vs the textbook Hull).

Long-only book, so only the +1 state can be held. Cross-sectional score is 126d
trailing momentum ranked among names flagged long (brief section 5).
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
    "V1_20": 20,
    "V2_10": 10,
    "V3_15": 15,
    "V4_30": 30,
    "V5_55": 55,
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)


def wma_panel(x: pd.DataFrame, period: int) -> pd.DataFrame:
    """Exact WMA over the trailing `period` bars, heaviest on the most recent.

    `ewm(alpha=1/p)` is NOT a WMA (geometric weights), so use a rolling weighted mean.
    """
    w = np.arange(1, period + 1, dtype=float)
    return x.rolling(period, min_periods=period).apply(
        lambda a: np.dot(a, w), raw=True
    ) / w.sum()


def hull_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised exact equivalent of cryptobot.strategies.indicators.hull."""
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period**0.5)))
    # Library term order: 2*WMA(period) - WMA(half). Textbooks use the reverse.
    raw = 2.0 * wma_panel(panel, period) - wma_panel(panel, half)
    out = wma_panel(raw, sqrt_p)
    out.iloc[: period + sqrt_p - 2] = np.nan
    return out


def hull_signal(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    h = hull_panel(panel, period)
    sig = pd.DataFrame(
        np.where(panel > h, 1, -1), index=panel.index, columns=panel.columns
    )
    sig[h.isna()] = 0
    return sig


def hull_score(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """126d trailing momentum, ranked, only among names the Hull flags long."""
    sig = hull_signal(panel, period)
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def textbook_hull_score(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """TRAIN-only diagnostic: the SAME strategy with the Hull terms un-swapped.

    Not a variant -- it is not selected on, not counted against the budget, and no
    reported result depends on it. It quantifies what the catalog bug costs.
    """
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period**0.5)))
    raw = 2.0 * wma_panel(panel, half) - wma_panel(panel, period)
    h = wma_panel(raw, sqrt_p)
    sig = pd.DataFrame(
        np.where(panel > h, 1, -1), index=panel.index, columns=panel.columns
    )
    sig[h.isna()] = 0
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


def run(panel, score, window, cfg=CFG, cost=COST):
    p = panel.loc[window[0] : window[1]]
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


HDR = (
    f"{'variant':<12}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
    f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'Long%':>7}"
)


def show(name, r, live=None):
    extra = f"{live * 100:>6.1f}%" if live is not None else "      -"
    print(
        f"{name:<12}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
        f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}"
        f"{r['cost_drag_pct_y']:>7.2f}{r['avg_names']:>7.1f}{extra}"
    )


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"nsealgo all-in round-trip bps (100k) = {COST.all_in_round_trip_bps(100000)}")

    out: dict = {"variants": {}}
    scores = {name: hull_score(panel, p) for name, p in VARIANTS.items()}
    sigs = {name: hull_signal(panel, p) for name, p in VARIANTS.items()}

    print(f"\n=== TRAIN ({TRAIN[0]} -> {TRAIN[1]}) — selection only ===")
    print(HDR)
    for name, p in VARIANTS.items():
        res = run(panel, scores[name], TRAIN)
        live = float((sigs[name].loc[TRAIN[0] : TRAIN[1]] > 0).to_numpy().mean())
        r = row(name, res)
        out["variants"][name] = {"period": p, "train": r, "train_long_frac": round(live, 4)}
        show(name, r, live)

    out["train_bh"] = row("BH", run(panel, bh_score(panel), TRAIN))
    show("BH", out["train_bh"])
    out["train_composite"] = row("COMP", run(panel, build_composite_score(panel), TRAIN))
    show("COMP", out["train_composite"])

    # TRAIN-only diagnostic of the catalog term-order bug
    tb = {}
    for name, p in VARIANTS.items():
        r = run(panel, textbook_hull_score(panel, p), TRAIN)
        tb[name] = round(r.metrics.cagr * 100, 2)
    out["train_textbook_hull_cagr"] = tb
    print(f"\nTRAIN CAGR% with Hull terms UN-SWAPPED (diagnostic only): {tb}")

    best = max(VARIANTS, key=lambda k: out["variants"][k]["train"]["calmar"])
    period = VARIANTS[best]
    out["selected_on_train"] = best
    print(f"\nselected on TRAIN (max Calmar): {best} (period={period})")

    sig = sigs[best]
    rng_scores = [random_score(panel, sig, seed) for seed in range(20)]
    out["rng_train_cagr"] = [
        round(run(panel, sc, TRAIN).metrics.cagr * 100, 2) for sc in rng_scores
    ]

    print(f"\n=== TEST ({TEST[0]} -> {TEST[1]}) — untouched until now ===")
    print(HDR)
    test_rows = {}
    for name in VARIANTS:
        res = run(panel, scores[name], TEST)
        r = row(name, res)
        test_rows[name] = r
        live = float((sigs[name].loc[TEST[0] : TEST[1]] > 0).to_numpy().mean())
        show(name + (" *" if name == best else ""), r, live)
    out["test"] = test_rows

    bh_res = run(panel, bh_score(panel), TEST)
    comp_res = run(panel, build_composite_score(panel), TEST)
    out["test_bh"] = row("BH", bh_res)
    out["test_composite"] = row("COMP", comp_res)
    out["test_random_cagr"] = [
        round(run(panel, sc, TEST).metrics.cagr * 100, 2) for sc in rng_scores
    ]
    out["test_random_sharpe"] = [
        round(run(panel, sc, TEST).metrics.sharpe, 2) for sc in rng_scores
    ]
    show("BH", out["test_bh"])
    show("COMP", out["test_composite"])

    sel = out["test"][best]
    rr = out["test_random_cagr"]
    print(f"\nrandom control (20 seeds, TEST): CAGR median {np.median(rr):.2f}%  "
          f"min {min(rr):.2f}  max {max(rr):.2f}  | "
          f"selected beat {sum(1 for x in rr if x < sel['cagr'])}/20")

    from decimal import Decimal as Dc

    stress = {}
    for k, cm in (
        ("zero_cost", CostModel(segment="delivery", slippage_bps=Dc("0"))),
        ("double_slippage", CostModel(segment="delivery", slippage_bps=Dc("10"))),
        ("triple_slippage", CostModel(segment="delivery", slippage_bps=Dc("15"))),
    ):
        stress[k] = round(run(panel, scores[best], TEST, cost=cm).metrics.cagr * 100, 2)
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (selected, TEST CAGR%): {stress}")

    out["test_yearly"] = {
        "hull": (yearly_returns(run(panel, scores[best], TEST).returns) * 100).round(2).to_dict(),
        "bh": (yearly_returns(bh_res.returns) * 100).round(2).to_dict(),
        "composite": (yearly_returns(comp_res.returns) * 100).round(2).to_dict(),
    }
    print("\n--- TEST yearly returns % (selected) ---")
    for k, v in out["test_yearly"].items():
        print(f"  {k:<9} {v}")

    with open("research/agent_hull_ma/results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nwrote research/agent_hull_ma/results.json")


if __name__ == "__main__":
    main()
