"""TRAIN-only controls for the on_balance_volume agent.

1. Negative control: random long/short coin with the SAME daily count of names long as
   the real variant and a random ranking among them. If the real variant sits inside
   the random band, it is noise.
2. Cost stress: base / double-slippage / triple-slippage / zero-cost.
3. Yearly returns.
4. Look-ahead tripwire: scrambling the panel's future must not change past weights.

Nothing here touches TEST. Runs are parallelised across processes (each backtest is
~2.5 s and the control grid is large); results are order-independent.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_obv")

from data_prep import load, split_test, split_train  # noqa: E402
from run_variants import VARIANTS, build_score, run  # noqa: E402

from nsealgo.backtest.engine import ENGINE_SHA, PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import STRESS_MODELS, CostModel  # noqa: E402

SEEDS = 50

_P = {}


def _init() -> None:
    panel, vol_panel = load()
    p, vp = split_train(panel), split_train(vol_panel)
    _P["p"], _P["vp"] = p, vp
    _P["model"] = CostModel(segment="delivery", slippage_bps=5)


def _init_test() -> None:
    panel, vol_panel = load()
    p, vp = split_test(panel), split_test(vol_panel)
    _P["p"], _P["vp"] = p, vp
    _P["model"] = CostModel(segment="delivery", slippage_bps=5)


def random_score_like(index: pd.Index, counts: np.ndarray, n_sym: int, seed: int,
                      ref: pd.DataFrame) -> pd.DataFrame:
    """Random score keeping the same per-day COUNT of long names, random ranking.

    Vectorised: draw uniform noise, keep the top-k per row (k = that day's real count),
    and score them by their noise rank. `counts` is (n_days, 1).
    """
    rng = np.random.default_rng(seed)
    R = rng.random((counts.shape[0], n_sym))
    order = np.argsort(-R, axis=1, kind="stable")
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(n_sym)[None, :].repeat(counts.shape[0], 0),
                      axis=1)
    keep = ranks < counts                     # (days, symbols) bool
    score = np.where(keep, ranks + 1.0, np.nan)
    # The date index MUST be set explicitly. Built from a bare ndarray the frame gets a
    # RangeIndex; `run_backtest` intersects the score index with the panel index, so an
    # empty intersection silently yields zero rebalances and a flat 0.00% equity curve
    # -- which reads exactly like a catastrophically bad control rather than a bug.
    return pd.DataFrame(score, index=index, columns=ref.columns)


def _one(job):
    lbl, seed = job
    p, vp = _P["p"], _P["vp"]
    sc = build_score(p, vp, VARIANTS[lbl])
    counts = sc.notna().sum(axis=1).to_numpy()[:, None]
    rnd = random_score_like(sc.index, counts, sc.shape[1], seed, sc)
    r = run(p, rnd, "rnd", _P["model"])
    if r["n_rebalances"] == 0:
        raise RuntimeError("control produced no rebalances -- score index misaligned")
    return lbl, seed, r["cagr"], r["sharpe"], r["max_drawdown"]


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "test"], default="train")
    args = ap.parse_args()
    is_test = args.split == "test"
    tag = args.split
    split = split_test if is_test else split_train
    init = _init_test if is_test else _init
    cut = pd.Timestamp("2025-03-31", tz="Asia/Kolkata") if is_test else \
        pd.Timestamp("2021-06-30", tz="Asia/Kolkata")

    panel, vol_panel = load()
    p, vp = split(panel), split(vol_panel)
    base = CostModel(segment="delivery", slippage_bps=5)
    cfg = PortfolioConfig()

    print(f"engine_sha = {ENGINE_SHA}   {tag.upper()} "
          f"{p.index[0].date()} -> {p.index[-1].date()}\n", flush=True)
    scores = {lbl: build_score(p, vp, n) for lbl, n in VARIANTS.items()}

    # ---------------- 1. negative control -------------------------------
    print(f"=== NEGATIVE CONTROL: random signal, same # names long, {SEEDS} seeds ===",
          flush=True)
    jobs = [(lbl, s) for lbl in scores for s in range(SEEDS)]
    got: dict[str, list] = {lbl: [] for lbl in scores}
    with ProcessPoolExecutor(max_workers=os.cpu_count(), initializer=init) as ex:
        for lbl, _seed, cagr, sharpe, dd in ex.map(_one, jobs, chunksize=4):
            got[lbl].append((cagr, sharpe, dd))
    ctrl = {}
    for lbl, sc in scores.items():
        arr = np.array(got[lbl])
        real = run(p, sc, lbl, base)
        ctrl[lbl] = {
            "real_cagr": real["cagr"], "real_sharpe": real["sharpe"],
            "real_maxdd": real["max_drawdown"],
            "rand_cagr_mean": float(arr[:, 0].mean()), "rand_cagr_std": float(arr[:, 0].std()),
            "rand_cagr_p05": float(np.percentile(arr[:, 0], 5)),
            "rand_cagr_p95": float(np.percentile(arr[:, 0], 95)),
            "rand_sharpe_mean": float(arr[:, 1].mean()), "rand_sharpe_std": float(arr[:, 1].std()),
            "rand_maxdd_mean": float(arr[:, 2].mean()),
            "pct_random_seeds_beaten_sharpe": float((arr[:, 1] < real["sharpe"]).mean() * 100),
            "pct_random_seeds_beaten_cagr": float((arr[:, 0] < real["cagr"]).mean() * 100),
        }
        c = ctrl[lbl]
        print(f"{lbl:<20} real   CAGR {c['real_cagr']*100:>6.2f}%  Sharpe {c['real_sharpe']:>5.2f}"
              f"  MaxDD {c['real_maxdd']*100:>7.2f}%")
        print(f"{'':<20} random CAGR {c['rand_cagr_mean']*100:>6.2f}% +/-{c['rand_cagr_std']*100:4.2f}"
              f"  [{c['rand_cagr_p05']*100:6.2f}..{c['rand_cagr_p95']*100:6.2f}]"
              f"  Sharpe {c['rand_sharpe_mean']:>5.2f}  MaxDD {c['rand_maxdd_mean']*100:>7.2f}%")
        print(f"{'':<20} -> beats {c['pct_random_seeds_beaten_sharpe']:.0f}% of random on Sharpe, "
              f"{c['pct_random_seeds_beaten_cagr']:.0f}% on CAGR\n", flush=True)

    # ---------------- 2. cost stress ------------------------------------
    print(f"=== COST STRESS ({tag.upper()}) ===", flush=True)
    print(f"{'variant':<20}{'model':<18}{'CAGR%':>9}{'Sharpe':>8}{'Cost/y%':>9}")
    stress = {}
    for lbl in ["V1_obv_n1_shipped", "V2_obv_n5", "V5_obv_n126"]:
        for mname, mdl in STRESS_MODELS.items():
            r = run(p, scores[lbl], f"{lbl}/{mname}", mdl)
            stress[f"{lbl}/{mname}"] = r
            print(f"{lbl:<20}{mname:<18}{r['cagr']*100:>9.2f}{r['sharpe']:>8.2f}"
                  f"{r['cost_drag_annual']*100:>9.2f}")
    print(flush=True)

    # ---------------- 3. yearly ------------------------------------------
    print(f"=== YEARLY RETURNS ({tag.upper()}) ===", flush=True)
    yr = {}
    for lbl, sc in scores.items():
        res = run_backtest(p, sc, base, cfg, rebalance="M")
        yr[lbl] = {str(k): float(v) for k, v in yearly_returns(res.returns).items()}
    bh = p.pct_change(fill_method=None).fillna(0.0).iloc[1:].mean(axis=1)
    yr["buy_and_hold"] = {str(k): float(v) for k, v in yearly_returns(bh).items()}
    years = sorted(yr["buy_and_hold"].keys())
    print(f"{'variant':<20}" + "".join(f"{y:>8}" for y in years))
    for lbl, d in yr.items():
        print(f"{lbl:<20}" + "".join(f"{d.get(y, float('nan'))*100:>8.1f}" for y in years))
    print("\npositive years: " + ", ".join(
        f"{k}={sum(1 for v in d.values() if v > 0)}/{len(years)}" for k, d in yr.items()))
    print(flush=True)

    # ---------------- 4. look-ahead tripwire -----------------------------
    print(f"=== LOOK-AHEAD TRIPWIRE ({tag.upper()}) ===", flush=True)
    sc = scores["V2_obv_n5"]
    base_res = run_backtest(p, sc, base, cfg, rebalance="M")
    cut = pd.Timestamp("2021-06-30", tz="Asia/Kolkata") if not is_test else \
        pd.Timestamp("2025-03-31", tz="Asia/Kolkata")
    tail = p.copy()
    noise = np.random.default_rng(7).normal(1.0, 0.25, size=tail.loc[cut:].shape)
    tail.loc[cut:] = tail.loc[cut:] * noise
    tv = vol_panel.copy()
    tv.loc[cut:] = tv.loc[cut:] * 0.5
    pert = run_backtest(tail, build_score(tail, tv, 5), base, cfg, rebalance="M")
    pre = p.index < cut
    same = bool(np.allclose(base_res.weights.loc[pre].fillna(0).to_numpy(),
                            pert.weights.loc[pre].fillna(0).to_numpy(), atol=1e-12))
    print(f"scrambling every price+volume AFTER {cut.date()} leaves earlier weights "
          f"identical: {same}")
    print("  (True = engine is point-in-time; False = it reads the future)")

    with open(f"research/agent_obv/controls_{tag}.json", "w") as fh:
        json.dump({"engine_sha": ENGINE_SHA, "split": tag, "negative_control": ctrl,
                   "stress": stress, "yearly": yr, "lookahead_tripwire_clean": same},
                  fh, indent=2)
    print(f"\nwrote research/agent_obv/controls_{tag}.json")


if __name__ == "__main__":
    main()
