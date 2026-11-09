"""Step 3 — controls on TEST. These are NOT parameter variants; nothing is selected.

1. Random-signal control: the same construction with a random flag at the same
   % of name-days long. The minimum bar from AGENT_BRIEF.md §6.5.
2. The nsealgo composite on the identical panel/window.
3. A no-gate ablation (plain 126d momentum, no volatility filter) to isolate whether
   the volatility gate contributes anything. This is a *reference*, not a variant --
   it is the strategy with the strategy removed.
"""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd
from harness import (
    TEST_END,
    TEST_START,
    bh_row,
    build_score,
    get_panel,
    mom_score,
    run_on,
)

from nsealgo.factors.core import build_composite_score


def load_frozen() -> tuple[str, dict]:
    with open("frozen.txt") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    return lines[0], ast.literal_eval(lines[1])


def main() -> None:
    label, params = load_frozen()
    panel, symbols = get_panel()
    print("=" * 92)
    print("STEP 3 — CONTROLS on TEST (2024-01-01 -> 2026-10-01)")
    print("=" * 92)
    print(f"strategy under test: {label}  {params}")

    strat = run_on(label, "TEST", build_score(**params), TEST_START, TEST_END)
    bh = bh_row("TEST_buy_and_hold", "TEST", TEST_START, TEST_END)
    print(f"\nstrategy  CAGR {strat.cagr * 100:6.2f}%  Sharpe {strat.sharpe:5.2f}  "
          f"MaxDD {strat.maxdd * 100:7.2f}%")
    print(f"buy&hold  CAGR {bh.cagr * 100:6.2f}%  Sharpe {bh.sharpe:5.2f}  "
          f"MaxDD {bh.maxdd * 100:7.2f}%")

    # ------------------------------------------------------------------ #
    # 1. random-signal control
    # ------------------------------------------------------------------ #
    # Match the strategy's *realised* TEST flag rate, not a nominal one: same
    # construction, same ranking, only the flag is random.
    base = build_score(**params)
    # Liveness must be measured on TEST only. `base` spans the whole panel, and the
    # gate is far more permissive in TRAIN (48%) than TEST (30%), so a full-panel
    # average over-states how many names are actually tradeable out of sample and
    # would hand the random control a *stronger* opponent than the real strategy.
    live = float(base.loc[TEST_START:TEST_END].notna().to_numpy().mean())
    print(f"\n--- 1. RANDOM-SIGNAL CONTROL ({live * 100:.2f}% of TEST name-days live) ---")

    rng = np.random.default_rng(12345)
    cagrs, sharpes, drawdowns = [], [], []
    N = 40
    for _ in range(N):
        rnd = pd.DataFrame(
            rng.random(base.shape) < live, index=base.index, columns=base.columns
        ).astype(float)
        rnd = rnd.where(panel.notna())
        sc = mom_score(126).where(rnd > 0).rank(axis=1, pct=True)
        r = run_on("rand", "TEST", sc, TEST_START, TEST_END, cost_detail=False)
        cagrs.append(r.cagr)
        sharpes.append(r.sharpe)
        drawdowns.append(r.maxdd)

    cagrs = np.array(cagrs)
    sharpes = np.array(sharpes)
    drawdowns = np.array(drawdowns)
    # `beaten` = random draws the strategy outperformed.
    beaten_cagr = int((cagrs < strat.cagr).sum())
    beaten_sharpe = int((sharpes < strat.sharpe).sum())
    print(f"  {N} random draws, identical construction, {live * 100:.2f}% live:")
    print(f"    CAGR    mean {cagrs.mean() * 100:6.2f}%   median {np.median(cagrs) * 100:6.2f}%   "
          f"p10 {np.percentile(cagrs, 10) * 100:6.2f}%   p90 {np.percentile(cagrs, 90) * 100:6.2f}%")
    print(f"    Sharpe  mean {sharpes.mean():6.2f}    median {np.median(sharpes):6.2f}")
    print(f"    MaxDD   mean {drawdowns.mean() * 100:6.2f}%")
    print(f"  strategy CAGR {strat.cagr * 100:.2f}%  Sharpe {strat.sharpe:.2f}")
    print(f"  strategy beat {beaten_cagr}/{N} random draws on CAGR, "
          f"{beaten_sharpe}/{N} on Sharpe")
    print(f"  -> {'PASSES' if beaten_cagr / N >= 0.95 else 'FAILS'} the random-signal control")

    # ------------------------------------------------------------------ #
    # 2. nsealgo composite
    # ------------------------------------------------------------------ #
    print("\n--- 2. nsealgo COMPOSITE, identical panel and window ---")
    comp = build_composite_score(panel)
    c = run_on("TEST_composite", "TEST", comp, TEST_START, TEST_END)
    print(f"    composite  CAGR {c.cagr * 100:6.2f}%  Sharpe {c.sharpe:5.2f}  "
          f"MaxDD {c.maxdd * 100:7.2f}%  names {c.avg_names:.1f}")
    print(f"    strategy   CAGR {strat.cagr * 100:6.2f}%  Sharpe {strat.sharpe:5.2f}  "
          f"MaxDD {strat.maxdd * 100:7.2f}%")
    print(f"    -> strategy {'BEATS' if strat.cagr > c.cagr else 'LOSES to'} the composite by "
          f"{abs(strat.cagr - c.cagr) * 100:.2f} pp/yr")

    # ------------------------------------------------------------------ #
    # 3. no-gate ablation: is the volatility filter doing anything?
    # ------------------------------------------------------------------ #
    print("\n--- 3. ABLATION: strategy with the volatility gate REMOVED ---")
    plain = mom_score(126).rank(axis=1, pct=True)
    p = run_on("TEST_nogate_mom126", "TEST", plain, TEST_START, TEST_END)
    print(f"    no gate, plain 126d momentum  CAGR {p.cagr * 100:6.2f}%  Sharpe {p.sharpe:5.2f}  "
          f"MaxDD {p.maxdd * 100:7.2f}%  names {p.avg_names:.1f}")
    print(f"    with vol gate                  CAGR {strat.cagr * 100:6.2f}%  Sharpe {strat.sharpe:5.2f}  "
          f"MaxDD {strat.maxdd * 100:7.2f}%")
    print(f"    -> the volatility gate is worth {(strat.cagr - p.cagr) * 100:+.2f} pp/yr "
          f"and {(strat.sharpe - p.sharpe):+.2f} Sharpe")


if __name__ == "__main__":
    main()
