"""Step 1 — TRAIN-only sweep of the 5 declared variants. TEST is NOT touched here."""

from __future__ import annotations

import json
import sys

import pandas as pd

sys.path.insert(0, "research/agent_adx_trend")

import harness as H  # noqa: E402


def main() -> None:
    panel, _ = H.load_panel()
    print("=" * 110)
    print("TRAIN ONLY  2016-01-01 -> 2023-12-31   (TEST untouched)")
    print("=" * 110)
    print(H.HDR)

    rows = []
    for v, desc in H.VARIANTS.items():
        r = H.row_for_variant(v, "TRAIN", v, panel, H.TRAIN_START, H.TRAIN_END)
        rows.append(r)
        print(H.line(r))
        print(f"{'':<26}{'':<6}  ({desc})")

    best = max(rows, key=lambda r: (r.sharpe, r.calmar))
    print()
    print(f"  -> selected on TRAIN by Sharpe (tie-break Calmar): {best.label}")
    print(f"     TRAIN Sharpe {best.sharpe:.2f}  CAGR {best.cagr * 100:.2f}%  "
          f"MaxDD {best.maxdd * 100:.2f}%")

    # TRAIN buy-and-hold reference, for context only (not a selection criterion).
    bh = H.buy_and_hold(panel, H.TRAIN_START, H.TRAIN_END)
    print(f"  TRAIN buy-and-hold (equal weight, 1 entry round trip): "
          f"CAGR {bh['metrics'].cagr * 100:.2f}%  Sharpe {bh['metrics'].sharpe:.2f}  "
          f"MaxDD {bh['metrics'].max_drawdown * 100:.2f}%")

    with open("research/agent_adx_trend/train_rows.json", "w") as fh:
        json.dump(
            [r.__dict__ for r in rows] + [{"label": "TRAIN_buy_and_hold",
                                           "cagr": bh["metrics"].cagr,
                                           "sharpe": bh["metrics"].sharpe,
                                           "maxdd": bh["metrics"].max_drawdown,
                                           "calmar": bh["metrics"].calmar}],
            fh, indent=2, default=float,
        )
    print("\n  wrote research/agent_adx_trend/train_rows.json")
    pd.DataFrame([r.__dict__ for r in rows]).to_csv(
        "research/agent_adx_trend/train_rows.csv", index=False
    )


if __name__ == "__main__":
    main()
