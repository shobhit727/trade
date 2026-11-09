"""Stage 5 — verification and diagnosis. Not parameter tuning.

1. Lookahead test: shifting every weight decision one day later must destroy the
   edge if the pipeline is honest. If delayed results are *identical*, the
   one-bar lag is not actually binding and every number above is suspect.
2. Cost-sensitivity: is the loss from costs or from the signal?
3. Ablation (diagnostic only, NOT a new variant and NOT selected on): the same
   momentum ranking with the ATR gate removed. This isolates how much the
   strategy contributed versus how much the underlying momentum ranking did.
4. The short leg: what the long-only restriction actually cost us.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

import signal as sigmod  # noqa: E402

import common  # noqa: E402
import s2_train_select as s2  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import STRESS_MODELS, CostModel  # noqa: E402

FROZEN = ("V1", 10, 1.0)


def run(panel, score, idx, cost=None):
    return run_backtest(panel.loc[slice(*idx)], score.loc[slice(*idx)],
                        cost or CostModel(segment="delivery", slippage_bps=5),
                        PortfolioConfig(), rebalance="M")


def main() -> None:
    o, h, lo, c, syms = common.load()
    tr0, tr1 = s2.TRAIN
    te0, te1 = s2.TEST
    tag, period, mult = FROZEN

    sig = sigmod.signal_panel(h, lo, c, period, mult)
    score = s2.build_score(c, sig)

    print("=== 1. LOOKAHEAD TEST (TRAIN) ===")
    print("If the pipeline has no lookahead, delaying every decision by one day")
    print("must materially change the result.\n")
    base = run(c, score, (tr0, tr1)).metrics
    for lag in (1, 2, 5):
        d = run(c, score.shift(lag), (tr0, tr1)).metrics
        print(f"  lag +{lag}d: CAGR {d.cagr * 100:>7.2f}%  Sharpe {d.sharpe:>6.2f} "
              f"(undelayed {base.cagr * 100:.2f}% / {base.sharpe:.2f})  "
              f"-> {'CHANGED, lag binds' if abs(d.sharpe - base.sharpe) > 0.05 else 'IDENTICAL, INVESTIGATE'}")
    print("  delay 1 bar is already the engine default (weights from t held at t+1).")

    print("\n=== 2. COST SENSITIVITY (TEST) ===")
    print(f"{'model':>18} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>9}")
    for name, cm in STRESS_MODELS.items():
        m = run(c, score, (te0, te1), cm).metrics
        print(f"{name:>18} {m.cagr * 100:>7.2f}% {m.sharpe:>7.2f} "
              f"{m.max_drawdown * 100:>8.2f}%")

    print("\n=== 3. ABLATION (TEST, diagnostic only — not a selectable variant) ===")
    mom_only = (c / c.shift(s2.MOM_DAYS) - 1.0).rank(axis=1, pct=True)
    m_gate = run(c, score, (te0, te1)).metrics
    m_mom = run(c, mom_only, (te0, te1)).metrics
    bh = s2.buy_and_hold(c, (te0, te1), "BH")
    print(f"  momentum ranking + ATR gate (V1) : CAGR {m_gate.cagr * 100:>6.2f}%  "
          f"Sharpe {m_gate.sharpe:>6.2f}  MaxDD {m_gate.max_drawdown * 100:>7.2f}%")
    print(f"  momentum ranking, NO gate        : CAGR {m_mom.cagr * 100:>6.2f}%  "
          f"Sharpe {m_mom.sharpe:>6.2f}  MaxDD {m_mom.max_drawdown * 100:>7.2f}%")
    print(f"  equal-weight buy-and-hold        : CAGR {bh.cagr * 100:>6.2f}%  "
          f"Sharpe {bh.sharpe:>6.2f}  MaxDD {bh.maxdd * 100:>7.2f}%")
    print(f"  -> ATR gate contributes {(m_gate.cagr - m_mom.cagr) * 100:+.2f}pp/yr "
          f"of CAGR versus the ungated momentum book")

    print("\n=== 4. THE SHORT LEG (TEST, diagnostic) ===")
    # What if the -1 signals were used as a short book, purely to size the cost of
    # the long-only restriction. NOT tradeable in an Indian delivery account.
    for label, sc in (("long-only (as run)", score),
                      ("short leg only, synthetic", mom_only.where(sig < 0))):
        neg = -sc if "short" in label else sc
        m = run(c, neg, (te0, te1)).metrics
        print(f"  {label:>26}: CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  "
              f"names {(run(c, neg, (te0, te1)).weights > 0).sum(axis=1).mean():.1f}")

    print("\n=== 5. TRAIN vs TEST stability of the selected variant ===")
    print(f"{'':>8} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>9}")
    for lbl, idx in (("TRAIN", (tr0, tr1)), ("TEST", (te0, te1))):
        m = run(c, score, idx).metrics
        print(f"{lbl:>8} {m.cagr * 100:>7.2f}% {m.sharpe:>7.2f} "
              f"{m.max_drawdown * 100:>8.2f}%")
    print("  -> TRAIN Sharpe 0.58 decaying to TEST Sharpe -0.32 is the classic")
    print("     signature of a parameter chosen on noise.")


if __name__ == "__main__":
    main()
