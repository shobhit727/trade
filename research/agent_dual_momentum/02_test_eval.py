"""STEP 2 — the TEST evaluation. Runs ONCE.

TEST = 2024-01-01 .. 2026-10-01, never looked at before this script.

Exactly ONE variant reaches this window: the one selected on TRAIN by the rule
declared in 00_DECLARED_BUDGET.md (V3 = EMA 50/200). The other four are deliberately
NOT evaluated on TEST -- running them would turn the holdout into a second training
set and would make "I only touched TEST once" untrue.

Alongside it, on the identical window and identical engine settings:
  * buy-and-hold (equal-weight universe, one round trip, same costs)
  * the nsealgo composite (build_composite_score) -- the benchmark to beat
  * two negative controls: a random gate and a fully random score, both with the
    same fraction of bars long as the real signal
  * cost stress (GOAL.md Gate 4) and a zero-cost run, so the cost drag is explicit
"""

from __future__ import annotations

import json
from pathlib import Path

import common as C
import numpy as np

from nsealgo.costs import STRESS_MODELS

HERE = Path(__file__).parent
N_CONTROL_SEEDS = 20


def _num(r: dict, key: str) -> dict:
    return {key: {k: float(v) for k, v in r.items() if not isinstance(v, str)}}


def main() -> None:
    px = C.panel()
    train = json.loads((HERE / "train_result.json").read_text())
    sel = train["selected"]
    params = train["selected_params"]
    fast, slow = params["fast"], params["slow"]

    print(f"SELECTED ON TRAIN: {sel}  (fast={fast}, slow={slow})")
    print(f"TEST window: {C.TEST[0]} -> {C.TEST[1]}   (untouched until now)\n")

    sig = C.build_signal(px, fast, slow)
    score = C.build_score(px, sig)
    live = C.signal_liveness(sig)
    liveness = live["frac_bars_long"]

    res = C.run(px, score, C.TEST)
    m = res.metrics

    bh = C.buy_and_hold(px, C.TEST)
    comp_res = C.run(px, C.composite_score(px), C.TEST)

    rows = [
        C.row("dual_momentum (SELECTED)", m, res, extra=f"EMA{fast}/{slow}"),
        C.row("composite_baseline", comp_res.metrics, comp_res, extra="nsealgo"),
        C.row("buy_and_hold", bh, extra="equal-weight, 1 round trip"),
    ]
    print("=== TEST  2024-01-01 .. 2026-10-01 ===")
    print(C.table(rows))
    print("\nfull metric dump, selected variant:")
    print(m.fmt())
    print(f"  total return {m.total_return * 100:.2f}%   "
          f"vol {m.volatility * 100:.2f}%   winrate {m.win_rate * 100:.1f}%   "
          f"best {m.best_day * 100:.2f}%  worst {m.worst_day * 100:.2f}%")
    print(f"  costs paid Rs {res.costs_paid:,.0f} on Rs 21,00,000  "
          f"({res.costs_paid / 21_00_000 * 100:.2f}% of capital over the window)")
    print(f"  rebalances {int(res.diag['n_rebalances'])}  "
          f"avg top weight {res.diag['avg_top_weight'] * 100:.2f}%")
    print(f"  yearly: {C.yearly(res.returns)}")
    print(f"  signal long {liveness * 100:.1f}% of symbol-bars; "
          f"flagged/day mean {live['mean_flagged_per_day']:.1f}")
    print(f"  avg names held {res.diag['avg_names']:.1f} (sanity: expect ~22)")

    # ------------------------------------------------------------------ #
    # Gross vs net, and cost stress (diagnostics, not parameter selection)
    # ------------------------------------------------------------------ #
    print("\n--- cost sensitivity (diagnostic; GOAL.md Gate 4) ---")
    for key, cm in STRESS_MODELS.items():
        r = C.run(px, score, C.TEST, cost_model=cm)
        print(f"  {key:<16} slippage {float(cm.slippage_bps):>4.0f}bps/side   "
              f"CAGR {r.metrics.cagr * 100:>7.2f}%  Sharpe {r.metrics.sharpe:>5.2f}  "
              f"MaxDD {r.metrics.max_drawdown * 100:>7.2f}%  "
              f"drag {r.metrics.cost_drag_annual * 100:>5.2f}%/y")

    # ------------------------------------------------------------------ #
    # Negative controls
    # ------------------------------------------------------------------ #
    print(f"\n--- negative controls ({N_CONTROL_SEEDS} seeds each, "
          f"same {liveness * 100:.1f}% of bars long) ---")
    ctrl: dict[str, dict[str, np.ndarray]] = {}
    for mode in ("gate", "score"):
        ms = []
        for s in range(N_CONTROL_SEEDS):
            ms.append(C.random_control(px, liveness, C.TEST, seed=s, mode=mode).metrics)
        cagr = np.array([x.cagr for x in ms])
        shp = np.array([x.sharpe for x in ms])
        dd = np.array([x.max_drawdown for x in ms])
        ctrl[mode] = {"cagr": cagr, "sharpe": shp, "maxdd": dd}
        print(f"  random {mode:<5} CAGR mean {cagr.mean() * 100:6.2f}%  "
              f"[{cagr.min() * 100:6.2f}, {cagr.max() * 100:6.2f}]  "
              f"Sharpe mean {shp.mean():5.2f}  MaxDD mean {dd.mean() * 100:6.2f}%")
    gate_shp = ctrl["gate"]["sharpe"]
    score_shp = ctrl["score"]["sharpe"]

    # ------------------------------------------------------------------ #
    # Head-to-head
    # ------------------------------------------------------------------ #
    print("\n--- TEST verdict numbers ---")
    print(f"  vs buy-and-hold : CAGR {m.cagr * 100:.2f}% vs {bh.cagr * 100:.2f}% "
          f"({(m.cagr - bh.cagr) * 100:+.2f}pp) | "
          f"Sharpe {m.sharpe:.2f} vs {bh.sharpe:.2f} ({m.sharpe - bh.sharpe:+.2f}) | "
          f"MaxDD {m.max_drawdown * 100:.2f}% vs {bh.max_drawdown * 100:.2f}% "
          f"({(m.max_drawdown - bh.max_drawdown) * 100:+.2f}pp)")
    print(f"  vs composite   : CAGR {m.cagr * 100:.2f}% vs "
          f"{comp_res.metrics.cagr * 100:.2f}% "
          f"({(m.cagr - comp_res.metrics.cagr) * 100:+.2f}pp) | "
          f"Sharpe {m.sharpe:.2f} vs {comp_res.metrics.sharpe:.2f} "
          f"({m.sharpe - comp_res.metrics.sharpe:+.2f}) | "
          f"MaxDD {m.max_drawdown * 100:.2f}% vs "
          f"{comp_res.metrics.max_drawdown * 100:.2f}% "
          f"({(m.max_drawdown - comp_res.metrics.max_drawdown) * 100:+.2f}pp)")
    print(f"  vs random gate : Sharpe {m.sharpe:.2f} vs {gate_shp.mean():.2f} "
          f"({m.sharpe - gate_shp.mean():+.2f}) | "
          f"beats {int((gate_shp < m.sharpe).sum())}/{N_CONTROL_SEEDS} seeds")
    print(f"  vs random score: Sharpe {m.sharpe:.2f} vs {score_shp.mean():.2f} "
          f"({m.sharpe - score_shp.mean():+.2f}) | "
          f"beats {int((score_shp < m.sharpe).sum())}/{N_CONTROL_SEEDS} seeds")

    out = {
        "window": C.TEST,
        "selected": sel,
        "params": params,
        "liveness": live,
        **_num(rows[0], "strategy"),
        **_num(rows[1], "composite"),
        **_num(rows[2], "buy_hold"),
        "costs_paid_rupees": float(res.costs_paid),
        "control_gate_sharpe_mean": float(gate_shp.mean()),
        "control_gate_sharpe_min": float(gate_shp.min()),
        "control_gate_sharpe_max": float(gate_shp.max()),
        "control_score_sharpe_mean": float(score_shp.mean()),
        "control_score_sharpe_min": float(score_shp.min()),
        "control_score_sharpe_max": float(score_shp.max()),
    }
    (HERE / "test_result.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {HERE / 'test_result.json'}")


if __name__ == "__main__":
    main()
