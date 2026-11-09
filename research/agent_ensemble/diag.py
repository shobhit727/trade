"""TRAIN-only mechanism diagnostic for `ensemble_signals`.

These are diagnostics of *why* the strategy behaves as it does, NOT parameter variants.
Every number here is computed on TRAIN (2016-01-01 -> 2023-12-31) only. TEST is not read.
No reported conclusion in REPORT.md depends on a backtest run in this file.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_ensemble")

from run import TRAIN, ensemble_signal, votes_panel  # noqa: E402

from nsealgo.data.loader import load_universe  # noqa: E402

FWD = 21  # trading days


def main() -> None:
    raw, syms, rep = load_universe("data/nse")
    panel = raw.ffill()
    tr = panel.loc[TRAIN[0]:TRAIN[1]]
    print(f"TRAIN slice {tr.shape}  {tr.index[0].date()} -> {tr.index[-1].date()}\n")

    p, r, mv = 10, 14, 2          # the variant selected on TRAIN Calmar
    sma_p = tr.rolling(p).mean()
    ema_p = tr.ewm(span=p, adjust=False).mean()
    d = tr.diff()
    gains = d.clip(lower=0).rolling(r).sum() / r
    losses = (-d.clip(upper=0)).rolling(r).sum() / r
    rsi = (100 - 100 / (1 + gains / losses)).where(losses != 0, 100.0)

    leg_sma = pd.DataFrame(np.where(tr > sma_p, 1, -1), index=tr.index, columns=tr.columns)
    leg_ema = pd.DataFrame(np.where(tr > ema_p, 1, -1), index=tr.index, columns=tr.columns)
    leg_rsi = pd.DataFrame(np.where(rsi > 55, 1, np.where(rsi < 45, -1, 0)),
                           index=tr.index, columns=tr.columns)
    votes = votes_panel(tr, p, r)
    sig = ensemble_signal(tr, p, r, mv)

    # ---- 1. are the three legs independent votes, or the same opinion? ----
    print("=== 1. pairwise leg agreement (TRAIN, cells where all legs defined) ===")
    legs = {"sma": leg_sma, "ema": leg_ema, "rsi": leg_rsi}
    for a, b in (("sma", "ema"), ("sma", "rsi"), ("ema", "rsi")):
        both = legs[a].notna() & legs[b].notna()
        agree = float((legs[a][both] == legs[b][both]).to_numpy().mean())
        print(f"  {a} vs {b}: identical sign on {agree * 100:.1f}% of cells")
    print(f"  all three agree: "
          f"{float(((leg_sma == leg_ema) & (leg_ema == leg_rsi)).to_numpy().mean()) * 100:.1f}%")
    print(f"  distinct vote sums observed: {sorted(set(votes.to_numpy().ravel().tolist()))}")

    # ---- 2. forward 21d return of flagged vs not flagged ----
    fwd = (tr.shift(-FWD) / tr - 1.0).stack(future_stack=True)
    long_mask = (sig > 0).stack(future_stack=True)
    print(f"\n=== 2. forward {FWD}d return by signal state (TRAIN, name-day cells) ===")
    print(f"  long  (+1): n={int(long_mask.sum()):>8,}  "
          f"mean fwd={fwd[long_mask].mean() * 100:+.3f}%")
    print(f"  short (-1): n={int((sig < 0).sum().to_numpy().sum()):>8,}  "
          f"mean fwd={fwd[(sig < 0).stack(future_stack=True)].mean() * 100:+.3f}%")
    flat = (sig == 0)
    print(f"  flat   ( 0): n={int(flat.sum().to_numpy().sum()):>8,}  "
          f"mean fwd={fwd[flat.stack(future_stack=True)].mean() * 100:+.3f}%")
    print(f"  SPREAD long-minus-flat = "
          f"{(fwd[long_mask].mean() - fwd[flat.stack(future_stack=True)].mean()) * 100:+.3f} pp")
    print(f"  overall universe mean fwd = {fwd.mean() * 100:+.3f}%")

    # ---- 3. does the vote count add information, or is it saturated at one bit? ----
    print(f"\n=== 3. forward {FWD}d return by raw vote sum (TRAIN) ===")
    v = votes.stack(future_stack=True)
    print(f"  {'votes':>7}{'n':>10}{'mean fwd%':>12}")
    for k in sorted(set(v.dropna().unique().tolist())):
        m = v == k
        if m.sum() >= 200:
            print(f"  {int(k):>7}{int(m.sum()):>10,}{fwd[m].mean() * 100:>12.3f}")
    pos = v >= 2
    one = (v == 1) | (v == 0)
    print(f"  votes>=2 (held long) vs votes in 0..1 (excluded): "
          f"{(fwd[pos].mean() - fwd[one].mean()) * 100:+.3f} pp")

    # ---- 4. per-leg ablation on forward returns (TRAIN) ----
    print(f"\n=== 4. leg ablation, forward {FWD}d mean by leg state (TRAIN) ===")
    for name, leg in legs.items():
        s1 = leg.stack(future_stack=True)
        on = s1 == 1
        off = s1 == -1
        print(f"  {name:>4}: on(+1) {fwd[on].mean() * 100:+.3f}%   "
              f"off(-1) {fwd[off].mean() * 100:+.3f}%   "
              f"spread {(fwd[on].mean() - fwd[off].mean()) * 100:+.3f} pp")

    # ---- 5. does the ensemble beat its own best single member? ----
    print("\n=== 5. agreement of the 3-vote ensemble with each single leg (TRAIN) ===")
    ens_on = long_mask
    for name, leg in legs.items():
        leg_on = (leg.stack(future_stack=True) == 1)
        both = ens_on & leg_on
        only_leg = (~ens_on) & leg_on
        print(f"  ensemble&{name:<4} n={int(both.sum()):>8,} fwd={fwd[both].mean() * 100:+.3f}%   "
              f"{name}-only n={int(only_leg.sum()):>7,} "
              f"fwd={fwd[only_leg].mean() * 100:+.3f}%   "
              f"agreement={float((ens_on == leg_on).mean()) * 100:.1f}%")

    # ---- 6. market timing power of signal breadth ----
    print(f"\n=== 6. breadth vs forward {FWD}d market return (TRAIN, daily) ===")
    breadth = (sig > 0).sum(axis=1) / sig.notna().sum(axis=1)
    mkt = (tr.mean(axis=1).shift(-FWD) / tr.mean(axis=1) - 1.0)
    ok = breadth.notna() & mkt.notna()
    print(f"  corr(breadth, fwd market ret) = "
          f"{float(np.corrcoef(breadth[ok], mkt[ok])[0, 1]):+.3f}")
    q = pd.qcut(breadth[ok], 5, labels=False)
    print("  forward market return by breadth quintile (1=low .. 5=high):")
    for k in sorted(set(q.tolist())):
        m = q == k
        print(f"    Q{k + 1}: breadth~{breadth[ok][m].mean():.2f}  "
              f"fwd mkt {mkt[ok][m].mean() * 100:+.2f}%")

    # ---- 7. where the TRAIN drawdown reduction came from ----
    print("\n=== 7. calendar-year forward returns of the universe (TRAIN) ===")
    ann = tr.mean(axis=1).pct_change().groupby(tr.index.year).apply(
        lambda s: (1 + s).prod() - 1
    )
    print((ann * 100).round(2).to_string())


if __name__ == "__main__":
    main()
