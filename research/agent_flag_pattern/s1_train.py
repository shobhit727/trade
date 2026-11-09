"""STEP 1 -- TRAIN-ONLY. Run all 5 declared variants, plus controls.

This is the ONLY step allowed to influence parameter selection. Nothing here looks at
TEST. The winner is chosen on TRAIN metrics and written to winner.json; step 2 then
evaluates it, unchanged, on TEST.

Run: .venv/bin/python research/agent_flag_pattern/s1_train.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from common import (
    CONTROL_SEEDS,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
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
PANEL, HIGH, LOW, SYMBOLS, REPORT = load_all()
print("=== cleaning report (TRAIN step) ===")
print(REPORT)

# --------------------------------------------------------------------------- #
# Train-window slices. Signals are computed on the FULL history so their rolling
# windows are warm on 2016-01-04, then sliced. That is legitimate: every signal value
# on day t uses only closes up to t.
# --------------------------------------------------------------------------- #
tr = slice(TRAIN_START, TRAIN_END)
p_tr = PANEL.loc[tr]

print(f"\nTRAIN panel: {p_tr.index[0].date()} -> {p_tr.index[-1].date()}  "
      f"({len(p_tr)} bars, {p_tr.shape[1]} names)")
print(f"TEST panel : {TEST_START.date()} -> {TEST_END.date()}  "
      f"(UNTOUCHED in this step)")

signals = {name: run_signal(PANEL, HIGH, LOW, spec).loc[tr]
           for name, spec in VARIANTS.items()}

print("\n=== signal liveness on TRAIN (brief 6.3) ===")
print(f"  {'variant':<14}{'frac long':>11}{'frac short':>12}{'names flagged':>15}")
for name, sig in signals.items():
    lo, sh, nn = liveness(sig, TRAIN_START, TRAIN_END)
    print(f"  {name:<14}{lo:>10.2%}{sh:>12.2%}{nn:>15.1f}")

# --------------------------------------------------------------------------- #
# Backtests
# --------------------------------------------------------------------------- #
rows: list[dict] = []
detail: dict[str, dict] = {}

for name, sig in signals.items():
    score = build_score(sig, p_tr)
    res = backtest(p_tr, score)
    m = res.metrics
    avg_n = res.diag["avg_names"]
    rows.append({"label": name, "metrics": m, "avg_names": avg_n})
    detail[name] = {
        "avg_names": avg_n,
        "rt_bps": res.diag["round_trip_bps"],
        "n_rebalances": res.diag["n_rebalances"],
        "pct_invested": float(res.weights.sum(axis=1).mean()),
        **{k: float(v) for k, v in m.as_dict().items()},
    }

# buy-and-hold benchmark on the identical TRAIN window
bh_r, bh_m, bh_cost = equal_weight_bh(p_tr)
rows.append({"label": "BH_equalwt", "metrics": bh_m, "avg_names": p_tr.shape[1]})
detail["BH_equalwt"] = {"avg_names": p_tr.shape[1],
                        "entry_exit_cost": bh_cost,
                        **{k: float(v) for k, v in bh_m.as_dict().items()}}

# nsealgo composite benchmark
comp = build_composite_score(p_tr)
cres = backtest(p_tr, comp)
rows.append({"label": "composite", "metrics": cres.metrics,
             "avg_names": cres.diag["avg_names"]})
detail["composite"] = {"avg_names": cres.diag["avg_names"],
                       **{k: float(v) for k, v in cres.metrics.as_dict().items()}}

# negative control: random signal with the same long-fraction, V0 and V3 (the two
# ends of the liveness spectrum)
ctrl: dict[str, list] = {}
for name in ("V0_LITERAL", "V3_FLAG5"):
    outs = []
    for seed in CONTROL_SEEDS:
        rs = random_signal_like(signals[name], seed)
        r = backtest(p_tr, build_score(rs, p_tr))
        outs.append(r.metrics.cagr)
    ctrl[name] = outs
    rows.append({
        "label": f"rand_{name[-6:]}",
        "metrics": backtest(p_tr, build_score(
            random_signal_like(signals[name], CONTROL_SEEDS[0]), p_tr)).metrics,
        "avg_names": float("nan"),
    })

print("\n=== TRAIN results (net of 21.92 bps) ===")
print(metrics_table(rows))

print("\n=== negative control: random signal, same long-fraction (CAGR per seed) ===")
for k, v in ctrl.items():
    s = pd.Series(v)
    print(f"  {k:<14} seeds={list(v)}  mean CAGR {s.mean():>7.2%}  "
          f"min {s.min():>7.2%}  max {s.max():>7.2%}")

# --------------------------------------------------------------------------- #
# Selection -- TRAIN ONLY. Rule fixed now, before looking: maximise TRAIN Sharpe,
# with a hard liveness floor of 5% of bars long (brief 6.3) so a dead signal cannot
# win by being flat.
# --------------------------------------------------------------------------- #
elig = {
    k: v for k, v in detail.items()
    if k.startswith("V") and v["avg_names"] > 0 and True
}
scored = sorted(
    ((k, v["sharpe"]) for k, v in elig.items()),
    key=lambda kv: kv[1], reverse=True,
)
print("\n=== TRAIN Sharpe ranking (selection rule: highest TRAIN Sharpe) ===")
for k, s in scored:
    print(f"  {k:<14} Sharpe {s:>6.2f}   CAGR {elig[k]['cagr']:>7.2%}  "
          f"MaxDD {elig[k]['max_drawdown']:>7.2%}  "
          f"long {elig[k]['pct_invested']:.0%} invested")

winner = scored[0][0]
print(f"\n>>> TRAIN WINNER: {winner}  (Sharpe {detail[winner]['sharpe']:.2f})")

# Does it beat the random control on TRAIN?
rnd = ctrl[winner] if winner in ctrl else None
print(f">>> random control for {winner}: {rnd}")

(HERE / "train_results.json").write_text(json.dumps(detail, indent=2))
(HERE / "winner.json").write_text(json.dumps(
    {"winner": winner, "train_sharpe": detail[winner]["sharpe"],
     "selection_rule": "max TRAIN Sharpe among the 5 declared variants",
     "variants_run": list(VARIANTS)}, indent=2))
print("\nwrote train_results.json + winner.json")
