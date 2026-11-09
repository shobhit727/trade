"""DIAGNOSTIC — run on TRAIN only, after the single TEST read.

Purpose: explain WHY the TEST result is negative, without touching TEST again.

Two questions:
  Q1 (signal study)  Does the raw gate predict forward returns at all? A cross-sectional
                     event study on TRAIN: mean forward return of signalled names minus
                     the panel, with a t-stat. No portfolio layer, so this isolates the
                     signal from the construction.
  Q2 (decomposition)  Is the damage done by the gate, by the momentum ranking, or by
                     the interaction? TRAIN backtests of four scores.

TEST is NOT read in this file.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_trendvol")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    COST,
    PORT,
    SCRATCH,
    TRAIN,
    VARIANTS,
    gated_momentum_score,
    load_panel,
    load_vol,
    metrics_row,
    run_backtest,
    save_json,
    slice_window,
    soft_gate_score,
    trend_volume_signal,
)


def event_study(panel: pd.DataFrame, sig: pd.DataFrame, window, horizons=(21, 63, 126)):
    """Cross-sectional forward-return study of the gate, on `window`.

    For each day t and horizon h: fwd[h] = panel.shift(-h)/panel - 1.
    signal_ret = equal-weighted fwd over names signalled at t.
    market_ret = equal-weighted fwd over ALL names at t.
    alpha = signal_ret - market_ret.  t-stat = mean / (std / sqrt(n)), overlapping
    observations acknowledged in the report (t-stats are inflated by overlap).
    """
    rows = []
    m = (panel.index >= window[0]) & (panel.index <= window[1])
    px, sg = panel.loc[m], sig.loc[m]
    for h in horizons:
        fwd = px.shift(-h) / px - 1.0
        fwd = fwd.where(px.notna() & px.shift(-h).notna())
        n_sig = (sg > 0).sum(axis=1)
        sig_ret = fwd.where(sg > 0).mean(axis=1)
        mkt_ret = fwd.mean(axis=1)
        alpha = (sig_ret - mkt_ret).where(n_sig >= 3).dropna()
        t = float(alpha.mean() / alpha.std(ddof=1) * np.sqrt(len(alpha))) if len(alpha) > 2 else float("nan")
        rows.append({
            "horizon": h,
            "n_days": int(len(alpha)),
            "mean_alpha_bp": float(alpha.mean() * 1e4),
            "median_alpha_bp": float(alpha.median() * 1e4),
            "t_stat": t,
            "hit_rate": float((alpha > 0).mean()),
            "mean_fwd_sig_pct": float(sig_ret.dropna().mean() * 100),
            "mean_fwd_mkt_pct": float(mkt_ret.dropna().mean() * 100),
        })
    return rows


def main() -> None:
    panel = load_panel()
    vol = load_vol()
    tr_panel = slice_window(panel, TRAIN)
    tr_idx = tr_panel.index
    selected = "tv_p20_r10"
    cfg = VARIANTS[selected]
    print(f"DIAGNOSTIC on TRAIN only. Variant: {selected} {cfg}\n")

    sig = trend_volume_signal(panel, vol, cfg["period"], cfg["vol_ratio"])

    # ---------------- Q1: event study ----------------
    print("=== Q1. Does the GATE predict forward returns? (TRAIN cross-section) ===")
    es = event_study(panel, sig, TRAIN)
    print(f"{'h(days)':>8}{'n days':>9}{'mean alpha bp':>15}{'median bp':>12}"
          f"{'t':>8}{'hit%':>8}{'sig fwd%':>11}{'mkt fwd%':>11}")
    for r in es:
        print(f"{r['horizon']:>8}{r['n_days']:>9}{r['mean_alpha_bp']:>15.2f}"
              f"{r['median_alpha_bp']:>12.2f}{r['t_stat']:>8.2f}"
              f"{r['hit_rate'] * 100:>7.1f}%{r['mean_fwd_sig_pct']:>11.2f}"
              f"{r['mean_fwd_mkt_pct']:>11.2f}")

    # Isolate the two legs: trend leg alone, volume leg alone, both.
    print("\n--- leg decomposition (h=21) ---")
    close, v = panel, vol
    sma_c = close.rolling(cfg["period"], min_periods=cfg["period"]).mean()
    avg_v = v.rolling(cfg["period"], min_periods=cfg["period"]).mean()
    trend_only = (close > sma_c).astype(int).where(close.notna(), 0)
    vol_only = (v > avg_v * cfg["vol_ratio"]).astype(int).where(close.notna(), 0)
    legs = {"trend_only(close>SMA)": trend_only, "vol_only(vol>avg)": vol_only,
            "both(=strategy +1 leg)": sig}
    leg_rows = []
    for name, sg in legs.items():
        e = event_study(panel, sg, TRAIN, horizons=(21,))[0]
        leg_rows.append({"leg": name, **e})
        print(f"  {name:<24} alpha {e['mean_alpha_bp']:>8.2f}bp  "
              f"t={e['t_stat']:>6.2f}  hit {e['hit_rate'] * 100:>5.1f}%  "
              f"n_days={e['n_days']}")

    # ---------------- Q2: construction decomposition ----------------
    print("\n=== Q2. TRAIN construction decomposition (net of 21.92 bps) ===")
    mom = panel / panel.shift(126) - 1.0
    scores = {
        "A_gate_only_randomtie": None,  # placeholder replaced below
        "B_momentum_no_gate": mom.rank(axis=1, pct=True),
        "C_gate+momentum(declared)": gated_momentum_score(panel, sig),
        "D_softgate_momentum": soft_gate_score(panel, sig),
    }
    del scores["A_gate_only_randomtie"]

    rows = []
    for name, sc in scores.items():
        r = run_backtest(tr_panel, sc.reindex(tr_idx), COST, PORT)
        m = metrics_row(r, name)
        m["avg_names_live"] = float((sig.loc[tr_idx] > 0).sum(axis=1).mean())
        rows.append(m)
        print(f"  {name:<26} CAGR {m['cagr'] * 100:+7.2f}%  Sharpe {m['sharpe']:+6.2f}  "
              f"MaxDD {m['max_dd'] * 100:+7.2f}%  names {m['avg_names']:5.2f}  "
              f"turn {m['annual_turnover']:.2f}x  drag {m['cost_drag_annual'] * 100:.2f}%")

    save_json({"event_study": es, "leg_rows": leg_rows, "decomposition": rows},
              f"{SCRATCH}/diagnostic_train.json")
    print(f"\nwrote {SCRATCH}/diagnostic_train.json")
    print("TEST still not re-read.")


if __name__ == "__main__":
    main()
