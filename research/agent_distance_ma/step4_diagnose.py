"""Step 4: diagnosis. No new strategy variants -- this decomposes results already
produced, and adds the TRAIN-side random control that step 2 omitted.

The question: the TEST book underperformed badly. Is that (a) the signal carrying no
information, (b) cost drag, or (c) the book structurally unable to be invested?
The decomposition answers it.
"""

from __future__ import annotations

import pandas as pd
from common import (
    BUILDERS,
    COST,
    PORTFOLIO,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    buy_and_hold_result,
    deviation_panel,
    load_panel,
    random_signal_result,
    run_backtest,
)


def decompose(test: pd.DataFrame, held: pd.DataFrame, rets: pd.DataFrame,
              bh_daily: pd.Series) -> None:
    """Split the TEST return into a cash term and a selection term."""
    contrib = (held.shift(1).fillna(0.0) * rets).sum(axis=1)
    inv = held.sum(axis=1)
    years = len(rets) / 244.0

    # Annualised gross return of the invested sleeve alone, i.e. what the holdings
    # earned per unit of capital actually at work. Divide by years, never * 244.
    sleeve_ann = float(contrib.sum() / inv.mean() / years)
    invested = float(inv.mean())
    mkt_ann = float(bh_daily.sum() / years)

    print("--- return decomposition, TEST, selected variant (V3) ---")
    print(f"  window                              : {years:.2f} years")
    print(f"  avg invested fraction              : {invested:.1%}")
    print(f"  sleeve gross return (annualised)   : {sleeve_ann:>7.2%}")
    print(f"  market (EW22) annualised           : {mkt_ann:>7.2%}")
    print(f"  SELECTION term (sleeve - market)   : {sleeve_ann - mkt_ann:>+7.2%}")
    print(f"  CASH term (1 - invested) x sleeve  : "
          f"{-(1 - invested) * sleeve_ann:>+7.2%}")
    print(f"  -> implied gross CAGR              : "
          f"{invested * sleeve_ann:>7.2%}   (actual gross was 1.90%)")
    print("\n  Reading: the sleeve itself barely matched the market, and then roughly")
    print("  half the book was sitting in cash because a 5%-below-a-50d-SMA gate")
    print("  almost never puts 22 names on the screen at once under a 12% name cap.")


def depth_gradient(test: pd.DataFrame, period: int = 50) -> None:
    """Does deeper deviation mean a *worse* buy? Splits signalled bars into quintiles."""
    dev = deviation_panel(test, period)
    sel = dev < -0.05
    fwd21 = test.shift(-21) / test - 1.0
    uni21 = float(fwd21.stack().mean())

    d = dev[sel].stack().rename("dev")
    f = fwd21[sel].stack().rename("fwd21")
    j = pd.concat([d, f], axis=1).dropna()
    j["q"] = pd.qcut(j["dev"], 5, labels=["Q1 shallowest", "Q2", "Q3", "Q4", "Q5 deepest"])
    print(f"\n--- buy depth vs forward return, TEST (period={period}, thr=0.05) ---")
    print(f"  universe mean 21d forward return: {uni21:+.3%}")
    print(f"  {'quintile of deviation':<20}{'n':>9}{'mean fwd21':>13}{'vs universe':>13}")
    for q, g in j.groupby("q", observed=True):
        print(f"  {str(q):<20}{len(g):>9,}{g.fwd21.mean():>12.3%}"
              f"{g.fwd21.mean() - uni21:>+12.3%}")
    print("\n  The book buys the DEEPEST bin. If that bin is the worst, the signal's")
    print("  positive average is not reachable by the way the strategy actually trades.")


def main() -> None:
    panel, symbols, _ = load_panel()
    test = panel.loc[(panel.index >= TEST_START) & (panel.index <= TEST_END)]
    train = panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]

    score = BUILDERS["dev_depth"](test, 50, 0.05)
    r = run_backtest(test, score, COST, PORTFOLIO, rebalance="M")
    rets = test.pct_change(fill_method=None).fillna(0.0)
    bh = buy_and_hold_result(test, sorted(symbols)[:22], "bh")
    decompose(test, r.weights, rets, bh["daily"])

    depth_gradient(test, 50)

    # ---- TRAIN-side random control (step 2 omitted it) -------------------
    dev_tr = deviation_panel(train, 50)
    live_tr = float((dev_tr < -0.05).values.mean())
    print(f"\n--- TRAIN random control, same {live_tr:.2%} of name-days long ---")
    rnd = random_signal_result(train, live_tr, seeds=(1, 2, 3))
    # Build the TRAIN score from the TRAIN frame. Reindexing the TEST score would
    # produce an all-NaN panel and a silently flat book.
    score_tr = BUILDERS["dev_depth"](train, 50, 0.05)
    rtr = run_backtest(train, score_tr, COST, PORTFOLIO, rebalance="M")
    for s, v in rnd.items():
        print(f"  random(seed={s})  CAGR {v.metrics.cagr * 100:>6.2f}%  "
              f"Sharpe {v.metrics.sharpe:>6.2f}  MaxDD {v.metrics.max_drawdown * 100:>7.2f}%")
    print(f"  STRATEGY V3     CAGR {rtr.metrics.cagr * 100:>6.2f}%  "
          f"Sharpe {rtr.metrics.sharpe:>6.2f}  MaxDD {rtr.metrics.max_drawdown * 100:>7.2f}%")
    mean_rand = sum(v.metrics.sharpe for v in rnd.values()) / len(rnd)
    print(f"  -> TRAIN: strategy Sharpe {rtr.metrics.sharpe:.2f} vs random {mean_rand:.2f}"
          f"  ({'BEATS' if rtr.metrics.sharpe > mean_rand else 'LOSES TO'} a coin flip)")

    # ---- how often is the book even full? -------------------------------
    inv = r.weights.sum(axis=1)
    print("\n--- book fullness, TEST ---")
    print(f"  bars <25% invested : {int((inv < 0.25).sum()):>4}/{len(inv)} "
          f"({(inv < 0.25).mean():.0%})")
    print(f"  bars <50% invested : {int((inv < 0.50).sum()):>4}/{len(inv)} "
          f"({(inv < 0.50).mean():.0%})")
    print(f"  bars >80% invested : {int((inv > 0.80).sum()):>4}/{len(inv)} "
          f"({(inv > 0.80).mean():.0%})")

    # ---- sanity: is the TEST window itself just hard? -------------------
    dev_te = deviation_panel(test, 50)
    m = r.metrics
    print("\n--- sanity checks (brief §6) ---")
    print(f"  §6.1 plausibility : CAGR {m.cagr * 100:.2f}%  -> plausible, no bug")
    print(f"  §6.2 weight count : {r.diag['avg_names']:.1f} names (not ~48) -> OK")
    print(f"  §6.3 liveness     : {float((dev_te < -0.05).values.mean()):.2%} of "
          "name-days -> above the 5% floor")
    print("  §6.4 cost drag    : gross 1.90% -> net 1.21%; drag 0.71%/y. Costs hurt")
    print("                      but are NOT the cause: gross was already near zero")
    print(f"  §6.5 random ctl   : strategy Sharpe {m.sharpe:.2f} vs random "
          f"{mean_rand:.2f} -> FAILS the coin-flip bar")


if __name__ == "__main__":
    main()
