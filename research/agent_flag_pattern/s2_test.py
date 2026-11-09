"""STEP 2 -- THE TEST RUN. Evaluates the TRAIN-selected winner, UNCHANGED, exactly once.

Nothing in this file chooses a parameter. It reads winner.json (written by s1_train.py
from TRAIN metrics only) and reports. The TEST window is opened here for the first time.

Run: .venv/bin/python research/agent_flag_pattern/s2_test.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from common import (
    CONTROL_SEEDS,
    TEST_END,
    TEST_START,
    VARIANTS,
    backtest,
    build_composite_score,
    build_score,
    equal_weight_bh,
    liveness,
    load_all,
    metrics_table,
    random_signal_like,
    run_signal,
)

HERE = Path(__file__).resolve().parent
winner = json.loads((HERE / "winner.json").read_text())["winner"]
print(f">>> TRAIN-selected winner, loaded from disk: {winner}")
print(f">>> TEST window {TEST_START.date()} -> {TEST_END.date()} -- OPENED NOW, ONCE")

PANEL, HIGH, LOW, SYMBOLS, _ = load_all()

# Signals computed on full history (so rolling windows are warm), then sliced to TEST.
# Every signal value on day t uses only data up to t.
te = slice(TEST_START, TEST_END)
p_te = PANEL.loc[te]
sig_w = run_signal(PANEL, HIGH, LOW, VARIANTS[winner]).loc[te]
score_w = build_score(sig_w, p_te)

res = backtest(p_te, score_w)
lo, sh, nn = liveness(sig_w, TEST_START, TEST_END)
bh_r, bh_m, bh_cost = equal_weight_bh(p_te)
cres = backtest(p_te, build_composite_score(p_te))

rows = [
    {"label": winner, "metrics": res.metrics, "avg_names": res.diag["avg_names"]},
    {"label": "BH_equalwt", "metrics": bh_m, "avg_names": p_te.shape[1]},
    {"label": "composite", "metrics": cres.metrics,
     "avg_names": cres.diag["avg_names"]},
]

# negative control on TEST (same long-fraction, 5 seeds)
ctrl_rows = []
ctrl_cagr, ctrl_sharpe = [], []
for seed in CONTROL_SEEDS:
    rs = random_signal_like(sig_w, seed)
    r = backtest(p_te, build_score(rs, p_te))
    ctrl_cagr.append(r.metrics.cagr)
    ctrl_sharpe.append(r.metrics.sharpe)
    ctrl_rows.append({"label": f"rand_seed{seed}", "metrics": r.metrics,
                      "avg_names": r.diag["avg_names"]})
rows.append(ctrl_rows[0])

print(f"\n=== TEST {TEST_START.date()} -> {TEST_END.date()} "
      f"({len(p_te)} bars, {p_te.shape[1]} names), net of 21.92 bps ===")
print(metrics_table(rows))

print("\n=== signal liveness on TEST ===")
print(f"  {winner}: frac long {lo:.2%}, frac short {sh:.2%}, "
      f"mean names flagged {nn:.1f}")

print("\n=== negative control on TEST (all 5 seeds) ===")
print(metrics_table(ctrl_rows))
s = pd.Series(ctrl_cagr)
print(f"  random CAGR  : mean {s.mean():>7.2%}  min {s.min():>7.2%}  "
      f"max {s.max():>7.2%}")
print(f"  real  CAGR   : {res.metrics.cagr:>7.2%}")
print(f"  real Sharpe  : {res.metrics.sharpe:>7.2f}   "
      f"random Sharpe mean {pd.Series(ctrl_sharpe).mean():>7.2f}")

# --------------------------------------------------------------------------- #
# brief 6 sanity checks
# --------------------------------------------------------------------------- #
print("\n=== brief 6 sanity checks on TEST ===")
print(f"  6.1 plausibility   : CAGR {res.metrics.cagr:.2%} "
      f"({'OK, far below the 40-50% ceiling' if res.metrics.cagr < 0.5 else 'IMPOSSIBLE'})")
print(f"  6.2 weight count   : avg names {res.diag['avg_names']:.1f} "
      f"(target ~22) {'OK' if res.diag['avg_names'] <= 30 else 'ACCUMULATION'}")
print(f"  6.3 liveness       : {lo:.2%} of bars long "
      f"{'OK (>5%)' if lo > 0.05 else 'DEAD (<5%)'}")
print(f"  6.4 cost drag      : {res.metrics.cost_drag_annual:.2%}/yr "
      f"on {res.metrics.annual_turnover:.2f}x turnover")
print(f"  6.5 negative ctrl  : real {res.metrics.cagr:.2%} vs random mean "
      f"{s.mean():.2%} -> "
      f"{'BEATS random' if res.metrics.cagr > s.max() else 'does NOT beat random'}")

# gross vs net, to see whether costs are what kills it
gross = backtest(p_te, score_w, gross=True)
print(f"\n  gross (0 bps) CAGR : {gross.metrics.cagr:.2%}")
print(f"  net   (21.92bps)    : {res.metrics.cagr:.2%}")
print(f"  cost-induced CAGR  : {(gross.metrics.cagr - res.metrics.cagr):.2%}")

# breakdown vs buy-and-hold
print("\n=== TEST vs buy-and-hold (brief 7.4) ===")
dm = res.metrics
print(f"  return : {dm.cagr:>7.2%} vs {bh_m.cagr:>7.2%}  -> "
      f"{'BETTER' if dm.cagr > bh_m.cagr else 'WORSE'} by "
      f"{abs(dm.cagr - bh_m.cagr):.2%} ({'annualised'})")
print(f"  drawdn : {dm.max_drawdown:>7.2%} vs {bh_m.max_drawdown:>7.2%}  -> "
      f"{'BETTER' if dm.max_drawdown > bh_m.max_drawdown else 'WORSE'} by "
      f"{abs(dm.max_drawdown - bh_m.max_drawdown):.2%} (lower magnitude is better)")
print(f"  Sharpe : {dm.sharpe:>7.2f} vs {bh_m.sharpe:>7.2f}")
print(f"  total  : {dm.total_return:>7.2%} vs {bh_m.total_return:>7.2%}")

print("\n=== yearly returns, TEST ===")
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402

yr_s = yearly_returns(res.returns)
yr_b = yearly_returns(bh_r)
yr_c = yearly_returns(cres.returns)
tab = pd.DataFrame({winner: yr_s, "BH_equalwt": yr_b, "composite": yr_c})
print(tab.map(lambda v: f"{v:.2%}").to_string())
print(f"\n  {winner} positive in "
      f"{int((yr_s > 0).sum())}/{len(yr_s)} calendar years "
      f"(GOAL.md 5 gate 3 wants >= 60%)")

out = {
    "window": f"{TEST_START.date()}..{TEST_END.date()}",
    "bars": int(len(p_te)),
    "winner": winner,
    "strategy": {**{k: float(v) for k, v in dm.as_dict().items()},
                 "avg_names": res.diag["avg_names"],
                 "frac_long": lo, "mean_names_flagged": nn},
    "buy_and_hold": {k: float(v) for k, v in bh_m.as_dict().items()},
    "composite": {k: float(v) for k, v in cres.metrics.as_dict().items()},
    "random_control": {
        "cagrs": [float(x) for x in ctrl_cagr],
        "sharpes": [float(x) for x in ctrl_sharpe],
        "cagr_mean": float(s.mean()), "cagr_max": float(s.max()),
    },
    "gross_cagr": float(gross.metrics.cagr),
}
(HERE / "test_results.json").write_text(json.dumps(out, indent=2))
print("\nwrote test_results.json")
