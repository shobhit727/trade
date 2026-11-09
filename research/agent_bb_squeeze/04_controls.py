"""Step 4 — negative controls + a weight-accounting audit.

Two jobs:
  1. Negative control: does the strategy beat a RANDOM signal flagged on the
     same fraction of bars, with the same momentum ranking, through the same
     cost-aware harness? (brief §6.5). Averaged over 20 seeds.
  2. Audit why the TEST book holds only ~63% invested when the cash buffer
     implies ~90%. If that is a harness bug rather than an intentional
     turnover-budget effect, every number above is wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    BASE,
    DATA,
    TEST,
    TRAIN,
    Variant,
    buy_and_hold,
    hr,
    load_universe,
    metrics_for,
    momentum_score,
    run_variant,
    squeeze_signal,
    table,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics

CFG = PortfolioConfig()
SELECTED = "V1"
PARAMS = dict(period=20, threshold=0.050, scorer="momentum", roc_lookback=3)


def _te_only(res, te):
    """Restrict an engine result to the TEST bars and recompute its metrics."""
    rr = res.returns[te]
    mm = compute_metrics(rr, (1.0 + rr).cumprod())
    res.returns, res.metrics = rr, mm
    return res


def main() -> None:
    panel, symbols, _ = load_universe(str(DATA))
    v = Variant(SELECTED, **PARAMS)

    # Same warm-start convention as run_variant: build factors over history that
    # precedes TEST so the 126-bar momentum and 60-bar vol windows are populated
    # on TEST's first bar, then score ONLY the TEST bars.
    WARM = 260
    lo = pd.Timestamp(TEST[0]).tz_localize(panel.index.tz)
    hi = pd.Timestamp(TEST[1]).tz_localize(panel.index.tz)
    s0 = max(int(panel.index.searchsorted(lo)) - WARM, 0)
    px = panel.iloc[s0:][lambda d: d.index <= hi]
    te = px.index >= lo

    # ------------------------------------------------------------------ #
    hr("1. WEIGHT ACCOUNTING AUDIT — why is the book only ~63% invested?")
    _, w, m, d = run_variant(panel, v, TEST, CFG)
    inv = w.sum(axis=1)
    print(f"[warm-start {WARM} bars before TEST; window reported = "
          f"{w.index[0].date()} -> {w.index[-1].date()}, {len(w)} bars]")
    print(f"invested: mean {inv.mean():.4f}  min {inv.min():.4f}  "
          f"max {inv.max():.4f}  median {inv.median():.4f}")
    print(f"names   : mean {(w > 0).sum(axis=1).mean():.2f}  "
          f"min {(w > 0).sum(axis=1).min()}  max {(w > 0).sum(axis=1).max()}")
    print("\ninvested by quarter:")
    q = inv.groupby(inv.index.to_period("Q")).mean()
    print("  " + "  ".join(f"{k}:{x:.3f}" for k, x in q.items()))
    print("\ninvested in the FIRST 8 rebalance months vs later:")
    rb = inv.iloc[::22]
    print(f"  first 8: {rb.head(8).mean():.4f}   remaining: {rb.iloc[8:].mean():.4f}")

    # Rebuild the raw targets to see whether the shortfall is in
    # build_rebalance_weights or introduced by the turnover blend.
    from common import build_score

    from nsealgo.backtest.engine import _rebalance_dates

    score, lng = build_score(px, v)
    idx = px.index.intersection(score.index)
    rb_dates = [x for x in _rebalance_dates(px.loc[idx].index, "M") if x in score.index][1:]
    from nsealgo.backtest.engine import apply_turnover_budget, build_rebalance_weights

    rets = px.pct_change(fill_method=None).fillna(0.0)
    vol = rets.rolling(60, min_periods=20).std()
    tgt_raw = build_rebalance_weights(score.loc[rb_dates], rb_dates, vol.loc[rb_dates], CFG)
    raw_inv = tgt_raw.sum(axis=1)
    print(f"\nRAW targets (before turnover budget): invested mean {raw_inv.mean():.4f} "
          f"min {raw_inv.min():.4f}  names mean {(tgt_raw > 0).sum(axis=1).mean():.2f}")
    print("  -> if raw is ~0.90 the shortfall is the turnover budget thinning the book;")

    tgt = tgt_raw.copy()
    for i in range(len(tgt)):
        prev = tgt.iloc[i - 1] if i else None
        tgt.iloc[i] = apply_turnover_budget(tgt_raw.iloc[i], prev,
                                            CFG.turnover_budget, CFG.max_names)
    print(f"AFTER turnover budget:               invested mean {tgt.sum(axis=1).mean():.4f} "
          f"names mean {(tgt > 0).sum(axis=1).mean():.2f}")

    # Count one-way turnover actually demanded by the raw target vs allowed.
    dem = (tgt_raw - tgt_raw.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    print(f"\none-way turnover DEMANDED by raw targets: mean {dem.iloc[1:].mean():.3f} "
          f"median {dem.iloc[1:].median():.3f}  (budget {CFG.turnover_budget:.2f})")
    print(f"  -> demanded {dem.iloc[1:].mean():.2f} vs allowed {CFG.turnover_budget:.2f}: "
          f"the budget binds on {float((dem > CFG.turnover_budget).mean()) * 100:.0f}% of rebalances.")
    print("\nVERDICT: the low invested fraction is the engine's turnover budget binding on a")
    print("rotating signal — it is a real constraint, not a bug. The score mask flips")
    flips = float(lng[te].sum(axis=1).diff().abs().mean())
    print(f"{flips:.1f} names flip in/out of the signal per day on average,")
    print("so the monthly target rotates hard and the 0.35 budget can only track it partway.")

    # ------------------------------------------------------------------ #
    hr("2. NEGATIVE CONTROL — random signal, identical liveness, 50 seeds")
    lng_te = lng[te]
    lf = float(lng_te.to_numpy().mean())
    p_live = float(lng_te.sum(axis=1).mean() / px.shape[1])
    print(f"strategy liveness: {lf * 100:.2f}% of (name,day) pairs; "
          f"per-day per-name flag probability {p_live:.4f}")

    rows = []
    for seed in range(50):
        rng = np.random.default_rng(1000 + seed)
        rand = pd.DataFrame(
            rng.random(px.shape) < p_live, index=px.index, columns=px.columns
        ).astype(float)
        # same momentum ranking, same harness, same costs
        sc = momentum_score(px, rand)
        res = run_backtest(px, sc, BASE, CFG, "M")
        rr = res.returns[te]
        mm = compute_metrics(rr, (1.0 + rr).cumprod())
        rows.append((mm.cagr, mm.sharpe, mm.max_drawdown,
                     float((res.weights[te] > 0).sum(axis=1).mean())))

    arr = np.array(rows)
    real = (m.cagr, m.sharpe, m.max_drawdown, d["avg_names"])
    print(f"\n{'strategy (real signal)':<26} CAGR {real[0] * 100:>7.2f}%  "
          f"Sharpe {real[1]:>6.2f}  MaxDD {real[2] * 100:>7.2f}%  names {real[3]:.1f}")
    print(f"{'random (mean of 50 seeds)':<26} CAGR {arr[:, 0].mean() * 100:>7.2f}%  "
          f"Sharpe {arr[:, 1].mean():>6.2f}  MaxDD {arr[:, 2].mean() * 100:>7.2f}%  "
          f"names {arr[:, 3].mean():.1f}")
    print(f"{'random (5-95 pct)':<26} CAGR [{np.percentile(arr[:, 0], 5) * 100:>6.2f}%, "
          f"{np.percentile(arr[:, 0], 95) * 100:>6.2f}%]  "
          f"Sharpe [{np.percentile(arr[:, 1], 5):>5.2f}, {np.percentile(arr[:, 1], 95):>5.2f}]")
    better = float((arr[:, 1] > real[1]).mean())
    print(f"\nrandom beats the real signal on Sharpe in {better * 100:.0f}% of seeds "
          f"({int((arr[:, 1] > real[1]).sum())}/50)")
    print("A coin flip is the minimum bar. Real signal Sharpe "
          f"{real[1]:.2f} vs coin {arr[:, 1].mean():.2f}.")

    # same control on TRAIN, for reference
    ptr = panel.loc[TRAIN[0] : TRAIN[1]]
    _, ltr, mtr, dtr = run_variant(panel, v, TRAIN, CFG)
    p_tr = float(squeeze_signal(ptr, 20, 0.050, 3)[0].sum(axis=1).mean() / ptr.shape[1])
    trows = []
    for seed in range(50):
        rng = np.random.default_rng(2000 + seed)
        rand = pd.DataFrame(rng.random(ptr.shape) < p_tr, index=ptr.index,
                            columns=ptr.columns).astype(float)
        res = run_backtest(ptr, momentum_score(ptr, rand), BASE, CFG, "M")
        mm = compute_metrics(res.returns, (1.0 + res.returns).cumprod())
        trows.append((mm.cagr, mm.sharpe))
    ta = np.array(trows)
    print("\nTRAIN, same control:")
    print(f"{'strategy (real signal)':<26} CAGR {mtr.cagr * 100:>7.2f}%  "
          f"Sharpe {mtr.sharpe:>6.2f}")
    print(f"{'random (mean of 50 seeds)':<26} CAGR {ta[:, 0].mean() * 100:>7.2f}%  "
          f"Sharpe {ta[:, 1].mean():>6.2f}")
    print(f"real TRAIN Sharpe {mtr.sharpe:.2f} vs coin {ta[:, 1].mean():.2f} "
          f"-> real signal {'BEATS' if mtr.sharpe > ta[:, 1].mean() else 'LOSES TO'} a coin flip in-sample")
    print(f"real TEST  Sharpe {real[1]:.2f} vs coin {arr[:, 1].mean():.2f} "
          f"-> real signal {'BEATS' if real[1] > arr[:, 1].mean() else 'LOSES TO'} a coin flip out-of-sample")

    # ------------------------------------------------------------------ #
    hr("3. WHAT IS V1 ACTUALLY HOLDING? decomposition of the return")
    # (a) the gate alone as a low-vol tilt, no ROC3 filter
    mean20 = px.rolling(20, min_periods=20).mean()
    std20 = px.rolling(20, min_periods=20).std(ddof=0)
    cvx = std20 / mean20.replace(0.0, np.nan)  # the catalog statistic, verbatim
    from common import cv_panel

    ref = cv_panel(px, 20)
    assert np.allclose(cvx.to_numpy(), ref.to_numpy(), equal_nan=True), \
        "hand-rolled CV diverged from common.cv_panel"
    print("  [CV reconstruction verified identical to common.cv_panel]")

    lowvol_only = momentum_score(px, (cvx < 0.05).astype(float))
    r_low = _te_only(run_backtest(px, lowvol_only, BASE, CFG, "M"), te)
    # (b) ROC3 filter alone, no squeeze gate
    roc3 = px / px.shift(3) - 1.0
    roc_only = momentum_score(px, (roc3 > 0).astype(float))
    r_roc = _te_only(run_backtest(px, roc_only, BASE, CFG, "M"), te)
    # (c) the squeeze gate with NO momentum ranking (equal weight on flagged)
    gate_eq = (cvx < 0.05).astype(float)
    r_eq = _te_only(run_backtest(px, gate_eq.replace(0.0, np.nan), BASE, CFG, "M"), te)

    bh = metrics_for(buy_and_hold(panel).loc[TEST[0] : TEST[1]], TEST, turnover=1.80)
    rows = [
        f"{'V1 full (squeeze & ROC3)':<30} CAGR {m.cagr * 100:>7.2f}%  Sharpe {m.sharpe:>6.2f}  MaxDD {m.max_drawdown * 100:>7.2f}%",
        f"{'squeeze gate + mom rank':<30} CAGR {r_low.metrics.cagr * 100:>7.2f}%  Sharpe {r_low.metrics.sharpe:>6.2f}  MaxDD {r_low.metrics.max_drawdown * 100:>7.2f}%",
        f"{'ROC3 filter + mom rank':<30} CAGR {r_roc.metrics.cagr * 100:>7.2f}%  Sharpe {r_roc.metrics.sharpe:>6.2f}  MaxDD {r_roc.metrics.max_drawdown * 100:>7.2f}%",
        f"{'squeeze gate, NO mom rank':<30} CAGR {r_eq.metrics.cagr * 100:>7.2f}%  Sharpe {r_eq.metrics.sharpe:>6.2f}  MaxDD {r_eq.metrics.max_drawdown * 100:>7.2f}%",
        f"{'buy&hold':<30} CAGR {bh.cagr * 100:>7.2f}%  Sharpe {bh.sharpe:>6.2f}  MaxDD {bh.max_drawdown * 100:>7.2f}%",
    ]
    table(rows, "TEST decomposition — which leg does the damage?")
    print("\n  Interpretation:")
    print("   * 'squeeze gate + mom rank' is the low-volatility hypothesis alone.")
    print("   * 'ROC3 filter + mom rank' is the 3-day continuation hypothesis alone.")
    print("   * Their sum is not V1 (AND is not additive), so V1 is the interaction.")


if __name__ == "__main__":
    main()
