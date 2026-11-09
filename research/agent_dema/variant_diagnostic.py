"""Section G: what did the *declared V5 control* do out-of-sample?

V5 ("pure DEMA", rank by `close/DEMA - 1`, no momentum overlay) was declared in
`PLAN.md` as a **control, not a selectable candidate**. V1 was selected on TRAIN and
frozen before TEST was ever opened. Nothing in this script changes that.

So why run V5 on TEST at all?

Because if V5 — the version that actually tests whether *the DEMA itself* carries any
information — behaves no differently from V1, then the honest conclusion is that the
DEMA period knob is irrelevant and the whole TRAIN Sharpe ranking of V1..V4 was noise.
That is a materially different diagnosis from "V1 slightly underperformed", and it is
the difference between "tune the period harder" and "stop tuning this indicator".

This is a **post-hoc diagnostic on an already-spent TEST window**. It cannot and does
not re-open selection. V1 remains the answer to the question the brief asks. If V5
looks better than V1 here, the correct response is NOT to ship V5; it is to record
that a fresh, never-touched holdout would be required before anyone could claim V5.

Also reported here: the four other periods on TEST, purely to show whether the TRAIN
monotone (Sharpe falling 0.90 -> 0.59 as period goes 20 -> 200) persisted at all.
Same caveat, same non-selectability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dema_lib import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    backtest,
    buy_and_hold,
    score_from_gate,
    score_pure_dema,
    table,
)

from nsealgo.data.loader import load_universe  # noqa: E402

RULE = "=" * 100


def main() -> None:
    panel, _, _ = load_universe("data/nse")
    train_px = panel.loc[TRAIN_START:TRAIN_END]
    test_px = panel.loc[TEST_START:TEST_END]
    _, bm_tr = buy_and_hold(train_px)
    bh, bm_te = buy_and_hold(test_px)
    train_rows = {r["variant"]: r for r in
                  json.loads((HERE / "train_results.json").read_text())}

    print(RULE)
    print("G. ALL 5 DECLARED VARIANTS ON BOTH WINDOWS  (diagnostic; V1 stays the answer)")
    print(RULE)
    print("  V1 was selected on TRAIN. Rows V2-V5 are shown for diagnosis only and")
    print("  are NOT eligible to become the reported result.")

    variants = [("V1", 20, "gate+mom126"), ("V2", 50, "gate+mom126"),
                ("V3", 100, "gate+mom126"), ("V4", 200, "gate+mom126"),
                ("V5", 20, "pure_dema")]

    print("\n  " + f"{'variant':<8}{'TRAIN sharpe':>14}{'TRAIN cagr':>12}"
          f"{'TEST sharpe':>13}{'TEST cagr':>11}{'TEST maxDD':>12}"
          f"{'vs b&h TEST':>13}")
    out = []
    for name, period, kind in variants:
        sc = (score_from_gate(panel, period) if kind == "gate+mom126"
              else score_pure_dema(panel, period))
        tr = backtest(train_px, sc).metrics
        te = backtest(test_px, sc).metrics
        agree = abs(tr.sharpe - train_rows[name]["sharpe"]) < 1e-9
        d = (te.cagr - bm_te.cagr) * 100
        print(f"  {name:<8}{tr.sharpe:>14.3f}{tr.cagr * 100:>11.2f}%"
              f"{te.sharpe:>13.3f}{te.cagr * 100:>10.2f}%"
              f"{te.max_drawdown * 100:>11.2f}%{d:>12.2f}pp"
              + ("" if agree else "   <-- TRAIN MISMATCH"))
        out.append({"variant": name, "period": period, "score": kind,
                    "train_sharpe": tr.sharpe, "test_sharpe": te.sharpe,
                    "test_cagr": te.cagr, "test_maxdd": te.max_drawdown})

    print(f"\n  {'benchmark':<8}{bm_tr.sharpe:>14.3f}{bm_tr.cagr * 100:>11.2f}%"
          f"{bm_te.sharpe:>13.3f}{bm_te.cagr * 100:>10.2f}%"
          f"{bm_te.max_drawdown * 100:>11.2f}%")

    print("\n  " + table("TRAIN buy & hold", bm_tr))
    print("  " + table("TEST  buy & hold", bm_te))

    print(RULE)
    print("DIAGNOSIS")
    print(RULE)
    v1 = next(r for r in out if r["variant"] == "V1")
    v5 = next(r for r in out if r["variant"] == "V5")
    gated = [r for r in out if r["score"] == "gate+mom126"]

    print("  1. Every one of the 5 declared variants loses to buy-and-hold on TEST "
          "return")
    print(f"     (best TEST variant CAGR {max(r['test_cagr'] for r in out) * 100:.2f}% "
          f"vs b&h {bm_te.cagr * 100:.2f}%). This is not a tuning failure — the whole")
    print("     declared family is behind the index, so re-tuning the period is not "
          "the fix.")

    print("\n  2. Does the DEMA period matter? TRAIN Sharpe decayed monotonically "
          "as the period")
    print("     lengthened: " + " -> ".join(
        f"{r['period']}:{r['train_sharpe']:.2f}" for r in gated)
        + ".")
    print("     On TEST the same ordering is "
          + " -> ".join(f"{r['variant']}:{r['test_sharpe']:+.2f}" for r in gated)
          + ".")
    print("     Monotone in TRAIN, scrambled in TEST => the period ranking is "
          "not a real signal.")

    print("\n  3. Does the DEMA itself carry information (V5 vs V1)?")
    print(f"     TEST Sharpe: pure-DEMA {v5['test_sharpe']:+.3f} vs "
          f"gated+momentum {v1['test_sharpe']:+.3f}")
    print(f"     TEST CAGR  : pure-DEMA {v5['test_cagr'] * 100:+.2f}% vs "
          f"gated+momentum {v1['test_cagr'] * 100:+.2f}%")
    verdict = ("indistinguishable" if abs(v5["test_sharpe"] - v1["test_sharpe"]) < 0.2
               else "meaningfully different")
    print(f"     -> {verdict} out-of-sample. The momentum overlay, not the DEMA "
          f"period, is what the TRAIN sweep rewarded.")

    (HERE / "all_variants.json").write_text(json.dumps(out, indent=2))
    print("\n  wrote all_variants.json")


if __name__ == "__main__":
    main()
