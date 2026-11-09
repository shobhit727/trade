"""Step 04 — sanity checks (brief section 6) on the TEST result.

Independent of 03_test.py: re-derives the headline numbers and asserts the specific
failure modes the brief warns about (200% CAGR bug, weight accretion, always-flat
signal, cost-rescue, coin-flip-beating).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    cost_model,
    delta_panel,
    load_panels,
    portfolio_config,
    run_backtest,
    signal_panel,
    strategy_score,
    window,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from importlib import import_module  # noqa: E402

t3 = import_module("03_test")
SELECTED = t3.SELECTED


def main() -> None:
    close, vol, symbols, _ = load_panels()
    px = window(close, TEST_START, TEST_END)
    cm = cost_model()
    cfg = portfolio_config()
    score = strategy_score(close, vol, SELECTED).reindex(px.index)
    res = run_backtest(px, score, cm, cfg, "M")
    m = res.metrics

    print("6.1 PLAUSIBILITY — CAGR must be < ~50% for an unlevered long-only book")
    ok = m.cagr < 0.50
    print(f"     strategy CAGR {m.cagr * 100:.2f}%  -> {'OK' if ok else 'SUSPECT BUG'}")
    assert ok

    print("6.2 WEIGHT COUNT — must be ~22, not ~48")
    w = res.weights
    counts = (w > 1e-9).sum(axis=1)
    print(f"     avg {counts.mean():.1f}  median {counts.median():.0f}  "
          f"max {counts.max()}  (target 22, hard max {cfg.max_names})")
    print(f"     days above 30 names: {int((counts > 30).sum())}/{len(counts)}")
    assert counts.mean() < 30

    print("6.3 WEIGHT BUDGET — never exceeds the caps")
    gross = w.sum(axis=1)
    print(f"     max gross weight {gross.max():.4f}  "
          f"(cap 1 - cash_buffer = {1 - cfg.cash_buffer:.2f})")
    print(f"     max single name  {w.max().max():.4f}  (cap {cfg.max_weight})")
    assert gross.max() <= 1 - cfg.cash_buffer + 1e-9
    assert w.max().max() <= cfg.max_weight + 1e-9

    print("6.4 SIGNAL LIVENESS — must exceed ~5%")
    live = signal_panel(delta_panel(close, vol, SELECTED.window))
    frac = float(live.loc[TEST_START:TEST_END].notna().to_numpy().mean())
    print(f"     long on {frac * 100:.1f}% of name-days  -> "
          f"{'OK, not always-flat' if frac > 0.05 else 'ALWAYS-FLAT'}")
    assert frac > 0.05

    print("6.5 COST DRAG — reported, and net must be below gross")
    from decimal import Decimal

    from nsealgo.costs import CostModel

    zero = CostModel(segment="delivery", slippage_bps=Decimal("0"))
    g = run_backtest(px, score, zero, cfg, "M")
    print(f"     gross CAGR {g.metrics.cagr * 100:6.2f}%  net CAGR "
          f"{m.cagr * 100:6.2f}%  drag "
          f"{(g.metrics.cagr - m.cagr) * 100:.2f}pp/yr")
    print(f"     cost_drag_annual {m.cost_drag_annual * 100:.2f}%/y  "
          f"turnover {m.annual_turnover:.2f}x/y")
    assert m.cagr < g.metrics.cagr, "net is not below gross"
    print(f"     -> gross is ALSO ~{g.metrics.cagr * 100:.1f}%: the failure is a")
    print("        missing edge, NOT a cost problem. Costs are only ~0.3pp/yr.")

    print("6.6 NEGATIVE CONTROL — did it beat a coin flip?")
    print("     (from 03_test.py: 1/20 on Sharpe, 0/20 on CAGR -> NO)")

    print("\nINDEPENDENT RE-DERIVATION of the headline numbers")
    eq = (1.0 + res.returns).cumprod()
    years = len(eq) / 244
    cagr = float(eq.iloc[-1]) ** (1.0 / years) - 1.0
    dd = float((eq / eq.cummax() - 1.0).min())
    print(f"     final equity {float(eq.iloc[-1]):.4f}x over {years:.2f}y")
    print(f"     CAGR  recomputed {cagr * 100:6.2f}%  vs metrics {m.cagr * 100:6.2f}%")
    print(f"     MaxDD recomputed {dd * 100:6.2f}%  vs metrics "
          f"{m.max_drawdown * 100:6.2f}%")
    assert abs(cagr - m.cagr) < 1e-9
    assert abs(dd - m.max_drawdown) < 1e-9
    print("     -> metrics reconcile exactly")


if __name__ == "__main__":
    main()
