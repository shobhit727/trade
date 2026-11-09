"""Step 06 — diagnostic attribution. NOT a strategy variant, NOT a candidate.

`V4_w30_mom_rank` is "gate on delta, then rank by 126d momentum". The only thing
separating it from plain momentum is the gate. This script runs plain momentum with NO
delta gate at all, so the gate's contribution can be isolated on both windows.

Plain unconditional momentum is a *different strategy*, not a parameter variant of
`cumulative_delta`, so it is a diagnostic control alongside buy-and-hold and the
nsealgo composite — it is not a 6th declared variant and is not selectable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    avg_names_held,
    buy_and_hold,
    cost_model,
    delta_panel,
    load_panels,
    momentum_panel,
    portfolio_config,
    row,
    run_backtest,
    signal_panel,
    window,
)

FROZEN = "V3_w60_delta_rank"


def main() -> None:
    close, vol, _, _ = load_panels()
    cm = cost_model()
    cfg = portfolio_config()

    print("=" * 118)
    print("DIAGNOSTIC: what does the delta GATE contribute?")
    print("  GATED   = momentum rank among names with delta>0   (= V4_w30_mom_rank)")
    print("  UNGATED = momentum rank over the whole universe     (no delta at all)")
    print("=" * 118)

    for label, (s, e) in (("TRAIN", (TRAIN_START, TRAIN_END)),
                          ("TEST", (TEST_START, TEST_END))):
        px = window(close, s, e)
        mom = momentum_panel(close).reindex(px.index)
        gated = mom.where(signal_panel(delta_panel(close, vol, 30)).reindex(px.index).notna())
        ungated = mom
        g = run_backtest(px, gated, cm, cfg, "M")
        u = run_backtest(px, ungated, cm, cfg, "M")
        bh = buy_and_hold(close, cm, s, e)
        print(f"\n--- {label}  {s.date()} .. {e.date()}  ({len(px)} sessions) ---")
        print(row("  momentum GATED", g.metrics, f"  names {avg_names_held(g):4.1f}"))
        print(row("  momentum UNGATED", u.metrics, f"  names {avg_names_held(u):4.1f}"))
        print(row("  BUY-AND-HOLD", bh["metrics"]))
        print(f"  -> delta gate costs {g.metrics.cagr * 100 - u.metrics.cagr * 100:+.2f}pp "
              f"CAGR and {g.metrics.sharpe - u.metrics.sharpe:+.2f} Sharpe vs no gate")
        print(f"  -> names held: gated {avg_names_held(g):.1f} vs ungated "
              f"{avg_names_held(u):.1f} (the gate shrinks the investable set below 22)")

    print("\n" + "=" * 118)
    print("SUMMARY: is the failure 'bad signal' or 'bad gate'?")
    px_t = window(close, TEST_START, TEST_END)
    mom = momentum_panel(close).reindex(px_t.index)
    u = run_backtest(px_t, mom, cm, cfg, "M")
    from common import (
        VARIANTS,  # noqa: PLC0415
        strategy_score,  # noqa: PLC0415
    )

    v3 = next(v for v in VARIANTS if v.name == FROZEN)
    frozen = run_backtest(px_t, strategy_score(close, vol, v3).reindex(px_t.index),
                          cm, cfg, "M")
    print(row(f"  {FROZEN} (frozen)", frozen.metrics))
    print(row("  momentum, no gate", u.metrics))
    print(f"  -> the delta gate is worth {frozen.metrics.cagr * 100 - u.metrics.cagr * 100:+.2f}pp "
          f"CAGR on TEST")


if __name__ == "__main__":
    main()
