"""TRAIN-only mechanism diagnostics for trend_momentum_strategy.

NOT a strategy-variant search. Nothing reported in REPORT.md's TEST tables depends on
anything here. These answer "why" — which leg of the two-leg confluence filter carries or
destroys the signal, and whether the short-horizon ROC gate adds anything over the
126d cross-sectional rank it is wrapped around.

All predictive statistics are computed on TRAIN only (2016-01-01 -> 2023-12-31).
"""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_trendmom")

from run import (  # noqa: E402
    COST,
    MOM_DAYS,
    TRAIN,
    VARIANTS,
    Variant,
    roc_panel,
    run,
    sma_panel,
    trend_mom_signal,
)

from nsealgo.data.loader import load_universe  # noqa: E402

FWD = 21  # forward horizon for the predictive test ~= the rebalance spacing


def fwd(panel: pd.DataFrame, n: int) -> pd.DataFrame:
    """Forward `n`-bar return. Used for diagnosis only, never inside the backtest."""
    return panel.shift(-n) / panel - 1.0


def legs(panel: pd.DataFrame, v: Variant) -> dict[str, pd.DataFrame]:
    f = sma_panel(panel, v.fast)
    s = sma_panel(panel, v.slow)
    m = roc_panel(panel, v.mom)
    return {
        "trend_up": f > s,
        "mom_up": m > v.thr,
        "both_up": (f > s) & (m > v.thr),
    }


def avg_fwd(mask: pd.DataFrame, f: pd.DataFrame) -> float:
    vals = f.where(mask & f.notna())
    return float(vals.stack().mean()) if vals.notna().any().any() else float("nan")


def bucket_table(panel: pd.DataFrame, masks: dict, label: str) -> None:
    w = panel.loc[TRAIN[0]:TRAIN[1]]
    fw = fwd(w, FWD)
    all_avg = float(fw.stack().mean())
    print(f"\n  {label} — average forward {FWD}d return, TRAIN")
    print(f"    universe                       {all_avg * 100:+7.3f}%")
    for name, m in masks.items():
        a = avg_fwd(m.loc[w.index], fw)
        n = int(m.loc[w.index].sum().sum())
        share = n / float(m.loc[w.index].size)
        print(f"    {name:<28}{a * 100:+7.3f}%   (n={n:,}  {share * 100:4.1f}% of cells)"
              f"   spread vs univ {(a - all_avg) * 100:+6.3f} pp")


def ablation_table(panel: pd.DataFrame, v: Variant) -> None:
    """Which leg matters, TRAIN only. Same book, same costs, same rank."""
    mom126 = roc_panel(panel, MOM_DAYS)
    lg = legs(panel, v)

    variants_score = {
        "both legs (= the strategy)": mom126.where(lg["both_up"]).rank(axis=1, pct=True),
        "trend leg only (SMA cross)": mom126.where(lg["trend_up"]).rank(axis=1, pct=True),
        "momentum leg only (ROC)": mom126.where(lg["mom_up"]).rank(axis=1, pct=True),
        "no gate at all (= BH_top22)": mom126.rank(axis=1, pct=True),
    }
    print(f"\n  TRAIN ablation, config {v}")
    print(f"    {'construction':<28}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>9}"
          f"{'Names':>7}{'Turn':>6}{'Cost%':>7}")
    for name, sc in variants_score.items():
        res = run(panel, sc, TRAIN)
        m = res.metrics
        print(f"    {name:<28}{m.cagr * 100:>8.2f}{m.sharpe:>8.2f}"
              f"{m.max_drawdown * 100:>9.2f}{res.diag['avg_names']:>7.1f}"
              f"{m.annual_turnover:>6.2f}{m.cost_drag_annual * 100:>7.2f}")


def own_roc_rank_ablation(panel: pd.DataFrame, v: Variant) -> None:
    """Rank by the strategy's OWN momentum instead of the 126d default."""
    sig = trend_mom_signal(panel, v)
    sc = roc_panel(panel, v.mom).where(sig > 0).rank(axis=1, pct=True)
    res = run(panel, sc, TRAIN)
    m = res.metrics
    print(f"\n    rank by ROC({v.mom}) among flagged  TRAIN: CAGR {m.cagr * 100:.2f}%  "
          f"Sharpe {m.sharpe:.2f}  MaxDD {m.max_drawdown * 100:.2f}%  "
          f"names {res.diag['avg_names']:.1f}")


def timing_power(panel: pd.DataFrame, v: Variant) -> None:
    """Does signal breadth time the market? TRAIN only."""
    w = panel.loc[TRAIN[0]:TRAIN[1]]
    f = sma_panel(panel, v.fast)
    s = sma_panel(panel, v.slow)
    breadth = ((f > s) & (f > s)).mean(axis=1).loc[w.index]  # frac of names trending up
    fwd_mkt = fwd(w, FWD).mean(axis=1)
    both = pd.concat([breadth, fwd_mkt], axis=1).dropna()
    corr = float(both.corr().iloc[0, 1])
    print(f"\n  market timing, TRAIN: corr(trend breadth, fwd {FWD}d equal-wt return) "
          f"= {corr:+.3f}  (n={len(both)})")
    q = both.iloc[:, 0].quantile([0.25, 0.75])
    lo = both.loc[both.iloc[:, 0] <= q.iloc[0], 1].mean()
    hi = both.loc[both.iloc[:, 0] >= q.iloc[1], 1].mean()
    print(f"    lowest-breadth quartile fwd {FWD}d {lo * 100:+.3f}%  |  "
          f"highest-breadth quartile {hi * 100:+.3f}%  |  spread {(hi - lo) * 100:+.3f} pp")


