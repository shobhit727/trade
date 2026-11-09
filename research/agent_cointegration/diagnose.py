"""Why did it fail? Event study + layer isolation.

Two questions the headline number cannot answer:

1. **Does the signal carry any information at all?** An event study measures the
   forward return of flagged symbol-bars against unflagged ones, paired by date. If
   the spread is ~0 the strategy is dead at the source and no construction saves it.
   If the spread is positive but the backtest is flat, the problem is cost/turnover,
   which is a *different* and more fixable finding.

2. **Is it the signal, or is the harness eating a real edge?** The layers are peeled
   off one at a time:
       L0  raw signal-following — buy every flagged name, equal weight, monthly,
            no caps / no sector limits / no turnover budget / no costs. The signal's
            own arithmetic, with nothing between it and the prices.
       L1  + full Indian cost stack
       L2  + portfolio caps, sector caps, cash buffer  (build_rebalance_weights)
       L3  + turnover budget  == the reported result

   If L0 is strong and L3 is flat, the edge is real and the construction is the
   problem. If L0 is already weak, the signal is the problem.

Nothing here is a parameter variant and no selection is made on anything reported:
V3 was fixed on TRAIN before either of these windows was opened.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coinlib import (  # noqa: E402
    CORRECTED_COSTS,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    build_score_window,
    buy_and_hold,
    composite_score,
    evaluate,
    fmt,
    panel,
    zscore_panel,
)

W, ENTRY = 126, 1.0


def event_study(px: pd.DataFrame, window: int, entry: float, label: str,
                horizons=(5, 21, 63, 126)) -> None:
    """Forward return of flagged vs unflagged symbol-bars, paired by date.

    The cross-section is extremely correlated within a day, so the standard error is
    computed across DATES (the cross-sectional mean of each group per day, then a
    t-test on those daily differences). An unclustered t-stat would be overstated by
    roughly sqrt(names).
    """
    z = zscore_panel(px, window)
    flag = (z < -float(entry))
    print(f"\n  {label}: flagged {flag.to_numpy().mean() * 100:.2f}% of symbol-bars")
    print(f"    {'h':>5} {'flagged':>10} {'unflagged':>11} {'spread':>10} "
          f"{'t-stat':>8} {'n days':>8}")

    for h in horizons:
        fwd = (px.shift(-h) / px - 1.0)
        a = fwd.where(flag).stack().groupby(level=0).mean()
        b = fwd.where(~flag).stack().groupby(level=0).mean()
        j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
        if len(j) < 30:
            continue
        d = j["a"] - j["b"]
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        t = float(d.mean() / se) if se > 0 else float("nan")
        print(f"    {h:>4}d {float(j['a'].mean()) * 100:>9.3f}% "
              f"{float(j['b'].mean()) * 100:>10.3f}% "
              f"{float(d.mean()) * 100:>9.3f}% {t:>8.2f} {len(j):>8d}")


def monthly_targets(px: pd.DataFrame, flag: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight every flagged name, re-decided monthly, held in between."""
    keys = px.index.tz_localize(None).to_period("M")
    s = pd.Series(px.index, index=px.index)
    rb = [g.index[0] for _, g in s.groupby(keys)][1:]
    out = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for d in rb:
        f = flag.loc[d].reindex(px.columns).fillna(False).astype(float)
        tot = f.sum()
        if tot > 0:
            out.loc[d:] = (f / tot).to_numpy()
    return out


def simulate(px: pd.DataFrame, held: pd.DataFrame, charge: bool) -> pd.Series:
    """Daily net returns from a held-weight panel. One-bar lag = no lookahead."""
    from nsealgo.backtest.engine import REF_POSITION_NOTIONAL, _d

    rate = float(CORRECTED_COSTS.all_in_round_trip_bps(
        _d(REF_POSITION_NOTIONAL))) / 10_000.0
    rets = px.pct_change(fill_method=None).fillna(0.0)
    w = np.vstack([np.zeros((1, held.shape[1])), held.to_numpy()[:-1]])
    gross = np.nansum(w * rets.to_numpy(), axis=1)
    turn = np.abs(np.diff(held.to_numpy(), axis=0,
                          prepend=np.zeros((1, held.shape[1])))).sum(axis=1) / 2.0

    eq = 1.0
    out = np.zeros(len(px))
    for i in range(len(px)):
        prev = eq
        eq *= 1.0 + gross[i]
        if charge and turn[i] > 0:
            eq -= turn[i] * eq * rate
        out[i] = eq / prev - 1.0
    return pd.Series(out, index=px.index)


