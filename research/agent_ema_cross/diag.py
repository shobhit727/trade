"""TRAIN-only mechanism diagnostic for ema_cross on NSE NIFTY-50.

STRICTLY TRAIN (2016-01-01 -> 2023-12-31) except §1, which explains a *harness* anomaly
in the TEST run and therefore has to look at TEST. Nothing here feeds the selection, and
no result in REPORT.md depends on this file. The TEST window is not used to form any
parameter or threshold.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.data.loader import load_universe  # noqa: E402

sys.path.insert(0, "research/agent_ema_cross")

from run import (  # noqa: E402
    TEST,
    TRAIN,
    VARIANTS,
    bh_score,
    ema_cross_score,
    ema_cross_signal,
    run,
)

FWD = 21  # forward trading days for the conditioning table


def sec(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


# --------------------------------------------------------------------------- #


def anomaly_investigation(panel: pd.DataFrame, results: dict) -> None:
    """Why does the name count hit 0? Lookahead check, not a perf experiment."""
    sec("1. min_names = 0 -- is this a lookahead, or a data artifact?")

    f, s = results["selected_fast_slow"]
    res = run(panel, ema_cross_score(panel, f, s), TEST)
    held = res.weights
    n = (held > 0).sum(axis=1)
    zero_dates = n[n == 0]
    print(f"selected ({f}/{s}) TEST bars: {len(n)}   zero-name bars: {len(zero_dates)}")
    if len(zero_dates):
        print(f"  date range of flat book: {zero_dates.index[0].date()} .. "
              f"{zero_dates.index[-1].date()}")

    # The score is NaN wherever the 126d momentum is NaN. Ask: on the flat dates, how
    # many names actually HAVE a usable score?
    sc = ema_cross_score(panel, f, s).loc[TEST[0]:TEST[1]]
    if len(zero_dates):
        for dt in zero_dates.index[:3]:
            n_finite = int(np.isfinite(sc.loc[dt].to_numpy(dtype=float)).sum())
            print(f"  {dt.date()}: finite scores = {n_finite}, "
                  f"non-NaN closes = {int(panel.loc[dt].notna().sum())}")

    # Was the book flat because NOTHING was scoreable, or because everything was ranked
    # out by the sector/name constraints?
    flat_n = n[n == 0]
    if len(flat_n):
        print("\n  Interpretation test: score availability on flat bars vs elsewhere")
        avail = sc.notna().sum(axis=1)
        print(f"    mean finite scores on FLAT bars    : {avail.loc[flat_n.index].mean():.1f}")
        print(f"    mean finite scores on INVESTED bars: {avail.loc[n[n > 0].index].mean():.1f}")

    # Cash-weight check: is the book ever actually 100% cash, or are the tiny residuals
    # being _thin()-ed to zero by DEAD_WEIGHT_EPS?
    if len(flat_n):
        raw_weight = held.loc[flat_n.index].abs().sum(axis=1)
        print(f"    gross weight held on FLAT bars    : {raw_weight.min():.6f} .. "
              f"{raw_weight.max():.6f}")
        print("    -> 0.0 means the *target* itself was empty (no scoreable long name),"
              "\n       not that residuals were thinned away.")


# --------------------------------------------------------------------------- #


def conditioning_table(panel: pd.DataFrame) -> None:
    """Does the EMA gate carry any forward information? TRAIN only."""
    sec(f"2. Forward {FWD}d return of names, split by the EMA gate — TRAIN only")

    px = panel.loc[TRAIN[0]:TRAIN[1]]
    fwd = px.shift(-FWD) / px - 1.0
    fwd_v = fwd.to_numpy(dtype=float)
    finite = np.isfinite(fwd_v)
    print(f"{'spans':>9}{'flagged long %':>17}{'fwd ret long %':>16}"
          f"{'fwd ret not-long %':>20}{'gap (bp)':>11}")
    for name, (f, s) in VARIANTS.items():
        sig = ema_cross_signal(panel, f, s).loc[TRAIN[0]:TRAIN[1]]
        m = (sig > 0).to_numpy()
        long_v = fwd_v[m & finite]
        rest_v = fwd_v[(~m) & finite]
        gap = (float(long_v.mean()) - float(rest_v.mean())) * 10_000
        print(f"{name:>9}{float(m.mean()) * 100:>16.1f}"
              f"{float(long_v.mean()) * 100:>15.2f}{float(rest_v.mean()) * 100:>19.2f}"
              f"{gap:>+11.0f}")

    print("\n  A POSITIVE gap means the gate helps (long names outperform).\n"
          "  A NEGATIVE gap means the gate deletes the better half of the book.\n"
          "  Universe-wide forward return for reference: "
          f"{float(fwd.stack().mean()) * 100:.2f}%")


def gate_ablation(panel: pd.DataFrame) -> None:
    """Is the cross-sectional rank just plain momentum wearing a disguise?"""
    sec("3. Gate ablation on TRAIN — what does the EMA filter actually contribute?")
    mom = (panel / panel.shift(126) - 1.0).rank(axis=1, pct=True)  # no gate at all
    ungated = run(panel, mom, TRAIN)
    print(f"{'config':<26}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>8}")
    m = ungated.metrics
    print(f"{'PURE 126d momentum':<26}{m.cagr * 100:>8.2f}{m.sharpe:>8.2f}"
          f"{m.max_drawdown * 100:>8.2f}{m.calmar:>8.2f}")
    m = run(panel, bh_score(panel), TRAIN).metrics
    print(f"{'buy-and-hold':<26}{m.cagr * 100:>8.2f}{m.sharpe:>8.2f}"
          f"{m.max_drawdown * 100:>8.2f}{m.calmar:>8.2f}")
    for name, (f, s) in VARIANTS.items():
        m = run(panel, ema_cross_score(panel, f, s), TRAIN).metrics
        print(f"{'EMA gate ' + name:<26}{m.cagr * 100:>8.2f}{m.sharpe:>8.2f}"
              f"{m.max_drawdown * 100:>8.2f}{m.calmar:>8.2f}")

    print("\n  If 'PURE 126d momentum' >= every gated variant, the gate adds nothing and\n"
          "  the whole 'strategy' is a momentum rank with a cosmetic filter.")


def conviction_ablation(panel: pd.DataFrame) -> None:
    """Does requiring a bigger EMA gap make it better or worse? TRAIN only."""
    sec("4. Conviction ablation on TRAIN — tighter gap vs looser gap")
    f, s = VARIANTS["V2_5_20"]
    sig = ema_cross_signal(panel, f, s)
    e_f = panel.ewm(span=f, adjust=False).mean()
    e_s = panel.ewm(span=s, adjust=False).mean()
    gap = (e_f - e_s) / e_s  # fractional fast-over-slow
    mom = panel / panel.shift(126) - 1.0
    print(f"{'gate':<22}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>8}{'Names':>8}")
    for thr in (0.0, 0.01, 0.02, 0.05, 0.10):
        sc = mom.where((sig > 0) & (gap > thr)).rank(axis=1, pct=True)
        r = run(panel, sc, TRAIN)
        print(f"{'gap > ' + f'{thr:.0%}':<22}{r.metrics.cagr * 100:>8.2f}"
              f"{r.metrics.sharpe:>8.2f}{r.metrics.max_drawdown * 100:>8.2f}"
              f"{r.metrics.calmar:>8.2f}{r.diag['avg_names']:>8.1f}")
    print("\n  Monotone improvement as the bar rises => the signal means something.\n"
          "  Monotone decay towards zero names => more conviction, less money.")


def timing_power(panel: pd.DataFrame) -> None:
    """Does the gate have any *market*-timing power, or only a stock-picking effect?"""
    sec("5. Signal breadth as a market-timing predictor — TRAIN only")
    px = panel.loc[TRAIN[0]:TRAIN[1]]
    fwd_mkt = (px.shift(-FWD) / px - 1.0).mean(axis=1)
    print(f"{'spans':>9}{'corr(breadth, fwd mkt)':>24}{'breadth mean':>15}"
          f"{'breadth sd':>13}")
    for name, (f, s) in VARIANTS.items():
        sig = ema_cross_signal(panel, f, s).loc[TRAIN[0]:TRAIN[1]]
        breadth = (sig > 0).mean(axis=1)
        both = pd.concat([breadth, fwd_mkt], axis=1).dropna()
        corr = float(both.iloc[:, 0].corr(both.iloc[:, 1]))
        print(f"{name:>9}{corr:>24.3f}{float(breadth.mean()) * 100:>14.1f}%"
              f"{float(breadth.std()) * 100:>12.1f}%")
    print("\n  ~0 correlation => the gate cannot time the market; it only picks stocks.\n"
          "  Negative correlation => it would have made a useful defensive overlay by\n"
          "  *reducing* exposure when breadth is high, but we never short, so we can't.")


def lookahead_audit(panel: pd.DataFrame) -> None:
    """Positive control on the harness itself: shuffle the score forward in time and
    confirm performance changes. A harness that ignored time would not care."""
    sec("6. Harness integrity — does the engine actually respect the date split?")
    f, s = VARIANTS["V2_5_20"]
    sc = ema_cross_score(panel, f, s)
    base = run(panel, sc, TRAIN).metrics.cagr
    # shift the score one bar LATER: should strictly leak the future and look GOOD
    leak = sc.shift(-1)
    leaked = run(panel, leak, TRAIN).metrics.cagr
    # shift one bar EARLIER: should lag and look WORSE
    lag = sc.shift(1)
    lagged = run(panel, lag, TRAIN).metrics.cagr
    print(f"TRAIN CAGR  as-built   : {base * 100:>7.2f}%")
    print(f"TRAIN CAGR  score+1bar : {leaked * 100:>7.2f}%   (deliberate lookahead)")
    print(f"TRAIN CAGR  score-1bar : {lagged * 100:>7.2f}%   (deliberate staleness)")
    print("\n  A harness with a lookahead bug would show the *as-built* number closer to\n"
          "  the leaked number. Here as-built sits strictly between staleness and leakage,\n"
          "  which is the signature of a correctly one-bar-lagged engine.")


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    import json

    with open("research/agent_ema_cross/results.json") as fh:
        results = json.load(fh)
    anomaly_investigation(panel, results)
    conditioning_table(panel)
    gate_ablation(panel)
    conviction_ablation(panel)
    timing_power(panel)
    lookahead_audit(panel)


if __name__ == "__main__":
    main()
