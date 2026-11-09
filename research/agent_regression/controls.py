"""Controls for agent_regression. Run on TRAIN only; TEST is evaluated once, later.

These are NOT parameter variants -- they are not candidates and cannot be selected.
  1. Random signal, 10 seeds, matched on fraction of bars long (brief 6.5).
  2. Zero-cost control: same variant re-run with slippage_bps=0.0 (11.92 bps).
  3. Signal-diagnostics: is the filter itself carrying information, independent
     of the 22-name book? Forward return of flagged vs unflagged names.

Usage:
    .venv/bin/python research/agent_regression/controls.py train
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from harness import (  # noqa: E402
    COSTS,
    TEST,
    TRAIN,
    VARIANTS,
    ZERO_COST,
    regression_score,
    sma_flag,
)

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

HERE = Path("research/agent_regression")
CFG = PortfolioConfig()
SEEDS = list(range(1, 11))


def _m(res):
    mt = compute_metrics(res.returns, res.equity)
    return {"cagr": mt.cagr, "sharpe": mt.sharpe, "maxdd": mt.max_drawdown,
            "calmar": mt.calmar, "total": mt.total_return}


def random_mask(panel: pd.DataFrame, live_frac: float, seed: int) -> pd.DataFrame:
    """Random signal matched on fraction of bars long (brief 6.5).

    Two draws are needed, not one. A bare 0/1 mask leaves every "live" name tied at
    1.0, and `run_backtest` breaks ties with a stable argsort -- i.e. column order --
    so the book would be the alphabetically-first live names, which is not random at
    all. So: draw the mask for coverage, then a second independent uniform for the
    score, masked to the live cells. That matches the live fraction AND leaves the
    selection of *which* 22 names to hold genuinely random.
    """
    rng = np.random.default_rng(seed)
    live = rng.random(panel.shape) < live_frac
    score = rng.random(panel.shape)
    df = pd.DataFrame(score, index=panel.index, columns=panel.columns)
    return df.where(pd.DataFrame(live, index=panel.index, columns=panel.columns))


def signal_diagnostic(panel: pd.DataFrame, period: int) -> dict:
    """Is the SMA filter informative at all, before any portfolio construction?

    For every symbol-day the flag is known at the close of day t. Compare the
    forward 21-day return of flagged cells against unflagged cells. This is the
    strategy's own claim, tested directly -- no 22-name book, no costs, no ranking
    -- so it is not contaminated by the book construction.

    Two views, because they disagreed and both are true:
      * mean RAW forward return  -- outlier-sensitive, dominated by the right tail
      * mean cross-sectional RANK of forward return -- the median-ish view, and the
        one that actually matches what the book does (it buys the top of the rank)
    `rank_spread` is on percentiles, so -1.0pp means the average flagged name sits
    one percentile below the average unflagged name. Under the null (flag drawn at
    random with the same rate) this is ~0 at any flag rate, because a random subset
    of a uniform distribution still has mean 0.5.
    """
    flag = sma_flag(panel, period) > 0
    fwd = panel.shift(-21) / panel - 1.0
    fwd_r = (fwd.rank(axis=1, pct=True) - 0.5).stack(future_stack=True)
    flag_s = flag.stack(future_stack=True)
    fwd_s = fwd.stack(future_stack=True)
    # Only cells where the flag was decidable at the close of t AND a 21d forward
    # return exists. The last 21 bars of the panel are excluded by construction.
    ok = flag_s.notna() & fwd_s.notna() & fwd_r.notna()
    is_f = ok & (flag_s == True)  # noqa: E712
    is_u = ok & (flag_s == False)  # noqa: E712
    a, b = fwd_r[is_f], fwd_r[is_u]
    n_a, n_b = int(a.size), int(b.size)
    mean_a, mean_b = float(a.mean()), float(b.mean())
    se = float(np.sqrt(a.var(ddof=1) / max(n_a, 1) + b.var(ddof=1) / max(n_b, 1)))
    # Pooled t on the raw forward return difference (the economically direct claim).
    fa, fb = fwd_s[is_f], fwd_s[is_u]
    se_raw = float(np.sqrt(fa.var(ddof=1) / max(n_a, 1) + fb.var(ddof=1) / max(n_b, 1)))
    return {
        "period": period,
        "n_flagged": n_a, "n_unflagged": n_b,
        "mean_rank_ret_flagged": mean_a,
        "mean_rank_ret_unflagged": mean_b,
        "spread_rank": mean_a - mean_b,
        "t_stat": (mean_a - mean_b) / se if se > 0 else 0.0,
        "flag_rate": float(flag.to_numpy().mean()),
        "mean_raw_fwd_flagged_pct": float(fa.mean() * 100),
        "mean_raw_fwd_unflagged_pct": float(fb.mean() * 100),
        "raw_diff_pp": float((fa.mean() - fb.mean()) * 100),
        "t_stat_raw": float((fa.mean() - fb.mean()) / se_raw) if se_raw > 0 else 0.0,
        "median_raw_fwd_flagged_pct": float(fa.median() * 100),
        "median_raw_fwd_unflagged_pct": float(fb.median() * 100),
    }


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "train"
    lo, hi = TRAIN if stage == "train" else TEST
    panel, _s, _r = load_universe("data/nse")
    p = panel.loc[lo:hi]
    print(f"[{stage}] {lo.date()} -> {hi.date()}  bars={len(p)}")
    print(f"[{stage}] prov={json.dumps(provenance())}")

    leader = json.loads((HERE / "selected_variant.json").read_text())["name"]
    period, kind = VARIANTS[leader]
    sc = regression_score(panel, period, kind).loc[lo:hi]
    live = float(sc.notna().to_numpy().mean())
    print(f"\nselected variant {leader}  period={period} kind={kind}  live={live*100:.1f}%")

    base = run_backtest(p, sc, COSTS, CFG, rebalance="M")
    bm = _m(base)
    print(f"  {leader:<22} CAGR {bm['cagr']*100:7.2f}%  Sh {bm['sharpe']:6.2f}  "
          f"MaxDD {bm['maxdd']*100:7.2f}%  Calmar {bm['calmar']:6.2f}")

    # ---- control 1: zero cost (slippage 0 -> 11.92 bps all-in)
    zres = run_backtest(p, sc, ZERO_COST, CFG, rebalance="M")
    zm = _m(zres)
    print(f"  {'ZERO_COST(11.92bps)':<22} CAGR {zm['cagr']*100:7.2f}%  "
          f"Sh {zm['sharpe']:6.2f}  MaxDD {zm['maxdd']*100:7.2f}%  "
          f"Calmar {zm['calmar']:6.2f}")
    drag = zm["cagr"] - bm["cagr"]
    print(f"  -> cost drag = {drag*100:+.2f} pp/yr of CAGR "
          f"(turnover {base.metrics.annual_turnover:.2f}x/y, "
          f"engine cost_drag {base.metrics.cost_drag_annual*100:.2f}%/y)")

    # ---- control 2: random, same live rate, 10 seeds
    print(f"\n  random control, {len(SEEDS)} seeds, live={live*100:.1f}%:")
    rows = []
    for seed in SEEDS:
        rs = random_mask(p, live, seed)
        rr = run_backtest(p, rs, COSTS, CFG, rebalance="M")
        m = _m(rr)
        m["seed"] = seed
        rows.append(m)
        print(f"    seed {seed:2d}  CAGR {m['cagr']*100:7.2f}%  Sh {m['sharpe']:6.2f}  "
              f"MaxDD {m['maxdd']*100:7.2f}%  Calmar {m['calmar']:6.2f}")
    df = pd.DataFrame(rows)
    print(f"    MEAN      CAGR {df['cagr'].mean()*100:7.2f}%  "
          f"Sh {df['sharpe'].mean():6.2f}  MaxDD {df['maxdd'].mean()*100:7.2f}%  "
          f"Calmar {df['calmar'].mean():6.2f}")
    # `lose_to` = how many random seeds returned MORE than the strategy.
    # (Label matters: the count is seeds-that-won, not seeds-the-strategy-beat.)
    lose_to = int((df["cagr"] > bm["cagr"]).sum())
    print(f"    random seeds that BEAT the strategy: {lose_to}/{len(SEEDS)}; "
          f"mean edge {(bm['cagr'] - df['cagr'].mean())*100:+.2f} pp/yr")

    # ---- control 3: does the filter itself carry information?
    # Diagnostic runs on THIS stage's panel only, so TRAIN never sees TEST bars.
    print("\n  signal diagnostic (forward 21d return, flagged vs unflagged) "
          f"-- {stage} window only:")
    diags = [signal_diagnostic(p, pr) for pr in (20, 50, 200)]
    for d in diags:
        print(f"    SMA{d['period']:<4} flagged {d['flag_rate']*100:5.1f}% of cells")
        print(f"          RAW   fwd {d['mean_raw_fwd_flagged_pct']:+.3f}% vs "
              f"{d['mean_raw_fwd_unflagged_pct']:+.3f}%  "
              f"diff {d['raw_diff_pp']:+.3f}pp  t={d['t_stat_raw']:+.2f}")
        print(f"          MEDIAN fwd {d['median_raw_fwd_flagged_pct']:+.3f}% vs "
              f"{d['median_raw_fwd_unflagged_pct']:+.3f}%")
        print(f"          RANK  spread {d['spread_rank']*100:+.3f}pp  "
              f"t={d['t_stat']:+.2f}   (n={d['n_flagged']:,} / {d['n_unflagged']:,})")

    payload = {
        "stage": stage, "window": [str(lo.date()), str(hi.date())],
        "leader": leader, "live_frac": live,
        "base": bm, "zero_cost": zm, "cost_drag_cagr_pp": drag * 100,
        "random": rows,
        "random_mean_cagr": float(df["cagr"].mean()),
        "random_mean_sharpe": float(df["sharpe"].mean()),
        "random_mean_maxdd": float(df["maxdd"].mean()),
        "random_seeds_that_beat_strategy": lose_to,
        "edge_vs_random_pp": (bm["cagr"] - float(df["cagr"].mean())) * 100,
        "signal_diagnostics": diags,
        "yearly_returns_strategy_pct": {
            str(k): float(v * 100) for k, v in yearly_returns(base.returns).items()
        },
        "provenance": provenance(),
    }
    (HERE / f"controls_{stage}.json").write_text(json.dumps(payload, indent=2))
    df.to_csv(HERE / f"random_{stage}.csv", index=False)
    print(f"\n  wrote {HERE}/controls_{stage}.json + random_{stage}.csv")


if __name__ == "__main__":
    main()
