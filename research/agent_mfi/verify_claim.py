"""Look-ahead tripwire + cash accounting for the MFI run.

Two questions:

1. **Is the pipeline point-in-time?** Scramble every price/volume bar after a cut date
   and require all *earlier* weights to be bit-identical. If any future value can reach a
   past weight, they will differ.

2. **Where did the return actually come from?** With 1-12 of 48 names held, most of the
   book is cash. Cash has a return. A book that holds 10% invested will "beat" a
   100%-invested benchmark in a drawdown for free. This decomposes each variant's return
   into *what the market did* and *what the selection added on top of being invested*,
   both net and gross of costs.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_mfi")

from data_prep import TEST_END, TEST_START, TRAIN_END, TRAIN_START, load_all  # noqa: E402
from mfi_lib import mfi_panel, signal_panel  # noqa: E402
from run_variants import BASE_COST, VARIANTS, build_score  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402

CUT = pd.Timestamp("2021-06-30", tz="Asia/Kolkata")


def tripwire() -> dict:
    """Scramble everything after CUT; earlier weights must not move at all."""
    panel, _, _, close, high, low, vol, _ = load_all()
    index = panel.loc[TRAIN_START:TRAIN_END].index
    sub_panel = panel.loc[index]

    mfi = mfi_panel(high, low, close, vol, 14)
    sig = signal_panel(mfi, 20.0)
    base = run_backtest(sub_panel, build_score(sub_panel, sig), BASE_COST,
                        config=PortfolioConfig(), rebalance="M")

    rng = np.random.default_rng(12345)
    scrambled_close = close.copy()
    scrambled_high = high.copy()
    scrambled_low = low.copy()
    scrambled_vol = vol.copy()
    # Shuffle the values of each symbol's post-CUT rows independently.
    for name in scrambled_close.columns:
        mask = scrambled_close.index > CUT
        n = int(mask.sum())
        if n < 2:
            continue
        # Reverse the price path, and scramble volumes separately.
        scrambled_close.loc[mask, name] = scrambled_close.loc[mask, name].to_numpy()[::-1]
        scrambled_high.loc[mask, name] = (
            scrambled_high.loc[mask, name].to_numpy()[::-1]
            * 1.02)
        scrambled_low.loc[mask, name] = (
            scrambled_low.loc[mask, name].to_numpy()[::-1]
            * 0.98)
        scrambled_vol.loc[mask, name] = (
            scrambled_vol.loc[mask, name].to_numpy()[rng.permutation(n)])

    scr_mfi = mfi_panel(scrambled_high, scrambled_low, scrambled_close, scrambled_vol, 14)
    scr_sig = signal_panel(scr_mfi, 20.0)
    scr = run_backtest(sub_panel, build_score(sub_panel, scr_sig), BASE_COST,
                       config=PortfolioConfig(), rebalance="M")

    w_base = base.weights
    w_scr = scr.weights.reindex(columns=w_base.columns)
    before = w_base.index <= CUT
    diff = (w_base.loc[before] - w_scr.loc[before]).abs()
    maxdiff = float(diff.to_numpy().max())
    n_diff = int((diff.to_numpy() > 1e-12).sum())
    after_diff = float(
        (w_base.loc[~before] - w_scr.loc[~before]).abs().to_numpy().max())

    return {
        "cut_date": str(CUT.date()),
        "weights_before_cut_max_abs_diff": maxdiff,
        "weights_before_cut_n_differing": n_diff,
        "weights_before_cut_n": int(w_base.loc[before].to_numpy().size),
        "weights_after_cut_max_abs_diff": after_diff,
        "pass": maxdiff <= 1e-12,
    }


def cash_decomposition() -> dict:
    """Attribute return to (market beta) + (selection alpha), net and gross."""
    panel, _, _, close, high, low, vol, _ = load_all()
    out: dict = {}
    for wname, index in (
        ("TRAIN", panel.loc[TRAIN_START:TRAIN_END].index),
        ("TEST", panel.loc[TEST_START:TEST_END].index),
    ):
        mfi = {p: mfi_panel(high, low, close, vol, p)
               for p in sorted({p for p, _ in VARIANTS.values()})}
        sub = panel.loc[index]
        rets = sub.pct_change(fill_method=None).fillna(0.0)
        mkt = rets.mean(axis=1)
        rows = {}
        for vname, (p, lo) in VARIANTS.items():
            sig = signal_panel(mfi[p], lo)
            res = run_backtest(sub, build_score(sub, sig), BASE_COST,
                               config=PortfolioConfig(), rebalance="M")
            held = res.weights
            invested = held.sum(axis=1)
            gross = (held.shift(1).fillna(0.0) * rets).sum(axis=1)
            beta = invested.shift(1).fillna(0.0) * mkt
            net = res.returns
            years = len(net) / 244.0

            def cagr(x, _years=years):
                return float((1.0 + x).cumprod().iloc[-1] ** (1 / _years) - 1)

            rows[vname] = {
                "mean_invested": float(invested.mean()),
                "pct_days_fully_invested": float((invested > 0.95).mean()),
                "pct_days_zero": float((invested <= 1e-9).mean()),
                "net_cagr": res.metrics.cagr,
                "gross_cagr": cagr(gross),
                "beta_component_cagr": cagr(beta),
                "selection_alpha_cagr": cagr(gross) - cagr(beta),
                "cost_drag_annual": res.metrics.cost_drag_annual,
                "mkt_cagr": cagr(mkt),
            }
        out[wname] = rows
    return out


if __name__ == "__main__":
    tw = tripwire()
    print("=== LOOK-AHEAD TRIPWIRE ===")
    print(json.dumps(tw, indent=2))
    cd = cash_decomposition()
    with open("research/agent_mfi/results_decomp.json", "w") as f:
        json.dump({"tripwire": tw, "decomposition": cd}, f, indent=2, default=str)

    for wname in ("TRAIN", "TEST"):
        print(f"\n===== {wname}: RETURN DECOMPOSITION =====")
        print(f"{'variant':18s} {'invest%':>8s} {'zero%':>6s} {'netCAGR%':>9s} "
              f"{'gross%':>8s} {'beta%':>7s} {'alpha%':>7s} {'cost%':>6s} {'mkt%':>7s}")
        for v, r in cd[wname].items():
            print(f"{v:18s} {r['mean_invested']*100:8.1f} "
                  f"{r['pct_days_zero']*100:6.1f} {r['net_cagr']*100:9.2f} "
                  f"{r['gross_cagr']*100:8.2f} {r['beta_component_cagr']*100:7.2f} "
                  f"{r['selection_alpha_cagr']*100:7.2f} "
                  f"{r['cost_drag_annual']*100:6.2f} {r['mkt_cagr']*100:7.2f}")
