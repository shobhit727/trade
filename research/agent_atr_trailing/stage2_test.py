"""STAGE 2 — TEST (2024-01-01 .. 2026-10-01), touched exactly once.

The variant is read from `stage1_train.json` (frozen by TRAIN Sharpe). Nothing in
this script re-selects parameters, and TEST was never opened before this point.

Reports: strategy vs buy-and-hold vs random-signal control vs nsealgo composite,
plus the sanity checks required by the brief.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    TEST_END,
    TEST_START,
    atr_trailing_signal,
    buy_and_hold,
    composite,
    fmt_row,
    load_ohlc,
    momentum_score,
    random_control,
    run,
    summarise,
)

from nsealgo.backtest.metrics import yearly_returns

HERE = Path(__file__).resolve().parent
PARAMS = {"V1_period14_mult2.0": (14, 2.0), "V2_period14_mult1.5": (14, 1.5),
          "V3_period20_mult2.5": (20, 2.5), "V4_period55_mult2.0": (55, 2.0),
          "V5_period10_mult3.0": (10, 3.0)}


def main() -> None:
    sel = json.loads((HERE / "stage1_train.json").read_text())["selected"]
    period, mult = PARAMS[sel]
    print(f"FROZEN TRAIN SELECTION: {sel}  (period={period}, multiplier={mult})")
    print(f"TEST window: {TEST_START.date()} .. {TEST_END.date()}\n")

    close, high, low = load_ohlc()
    sig = atr_trailing_signal(close, high, low, period, mult)
    score = momentum_score(close, sig)

    # ---- 1. strategy ------------------------------------------------------
    res = run(close, score, TEST_START, TEST_END)
    strat = summarise(res, close, "atr_trailing_stop")
    w = res.weights

    # ---- 2. buy & hold ----------------------------------------------------
    bench = buy_and_hold(close, TEST_START, TEST_END)
    # ---- 3. random control (matched #names long) --------------------------
    elig = (sig > 0).sum(axis=1)
    rb_elig = elig.groupby(elig.index.tz_localize(None).to_period("M")).first()
    ctrl = random_control(close, rb_elig, TEST_START, TEST_END, seeds=30)
    sh = np.array([c["sharpe"] for c in ctrl])
    cg = np.array([c["cagr"] for c in ctrl])
    dd = np.array([c["max_drawdown"] for c in ctrl])
    nm = np.array([c["avg_names"] for c in ctrl])
    # ---- 4. composite -----------------------------------------------------
    comp = run(close, composite(close), TEST_START, TEST_END)

    print("=" * 118)
    print("TEST 2024-01-01 .. 2026-10-01 — Indian delivery cost stack, 5 bps slippage")
    print("=" * 118)
    print(fmt_row(strat))
    print(fmt_row(bench))
    print(fmt_row(summarise(comp, close, "nsealgo_composite")))

    print("\n--- SANITY CHECKS ---")
    live_bar = float((sig.loc[TEST_START:TEST_END] > 0).to_numpy().mean())
    print(f"1 plausibility   CAGR {strat['cagr'] * 100:.2f}% (long-only unlevered, "
          f"plausible ceiling 40-50%) -> {'OK' if strat['cagr'] < 0.5 else 'BUG'}")
    print(f"2 weight count   avg names {strat['avg_names']:.1f} (cap 22, hard "
          f"max_names 30), max {strat['max_names']}, "
          f"avg invested {strat['avg_invested'] * 100:.1f}%")
    print(f"3 signal liveness {live_bar * 100:.1f}% of symbol-bars flagged +1 "
          f"(brief flags <5% as 'effectively always-flat')")
    print(f"4 cost drag      net CAGR {strat['cagr'] * 100:.2f}% vs gross "
          f"{strat['gross_cagr'] * 100:.2f}% -> drag "
          f"{(strat['gross_cagr'] - strat['cagr']) * 100:+.2f} pp/yr "
          f"({strat['cost_drag'] * 100:.2f}%/yr on {strat['turnover']:.2f}x turnover)")
    print(f"5 negative ctrl  random Sharpe mean {sh.mean():.2f} (sd {sh.std():.2f}); "
          f"strategy {strat['sharpe']:.2f}; "
          f"P(random > strategy) = {float((sh > strat['sharpe']).mean()) * 100:.0f}%")

    print("\n--- RANDOM-SIGNAL CONTROL DETAIL (TEST, 30 seeds) ---")
    print(f"  CAGR    mean {cg.mean() * 100:6.2f}%  sd {cg.std() * 100:5.2f}%  "
          f"range [{cg.min() * 100:6.2f}%, {cg.max() * 100:6.2f}%]")
    print(f"  Sharpe  mean {sh.mean():6.2f}  sd {sh.std():5.2f}  "
          f"range [{sh.min():5.2f}, {sh.max():5.2f}]")
    print(f"  MaxDD   mean {dd.mean() * 100:6.2f}%   names {nm.mean():.1f} "
          f"(strategy {strat['avg_names']:.1f})")
    print(f"  delta vs strategy: CAGR {(strat['cagr'] - cg.mean()) * 100:+.2f} pp, "
          f"Sharpe {strat['sharpe'] - sh.mean():+.2f}")

    print("\n--- HEAD TO HEAD vs BUY & HOLD ---")
    print(f"  CAGR    strategy {strat['cagr'] * 100:6.2f}%  vs EW "
          f"{bench['cagr'] * 100:6.2f}%  -> "
          f"{(strat['cagr'] - bench['cagr']) * 100:+.2f} pp/yr  "
          f"[{'BEATS' if strat['cagr'] > bench['cagr'] else 'LOSES TO'}]")
    print(f"  Sharpe  strategy {strat['sharpe']:6.2f}    vs EW "
          f"{bench['sharpe']:6.2f}  -> {strat['sharpe'] - bench['sharpe']:+.2f}")
    print(f"  MaxDD   strategy {strat['max_drawdown'] * 100:6.2f}%  vs EW "
          f"{bench['max_drawdown'] * 100:6.2f}%  -> "
          f"{(strat['max_drawdown'] - bench['max_drawdown']) * 100:+.2f} pp "
          f"({'shallower' if strat['max_drawdown'] > bench['max_drawdown'] else 'deeper'})")
    print(f"  Calmar  strategy {strat['calmar']:6.2f}    vs EW {bench['calmar']:6.2f}")

    y = pd.DataFrame({
        "strategy": yearly_returns(res.returns),
        "equal_weight": yearly_returns(bench["returns"]),
        "composite": yearly_returns(comp.returns),
    })
    y["alpha_vs_ew"] = y["strategy"] - y["equal_weight"]
    print("\nTEST yearly returns (net of costs):")
    print(y.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))
    print(f"positive years: strategy {(y['strategy'] > 0).sum()}/{len(y)}, "
          f"equal-weight {(y['equal_weight'] > 0).sum()}/{len(y)}")

    (HERE / "stage2_test.json").write_text(json.dumps({
        "selected": sel, "strategy": strat, "buy_hold": bench,
        "composite": summarise(comp, close, "composite"),
        "random": {"sharpe_mean": float(sh.mean()), "sharpe_sd": float(sh.std()),
                   "sharpe_max": float(sh.max()),
                   "cagr_mean": float(cg.mean()), "cagr_sd": float(cg.std()),
                   "p_random_beats": float((sh > strat["sharpe"]).mean())},
        "live_frac_test": live_bar,
        "yearly": y.to_dict(),
    }, indent=2, default=str))
    print(f"\nwrote {HERE / 'stage2_test.json'}")
    _ = w


if __name__ == "__main__":
    main()
