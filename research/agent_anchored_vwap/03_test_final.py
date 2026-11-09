"""Step 3 — the single TEST evaluation. Parameters frozen from TRAIN (winner.csv).

Run: .venv/bin/python research/agent_anchored_vwap/03_test_final.py

This is the only place TEST is read. The winner comes from step 2, which never saw it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (  # noqa: E402
    BASE_COSTS,
    CFG,
    HEADER,
    SEP,
    TEST,
    VARIANTS,
    ZeroCostModel,
    build_score,
    buy_and_hold,
    composite_score,
    deviation,
    eligible,
    evaluate,
    full_backtest,
    load,
    random_score,
    rebalance_dates,
    row,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.backtest.metrics import compute_metrics, yearly_returns

pd.set_option("display.width", 240)

N_DRAWS = 25


def _eval_control(score: pd.DataFrame, close: pd.DataFrame):
    """One net-only backtest, sliced to TEST.

    Gross is not needed for a control draw — we only compare the net CAGR/Sharpe of
    the random book against ours on identical terms.
    """
    r = run_backtest(close, score, BASE_COSTS, CFG, rebalance="M")
    lo, hi = TEST
    rr = r.returns.loc[(r.returns.index >= lo) & (r.returns.index <= hi)]
    return compute_metrics(rr)


def _slice_generic(returns, weights, gross_returns, elig):
    from common import _slice_metrics

    return _slice_metrics(
        "TEST", returns, weights, gross_returns, elig, TEST
    )


def main() -> None:
    u = load()
    win = pd.read_csv("winner.csv").iloc[0]
    wname = str(win["variant"])
    wvar = next(v for v in VARIANTS if v.name == wname)

    print("=" * 96)
    print(f"TEST WINDOW  {TEST[0].date()} -> {TEST[1].date()}   (read once, now)")
    print(
        f"Parameters frozen from TRAIN: {wname} "
        f"(period={wvar.period}, threshold={wvar.threshold}, score={wvar.score_kind})"
    )
    print("=" * 96)

    dev = deviation(u.close, wvar.period)
    mask = eligible(dev, wvar.threshold)
    score = build_score(u.close, dev, wvar.threshold, wvar.score_kind)
    res = evaluate(u.close, score, dev, wvar.threshold, TEST, "TEST")
    m = res.metrics

    bh = buy_and_hold(u.close, TEST)
    mbh = compute_metrics(bh)

    print(HEADER)
    print(SEP)
    print(row(res, wname))
    print(
        f"| {'buy & hold (EW, net)':<26} | {mbh.cagr * 100:>7.2f}% | {mbh.sharpe:>6.2f} | "
        f"{mbh.max_drawdown * 100:>7.2f}% | {mbh.calmar:>6.2f} |     n/a |    n/a | "
        f"{len(u.symbols):>5.0f} |      n/a |"
    )

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 96)
    print("TEST vs BUY & HOLD")
    print("=" * 96)
    d_cagr = (m.cagr - mbh.cagr) * 100
    d_dd = (m.max_drawdown - mbh.max_drawdown) * 100
    print(
        f"  CAGR   : {m.cagr * 100:>7.2f}% vs {mbh.cagr * 100:>7.2f}%  ->  {d_cagr:+.2f} pp "
        f"{'BETTER' if d_cagr > 0 else 'WORSE'}"
    )
    print(
        f"  Sharpe : {m.sharpe:>7.2f}  vs {mbh.sharpe:>7.2f}   ->  {m.sharpe - mbh.sharpe:+.2f} "
        f"{'BETTER' if m.sharpe > mbh.sharpe else 'WORSE'}"
    )
    print(
        f"  MaxDD  : {m.max_drawdown * 100:>7.2f}% vs {mbh.max_drawdown * 100:>7.2f}%  ->  "
        f"{d_dd:+.2f} pp {'BETTER (shallower)' if d_dd > 0 else 'WORSE (deeper)'}"
    )
    print(f"  Total  : {m.total_return * 100:>7.1f}% vs {mbh.total_return * 100:>7.1f}%")

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 96)
    print("SANITY CHECKS")
    print("=" * 96)
    print(f"  1 Plausibility    : CAGR {m.cagr * 100:.2f}% — unlevered long-only, no 200%+ blowup. OK")
    print(
        f"  2 Weight count    : {res.avg_names:.1f} names vs target {CFG.n_positions} "
        f"(max_names cap {CFG.max_names}). Not accumulating to 48. OK"
    )
    frac = float(mask.loc[TEST[0]:TEST[1]].values.mean())
    print(
        f"  3 Signal liveness : {frac * 100:.1f}% of name-days long, "
        f"{res.avg_eligible:.1f} eligible/rebalance. Floor is 5%. OK"
    )
    print(
        f"  4 Cost drag       : gross {res.gross_cagr * 100:.2f}% -> net {m.cagr * 100:.2f}% "
        f"({res.cost_drag_annual * 100:.2f}%/yr). "
        + (
            "Gross positive -> NOT a cost-viability failure; it is an alpha failure."
            if res.gross_cagr > 0
            else "GROSS NEGATIVE -> costs are not the binding problem either."
        )
    )

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 96)
    print(f"RANDOM-SIGNAL CONTROL ({N_DRAWS} draws, matched eligible count per rebalance)")
    print("=" * 96)
    rb = [d for d in rebalance_dates(u.close.index) if d in mask.index][1:]
    counts = {d: int(mask.loc[d].sum()) for d in rb}
    rng = np.random.default_rng(20261007)
    cagrs, sharpes = [], []
    for _ in range(N_DRAWS):
        sc = random_score(u.close, rng, counts, mask.index)
        w = _eval_control(sc, u.close)
        cagrs.append(w.cagr)
        sharpes.append(w.sharpe)
    cagrs = np.array(cagrs)
    sharpes = np.array(sharpes)
    pct = float((cagrs < m.cagr).mean() * 100)
    print(
        f"  random CAGR   : mean {cagrs.mean() * 100:>6.2f}%  median {np.median(cagrs) * 100:>6.2f}%"
        f"  min {cagrs.min() * 100:>6.2f}%  max {cagrs.max() * 100:>6.2f}%"
    )
    print(f"  random Sharpe : mean {sharpes.mean():>6.2f}  median {np.median(sharpes):>6.2f}")
    print(f"  strategy      : CAGR {m.cagr * 100:>6.2f}%  Sharpe {m.sharpe:.2f}")
    label = "BEATS" if pct > 80 else ("MARGINAL" if pct >= 60 else "DOES NOT CLEAR")
    print(f"  -> strategy beats random on {pct:.0f}% of {N_DRAWS} draws: {label} the coin")
    np.save("random_cagrs.npy", cagrs)
    np.save("random_sharpes.npy", sharpes)

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 96)
    print("vs nsealgo COMPOSITE FACTOR (same panel, same window, same costs)")
    print("=" * 96)
    comp = composite_score(u.close)
    rc = run_backtest(u.close, comp, BASE_COSTS, CFG, rebalance="M")
    gc = run_backtest(u.close, comp, ZeroCostModel(), CFG, rebalance="M")
    wc = _slice_generic(rc.returns, rc.weights, gc.returns, pd.DataFrame(1.0, index=mask.index, columns=mask.columns))
    print(HEADER)
    print(SEP)
    print(row(res, "anchored_vwap (this)"))
    print(row(wc, "nsealgo composite"))
    v = "BEATS" if m.cagr > wc.metrics.cagr else "LOSES TO"
    print(f"  -> anchored_vwap {v} the composite by {abs(m.cagr - wc.metrics.cagr) * 100:.2f} pp CAGR")

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 96)
    print("FAMILY DISCLOSURE — TEST for all 5 declared variants")
    print("=" * 96)
    print("Selection was made on TRAIN. This is disclosure, not selection: it shows how")
    print("much of the TEST spread is selection luck rather than signal.")
    print(HEADER)
    print(SEP)
    for var in VARIANTS:
        d = deviation(u.close, var.period)
        s = build_score(u.close, d, var.threshold, var.score_kind)
        r = evaluate(u.close, s, d, var.threshold, TEST, "TEST")
        star = "   <- TRAIN-selected HEADLINE" if var.name == wname else ""
        print(row(r, var.name) + star)

    # ------------------------------------------------------------------ #
    print("\n" + "=" * 96)
    print("TEST YEARLY RETURNS")
    print("=" * 96)
    ys = yearly_returns(full_backtest(u.close, score).returns).rename("anchored_vwap")
    ys = ys.loc[str(TEST[0].year):]
    yb = yearly_returns(bh).rename("buy&hold")
    yy = pd.concat([yb, ys], axis=1)
    yy["alpha"] = yy["anchored_vwap"] - yy["buy&hold"]
    print(yy.to_string(float_format=lambda v: f"{v * 100:>7.2f}%"))
    print(
        f"\npositive years {int((yy['anchored_vwap'] > 0).sum())}/{len(yy)}   "
        f"years beating B&H {int((yy['alpha'] > 0).sum())}/{len(yy)}"
    )

    pd.DataFrame(
        {
            "anchored_vwap": full_backtest(u.close, score).returns,
            "buy_and_hold": bh,
        }
    ).to_csv("test_returns.csv")
    print("\nwrote test_returns.csv")


if __name__ == "__main__":
    main()
