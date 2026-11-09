"""TRAIN-only diagnostics for triple_moving_average on NSE NIFTY-50.

Answers: WHY does the strategy fail? Everything here is computed on
2016-01-01 -> 2023-12-31 only. TEST is not touched by this file.

Questions:
  1. Is the `f > m > s` state positively or negatively predictive of forward returns?
  2. Does demanding monotone alignment cost anything versus a plain `f > m` filter?
  3. Does the filter have any market-timing power (breadth vs forward market return)?
  4. What does the gate contribute once the book already ranks by momentum?
  5. Is the book under-invested (fewer than 22 eligible names on rebalance days)?
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
FWD = 21
MOM = 126
VARIANTS = {
    "V1_5_15_30": (5, 15, 30),
    "V2_10_30_60": (10, 30, 60),
    "V3_20_50_100": (20, 50, 100),
    "V4_20_60_120": (20, 60, 120),
    "V5_10_20_50": (10, 20, 50),
}
CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)


def sma(p: pd.DataFrame, n: int) -> pd.DataFrame:
    return p.rolling(n, min_periods=n).mean()


def parts(panel, f_n, m_n, s_n):
    f, m, s = sma(panel, f_n), sma(panel, m_n), sma(panel, s_n)
    return f, m, s


def fwd21(panel: pd.DataFrame) -> pd.DataFrame:
    """Forward 21-trading-day return, point-in-time (uses only future prices as the
    LABEL — never as an input)."""
    return panel.shift(-FWD) / panel - 1.0


def main() -> None:  # noqa: PLR0915
    panel, symbols, _ = load_universe("data/nse")
    tr = panel.loc[TRAIN[0]:TRAIN[1]]
    lab = fwd21(tr)

    print(f"TRAIN panel {tr.shape}  {tr.index[0].date()} -> {tr.index[-1].date()}")

    # ---- Q1: is the +1 state predictive? ---------------------------------- #
    print(f"\n=== Q1  forward {FWD}d return by strategy state (TRAIN) ===")
    print(f"{'variant':<14}{'f>m>s +1':>12}{'f<m<s -1':>12}{'mixed 0':>12}"
          f"{'gap(+1 - 0)':>13}")
    q1 = {}
    for name, (fn, mn, sn) in VARIANTS.items():
        f, m, s = parts(tr, fn, mn, sn)
        ok = f.notna() & m.notna() & s.notna()
        bull = ((f > m) & (m > s) & ok).to_numpy()
        bear = ((f < m) & (m < s) & ok).to_numpy()
        mix = (ok & ~bull & ~bear).to_numpy()
        lv = lab.to_numpy()
        r1 = float(np.nanmean(lv[bull]) * 100)
        rm = float(np.nanmean(lv[mix]) * 100)
        r2 = float(np.nanmean(lv[bear]) * 100)
        q1[name] = (r1, rm, r2)
        print(f"{name:<14}{r1:>11.2f}%{r2:>11.2f}%{rm:>11.2f}%{r1 - rm:>12.2f}%")
    print("read: a POSITIVE gap column means flagging long picks names that outperform "
          "the rest.")

    # ---- Q2: monotone alignment vs a plain fast>slow filter ---------------- #
    print("\n=== Q2  does requiring alignment (f>m>s) beat a looser f>s? (TRAIN) ===")
    print(f"{'variant':<14}{'f>m>s':>10}{'f>m only':>10}{'f>s only':>10}"
          f"{'strict lift':>13}")
    q2 = {}
    for name, (fn, mn, sn) in VARIANTS.items():
        f, m, s = parts(tr, fn, mn, sn)
        ok = f.notna() & m.notna() & s.notna()
        strict = ((f > m) & (m > s) & ok).to_numpy()
        gm = ((f > m) & ok).to_numpy()
        gs = ((f > s) & ok).to_numpy()
        lv = lab.to_numpy()
        a = float(np.nanmean(lv[strict]) * 100)
        b = float(np.nanmean(lv[gm]) * 100)
        c = float(np.nanmean(lv[gs]) * 100)
        q2[name] = (a, b, c)
        print(f"{name:<14}{a:>9.2f}%{b:>9.2f}%{c:>9.2f}%{a - b:>12.2f}%")
    print("read: NEGATIVE strict lift = the extra 'monotone' requirement removes "
          "better names.")

    # ---- Q3: does breadth time the market? --------------------------------- #
    print(f"\n=== Q3  signal breadth vs forward {FWD}d equal-weight market (TRAIN) ===")
    print(f"{'variant':<14}{'corr(breadth, fwd mkt)':>24}")
    mkt = tr.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    mkt_fwd = mkt.shift(-FWD)
    q3 = {}
    for name, (fn, mn, sn) in VARIANTS.items():
        f, m, s = parts(tr, fn, mn, sn)
        ok = f.notna() & m.notna() & s.notna()
        br = pd.Series(
            (((f > m) & (m > s) & ok).sum(axis=1) / ok.sum(axis=1)).to_numpy(),
            index=tr.index,
        )
        c = float(br.corr(mkt_fwd))
        q3[name] = c
        print(f"{name:<14}{c:>24.4f}")
    print("read: |corr| well under ~0.15 means no usable market-timing power.")

    # ---- Q4: what does the gate contribute? (ablation) --------------------- #
    print("\n=== Q4  TRAIN ablation — strip the gate, rank by 126d momentum alone ===")
    n_pos = CFG.n_positions
    # Build the momentum and the gate on the FULL panel then slice, exactly as
    # run.py does, so these numbers reconcile with the headline table rather than
    # losing 126 days of warmup at the TRAIN boundary.
    mom_full = panel / panel.shift(MOM) - 1.0

    def gate_full(fn: int, mn: int, sn: int) -> pd.DataFrame:
        f, m, s = parts(panel, fn, mn, sn)
        ok = f.notna() & m.notna() & s.notna()
        return (f > m) & (m > s) & ok

    def run_win(score: pd.DataFrame) -> dict:
        r = run_backtest(tr, score.loc[tr.index], COST, CFG, rebalance="M")
        return {
            "cagr": round(r.metrics.cagr * 100, 2),
            "sharpe": round(r.metrics.sharpe, 2),
            "maxdd": round(r.metrics.max_drawdown * 100, 2),
            "calmar": round(r.metrics.calmar, 2),
            "names": round(r.diag["avg_names"], 1),
        }

    no_gate = run_win(mom_full.rank(axis=1, pct=True))
    print(f"  no gate (pure 126d momentum rank) : {no_gate}")

    for name in ("V1_5_15_30", "V3_20_50_100"):
        fn, mn, sn = VARIANTS[name]
        sc = mom_full.where(gate_full(fn, mn, sn)).rank(axis=1, pct=True)
        print(f"  with {name:<16} gate  : {run_win(sc)}")

    # ---- Q5: is the book under-invested? ----------------------------------- #
    print("\n=== Q5  how many names qualify on each rebalance day? (TRAIN) ===")
    idx = tr.index.tz_localize(None).to_period("M")
    rb = [g.index[0] for _, g in pd.Series(tr.index, index=tr.index).groupby(idx)][1:]
    for name, (fn, mn, sn) in VARIANTS.items():
        f, m, s = parts(tr, fn, mn, sn)
        ok = f.notna() & m.notna() & s.notna()
        n_long = (((f > m) & (m > s) & ok).sum(axis=1)).loc[rb]
        short = int((n_long < n_pos).sum())
        print(f"{name:<14} median eligible {n_long.median():>5.1f}  "
              f"min {n_long.min():>3d}  max {n_long.max():>3d}  "
              f"| rebalances with <{n_pos} eligible: {short}/{len(rb)} "
              f"({100 * short / len(rb):.0f}%)")

    # ---- Q6: how much of the +1 state's book actually survives the caps? ---- #
    print("\n=== Q6  realised invested weight on rebalance days (V1, TRAIN) ===")
    fn, mn, sn = VARIANTS["V1_5_15_30"]
    sc = mom_full.where(gate_full(fn, mn, sn)).rank(axis=1, pct=True)
    res = run_backtest(tr, sc.loc[tr.index], COST, CFG, rebalance="M")
    w = res.weights
    inv = w.sum(axis=1)
    print(f"  invested weight: mean {inv.mean() * 100:.1f}%  "
          f"p05 {inv.quantile(0.05) * 100:.1f}%  "
          f"p95 {inv.quantile(0.95) * 100:.1f}%")
    print("  (cash buffer target 10% -> ideal invested 90%)")

    print("\n--- summary numbers for the report ---")
    print(f"Q1 gap (+1 minus mixed), V1 = {q1['V1_5_15_30'][0] - q1['V1_5_15_30'][1]:+.2f} pp")
    print(f"Q2 strict-vs-f>m lift, V1 = {q2['V1_5_15_30'][0] - q2['V1_5_15_30'][1]:+.2f} pp")
    print(f"Q3 breadth corr, V1 = {q3['V1_5_15_30']:+.4f}")
    print(f"Q4 no-gate TRAIN = {no_gate}")
    print(f"np_annualise_check: FWD={FWD} MOM={MOM} n_pos={n_pos}")


if __name__ == "__main__":
    main()
