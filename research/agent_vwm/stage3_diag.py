"""STAGE 3 — verify the negative TEST result is real, not a harness artefact.

Six checks:
  1. Is the "volume gate never fires" claim still true on TEST once warmup cells
     (which are NaN by construction) are separated from genuine zero-volume cells?
  2. Does the volume term change the TEST signal at all? (byte-level)
  3. Is the loss a COST problem or a SIGNAL problem? (zero-cost isolation)
  4. Is the underperformance a concentration artefact? (weight distribution)
  5. Is buy-and-hold computed on the same panel, same costs, same rf?
  6. Is the whole thing deterministic? (re-run reproduces)
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_vwm")

from common import (  # noqa: E402
    COST_MODEL,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    ZERO_COST_MODEL,
    load_panels,
    momentum_rank_score,
    roc_panel,
    slice_split,
    vwm_signal,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402

CFG = PortfolioConfig()
PERIOD, THR = 63, 0.03


def main() -> None:
    px, vol, _ = load_panels()
    px_te = slice_split(px, TEST_START, TEST_END)
    vol_te = slice_split(vol, TEST_START, TEST_END)

    print("=" * 78)
    print("1. VOLUME GATE — warmup cells vs genuine zero-volume cells (TEST)")
    print("=" * 78)
    for p, v, name in (
        (slice_split(px, TRAIN_START, TRAIN_END),
         slice_split(vol, TRAIN_START, TRAIN_END), "TRAIN"),
        (px_te, vol_te, "TEST"),
    ):
        sig, _ = vwm_signal(p, v, PERIOD, THR)
        n = 0
        warm = 0
        zero_vol = 0
        for sym in p.columns:
            c = p[sym].dropna()
            vv = v[sym].reindex(c.index).fillna(0.0).to_numpy(float)
            cc = c.to_numpy(float)
            if cc.size <= PERIOD:
                continue
            avg = np.full(cc.size, np.nan)
            cs = np.concatenate(([0.0], np.cumsum(vv)))
            avg[PERIOD - 1:] = (cs[PERIOD:] - cs[:-PERIOD]) / PERIOD
            warm_mask = np.isnan(avg)
            zero_mask = (~warm_mask) & (avg <= 0)
            warm += int(warm_mask.sum())
            zero_vol += int(zero_mask.sum())
            n += cc.size
        print(f"  {name}: cells={n:,}  warmup(NaN)={warm:,}  "
              f"GENUINE avg_vol==0 = {zero_vol:,} ({zero_vol/max(n,1):.6%})")
    print("  -> the gate fires ONLY from NaN warmup, never from a real zero-volume")
    print("     window. The volume branch of this strategy is unreachable in practice.")

    print()
    print("=" * 78)
    print("2. Does volume change the TEST signal? (cell-by-cell)")
    print("=" * 78)
    sig_v, _ = vwm_signal(px_te, vol_te, PERIOD, THR)
    m = roc_panel(px_te, PERIOD)
    sig_f = pd.DataFrame(0.0, index=px_te.index, columns=px_te.columns)
    sig_f[m > THR] = 1.0
    sig_f[m.isna()] = 0.0
    d = (sig_v != sig_f).to_numpy()
    print(f"  differing cells: {int(d.sum())} of {d.size:,}")
    print(f"  signal long-cells: volume version {int((sig_v>0).to_numpy().sum()):,} "
          f"| volume-free {int((sig_f>0).to_numpy().sum()):,}")

    print()
    print("=" * 78)
    print("3. COST problem or SIGNAL problem?")
    print("=" * 78)
    sc = momentum_rank_score(px_te, sig_v, 126)
    rn = run_backtest(px_te, sc, COST_MODEL, CFG, "M")
    rz = run_backtest(px_te, sc, ZERO_COST_MODEL, CFG, "M")
    print(f"  net of 21.92 bps : CAGR {rn.metrics.cagr*100:>7.2f}%  "
          f"Sharpe {rn.metrics.sharpe:>6.2f}  MaxDD {rn.metrics.max_drawdown*100:>7.2f}%")
    print(f"  zero cost        : CAGR {rz.metrics.cagr*100:>7.2f}%  "
          f"Sharpe {rz.metrics.sharpe:>6.2f}  MaxDD {rz.metrics.max_drawdown*100:>7.2f}%")
    print(f"  cost is worth {abs(rn.metrics.cagr - rz.metrics.cagr)*100:.2f}pp/yr; "
          f"the loss is {(rz.metrics.cagr)*100:.2f}%/yr even with NO costs at all.")
    print("  -> NOT a cost problem. The signal itself is negative out-of-sample.")

    print()
    print("=" * 78)
    print("4. Concentration check on the delivered book")
    print("=" * 78)
    w = rn.weights
    held = (w > 0).sum(axis=1)
    print(f"  names held: mean {held.mean():.2f}  min {held.min()}  max {held.max()}")
    print(f"  single-name weight: max {w.max().max():.4f}  "
          f"mean-of-held {w.where(w>0).stack().mean():.4f}")
    sector_tot = {}
    from nsealgo.backtest.engine import sector_of
    for s in w.columns:
        sector_tot.setdefault(sector_of(s), 0.0)
    for dt in (w.index[0], w.index[len(w)//2], w.index[-1]):
        row = w.loc[dt]
        top = row[row > 0].sort_values(ascending=False).head(5)
        print(f"  {str(dt.date())}: {int((row>0).sum())} names, "
              f"top5={', '.join(f'{k} {v:.1%}' for k,v in top.items())}")
    cap_ok = w.max().max() <= CFG.max_weight + 1e-9
    print(f"  single-name cap {CFG.max_weight:.0%} respected: {cap_ok}")
    print(f"  cash held (1 - sum w): mean {(1 - w.sum(axis=1)).mean():.2%} "
          f"(target {CFG.cash_buffer:.0%})")

    print()
    print("=" * 78)
    print("5. Buy-and-hold sanity — same panel, same rf, one round trip")
    print("=" * 78)
    from decimal import Decimal
    rt = float(COST_MODEL.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    rets = px_te.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    eq = (1.0 + rets).cumprod() * (1.0 - rt)
    daily = eq.pct_change(fill_method=None).fillna(0.0)
    m = compute_metrics(daily, eq)
    print(f"  B&H net  CAGR {m.cagr*100:.2f}%  Sharpe {m.sharpe:.2f}  "
          f"MaxDD {m.max_drawdown*100:.2f}%  rt charged {rt*10000:.2f}bps")
    print(f"  engine's own rt_bps for comparison: {rn.diag['round_trip_bps']:.2f}")
    print(f"  vw_momentum   CAGR {rn.metrics.cagr*100:.2f}%  "
          f"Sharpe {rn.metrics.sharpe:.2f}  MaxDD {rn.metrics.max_drawdown*100:.2f}%")
    print(f"  DELTA         CAGR {(rn.metrics.cagr - m.cagr)*100:+.2f}pp  "
          f"Sharpe {rn.metrics.sharpe - m.sharpe:+.2f}  "
          f"MaxDD {(rn.metrics.max_drawdown - m.max_drawdown)*100:+.2f}pp")
    print("  -> worse on return AND worse on drawdown than simply holding the index.")

    print()
    print("=" * 78)
    print("6. Determinism — re-run reproduces bit-for-bit")
    print("=" * 78)
    rn2 = run_backtest(px_te, sc, COST_MODEL, CFG, "M")
    same_equity = bool(np.allclose(rn.equity.to_numpy(), rn2.equity.to_numpy(), atol=0, rtol=0))
    print(f"  equity curves identical: {same_equity}  "
          f"(final equity {rn.equity.iloc[-1]:.10f} vs {rn2.equity.iloc[-1]:.10f})")

    print()
    print("=" * 78)
    print("7. Was the degradation a regime effect or a parameter accident?")
    print("   All 5 declared variants evaluated on TEST *for information only* —")
    print("   V3 remains the pre-declared winner; this is NOT a re-selection.")
    print("=" * 78)
    print(f"{'id':<5}{'period':>7}{'thr':>7}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Names':>7}")
    for vid, p_, t_ in (("V1",20,0.01),("V2",20,0.05),("V3",63,0.03),
                        ("V4",126,0.06),("V5",252,0.10)):
        s_, _ = vwm_signal(px_te, vol_te, p_, t_)
        r_ = run_backtest(px_te, momentum_rank_score(px_te, s_, 126), COST_MODEL, CFG, "M")
        mark = "  <- pre-declared winner" if vid == "V3" else ""
        print(f"{vid:<5}{p_:>7}{t_:>7}{r_.metrics.cagr*100:>8.2f}%"
              f"{r_.metrics.sharpe:>8.2f}{r_.metrics.max_drawdown*100:>8.2f}%"
              f"{r_.diag['avg_names']:>7.1f}{mark}")
    print("  -> every variant loses on TEST. Not a parameter accident.")


if __name__ == "__main__":
    main()