def threshold_monotone(panel: pd.DataFrame, v: Variant) -> None:
    """Does a stricter conviction bar help or hurt, TRAIN only?"""
    print("\n  conviction bar (threshold) on the momentum leg, TRAIN "
          f"(selected config fast={v.fast} slow={v.slow} mom={v.mom}):")
    print(f"    {'thr':>6}{'CAGR%':>9}{'Sharpe':>8}{'Live%':>8}{'Names':>7}")
    for thr in (0.00, 0.01, 0.02, 0.05, 0.10):
        vv = Variant(v.fast, v.slow, v.mom, thr)
        res = run(panel, trend_mom_signal(panel, vv).pipe(
            lambda s: roc_panel(panel, MOM_DAYS).where(s > 0).rank(axis=1, pct=True)
        ), TRAIN)
        m = res.metrics
        sig = trend_mom_signal(panel, vv)
        live = float((sig.loc[TRAIN[0]:TRAIN[1]] > 0).to_numpy().mean())
        print(f"    {thr:>6.2f}{m.cagr * 100:>9.2f}{m.sharpe:>8.2f}"
              f"{live * 100:>7.1f}%{res.diag['avg_names']:>7.1f}")


def rebalance_breadth(panel: pd.DataFrame, v: Variant, window: tuple[str, str]) -> None:
    """Structural fact: how many names the gate offers on each actual rebalance date."""
    sig = trend_mom_signal(panel, v)
    s = sig.loc[window[0]:window[1]].gt(0).sum(axis=1)
    rb = s.groupby(s.index.to_period("M")).first()
    print(f"\n  flagged names on the FIRST trading day of each month, {window[0]}"
          f" -> {window[1]} (config {v})")
    print(f"    mean {rb.mean():.1f}  median {rb.median():.0f}  min {rb.min()}  "
          f"max {rb.max()}")
    print(f"    rebalance dates with < 22 flagged names: "
          f"{int((rb < 22).sum())}/{len(rb)}")
    print(f"    rebalance dates with < 10 flagged names:  "
          f"{int((rb < 10).sum())}/{len(rb)}")


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")
    print("\n############ TRAIN-ONLY DIAGNOSTICS ############")

    # Same declared selection rule as run.py: max TRAIN Sharpe. Recomputed here rather
    # than hardcoded so the diagnostic can never drift from the protocol run.
    best, best_sh = None, -1e9
    for k, vv in VARIANTS.items():
        sh = run(panel, roc_panel(panel, MOM_DAYS)
                 .where(trend_mom_signal(panel, vv) > 0).rank(axis=1, pct=True),
                 TRAIN).metrics.sharpe
        print(f"  TRAIN Sharpe {k} ({vv}) = {sh:.2f}")
        if sh > best_sh:
            best, best_sh = k, sh
    v = VARIANTS[best]
    print(f"\nselected variant (max TRAIN Sharpe): {best} -> {v}")

    bucket_table(panel, legs(panel, v), f"per-leg, {v}")
    ablation_table(panel, v)
    own_roc_rank_ablation(panel, v)
    timing_power(panel, v)
    threshold_monotone(panel, v)

    print("\n############ STRUCTURAL (construction, not a tuning decision) ############")
    for w in (TRAIN, ("2024-01-01", "2026-10-01")):
        rebalance_breadth(panel, v, w)

    # turnover decomposition, TRAIN
    sc = roc_panel(panel, MOM_DAYS).where(trend_mom_signal(panel, v) > 0).rank(
        axis=1, pct=True)
    res = run(panel, sc, TRAIN)
    print(f"\n  cost decomposition, TRAIN, selected variant: turnover "
          f"{res.metrics.annual_turnover:.2f}x/y one-way "
          f"-> drag {res.metrics.cost_drag_annual * 100:.2f}%/y "
          f"(= {res.metrics.annual_turnover:.2f} x 2 x "
          f"{float(COST.all_in_round_trip_bps(100000)):.2f}bps / 1e4 compounded)")
    print(f"  realised costs on Rs 21,00,000 over TRAIN: "
          f"Rs {res.costs_paid:,.0f}")

    # portfolio concentration of realised P&L, TRAIN (GOAL.md Gate 4)
    px = panel.loc[TRAIN[0]:TRAIN[1]]
    held = res.weights.reindex(px.index).ffill().fillna(0.0)
    contrib = (held.shift(1).fillna(0.0) * px.pct_change(fill_method=None)
               .fillna(0.0)).sum(axis=0)
    tot = contrib.sum()
    print(f"\n  P&L concentration, TRAIN: top stock "
          f"{contrib.nlargest(1).index[0]} = {contrib.max() / tot * 100:.1f}% of "
          f"gross sum  |  top 3 = {contrib.nlargest(3).sum() / tot * 100:.1f}%")
    print(f"    n contributors: {int((contrib != 0).sum())} of {len(contrib)} names")


if __name__ == "__main__":
    main()

