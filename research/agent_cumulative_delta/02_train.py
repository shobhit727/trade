"""Step 02 — TRAIN window only (2016-01-01 .. 2023-12-31).

Runs all 5 declared variants on TRAIN, plus benchmarks and controls. Nothing in this
file touches the TEST window. The variant chosen here is the ONLY thing carried to
step 03.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    avg_names_held,
    buy_and_hold,
    composite_score,
    cost_drag_split,
    cost_model,
    delta_panel,
    liveness,
    load_panels,
    portfolio_config,
    random_control_score,
    row,
    run_backtest,
    signal_panel,
    strategy_score,
    window,
    yearly_returns,
)

N_RANDOM = 20
SEEDS = list(range(N_RANDOM))


def main() -> None:
    close, vol, symbols, _ = load_panels()
    px = window(close, TRAIN_START, TRAIN_END)
    cm = cost_model()
    cfg = portfolio_config()

    print("=" * 118)
    print(f"TRAIN  {TRAIN_START.date()} .. {TRAIN_END.date()}   "
          f"{len(px)} sessions   cost stack = Indian delivery, 5bps slippage "
          f"(~11.9bps round trip @Rs1L)")
    print("=" * 118)

    # ---------------- benchmark: buy-and-hold ----------------
    bh = buy_and_hold(close, cm, TRAIN_START, TRAIN_END)
    print(row("BUY-AND-HOLD", bh["metrics"]))

    # ---------------- benchmark: nsealgo composite ----------------
    comp = run_backtest(px, composite_score(close).reindex(px.index), cm, cfg, "M")
    print(row("nsealgo composite", comp.metrics,
              f"  names {avg_names_held(comp):4.1f}"))

    print("-" * 118)
    results = {}
    for v in VARIANTS:
        score = strategy_score(close, vol, v)
        d = delta_panel(close, vol, v.window)
        live = liveness(d, TRAIN_START, TRAIN_END)
        res = run_backtest(px, score.reindex(px.index), cm, cfg, "M")
        net, gross = cost_drag_split(close, score, TRAIN_START, TRAIN_END)
        results[v.name] = {"res": res, "net": net, "gross": gross, "live": live,
                           "score": score}
        print(row(v.name, res.metrics,
                  f"  names {avg_names_held(res):4.1f}  "
                  f"live {live['long_frac'] * 100:4.1f}%  "
                  f"grossCAGR {gross.metrics.cagr * 100:6.2f}%  "
                  f"drag {(gross.metrics.cagr - net.metrics.cagr) * 100:5.2f}pp"))

    print("-" * 118)
    print("YEARLY RETURNS (net, TRAIN)")
    for name, r in results.items():
        yr = yearly_returns(r["res"].returns)
        print(f"  {name:<20} " + "  ".join(f"{k}:{v * 100:6.2f}%" for k, v in yr.items()))

    # ---------------- negative control: random signal ----------------
    # Matched per-day to the *chosen-candidate* construction so the comparison is
    # about the ranking, not about how many names happened to be eligible.
    print("-" * 118)
    print(f"NEGATIVE CONTROL — {N_RANDOM} random seeds, eligible-name count matched "
          f"per day to V2_w30_delta_rank")
    v2 = next(v for v in VARIANTS if v.name == "V2_w30_delta_rank")
    n_flagged = signal_panel(delta_panel(close, vol, v2.window)).notna().sum(axis=1)
    base = results["V2_w30_delta_rank"]["res"].metrics
    rows = []
    for s in SEEDS:
        rc = run_backtest(px, random_control_score(n_flagged, px.index,
                                                  list(px.columns), s),
                          cm, cfg, "M")
        rows.append(rc.metrics)
    f = pd.DataFrame([m.as_dict() for m in rows])
    print(f"  random    CAGR {f.cagr.mean() * 100:6.2f}% (sd {f.cagr.std() * 100:4.2f})  "
          f"Sharpe {f.sharpe.mean():5.2f} (sd {f.sharpe.std():4.2f})  "
          f"MaxDD {f.max_drawdown.mean() * 100:6.2f}%")
    print(f"  strategy  CAGR {base.cagr * 100:6.2f}%                     "
          f"Sharpe {base.sharpe:5.2f}              MaxDD {base.max_drawdown * 100:6.2f}%")
    beat = sum(1 for m in rows if base.sharpe > m.sharpe)
    beat_c = sum(1 for m in rows if base.cagr > m.cagr)
    print(f"  strategy beats {beat}/{N_RANDOM} random seeds on Sharpe, "
          f"{beat_c}/{N_RANDOM} on CAGR")

    print("-" * 118)
    print("TRAIN SUMMARY (ranked by Sharpe)")
    for name, r in sorted(results.items(), key=lambda kv: -kv[1]["res"].metrics.sharpe):
        m = r["res"].metrics
        print(row(name, m))


if __name__ == "__main__":
    main()