def report(name: str, daily, expo: float, annual_turn: float = 0.0) -> None:
    """Accepts either a daily-return Series (to be metriced) or a ready Metrics."""
    from nsealgo.backtest.engine import REF_POSITION_NOTIONAL, _d
    from nsealgo.backtest.metrics import Metrics, compute_metrics

    rate = float(CORRECTED_COSTS.all_in_round_trip_bps(
        _d(REF_POSITION_NOTIONAL))) / 10_000.0
    if isinstance(daily, Metrics):
        m = daily
    else:
        m = compute_metrics(daily, (1.0 + daily).cumprod(),
                            annual_turnover=annual_turn,
                            cost_drag_annual=annual_turn * rate)
    print(f"  {name:<50} {fmt(m)}  exp {expo * 100:5.1f}%")


def flag_panel(full: pd.DataFrame, wpx: pd.DataFrame) -> pd.DataFrame:
    """Trailing z-score flag on ``wpx``, warmed up on the ``W`` bars before it.

    Mirrors what ``build_score_window`` feeds the score panel, so the L0/L1 layers
    measure exactly the same signal as the engine layers L2/L3.
    """
    first = wpx.index[0]
    warm = full.loc[:first][-(W + 3):]
    warm = warm.loc[warm.index < first]
    return zscore_panel(pd.concat([warm, wpx]), W).loc[wpx.index]


def main() -> None:
    px = panel()
    wins = {"TRAIN": (TRAIN_START, TRAIN_END), "TEST": (TEST_START, TEST_END)}

    print("=" * 100)
    print("1. EVENT STUDY — is the z-score break informative at all?")
    print("=" * 100)
    for name, (lo, hi) in wins.items():
        w = px.loc[(px.index >= lo) & (px.index <= hi)]
        event_study(w, W, ENTRY, f"{name} W{W} e{ENTRY}")

    print("\n" + "=" * 100)
    print("2. LAYER PEEL — is it the signal, or the construction eating it?")
    print("=" * 100)
    for name, (lo, hi) in wins.items():
        print(f"\n{'=' * 100}\n{name}\n{'=' * 100}")
        wpx, score = build_score_window((lo, hi), W, ENTRY, "depth")
        flag = flag_panel(px, wpx) < -ENTRY
        held = monthly_targets(wpx, flag)
        expo = float(held.sum(axis=1).mean())
        turn = (np.abs(np.diff(held.to_numpy(), axis=0,
                               prepend=np.zeros((1, held.shape[1])))).sum(axis=1) / 2.0)
        at = float(turn.sum() / (len(wpx) / 244))

        report("L0 raw signal-following (no constraints, no costs)", simulate(wpx, held, False), expo, at)
        report("L1 + full Indian cost stack", simulate(wpx, held, True), expo, at)
        l2 = evaluate("L2", wpx, score)
        report("L2 + caps, sector limits, cash buffer", l2.metrics, l2.diag["avg_exposure"])
        l3 = evaluate("L3", wpx, score)
        report("L3 + turnover budget  == THE REPORTED RESULT", l3.metrics, l3.diag["avg_exposure"])

        bh = buy_and_hold(wpx)
        cmp_ = evaluate("cmp", wpx, composite_score(px).loc[wpx.index])
        report("  [ref] buy-and-hold", bh, 1.0)
        report("  [ref] nsealgo composite", cmp_.metrics, cmp_.diag["avg_exposure"])

        n = flag.sum(axis=1)
        n = n[n > 0]
        print(f"\n  flagged names per rebalance: mean {n.mean():.1f} median "
              f"{n.median():.0f} min {n.min():.0f} max {n.max():.0f} (engine cap 22)")
        print(f"  raw signal turnover {at:.2f}x/y -> drag at corrected costs "
              f"{at * 0.004384 * 100:.2f}%/y")

    print("\n" + "=" * 100)
    print("3. HOW OFTEN IS AN OVERSOLD READING STILL OVERSOLD?")
    print("=" * 100)
    for name, (lo, hi) in wins.items():
        w = px.loc[(px.index >= lo) & (px.index <= hi)]
        z = zscore_panel(w, W)
        fl = z < -1.0
        frac = fl.shift(-1).rolling(200, min_periods=20).mean().to_numpy()
        f = frac[fl.to_numpy()]
        f = f[np.isfinite(f)]
        print(f"  {name}: mean fraction of the NEXT 200 bars still below -1 sigma "
              f"= {f.mean() * 100:.1f}% (median {np.median(f) * 100:.1f}%)")
        # and the raw forward return of a flagged bar vs an unconditional bar
        fwd = (w.shift(-21) / w - 1.0)
        a = fwd.where(fl).stack()
        print(f"      flagged 21d fwd return {float(a.mean()) * 100:+.3f}%  vs "
              f"unconditional {float(fwd.stack().mean()) * 100:+.3f}%")


if __name__ == "__main__":
    main()
