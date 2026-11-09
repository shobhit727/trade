"""Stage 1: run the 5 DECLARED variants on TRAIN only. TEST is not touched here."""

from __future__ import annotations

import json
import sys

import pandas as pd

sys.path.insert(0, "research/agent_momvol")

from common import (  # noqa: E402
    TRAIN_END,
    TRAIN_START,
    assert_atr_tautology,
    buy_hold_score,
    composite_score,
    get_panel,
    out,
    run,
    signal_panel,
    train_parts,
)

VARIANTS = [
    ("V1", 20, 0.01),    # catalog default
    ("V2", 60, 0.01),    # quarter-horizon ROC
    ("V3", 126, 0.02),   # half-year ROC, 2% bar
    ("V4", 60, 0.05),    # 5% bar -- hard to clear
    ("V5", 5, 0.005),    # one-week ROC
]


def main() -> None:
    panel, symbols = get_panel()
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"TRAIN window {TRAIN_START.date()} -> {TRAIN_END.date()}")

    n_atr = assert_atr_tautology(TRAIN_START, TRAIN_END, "TRAIN")
    print(f"ATR-predicate guard: {n_atr} gating endpoints in TRAIN -> ROC-only is equivalent")

    rows = []
    for name, mp, th in VARIANTS:
        p, sc = train_parts(panel, mp, th)
        sig = signal_panel(panel, mp, th)
        long_frac = float(sig.loc[p.index].notna().to_numpy().mean())
        # Signal liveness on TRAIN, and separately on the TEST window *dates* is
        # deliberately NOT computed here -- see below. long_frac uses TRAIN only.
        r = run(p, sc, f"{name}_momperiod={mp}_thr={th}", long_frac=long_frac)
        d = r.row()
        rows.append(d)
        print(
            f"  {name:>3} mp={mp:<4} thr={th:<6} "
            f"CAGR {d['cagr']*100:>6.2f}%  Sharpe {d['sharpe']:>5.2f}  "
            f"MaxDD {d['maxdd']*100:>6.2f}%  Calmar {d['calmar']:>5.2f}  "
            f"turn {d['turnover']:>4.2f}x  cost {d['cost_drag']*100:>5.2f}%/y  "
            f"names {d['avg_names']:>4.1f}  long {long_frac*100:>5.1f}%"
        )

    # Benchmarks on the identical TRAIN window (fixed construction, not tuned).
    p_tr = panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]
    for nm, sc in (("BUY_HOLD", buy_hold_score(p_tr)), ("COMPOSITE", composite_score(p_tr))):
        r = run(p_tr, sc, nm)
        d = r.row()
        rows.append(d)
        print(
            f"  {nm:>3} {'(benchmark)':<26} "
            f"CAGR {d['cagr']*100:>6.2f}%  Sharpe {d['sharpe']:>5.2f}  "
            f"MaxDD {d['maxdd']*100:>6.2f}%  Calmar {d['calmar']:>5.2f}  "
            f"turn {d['turnover']:>4.2f}x  names {d['avg_names']:>4.1f}"
        )

    df = pd.DataFrame(rows)
    out("stage1_train.csv", df)
    out("stage1_train.json", json.loads(df.to_json(orient="records")))

    print()
    print("RANKING ON TRAIN (Sharpe, tie-break Calmar) — this is the only basis for")
    print("choosing which variant goes to TEST:")
    v = df[df["name"].str.startswith("V")].sort_values(
        ["sharpe", "calmar"], ascending=False
    )
    for _, d in v.iterrows():
        print(f"  {d['name']:<32} Sharpe {d['sharpe']:>5.2f}  Calmar {d['calmar']:>5.2f}"
              f"  CAGR {d['cagr']*100:>6.2f}%")
    print()
    print("SELECTED FOR TEST:", v.iloc[0]["name"])


if __name__ == "__main__":
    main()
