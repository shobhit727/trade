"""Step 03 — THE SINGLE TEST READ.

V5 (L=60, entry=0.5) is frozen. Selected on TRAIN in 02_train_select.py by a rule fixed
before any run. Nothing is tuned here. This script is run exactly once.

It reports, over the identical TEST window 2024-01-01 .. 2026-10-01:
  * the selected strategy, net of 21.92 bps
  * buy-and-hold, same window, same net footing
  * the nsealgo production composite, same window
  * 20 random-signal controls with the same number of flagged names per day
  * cost stress, beta/alpha, sanity checks, yearly returns
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from common import (
    CFG,
    ENGINE_SHA,
    HDR,
    buy_and_hold,
    fmt_yearly,
    liveness,
    load_panel,
    row,
    run,
    test_panel,
    zscore_score,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import CostModel
from nsealgo.factors.core import build_composite_score

HERE = Path(__file__).resolve().parent
SEL = json.loads((HERE / "selected_variant.json").read_text())
N_SEEDS = 20
TD = 244


def random_control_score(panel: pd.DataFrame, mask: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    m = mask.to_numpy()
    score = np.full(m.shape, np.nan)
    for i in range(m.shape[0]):
        idx = np.flatnonzero(m[i])
        if idx.size == 0:
            continue
        score[i, rng.choice(idx, size=idx.size, replace=False)] = rng.permutation(
            np.arange(1, idx.size + 1) / idx.size
        )
    return pd.DataFrame(score, index=panel.index, columns=panel.columns)


def main() -> None:
    panel = load_panel()[0]
    te = test_panel()
    L, entry, vid = SEL["L"], SEL["entry"], SEL["id"]

    print("=" * 78)
    print("THE SINGLE TEST READ — variant frozen from TRAIN, nothing tuned here")
    print("=" * 78)
    print(f"engine_sha = {ENGINE_SHA}")
    print(f"variant    = {vid}  L={L} entry={entry}   (selected on TRAIN)")
    print(f"TEST       = {te.index[0].date()} .. {te.index[-1].date()}  "
          f"({len(te):,} bars, {te.shape[1]} symbols)")
    print(f"train sha of selection = {SEL['engine_sha']}  "
          f"{'MATCH' if SEL['engine_sha'] == ENGINE_SHA else '*** MISMATCH ***'}")
    assert SEL["engine_sha"] == ENGINE_SHA, "engine changed between TRAIN and TEST"

    score = zscore_score(panel, L, entry).loc[te.index]
    res = run(te, score)
    m = res.metrics

    bh = buy_and_hold(te, "buy_and_hold TEST")
    comp = run(te, build_composite_score(panel).loc[te.index])
    zero = run_backtest(te, score, CostModel(segment="delivery", slippage_bps=Decimal("0")),
                        config=CFG, rebalance="M")

    print()
    print(HDR)
    print(row(f"**{vid} STRATEGY**", m, f"avg_names={res.diag['avg_names']:.1f}"))
    print(row("buy-and-hold", bh["metrics"], f"{te.shape[1]} names, net"))
    print(row("nsealgo composite", comp.metrics, "production factor blend"))
    print(row("zero-cost DIAG", zero.metrics, "not reportable — diagnostic only"))

    # ---- controls -------------------------------------------------------- #
    mask = score.notna()
    sh, ca = [], []
    for s in range(N_SEEDS):
        r = run(te, random_control_score(te, mask, s))
        sh.append(r.metrics.sharpe)
        ca.append(r.metrics.cagr)
    sh, ca = np.array(sh), np.array(ca)

    print()
    print(f"random-signal control ({N_SEEDS} seeds, same #flagged/day, TEST):")
    print(f"  Sharpe  min {sh.min():.2f}  p25 {np.percentile(sh,25):.2f}  "
          f"median {np.median(sh):.2f}  p75 {np.percentile(sh,75):.2f}  max {sh.max():.2f}")
    print(f"  CAGR    min {ca.min()*100:.2f}%  median {np.median(ca)*100:.2f}%  "
          f"max {ca.max()*100:.2f}%")
    print(f"  strategy Sharpe {m.sharpe:.2f} beats {int((sh < m.sharpe).sum())}/{N_SEEDS} "
          f"({(sh < m.sharpe).mean()*100:.0f}th pct)")

    # ---- beta / alpha ---------------------------------------------------- #
    x = bh["returns"].reindex(res.returns.index).fillna(0.0)
    y = res.returns.fillna(0.0)
    beta = float(np.cov(x, y, ddof=1)[0, 1]) / float(np.var(x, ddof=1))
    alpha_ann = (1.0 + (float(y.mean()) - beta * float(x.mean()))) ** TD - 1.0
    print()
    print(f"beta {beta:.3f}   alpha(ann) {alpha_ann * 100:+.2f}%/y   "
          f"corr {float(np.corrcoef(x, y)[0, 1]):.3f}")

    # ---- sanity ---------------------------------------------------------- #
    w = res.weights
    inv = w.sum(axis=1)
    print()
    print("sanity (brief §6):")
    print(f"  liveness        {liveness(te, L, entry) * 100:.1f}%")
    print(f"  avg names       {float((w > 0).sum(axis=1).mean()):.1f}  "
          f"(max {int((w > 0).sum(axis=1).max())}, dead residues "
          f"{int(((w > 0) & (w < 1e-4)).to_numpy().sum())})")
    print(f"  max weight      {float(w.max().max()) * 100:.2f}% (cap 12%)")
    print(f"  invested        mean {inv.mean() * 100:.1f}%  median {inv.median() * 100:.1f}%  "
          f"min {inv.min() * 100:.1f}%")
    print(f"  BUY&HOLD NaN%   {bh['nan_frac'] * 100:.3f}")

    # ---- yearly ---------------------------------------------------------- #
    # `yearly_returns` measures 2017 against a starting equity of 1.0, so the first
    # (partial) year is reported rather than silently dropped. An earlier draft of this
    # script sliced off the first year, which would have hidden 2024 from the table and
    # made the result look cherry-picked. Nothing about the variant changed; this is a
    # reporting fix only.
    from nsealgo.backtest.metrics import yearly_returns

    yr_s = yearly_returns(res.returns)
    yr_c = yearly_returns(comp.returns)
    print()
    print("yearly returns (TEST; first year measured from a starting equity of 1.0, "
          "so 2024 is a partial year):")
    print(f"  {vid:<4} {fmt_yearly(yr_s)}")
    print(f"  BH   {fmt_yearly(bh['yearly'])}")
    print(f"  comp {fmt_yearly(yr_c)}")

    # ---- verdict arithmetic --------------------------------------------- #
    print()
    print("=" * 78)
    print("HEAD TO HEAD vs buy-and-hold (TEST, identical window, both net)")
    print("=" * 78)
    print(f"  CAGR    {m.cagr * 100:>7.2f}%  vs {bh['metrics'].cagr * 100:>7.2f}%   "
          f"-> {(m.cagr - bh['metrics'].cagr) * 100:+7.2f} pts")
    print(f"  Sharpe  {m.sharpe:>7.2f}   vs {bh['metrics'].sharpe:>7.2f}    "
          f"-> {m.sharpe - bh['metrics'].sharpe:+7.2f}")
    print(f"  MaxDD   {m.max_drawdown * 100:>7.2f}%  vs {bh['metrics'].max_drawdown * 100:>7.2f}%   "
          f"-> {(m.max_drawdown - bh['metrics'].max_drawdown) * 100:+7.2f} pts")
    print(f"  Calmar  {m.calmar:>7.2f}   vs {bh['metrics'].calmar:>7.2f}    "
          f"-> {m.calmar - bh['metrics'].calmar:+7.2f}")
    print(f"  vs nsealgo composite: CAGR {(m.cagr - comp.metrics.cagr) * 100:+.2f} pts, "
          f"Sharpe {m.sharpe - comp.metrics.sharpe:+.2f}, "
          f"MaxDD {(m.max_drawdown - comp.metrics.max_drawdown) * 100:+.2f} pts")

    out = {
        "engine_sha": ENGINE_SHA,
        "variant": {"id": vid, "L": L, "entry": entry},
        "test_window": [str(te.index[0].date()), str(te.index[-1].date())],
        "strategy": {k: getattr(m, k) for k in
                     ("cagr", "sharpe", "sortino", "calmar", "max_drawdown",
                      "volatility", "total_return", "annual_turnover",
                      "cost_drag_annual", "win_rate")},
        "buy_and_hold": {k: getattr(bh["metrics"], k) for k in
                         ("cagr", "sharpe", "calmar", "max_drawdown",
                          "volatility", "total_return")},
        "composite": {k: getattr(comp.metrics, k) for k in
                      ("cagr", "sharpe", "calmar", "max_drawdown", "total_return")},
        "random_sharpe": sh.tolist(),
        "random_cagr": ca.tolist(),
        "beat_rate": float((sh < m.sharpe).mean()),
        "beta": beta, "alpha_ann": alpha_ann,
        "zero_cost_cagr": zero.metrics.cagr,
        "avg_names": res.diag["avg_names"],
        "mean_invested": float(inv.mean()),
        "liveness": liveness(te, L, entry),
        "yearly_strategy": {int(k): v for k, v in yr_s.items()},
        "yearly_bh": {int(k): v for k, v in bh["yearly"].items()},
        "yearly_composite": {int(k): v for k, v in yr_c.items()},
    }
    (HERE / "test_results.json").write_text(json.dumps(out, indent=2))
    print("\nwrote test_results.json")


if __name__ == "__main__":
    main()
