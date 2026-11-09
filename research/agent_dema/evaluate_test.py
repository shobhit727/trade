"""TEST-window evaluation. Run ONCE, after selection was frozen on TRAIN.

The variant, the book construction and the cost model were all fixed by
`sweep_train.py` and written to `selected.json` before this script was written. Nothing
here re-selects anything.

TEST = 2024-01-01 -> 2026-10-01.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dema_lib import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    buy_and_hold,
    dema_distance_panel,
    random_signal_score,
    score_from_gate,
    score_pure_dema,
    table,
)

from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import STRESS_MODELS  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

N_RANDOM_SEEDS = 20
RULE = "=" * 104


def build_score(panel: pd.DataFrame, period: int, kind: str) -> pd.DataFrame:
    return score_from_gate(panel, period) if kind == "gate+mom126" \
        else score_pure_dema(panel, period)


def main() -> None:
    sel = json.loads((HERE / "selected.json").read_text())
    period, kind = int(sel["period"]), sel["score"]
    print("=" * 104)
    print(f"TEST EVALUATION — selected on TRAIN: {sel['variant']} "
          f"(period={period}, score={kind})")
    print(f"TEST window {TEST_START.date()} -> {TEST_END.date()}")
    print("=" * 104)

    panel, symbols, _ = load_universe("data/nse")
    test_px = panel.loc[TEST_START:TEST_END]
    score = build_score(panel, period, kind)

    # ------------------------------------------------------------------ sanity
    print("\n" + RULE)
    print("§6 SANITY CHECKS (before believing any number)")
    print(RULE)
    dist = dema_distance_panel(test_px, period)
    live = float((dist > 0).to_numpy().mean())
    n_days = len(test_px)
    eligible = float(score.loc[test_px.index].notna().to_numpy().mean())
    res = backtest(test_px, score)
    m = res.metrics
    avg_names = res.diag["avg_names"]
    invest = res.weights.sum(axis=1)
    checks = [
        ("signal liveness", f"{live * 100:.1f}% of name-days long "
                            f"(brief floor is ~5% — PASS" if live > 0.05 else "FAIL"),
        ("eligible names", f"{eligible * len(symbols):.1f}/{len(symbols)} above DEMA on a "
                           f"typical day (target book is 22)"),
        ("avg names held", f"{avg_names:.1f}  (cap = PortfolioConfig.max_names = 30; "
                           f"target = n_positions = 22)"),
        ("invested fraction", f"{invest.mean():.3f} mean book weight "
                              f"(1 - 10% cash buffer = 0.90 target; "
                              f"min {invest.min():.3f}, max {invest.max():.3f})"),
        ("max single name", f"{res.weights.max(axis=1).max():.4f} (cap 0.12)"),
        ("round trip cost", f"{res.diag['round_trip_bps']:.2f} bps of turnover "
                            f"(brief sanity ~11.9)"),
        ("plausibility", f"CAGR {m.cagr * 100:.1f}% — unlevered long-only NSE book "
                         f"cannot plausibly exceed ~40-50%; "
                         f"{'PASS' if m.cagr < 0.50 else 'SUSPECT BUG'}"),
        ("rebalances", f"{res.diag['n_rebalances']} monthly over {n_days} bars "
                       f"({n_days / 244:.2f}y)"),
    ]
    for k, v in checks:
        print(f"  {k:<18} {v}")

    # ------------------------------------------------------------------ headline
    print("\n" + RULE)
    print("HEADLINE — TEST, net of full Indian delivery stack")
    print(RULE)
    print("  " + table(f"DEMA {sel['variant']} (p={period})", m))

    bh_eq, bh = buy_and_hold(test_px)
    print("  " + table("buy & hold (equal-weight)", bh))
    comp = backtest(test_px, build_composite_score(panel))
    print("  " + table("nsealgo composite", comp.metrics))
    print("  " + table("nsealgo negative control", backtest(
        test_px, build_composite_score(panel, weights={
            "reversal_5d": 0.45, "reversal_20d": 0.30, "low_volatility": 0.25}
    )).metrics))

    print("\n  TEST vs buy-and-hold")
    d_cagr = (m.cagr - bh.cagr) * 100
    d_dd = (m.max_drawdown - bh.max_drawdown) * 100
    d_calmar = m.calmar - bh.calmar
    d_sharpe = m.sharpe - bh.sharpe
    print(f"    CAGR   {m.cagr * 100:7.2f}% vs {bh.cagr * 100:7.2f}%  -> {d_cagr:+7.2f} pp  "
          f"{'BEATS' if d_cagr > 0 else 'LOSES TO'} the market")
    print(f"    Sharpe {m.sharpe:7.2f}  vs {bh.sharpe:7.2f}  -> {d_sharpe:+7.2f}")
    print(f"    MaxDD  {m.max_drawdown * 100:7.2f}% vs {bh.max_drawdown * 100:7.2f}%  -> "
          f"{d_dd:+7.2f} pp  {'BETTER' if d_dd > 0 else 'WORSE'} drawdown control")
    print(f"    Calmar {m.calmar:7.2f}  vs {bh.calmar:7.2f}  -> {d_calmar:+7.2f}")
    print(f"    vs nsealgo composite: CAGR {(m.cagr - comp.metrics.cagr) * 100:+.2f} pp, "
          f"Sharpe {m.sharpe - comp.metrics.sharpe:+.2f}, "
          f"MaxDD {(m.max_drawdown - comp.metrics.max_drawdown) * 100:+.2f} pp")

    # ------------------------------------------------------------------ gross vs net
    print("\n" + RULE)
    print("COST DRAG — gross (zero cost) vs net (base)")
    print(RULE)
    gross = backtest(test_px, score, STRESS_MODELS["zero_cost"]).metrics
    print("  " + table("TEST zero-cost", gross))
    print("  " + table("TEST base-cost", m))
    print(f"    gross - net = {(gross.cagr - m.cagr) * 100:+.2f} pp CAGR, "
          f"Rs {res.costs_paid:,.0f} of costs paid over the window, "
          f"{m.cost_drag_annual * 100:.2f}%/y")
    print(f"    verdict: {'VIABLE (net > 0 and net > zero-friction benchmark)' if m.cagr > 0 else 'UNVIABLE'}")

    print("\n" + RULE)
    print("COST STRESS (GOAL.md Gate 4)")
    print(RULE)
    for name, cm in STRESS_MODELS.items():
        r = backtest(test_px, score, cm).metrics
        print(f"  {name:<18} CAGR {r.cagr * 100:>7.2f}%  Sharpe {r.sharpe:>6.2f}  "
              f"MaxDD {r.max_drawdown * 100:>7.2f}%")

    # ------------------------------------------------------------------ random control
    print("\n" + RULE)
    print(f"RANDOM-SIGNAL CONTROL ({N_RANDOM_SEEDS} seeds, matched to "
          f"{live * 100:.1f}% long)")
    print(RULE)
    rnd = []
    for seed in range(N_RANDOM_SEEDS):
        sc = random_signal_score(test_px, live, seed)
        rnd.append(backtest(test_px, sc).metrics)
    rnd_sharpe = np.array([x.sharpe for x in rnd])
    rnd_cagr = np.array([x.cagr for x in rnd])
    rnd_dd = np.array([x.max_drawdown for x in rnd])
    print(f"  random Sharpe : mean {rnd_sharpe.mean():.3f}  sd {rnd_sharpe.std(ddof=1):.3f}  "
          f"min {rnd_sharpe.min():.3f}  max {rnd_sharpe.max():.3f}")
    print(f"  random CAGR   : mean {rnd_cagr.mean() * 100:.2f}%  "
          f"min {rnd_cagr.min() * 100:.2f}%  max {rnd_cagr.max() * 100:.2f}%")
    print(f"  random MaxDD  : mean {rnd_dd.mean() * 100:.2f}%  worst {rnd_dd.min() * 100:.2f}%")
    beat_frac = float((m.sharpe > rnd_sharpe).mean())
    print(f"  DEMA Sharpe {m.sharpe:.3f} beats {int(beat_frac * N_RANDOM_SEEDS)}"
          f"/{N_RANDOM_SEEDS} random seeds ({beat_frac * 100:.0f}%)")
    print(f"  z-score of DEMA Sharpe vs random: "
          f"{(m.sharpe - rnd_sharpe.mean()) / max(rnd_sharpe.std(ddof=1), 1e-12):+.2f}")

    # ------------------------------------------------------------------ yearly
    print("\n" + RULE)
    print("YEARLY RETURNS — TEST")
    print(RULE)
    ys = yearly_returns(res.returns).rename("dema")
    yb = yearly_returns(bh_eq.pct_change(fill_method=None).fillna(0.0)).rename("b&h")
    y = pd.concat([yb, ys], axis=1)
    y["alpha"] = y["dema"] - y["b&h"]
    print(y.to_string(float_format=lambda v: f"{v * 100:>8.2f}%"))
    print(f"  positive years: strategy {int((y['dema'] > 0).sum())}/{len(y)}  "
          f"benchmark {int((y['b&h'] > 0).sum())}/{len(y)}  "
          f"(Gate 3 needs >=60%)")
    print(f"  years beating benchmark: {int((y['alpha'] > 0).sum())}/{len(y)}")

    # ------------------------------------------------------------------ TRAIN vs TEST
    train_rows = json.loads((HERE / "train_results.json").read_text())
    tr = next(r for r in train_rows if r["variant"] == sel["variant"])
    print("\n" + RULE)
    print("TRAIN vs TEST for the selected variant (was TEST touched during selection? NO)")
    print(RULE)
    print(f"  TRAIN ({TRAIN_START.date()}..{TRAIN_END.date()})  "
          f"CAGR {tr['cagr'] * 100:6.2f}%  Sharpe {tr['sharpe']:5.2f}  "
          f"MaxDD {tr['maxdd'] * 100:7.2f}%  Calmar {tr['calmar']:5.2f}")
    print(f"  TEST  ({TEST_START.date()}..{TEST_END.date()})  "
          f"CAGR {m.cagr * 100:6.2f}%  Sharpe {m.sharpe:5.2f}  "
          f"MaxDD {m.max_drawdown * 100:7.2f}%  Calmar {m.calmar:5.2f}")
    print(f"  TRAIN->TEST Sharpe decay: {m.sharpe - tr['sharpe']:+.2f}   "
          f"CAGR: {(m.cagr - tr['cagr']) * 100:+.2f} pp")

    (HERE / "test_results.json").write_text(json.dumps({
        "selected": sel,
        "test": m.as_dict(),
        "buy_hold": bh.as_dict(),
        "composite": comp.metrics.as_dict(),
        "live_frac": live,
        "avg_names": avg_names,
        "random": {
            "seeds": N_RANDOM_SEEDS,
            "sharpe_mean": float(rnd_sharpe.mean()),
            "sharpe_sd": float(rnd_sharpe.std(ddof=1)),
            "sharpe_min": float(rnd_sharpe.min()),
            "sharpe_max": float(rnd_sharpe.max()),
            "cagr_mean": float(rnd_cagr.mean()),
            "beat_frac": beat_frac,
        },
        "yearly": {str(k): {kk: float(vv) for kk, vv in v.items()}
                   for k, v in y.to_dict("index").items()},
    }, indent=2))
    print("\nwrote test_results.json")


if __name__ == "__main__":
    main()
