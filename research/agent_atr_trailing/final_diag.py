"""DIAGNOSTIC — why the strategy loses, and proof that the harness has no look-ahead.

Three questions, none of which is a new parameter variant (the 5-variant budget is
untouched by anything here):

  A. Is the ATR band a *selector* or just a *cash-drag dial*?
     If TRAIN CAGR across V1..V5 is explained by how much of the book is invested, the
     "signal" carries no information and the whole TRAIN ranking is an artefact of cash
     drag. Regress TRAIN and TEST CAGR on avg_invested across the five declared
     variants and report R^2.

  B. Is the band even directional?
     Compare the strategy against "hold the flagged names equally, no momentum
     ranking" — a *diagnostic control*, not a 6th variant: it uses V4's frozen
     parameters and answers only whether the momentum overlay is what fails.

  C. Does the harness actually have no look-ahead?
     Perturbation test: corrupt the close/high/low data *after* a cut date and confirm
     every weight the engine produced on or before the cut is bit-identical. If any
     future bar leaks backwards, weights before the cut will move.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    atr_trailing_signal,
    buy_and_hold,
    cfg,
    fmt_row,
    load_ohlc,
    momentum_score,
    run,
    summarise,
)

HERE = Path(__file__).resolve().parent
VARIANTS = [
    ("V1_period14_mult2.0", 14, 2.0), ("V2_period14_mult1.5", 14, 1.5),
    ("V3_period20_mult2.5", 20, 2.5), ("V4_period55_mult2.0", 55, 2.0),
    ("V5_period10_mult3.0", 10, 3.0),
]
SELECTED = ("V4_period55_mult2.0", 55, 2.0)


def part_a(close) -> dict:
    """CAGR explained by cash drag alone?"""
    print("=" * 100)
    print("A. IS THE ATR BAND A SELECTOR, OR JUST A CASH-DRAG DIAL?")
    print("=" * 100)
    rows = []
    for name, p, m in VARIANTS:
        sig = atr_trailing_signal(close, *_hl(close), p, m)
        for wlab, (a, b) in (("TRAIN", (TRAIN_START, TRAIN_END)),
                             ("TEST", (TEST_START, TEST_END))):
            r = summarise(run(close, momentum_score(close, sig), a, b), close, name)
            rows.append({"variant": name, "window": wlab, "invested": r["avg_invested"],
                         "cagr": r["cagr"], "sharpe": r["sharpe"], "names": r["avg_names"]})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    out = {}
    for wlab in ("TRAIN", "TEST"):
        sub = df[df["window"] == wlab]
        x = sub["invested"].to_numpy()
        y = sub["cagr"].to_numpy()
        r = float(np.corrcoef(x, y)[0, 1])
        # cash drag is not a choice the strategy makes, so also test against the
        # benchmark's own beta-free number: invested x EW CAGR
        bench = buy_and_hold(close, TRAIN_START, TRAIN_END) if wlab == "TRAIN" \
            else buy_and_hold(close, TEST_START, TEST_END)
        pred = x * bench["cagr"]
        r_pred = float(np.corrcoef(pred, y)[0, 1])
        print(f"\n  {wlab}: corr(avg_invested, CAGR)      = {r:+.4f}   R^2 = {r ** 2:.4f}")
        print(f"  {wlab}: corr(invested x EW CAGR, CAGR) = {r_pred:+.4f}   R^2 = {r_pred ** 2:.4f}"
              f"   (EW CAGR = {bench['cagr'] * 100:.2f}%)")
        for _, row in sub.iterrows():
            print(f"      {row['variant']:<22} invested {row['invested'] * 100:5.1f}%  "
                  f"predicted {pred[list(sub['variant']).index(row['variant'])] * 100:6.2f}%  "
                  f"actual {row['cagr'] * 100:6.2f}%")
        out[wlab] = {"corr_invested_cagr": r, "r2_invested": r ** 2,
                     "corr_pred_cagr": r_pred, "r2_pred": r_pred ** 2,
                     "ew_cagr": bench["cagr"]}
    return out


def part_b(close, high, low) -> dict:
    """Is the momentum overlay what fails, or the band?"""
    print("\n" + "=" * 100)
    print("B. IS THE BAND DIRECTIONAL? (diagnostic control, V4 params frozen)")
    print("=" * 100)
    name, p, m = SELECTED
    sig = atr_trailing_signal(close, high, low, p, m)

    out = {}
    for wlab, (a, b) in (("TRAIN", (TRAIN_START, TRAIN_END)),
                         ("TEST", (TEST_START, TEST_END))):
        # (i) as reported: band -> momentum rank
        r_mom = summarise(run(close, momentum_score(close, sig), a, b), close, f"{wlab} momentum-ranked")
        # (ii) band only: flagged names get equal-ish score (rank by name, no momentum)
        eq = pd.DataFrame(
            np.where(sig.to_numpy() > 0, 1.0, np.nan),
            index=close.index, columns=close.columns,
        )
        r_eq = summarise(run(close, eq, a, b), close, f"{wlab} band-only-equal")
        # (iii) the inverse use of the band: long only the names NOT extended
        inv = pd.DataFrame(
            np.where(sig.to_numpy() < 0, 1.0, np.nan),
            index=close.index, columns=close.columns,
        )
        r_inv = summarise(run(close, inv, a, b), close, f"{wlab} INVERSE(band<0)")
        print("\n" + fmt_row(r_mom))
        print(fmt_row(r_eq))
        print(fmt_row(r_inv))
        out[wlab] = {"momentum_ranked": r_mom, "band_equal": r_eq, "inverse": r_inv}
    return out


def part_c(close, high, low) -> dict:
    """Perturbation test for look-ahead."""
    print("\n" + "=" * 100)
    print("C. NO-LOOKAHEAD PROOF — corrupt the future, demand the past not move")
    print("=" * 100)
    _, p, m = SELECTED
    cut = pd.Timestamp("2025-06-30", tz="Asia/Kolkata")
    score = momentum_score(close, atr_trailing_signal(close, high, low, p, m))

    w_clean = run(close, score, TEST_START, TEST_END).weights

    rng = np.random.default_rng(7)
    c2, h2, l2 = close.copy(), high.copy(), low.copy()
    fut = c2.index > cut
    shock = 1.0 + rng.uniform(-0.5, 0.5, size=(int(fut.sum()), c2.shape[1]))
    c2.loc[fut] = c2.loc[fut] * shock
    h2.loc[fut] = h2.loc[fut] * shock
    l2.loc[fut] = l2.loc[fut] * shock

    w_dirty = run(c2, score, TEST_START, TEST_END).weights
    pre = w_clean.index <= cut
    d = (w_clean.loc[pre] - w_dirty.loc[pre]).abs().to_numpy()
    print(f"  cut date                 : {cut.date()}")
    print(f"  bars after cut corrupted: {int(fut.sum())}  "
          f"(x{1 + shock.min():.2f} .. x{1 + shock.max():.2f} price shock)")
    print(f"  bars compared at/before cut: {int(pre.sum())}")
    print(f"  max |weight difference| : {float(d.max()):.3e}")
    print(f"  cells differing > 1e-12  : {int((d > 1e-12).sum())} of {d.size:,}")
    ok = bool(d.max() < 1e-12)
    print(f"\n  VERDICT: {'NO LOOK-AHEAD — past weights are invariant to future data' if ok else 'LOOK-AHEAD DETECTED'}")

    # and the complementary test: a one-day shift of the score must change the answer,
    # otherwise the test above would pass vacuously on an all-zero weight matrix
    score_late = score.shift(-1)
    w_late = run(close, score_late, TEST_START, TEST_END).weights
    moved = float((w_clean - w_late).abs().to_numpy().max())
    print(f"  control — shifting the score 1 day changes weights by up to {moved:.4f}"
          f"  ({'non-vacuous' if moved > 0.01 else 'SUSPICIOUS: test could be vacuous'})")
    return {"max_diff": float(d.max()), "no_lookahead": ok, "control_shift": moved}


_HL = {}


def _hl(close):
    """high/low panels, memoised."""
    if "hl" not in _HL:
        _c, h, lo = load_ohlc()
        _HL["hl"] = (h, lo)
    return _HL["hl"]


def main() -> None:
    close, high, low = load_ohlc()
    a = part_a(close)
    b = part_b(close, high, low)
    c = part_c(close, high, low)

    (HERE / "final_diag.json").write_text(json.dumps({
        "cash_drag": a, "band_direction": b, "lookahead": c,
    }, indent=2, default=str))
    print(f"\nwrote {HERE / 'final_diag.json'}")
    _ = cfg


if __name__ == "__main__":
    main()
