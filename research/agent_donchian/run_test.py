"""THE TEST RUN. Executed once, on the variant that TRAIN selected.

Nothing here chooses a parameter. The winner is read out of train_results.json
(written by run_train.py) and used verbatim. There is no parameter search in this
file, by design -- if you add one, the run is void.

Usage: .venv/bin/python research/agent_donchian/run_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    CONTROL_SEEDS,
    TEST_END,
    TEST_START,
    backtest,
    breakout_signal,
    build_composite_score,
    build_score,
    equal_weight_bh,
    literal_signal,
    liveness,
    load_all,
    metrics_table,
    random_signal_like,
    slice_panel,
)

from nsealgo.backtest.metrics import yearly_returns  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    train = json.loads((HERE / "train_results.json").read_text())
    selected = train["selected"]
    sel = train["variants"][selected]
    kind, period = sel["kind"], sel["period"]
    print("=" * 84)
    print(f"SELECTED ON TRAIN (by frozen rule): {selected}  "
          f"[{kind}, period={period}]")
    print(f"  TRAIN Sharpe {sel['sharpe']:.2f} -> now run UNCHANGED on TEST")
    print("=" * 84 + "\n")

    close, high, low, symbols, _ = load_all()
    te = (str(TEST_START.date()), str(TEST_END.date()))
    p_te = slice_panel(close, *te)

    sig = (
        literal_signal(close, high, low, period)
        if kind == "literal"
        else breakout_signal(close, high, low, period)
    )
    score = build_score(sig, close)
    assert kind == "breakout", "selected variant should be the breakout semantics"

    res = backtest(p_te, score.loc[p_te.index])
    gross = backtest(p_te, score.loc[p_te.index], gross=True)

    bm_rets, bm_m, bm_cost = equal_weight_bh(p_te)
    comp = backtest(p_te, build_composite_score(p_te).reindex(p_te.index))

    print("=" * 84)
    print(f"TEST  {te[0]} -> {te[1]}   ({len(p_te)} bars, {len(symbols)} names)")
    print("Net of full Indian delivery stack. Monthly rebalance. PortfolioConfig defaults.")
    print("=" * 84)
    print(metrics_table([
        {"label": f"donchian {selected}", "metrics": res.metrics,
         "avg_names": res.diag["avg_names"]},
        {"label": "buy & hold", "metrics": bm_m, "avg_names": len(symbols)},
        {"label": "nsealgo composite", "metrics": comp.metrics,
         "avg_names": comp.diag["avg_names"]},
        {"label": "[gross, no costs]", "metrics": gross.metrics,
         "avg_names": gross.diag["avg_names"]},
    ]))

    m, b, c = res.metrics, bm_m, comp.metrics
    print("\n--- TEST vs buy & hold ---")
    print(f"  return   {m.cagr * 100:>7.2f}% vs {b.cagr * 100:>7.2f}%   "
          f"-> {m.cagr - b.cagr:+.2%} per year  (WORSE)"
          if m.cagr < b.cagr else
          f"  return   {m.cagr * 100:>7.2f}% vs {b.cagr * 100:>7.2f}%   "
          f"-> {m.cagr - b.cagr:+.2%} per year  (BETTER)")
    print(f"  drawdown {m.max_drawdown * 100:>7.2f}% vs {b.max_drawdown * 100:>7.2f}%   "
          f"-> {m.max_drawdown - b.max_drawdown:+.2%}  (BETTER = smaller loss)")
    print(f"  Sharpe   {m.sharpe:>7.2f} vs {b.sharpe:>7.2f}   -> {m.sharpe - b.sharpe:+.2f}")
    print(f"  Calmar   {m.calmar:>7.2f} vs {b.calmar:>7.2f}   -> {m.calmar - b.calmar:+.2f}")
    print("\n--- TEST vs nsealgo composite ---")
    print(f"  CAGR     {m.cagr * 100:>7.2f}% vs {c.cagr * 100:>7.2f}%   -> {m.cagr - c.cagr:+.2%}")
    print(f"  Sharpe   {m.sharpe:>7.2f} vs {c.sharpe:>7.2f}   -> {m.sharpe - c.sharpe:+.2f}")

    # ---- cost decomposition
    print("\n--- COST DRAG (brief 6.4) ---")
    print(f"  gross CAGR {gross.metrics.cagr * 100:>7.2f}%  ->  net CAGR {m.cagr * 100:>7.2f}%")
    print(f"  drag {(gross.metrics.cagr - m.cagr) * 100:>6.2f} pp/yr   "
          f"(engine reports {m.cost_drag_annual * 100:.2f}%/y on a compounding base)")
    print(f"  turnover {m.annual_turnover:.2f}x/yr, {m.trades_per_year:.1f} rebalances/yr")
    print(f"  costs paid over TEST: Rs {res.costs_paid:,.0f} on Rs 21,00,000")
    print(f"  VERDICT: gross {'POSITIVE' if gross.metrics.cagr > 0 else 'NEGATIVE'} "
          f"and net {'POSITIVE' if m.cagr > 0 else 'NEGATIVE'} -> "
          f"{'viable after costs' if m.cagr > 0 else 'NOT viable (costs kill it)'}")

    # ---- negative control: random names, same % of bars long
    print(f"\n--- NEGATIVE CONTROL: random signal, same live fraction, "
          f"seeds {CONTROL_SEEDS} ---")
    ctrl_rows = []
    ctrl = []
    for s in CONTROL_SEEDS:
        rsig = random_signal_like(sig.loc[p_te.index], s)
        rsc = build_score(rsig, p_te)
        r = backtest(p_te, rsc.loc[p_te.index])
        ctrl.append(r.metrics.cagr)
        ctrl_rows.append({"label": f"random seed={s}", "metrics": r.metrics,
                          "avg_names": r.diag["avg_names"]})
    print(metrics_table(ctrl_rows))
    import numpy as np

    ctrl_arr = np.array(ctrl)
    print(f"\n  strategy CAGR {m.cagr * 100:.2f}%  vs random mean "
          f"{ctrl_arr.mean() * 100:.2f}%  (range "
          f"{ctrl_arr.min() * 100:.2f}% .. {ctrl_arr.max() * 100:.2f}%)")
    print(f"  beats every random seed: {m.cagr > ctrl_arr.max()}")
    print(f"  beats random mean:      {m.cagr > ctrl_arr.mean()}")
    print(f"  Sharpe vs random mean:  {m.sharpe:.2f} vs "
          f"{np.mean([r['metrics'].sharpe for r in ctrl_rows]):.2f}")

    # ---- sanity checks
    print("\n" + "=" * 84)
    print("SANITY CHECKS (brief 6)")
    print("=" * 84)
    fl, fs, ff = liveness(sig, *te)
    print(f"  [1] plausibility   CAGR {m.cagr * 100:.2f}%  "
          f"{'OK (<<40-50% ceiling)' if m.cagr < 0.5 else 'SUSPICIOUS - investigate'}")
    print(f"  [2] weight count   avg names {res.diag['avg_names']:.1f} of "
          f"PortfolioConfig.n_positions=22  "
          f"{'OK' if res.diag['avg_names'] <= 22.5 else 'BUG: residual accumulation'}")
    print(f"      max top weight {res.diag['avg_top_weight'] * 100:.2f}% "
          f"(cap 12%)   rebalances {res.diag['n_rebalances']}")
    print(f"      round-trip charged by engine: {res.diag['round_trip_bps']:.2f} bps")
    print(f"  [3] liveness       long {fl:.2%}  short {fs:.2%}  flat {ff:.2%}   "
          f"{'OK (>5%)' if fl > 0.05 else 'BELOW 5% FLOOR - near always-flat'}")
    print(f"      shorts are discarded by build_score (long-only book): "
          f"held names come only from the {fl:.2%} long bars")
    print(f"  [4] cost drag      gross {gross.metrics.cagr * 100:.2f}% -> net "
          f"{m.cagr * 100:.2f}%  ({(gross.metrics.cagr - m.cagr) * 100:+.2f} pp)")
    print("  [5] negative ctrl  see above")

    # ---- yearly
    print("\n--- TEST calendar-year returns ---")
    ys = yearly_returns(res.returns).rename("donchian")
    yb = yearly_returns(bm_rets).rename("buy_hold")
    y = pd.concat([yb, ys], axis=1)
    y["alpha"] = y["donchian"] - y["buy_hold"]
    print(y.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))
    pos = int((y["donchian"] > 0).sum())
    print(f"\n  positive years: {pos}/{len(y)} = {pos / len(y) * 100:.0f}% "
          f"(GOAL.md Gate 3 needs >=60%)")
    print(f"  years beating buy&hold: {int((y['alpha'] > 0).sum())}/{len(y)}")

    out = {
        "selected": selected, "kind": kind, "period": period,
        "strategy": {k: getattr(m, k) for k in
                     ("cagr", "sharpe", "sortino", "calmar", "max_drawdown",
                      "max_drawdown_days", "total_return", "annual_turnover",
                      "cost_drag_annual", "trades_per_year", "volatility")},
        "avg_names": res.diag["avg_names"],
        "gross_cagr": gross.metrics.cagr,
        "costs_paid_rs": res.costs_paid,
        "buy_hold": {k: getattr(b, k) for k in
                     ("cagr", "sharpe", "calmar", "max_drawdown", "total_return")},
        "composite": {k: getattr(c, k) for k in
                      ("cagr", "sharpe", "calmar", "max_drawdown")},
        "random_cagrs": ctrl, "random_mean_cagr": float(ctrl_arr.mean()),
        "random_max_cagr": float(ctrl_arr.max()),
        "liveness_test": {"long": fl, "short": fs, "flat": ff},
    }
    (HERE / "test_results.json").write_text(json.dumps(out, indent=2))
    print("\nwrote research/agent_donchian/test_results.json")


if __name__ == "__main__":
    main()
