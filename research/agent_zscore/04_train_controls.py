"""Step 04 — TRAIN-only controls. Establishes what "beating nothing" looks like
BEFORE the single TEST read, so the TEST numbers can be interpreted honestly.

Controls:
  1. Random-signal controls: same number of flagged names per day, random identities,
     20 seeds. If the real strategy does not clear this band, it is noise.
  2. Beta/alpha regression of the selected variant against the equal-weight universe.
     If alpha ~ 0 and beta ~ 1, the "signal" is market exposure, not edge.
  3. Cost stress: the same run at zero cost, to isolate how much of the return is
     the drag the strategy pays to trade.
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
    load_panel,
    row,
    run,
    train_panel,
    zscore_score,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import CostModel

HERE = Path(__file__).resolve().parent
SEL = json.loads((HERE / "selected_variant.json").read_text())
N_SEEDS = 20


def random_control_score(panel: pd.DataFrame, mask: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Uniform random names, same count per day as `mask`, same score shape.

    Matches the strategy on *everything the engine can see*: how many names are
    eligible, and that the score is a percentile rank in [0,1]. Only the identity
    of the names is random.
    """
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
    tr = train_panel()
    L, entry, vid = SEL["L"], SEL["entry"], SEL["id"]
    print(f"engine_sha = {ENGINE_SHA}")
    print(f"selected   = {vid}  L={L} entry={entry}\n")

    real_score = zscore_score(panel, L, entry)
    mask = real_score.notna()
    res = run(tr, real_score.loc[tr.index])
    m = res.metrics

    # ---- 1. random-signal controls -------------------------------------- #
    ctrls = []
    for s in range(N_SEEDS):
        r = run(tr, random_control_score(tr, mask.loc[tr.index], s))
        ctrls.append(r.metrics)
    sh = np.array([c.sharpe for c in ctrls])
    ca = np.array([c.cagr for c in ctrls])
    dd = np.array([c.max_drawdown for c in ctrls])

    print(HDR)
    print(row(f"{vid} REAL", m, f"avg_names={res.diag['avg_names']:.1f}"))
    print(row("random median", ctrls[int(np.median(np.argsort(sh)))], f"of {N_SEEDS} seeds"))
    print()
    print(f"random Sharpe : min {sh.min():.2f}  p25 {np.percentile(sh,25):.2f}  "
          f"median {np.median(sh):.2f}  p75 {np.percentile(sh,75):.2f}  max {sh.max():.2f}")
    print(f"random CAGR   : min {ca.min()*100:.2f}%  median {np.median(ca)*100:.2f}%  "
          f"max {ca.max()*100:.2f}%")
    print(f"random MaxDD  : median {np.median(dd)*100:.2f}%  "
          f"(best {dd.max()*100:.2f}%, worst {dd.min()*100:.2f}%)")
    print(f"real Sharpe   : {m.sharpe:.2f}   -> beats {int((sh < m.sharpe).sum())}/{N_SEEDS} "
          f"random controls ({(sh < m.sharpe).mean()*100:.0f}th pct)")

    # ---- 2. beta / alpha vs equal-weight universe ------------------------ #
    bh = buy_and_hold(tr, "bh")
    x = bh["returns"].reindex(res.returns.index).fillna(0.0)
    y = res.returns.fillna(0.0)
    cov = float(np.cov(x, y, ddof=1)[0, 1])
    beta = cov / float(np.var(x, ddof=1))
    alpha_d = float(y.mean()) - beta * float(x.mean())
    TD = 244
    alpha_ann = (1.0 + alpha_d) ** TD - 1.0
    corr = float(np.corrcoef(x, y)[0, 1])
    resid = y - beta * x
    print()
    print("beta / alpha of the selected strategy vs equal-weight universe (TRAIN):")
    print(f"  beta            {beta:.3f}")
    print(f"  alpha (annual)  {alpha_ann * 100:+.2f}%/y")
    print(f"  correlation     {corr:.3f}")
    print(f"  resid vol ann   {float(resid.std(ddof=1)) * np.sqrt(TD) * 100:.2f}%")

    # ---- 3. cost stress -------------------------------------------------- #
    # Diagnostic only: how much of the return is the price of trading at all.
    # NOT a reportable result — a zero-cost result is not a result (brief §3).
    zero_cost_model = CostModel(segment="delivery", slippage_bps=Decimal("0"))
    rz = run_backtest(tr, real_score.loc[tr.index], zero_cost_model, config=CFG,
                      rebalance="M")
    assert rz.engine_sha == ENGINE_SHA
    print()
    print(HDR)
    print(row(f"{vid} net 21.92bps", m))
    print(row(f"{vid} ZERO cost", rz.metrics, "diagnostic only — not a reportable result"))
    print(f"  cost drag = {(m.cagr - rz.metrics.cagr) * 100:.2f} pts of CAGR/yr")
    print(f"  gross-positive / net-negative? "
          f"{'GROSS+ NET-' if rz.metrics.cagr > 0 > m.cagr else 'n/a'}")

    # ---- 4. sanity: weight count, liveness, cash ------------------------- #
    w = res.weights
    print()
    print("sanity checks (brief §6):")
    print(f"  avg names held      {float((w > 0).sum(axis=1).mean()):.1f} "
          f"(target ~22; lower is the strategy being selective, not residue)")
    print(f"  max names held      {int((w > 0).sum(axis=1).max())}")
    print(f"  mean invested wt    {float(w.sum(axis=1).mean()) * 100:.1f}% "
          f"(cash buffer 10% -> residual {float((1 - w.sum(axis=1)).mean()) * 100:.1f}%)")
    print(f"  max single weight   {float(w.max().max()) * 100:.2f}% (cap 12%)")
    dead = int(((w > 0) & (w < 1e-4)).to_numpy().sum())
    print(f"  dead residues       {dead}")
    inv = w.sum(axis=1)
    print(f"  invested wt   min {inv.min() * 100:.1f}%  p25 {inv.quantile(.25) * 100:.1f}%  "
          f"median {inv.median() * 100:.1f}%  p75 {inv.quantile(.75) * 100:.1f}%  "
          f"max {inv.max() * 100:.1f}%")
    # Is the cash drag structural (selectivity + turnover budget) or a warm-up ramp?
    yr_inv = inv.groupby(inv.index.year).mean()
    print("  invested wt by year: "
          + "  ".join(f"{y}:{v * 100:.0f}%" for y, v in yr_inv.items()))

    out = {
        "engine_sha": ENGINE_SHA,
        "real": {k: getattr(m, k) for k in
                 ("cagr", "sharpe", "calmar", "max_drawdown", "total_return",
                  "annual_turnover", "cost_drag_annual")},
        "random_sharpe": sh.tolist(),
        "random_cagr": ca.tolist(),
        "beta": beta, "alpha_ann": alpha_ann, "corr": corr,
        "zero_cost_cagr": rz.metrics.cagr,
        "real_beat_rate": float((sh < m.sharpe).mean()),
    }
    (HERE / "train_controls.json").write_text(json.dumps(out, indent=2))
    print("\nwrote train_controls.json")


if __name__ == "__main__":
    main()
