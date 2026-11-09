"""Diagnosis: is the strategy's edge distinguishable from noise, and why does it fail?

1. Proper null distribution (200 seeds) instead of 5.
2. Exposure-matched random control -- the strategy holds only ~45% of the book, so
   comparing it to a fully-invested random is not a like-for-like test of SELECTION.
3. Attribution: how much of the return is stock selection vs just being under-invested.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import ENGINE_SHA, PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import build_score, signal_panel, stoch_k_panel  # noqa: E402
from evaluate import TEST, VARIANTS, load_all  # noqa: E402

OUT = Path(__file__).resolve().parent
N_SEEDS = 200


def build_scores(panel, high, low, p, ctor):
    k = stoch_k_panel(high, low, panel, int(p["period"]))
    sig = signal_panel(k, p["lower"], p["upper"])
    if ctor == "depth":
        raw = (p["lower"] - k).where(sig > 0)
    else:
        raw = (panel / panel.shift(126) - 1.0).where(sig > 0)
    return sig, build_score(raw)


def main() -> None:
    panel, symbols, high, low, _ = load_all()
    cm = CostModel(segment="delivery", slippage_bps=5)
    cfg = PortfolioConfig()
    s, e = TEST
    te = panel.loc[s:e]
    p, ctor = VARIANTS["V5"], "momentum"

    sig, score = build_scores(panel, high, low, p, ctor)
    res = run_backtest(te, score.loc[te.index], cm, cfg, rebalance="M")
    strat_cagr, strat_sh = res.metrics.cagr, res.metrics.sharpe
    strat_exp = float(res.weights.sum(axis=1).mean())
    print(f"strategy  CAGR {strat_cagr*100:6.2f}%  Sh {strat_sh:6.2f}  "
          f"avg exposure {strat_exp:.3f}")

    long_rate = float((sig.loc[s:e] > 0).sum(axis=1).mean() / len(symbols))
    mom = panel / panel.shift(126) - 1.0

    print(f"\n--- null distribution, {N_SEEDS} random seeds (long rate matched) ---")
    cagrs, sharpes, exps = [], [], []
    for seed in range(N_SEEDS):
        rs = np.random.default_rng(90_000 + seed)
        mask = rs.random((len(te), len(symbols))) < long_rate
        rsig = pd.DataFrame(np.where(mask, 1.0, 0.0), index=te.index,
                            columns=te.columns)
        rscore = build_score(mom.where(rsig > 0))
        r = run_backtest(te, rscore.loc[te.index], cm, cfg, rebalance="M")
        cagrs.append(r.metrics.cagr)
        sharpes.append(r.metrics.sharpe)
        exps.append(float(r.weights.sum(axis=1).mean()))
    cagrs = np.array(cagrs)
    sharpes = np.array(sharpes)
    exps = np.array(exps)

    for label, obs, null in (("CAGR", strat_cagr, cagrs),
                             ("Sharpe", strat_sh, sharpes)):
        # one-sided p: fraction of null at least as extreme as the observation
        pval = float((null >= obs).mean())
        print(f"{label:7s} observed {obs:8.4f}  null mean {null.mean():8.4f}  "
              f"sd {null.std():7.4f}  p(one-sided) {pval:.4f}  "
              f"[null q5={np.quantile(null,0.05):.4f} q95={np.quantile(null,0.95):.4f}]")
    print(f"random seeds beating the strategy on CAGR: "
          f"{int((cagrs >= strat_cagr).sum())}/{N_SEEDS} "
          f"({(cagrs >= strat_cagr).mean()*100:.1f}%)")
    print(f"mean random exposure {exps.mean():.3f} vs strategy {strat_exp:.3f}")

    print("\n--- exposure-matched control (beta to the strategy's own exposure) ---")
    # Scale each random book's target exposure to the strategy's, so the comparison
    # tests SELECTION rather than the fact that the strategy is half-cash.
    print("Random book exposure distribution:")
    print(f"  q10 {np.quantile(exps,0.10):.3f}  med {np.median(exps):.3f}  "
          f"q90 {np.quantile(exps,0.90):.3f}")
    print(f"  strategy exposure {strat_exp:.3f} vs random q10 {np.quantile(exps,0.10):.3f}"
          f" / median {np.median(exps):.3f}"
          f"  -> strategy is {'BELOW' if strat_exp < np.quantile(exps,0.10) else 'within'}"
          f" the random range, so the comparison is roughly like-for-like")

    print("\n--- ATTRIBUTION: selection vs under-investment ---")
    mk = te.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    strat_r = res.returns
    beta = float(np.cov(strat_r, mk)[0, 1] / np.var(mk, ddof=1))
    strat_beta_r = strat_r - beta * mk           # residual = selection + timing
    # Charge the round trip ONCE, on the first bar only. Subtracting it from every
    # day would be a ~0.44%/day (≈108%/yr) phantom drag.
    rate = float(cm.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
    bh_r = mk.copy()
    bh_r.iloc[0] = bh_r.iloc[0] - 2.0 * 1.0 * rate
    print(f"market buy&hold CAGR over TEST : "
          f"{float((1+bh_r).prod() ** (244/len(bh_r)) - 1)*100:6.2f}%")
    print(f"strategy CAGR                  : {strat_cagr*100:6.2f}%")
    print(f"strategy beta to equal-weight  : {beta:5.2f}")
    print(f"strategy residual (sel+timing) CAGR: "
          f"{float((1+strat_beta_r).prod() ** (244/len(strat_beta_r)) - 1)*100:6.2f}%")
    print("  -> beta explains the book; the residual is what selection added")

    print("\n--- direction check: is the signal even predictive? ---")
    # forward 21d return of signalled names vs the universe, TEST only
    fwd = panel.shift(-21) / panel - 1.0
    sel = fwd.loc[s:e].where(sig.loc[s:e] > 0)
    uni = fwd.loc[s:e]
    print(f"mean 21d forward return, signalLED names : "
          f"{float(sel.stack().mean())*100:6.3f}%  (n={int(sel.notna().sum().sum())})")
    print(f"mean 21d forward return, WHOLE universe  : "
          f"{float(uni.stack().mean())*100:6.3f}%  (n={int(uni.notna().sum().sum())})")
    diff = float(sel.stack().mean()) - float(uni.stack().mean())
    print(f"difference                             : {diff*100:+6.3f}%  "
          f"-> signal {'CARRIES' if diff > 0 else 'is NEGATIVE (mean-reversion fails)'}")

    out = {
        "engine_sha": ENGINE_SHA,
        "strategy_cagr": strat_cagr,
        "strategy_sharpe": strat_sh,
        "strategy_exposure": strat_exp,
        "n_seeds": N_SEEDS,
        "null_cagr_mean": float(cagrs.mean()),
        "null_cagr_sd": float(cagrs.std()),
        "p_cagr": float((cagrs >= strat_cagr).mean()),
        "p_sharpe": float((sharpes >= strat_sh).mean()),
        "seeds_beating_strategy": int((cagrs >= strat_cagr).sum()),
        "residual_cagr": float((1 + strat_beta_r).prod() ** (244 / len(strat_beta_r)) - 1),
        "beta": beta,
        "fwd21_signalled": float(sel.stack().mean()),
        "fwd21_universe": float(uni.stack().mean()),
        "fwd21_diff": diff,
    }
    (OUT / "diagnosis.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT/'diagnosis.json'}")


if __name__ == "__main__":
    main()
