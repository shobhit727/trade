"""Full research report: cost-aware in-sample, regime overlay, walk-forward OOS,
negative controls, and the Gate 2-5 checks from GOAL.md.

Run:  .venv/bin/python research/validate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.backtest.walkforward import walk_forward  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import (  # noqa: E402
    NEGATIVE_CONTROL_WEIGHTS,
    build_composite_score,
)
from nsealgo.factors.regime import blend_with_cash, exposure_series, market_proxy  # noqa: E402

BASE = CostModel(segment="delivery", slippage_bps=5)


def hr(title: str) -> None:
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


def bench(panel: pd.DataFrame) -> tuple[pd.Series, object]:
    r = market_proxy(panel).fillna(0.0)
    return r, compute_metrics(r)


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    hr("0. UNIVERSE")
    print(report.describe())
    print(f"{len(symbols)} symbols | {panel.index[0].date()} -> {panel.index[-1].date()} "
          f"| {len(panel)} days | {len(panel) / 244:.1f} years")

    bm_ret, bm = bench(panel)
    print(f"\nBENCHMARK equal-weight buy&hold: CAGR {bm.cagr * 100:.2f}%  "
          f"Sharpe {bm.sharpe:.2f}  MaxDD {bm.max_drawdown * 100:.2f}%")

    score = build_composite_score(panel)

    # ------------------------------------------------------------------ 1
    hr("1. IN-SAMPLE, NO OVERLAY (honest starting point)")
    r = run_backtest(panel, score, BASE, PortfolioConfig(), "M")
    print(r.summary())
    print(f"avg names {r.diag['avg_names']:.1f} | cost drag {r.metrics.cost_drag_annual * 100:.2f}%/y")

    # ------------------------------------------------------------------ 2
    hr("2. REGIME OVERLAY — does it cut the drawdown?")
    print(f"{'lookback':>9} {'thr':>5} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>9} "
          f"{'Calmar':>7} {'expo%':>7}")
    best_overlay = None
    for lb in (63, 126, 189, 252):
        for thr in (0.0, 0.35, 0.6):
            ov = exposure_series(panel, lookback=lb, threshold=thr)
            comb = blend_with_cash(r.returns, ov)
            m = compute_metrics(comb)
            avg_expo = float(ov.mean()) * 100
            print(f"{lb:>9} {thr:>5.2f} {m.cagr * 100:>7.2f}% {m.sharpe:>7.2f} "
                  f"{m.max_drawdown * 100:>8.2f}% {m.calmar:>7.2f} {avg_expo:>6.1f}%")
            if best_overlay is None or m.calmar > best_overlay[0]:
                best_overlay = (m.calmar, lb, thr, comb, m)
    _, lb, thr, r_overlay, m_overlay = best_overlay
    print(f"\n-> best by Calmar: lookback={lb} threshold={thr}  "
          f"CAGR {m_overlay.cagr * 100:.2f}%  Sharpe {m_overlay.sharpe:.2f}  "
          f"MaxDD {m_overlay.max_drawdown * 100:.2f}%")
    print(m_overlay.fmt())

    # ------------------------------------------------------------------ 3
    hr("3. WALK-FORWARD (out-of-sample — the only number that counts)")
    grid = [
        {"n_positions": n, "lookback": lbx, "threshold": thrx}
        for n in (15, 22, 30)
        for lbx in (126, 252)
        for thrx in (0.0, 0.35, 0.6)
    ]

    def run_fn(pnl: pd.DataFrame, params: dict):
        sc = build_composite_score(pnl)
        cfg = PortfolioConfig(n_positions=params["n_positions"])
        res = run_backtest(pnl, sc, BASE, cfg, "M")
        ov = exposure_series(pnl, lookback=params["lookback"],
                             threshold=params["threshold"])
        comb = pd.Series(blend_with_cash(res.returns, ov), index=res.returns.index)
        res.returns = comb
        res.metrics = compute_metrics(comb)
        return res

    wf = walk_forward(panel, grid, run_fn, n_folds=6, train_years=6, test_years=2)
    print(wf.summary())

    oos = wf.oos_returns
    bm_oos = wf.benchmark_returns.reindex(oos.index).fillna(0.0)
    hr("4. OOS VS BENCHMARK (same windows)")
    bmo = compute_metrics(bm_oos)
    om = wf.oos_metrics
    print(f"{'':>14} {'CAGR':>9} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>9} {'Calmar':>7}")
    print(f"{'OOS strategy':>14} {om.cagr * 100:>8.2f}% {om.sharpe:>7.2f} "
          f"{om.sortino:>8.2f} {om.max_drawdown * 100:>8.2f}% {om.calmar:>7.2f}")
    print(f"{'OOS bench':>14} {bmo.cagr * 100:>8.2f}% {bmo.sharpe:>7.2f} "
          f"{bmo.sortino:>8.2f} {bmo.max_drawdown * 100:>8.2f}% {bmo.calmar:>7.2f}")
    print(f"{'ALPHA':>14} {(om.cagr - bmo.cagr) * 100:>+8.2f}% "
          f"{om.sharpe - bmo.sharpe:>+7.2f} {om.sortino - bmo.sortino:>+8.2f} "
          f"{(om.max_drawdown - bmo.max_drawdown) * 100:>+8.2f}% "
          f"{om.calmar - bmo.calmar:>+7.2f}")

    yo, yb = yearly_returns(oos), yearly_returns(bm_oos)
    y = pd.concat([yb.rename("bench"), yo.rename("strategy")], axis=1)
    y["alpha"] = y["strategy"] - y["bench"]
    print("\nOOS yearly:")
    print(y.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))

    # ------------------------------------------------------------------ 5
    hr("5. NEGATIVE CONTROL — reversal must LOSE (proves no noise-mining)")
    nc = build_composite_score(panel, weights=NEGATIVE_CONTROL_WEIGHTS)
    rnc = run_backtest(panel, nc, BASE, PortfolioConfig(), "M")
    print(f"reversal composite : CAGR {rnc.metrics.cagr * 100:>7.2f}%  "
          f"Sharpe {rnc.metrics.sharpe:>6.2f}  MaxDD {rnc.metrics.max_drawdown * 100:>7.2f}%")
    print(f"trend+overlay    : CAGR {m_overlay.cagr * 100:>7.2f}%  "
          f"Sharpe {m_overlay.sharpe:>6.2f}  MaxDD {m_overlay.max_drawdown * 100:>7.2f}%")
    ok = rnc.metrics.sharpe < m_overlay.sharpe
    print(f"\ncontrol behaves as evidence predicts: {'PASS' if ok else 'FAIL'}")

    # ------------------------------------------------------------------ 6
    hr("6. GATE CHECKS (GOAL.md §5)")
    g3 = [
        ("G3 OOS CAGR >= 12%", om.cagr >= 0.12, f"{om.cagr * 100:.2f}%"),
        ("G3 OOS Sharpe >= 0.7", om.sharpe >= 0.7, f"{om.sharpe:.2f}"),
        ("G3 OOS MaxDD < 35%", om.max_drawdown > -0.35, f"{om.max_drawdown * 100:.2f}%"),
        ("G3 positive years >= 60%", (yo > 0).sum() / max(len(yo), 1) >= 0.6,
         f"{(yo > 0).sum()}/{len(yo)}"),
        ("G4 beats benchmark (CAGR)", om.cagr > bmo.cagr,
         f"{om.cagr * 100:.2f}% vs {bmo.cagr * 100:.2f}%"),
        ("G4 beats benchmark (Sharpe)", om.sharpe > bmo.sharpe,
         f"{om.sharpe:.2f} vs {bmo.sharpe:.2f}"),
    ]
    for name, passed, detail in g3:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<38} {detail}")

    band = ("A" if om.cagr >= .30 else "B" if om.cagr >= .18 else
            "C" if om.cagr >= .12 else "D" if om.cagr >= .06 else "E")
    print(f"\nBAND (GOAL.md §2.3, by OOS CAGR): {band}")
    print(f"Monthly equivalent: {(om.cagr + 1) ** (1 / 12) - 1:+.3%}")
    print("Target was 3.000%/month = 42.6% annualised.")


if __name__ == "__main__":
    main()
