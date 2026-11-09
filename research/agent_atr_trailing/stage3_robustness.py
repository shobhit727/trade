"""STAGE 3 — robustness of the negative result + the diagnostic that explains it.

(a) All 5 DECLARED variants on TEST. The selection stays frozen at the TRAIN winner
    (V4); this table is reported only to show the negative result is not an artefact
    of one parameter pair. No re-selection is performed and the headline verdict is
    unchanged.
(b) Cost stress on the frozen variant (GOAL.md §5 Gate 4 style): slippage 0/5/10/15 bps.
(c) TRAIN-ONLY information-coefficient diagnostic: does the strategy's own continuous
    output — distance of close above its SMA measured in ATR units — carry any
    cross-sectional information about the next month's return? This is a pure
    statistic (no portfolio, no new parameter variant) and it is the evidence for the
    "why". TEST is not used for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    TEST_END,
    TEST_START,
    TRAIN_END,
    atr_trailing_signal,
    fmt_row,
    load_ohlc,
    momentum_score,
    run,
    summarise,
    true_range,
)

from nsealgo.costs import STRESS_MODELS

HERE = Path(__file__).resolve().parent
VARIANTS = [
    ("V1_period14_mult2.0", 14, 2.0), ("V2_period14_mult1.5", 14, 1.5),
    ("V3_period20_mult2.5", 20, 2.5), ("V4_period55_mult2.0", 55, 2.0),
    ("V5_period10_mult3.0", 10, 3.0),
]


def ic_table(sig_cont: pd.DataFrame, fwd: pd.DataFrame, tag: str) -> pd.DataFrame:
    """Monthly cross-sectional Spearman IC between signal and forward 21d return."""
    rows = []
    keys = sig_cont.index.tz_localize(None).to_period("M")
    for period, grp in sig_cont.groupby(keys):
        d = grp.index[0]
        if d not in fwd.index:
            continue
        y = fwd.loc[d]
        both = pd.concat([grp.iloc[0], y], axis=1).dropna()
        if len(both) < 10:
            continue
        rows.append({
            "month": str(period),
            "n": len(both),
            "ic": float(both.corr(method="spearman").iloc[0, 1]),
        })
    out = pd.DataFrame(rows)
    t = out["ic"].mean() / (out["ic"].std(ddof=1) / np.sqrt(len(out)))
    print(f"\n{tag}: monthly IC mean {out['ic'].mean():+.4f}  sd {out['ic'].std(ddof=1):.4f}"
          f"  t = {t:+.2f}  (n_months {len(out)}, "
          f"IC>0 in {(out['ic'] > 0).sum()}/{len(out)})")
    return out


def main() -> None:
    close, high, low = load_ohlc()

    # ---- (a) all declared variants on TEST (selection stays frozen at V4) ----
    print("=" * 118)
    print("(a) ALL 5 DECLARED VARIANTS ON TEST — robustness only, selection frozen at V4")
    print("=" * 118)
    test_rows = []
    for name, p, m in VARIANTS:
        sig = atr_trailing_signal(close, high, low, p, m)
        row = summarise(run(close, momentum_score(close, sig), TEST_START, TEST_END),
                        close, name)
        test_rows.append(row)
        print(fmt_row(row))
    print(pd.DataFrame(test_rows).set_index("label")[
        ["cagr", "sharpe", "max_drawdown", "calmar", "turnover", "cost_drag",
         "avg_names"]].to_string(float_format=lambda v: f"{v:.4f}"))

    # ---- (b) cost stress on the frozen variant -------------------------------
    print("\n" + "=" * 118)
    print("(b) COST STRESS on V4 (period=55, multiplier=2.0), TEST window")
    print("=" * 118)
    sig = atr_trailing_signal(close, high, low, 55, 2.0)
    score = momentum_score(close, sig)
    stress = []
    for cname, cm in STRESS_MODELS.items():
        row = summarise(run(close, score, TEST_START, TEST_END, cm=cm), close, cname)
        stress.append(row)
        print(f"  {cname:<18} CAGR {row['cagr'] * 100:>7.2f}%  gross "
              f"{row['gross_cagr'] * 100:>7.2f}%  Sharpe {row['sharpe']:>6.2f}  "
              f"MaxDD {row['max_drawdown'] * 100:>7.2f}%")

    # ---- (c) TRAIN-only information-coefficient diagnostic -------------------
    print("\n" + "=" * 118)
    print("(c) TRAIN-ONLY DIAGNOSTIC — information coefficient of the raw signal")
    print("=" * 118)
    b = true_range(close, high, low).rolling(55, min_periods=55).mean()
    m55 = close.rolling(55, min_periods=55).mean()
    dist = (close - m55) / b  # strategy's own continuous output, in ATR units
    fwd = close.shift(-21) / close - 1.0  # realised next-month return
    # The IC is computed on TRAIN data only; month t pairs the signal at t with the
    # realised return t -> t+21. No TEST rows are touched.
    ic_atr = ic_table(dist.loc[:TRAIN_END], fwd.loc[:TRAIN_END],
                      "IC(breakout distance / ATR, 55) vs fwd 21d")
    mom126 = close / close.shift(126) - 1.0
    ic_mom = ic_table(mom126.loc[:TRAIN_END], fwd.loc[:TRAIN_END], "IC(126d momentum) vs fwd 21d")

    (HERE / "stage3_robust.json").write_text(json.dumps({
        "test_variants": test_rows, "cost_stress": stress,
        "ic_atr_mean": float(ic_atr["ic"].mean()),
        "ic_mom_mean": float(ic_mom["ic"].mean()),
        "ic_atr_pos": int((ic_atr["ic"] > 0).sum()), "ic_mom_pos": int((ic_mom["ic"] > 0).sum()),
        "n_months": int(len(ic_atr)),
    }, indent=2, default=str))
    print(f"\nwrote {HERE / 'stage3_robust.json'}")


if __name__ == "__main__":
    main()
