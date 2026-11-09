"""TRAIN-only, part 2: where does the return actually go?

Follows on from diag.py Q6, which found the V1 book is only ~52% invested on average
and 0% invested on some rebalance days. That is a *structural* failure mode of a
ternary per-symbol signal in a long-only book, distinct from picking the wrong stocks.

Questions:
  7.  When is the book at ~zero weight? (calendar attribution)
  8.  How much of TRAIN return is lost to holding cash rather than to stock selection?
      Counterfactual: the uninvested sleeve earns the equal-weight universe return.
  9.  Same question in the neutral state only vs the bearish state only — which one
      costs the money?
"""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
MOM = 126
CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)
SEL = (5, 15, 30)  # the variant selected on TRAIN


def sma(p: pd.DataFrame, n: int) -> pd.DataFrame:
    return p.rolling(n, min_periods=n).mean()


def mask_strict(tr, fn, mn, sn):
    f, m, s = sma(tr, fn), sma(tr, mn), sma(tr, sn)
    ok = f.notna() & m.notna() & s.notna()
    return (f > m) & (m > s) & ok


def mask_bearish(tr, fn, mn, sn):
    f, m, s = sma(tr, fn), sma(tr, mn), sma(tr, sn)
    ok = f.notna() & m.notna() & s.notna()
    return (f < m) & (m < s) & ok


def main() -> None:
    panel, _, _ = load_universe("data/nse")
    # Build on the FULL panel then slice, exactly as run.py does, so the warmup
    # matches the headline table and the two sets of numbers reconcile.
    mom = panel / panel.shift(MOM) - 1.0
    strict = mask_strict(panel, *SEL)
    bear = mask_bearish(panel, *SEL)
    tr = panel.loc[TRAIN[0]:TRAIN[1]]
    mom = mom.loc[tr.index]
    strict = strict.loc[tr.index]
    bear = bear.loc[tr.index]

    score = mom.where(strict).rank(axis=1, pct=True)
    res = run_backtest(tr, score.loc[tr.index], COST, CFG, rebalance="M")
    w = res.weights
    inv = w.sum(axis=1)

    # ---- Q7: calendar attribution of the cash periods --------------------- #
    print("=== Q7  invested weight by calendar year (V1, TRAIN) ===")
    by_year = inv.groupby(inv.index.year).mean() * 100
    for y, v in by_year.items():
        days = int((inv.index.year == y).sum())
        worst = inv[inv.index.year == y].min() * 100
        print(f"  {y}: mean invested {v:5.1f}%   min {worst:5.1f}%   ({days} bars)")
    zero = inv[inv < 1e-6]
    print(f"  bars with 0% invested: {len(zero)}/{len(inv)} "
          f"({100 * len(zero) / len(inv):.1f}%)")
    if len(zero):
        spells: list[tuple] = []
        start = prev_d = zero.index[0]
        for d in zero.index[1:]:
            if (d - prev_d).days > 5:
                spells.append((start, prev_d))
                start = d
            prev_d = d
        spells.append((start, prev_d))
        print(f"  contiguous cash spells: {len(spells)}")
        for a, b in sorted(spells, key=lambda x: -(x[1] - x[0]).days)[:5]:
            print(f"    {a:%Y-%m-%d} -> {b:%Y-%m-%d}  ({(b - a).days + 1} calendar days)")

    # ---- Q8: cash-drag counterfactual ------------------------------------- #
    print("\n=== Q8  cash-drag counterfactual (TRAIN) ===")
    print("  sleeves: the engine's book earns nothing where it is not invested;")
    print("  the counterfactual lets the uninvested sleeve earn the equal-weight")
    print("  universe return on the same days. Same costs, same caps.")
    rets = tr.pct_change(fill_method=None).fillna(0.0)
    universe = rets.mean(axis=1)
    strat_gross = (w.shift(1).fillna(0.0) * rets).sum(axis=1)
    blended = strat_gross + (1.0 - inv).shift(1).fillna(0.0) * universe

    def cagr_of(series: pd.Series, costs: pd.Series) -> tuple[float, float]:
        eq = 1.0
        out = []
        for dt in tr.index:
            eq *= 1.0 + float(series.loc[dt])
            c = float(costs.loc[dt])
            if c:
                eq -= c * eq
            out.append(eq)
        e = pd.Series(out, index=tr.index)
        yrs = len(e) / 244
        return float((e.iloc[-1] ** (1 / yrs) - 1) * 100), float(e.iloc[-1])

    # reconstruct the engine's cost series on the normalised equity path
    rb_set = set(_rebal(tr.index))
    tgt_dates = [d for d in tr.index if d in rb_set]
    tg = pd.DataFrame([w.loc[d] for d in tgt_dates], index=tgt_dates)
    turn = (tg - tg.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    rate = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0

    def cost_series(base: pd.Series) -> pd.Series:
        eq = 1.0
        cs = pd.Series(0.0, index=tr.index)
        for dt in tr.index:
            eq *= 1.0 + float(base.loc[dt])
            t = float(turn.loc[dt]) if dt in turn.index else 0.0
            if t > 0:
                amt = 2.0 * t * eq * rate
                eq -= amt
                cs.loc[dt] = amt
        return cs

    c_strat = cost_series(strat_gross)
    c_blend = cost_series(blended)
    cs1, _ = cagr_of(strat_gross, c_strat)
    cs2, _ = cagr_of(blended, c_blend)
    print(f"  strategy as run (cash earns 0%)     TRAIN CAGR {cs1:6.2f}%")
    print(f"  + uninvested sleeve earns universe  TRAIN CAGR {cs2:6.2f}%")
    print(f"  => cash drag cost TRAIN return      {cs1 - cs2:6.2f} pp/yr")
    print(f"  (mean invested {inv.mean() * 100:.1f}%, mean uninvested "
          f"{(1 - inv).mean() * 100:.1f}%)")

    # ---- Q9: which neutral state costs the money? -------------------------- #
    print("\n=== Q9  same counterfactual, variant of the exclusion rule (TRAIN) ===")

    def run_with(exclude_mask: pd.DataFrame | None, label: str) -> None:
        """`exclude_mask` = cells the book may NOT hold. None = hold everything."""
        sc = mom.rank(axis=1, pct=True) if exclude_mask is None \
            else mom.where(~exclude_mask).rank(axis=1, pct=True)
        r = run_backtest(tr, sc.loc[tr.index], COST, CFG, rebalance="M")
        iw = r.weights.sum(axis=1)
        g = (r.weights.shift(1).fillna(0.0) * rets).sum(axis=1)
        b = g + (1.0 - iw).shift(1).fillna(0.0) * universe
        cg = cost_series(g)
        cb = cost_series(b)
        a, _ = cagr_of(g, cg)
        bb, _ = cagr_of(b, cb)
        print(f"  {label:<38} CAGR {r.metrics.cagr * 100:6.2f}%  "
              f"invested {iw.mean() * 100:5.1f}%  "
              f"+cash->universe {bb:6.2f}%  (lift {bb - a:+5.2f} pp)")

    run_with(~strict, "hold f>m>s only (as reported)")
    run_with(bear, "exclude only the bearish f<m<s state")
    run_with(strict | bear, "exclude both extremes")
    run_with(None, "hold everything (pure momentum rank)")


def _rebal(index: pd.DatetimeIndex) -> list:
    keys = index.tz_localize(None).to_period("M")
    s = pd.Series(index, index=index)
    return [g.index[0] for _, g in s.groupby(keys)][1:]


if __name__ == "__main__":
    main()
