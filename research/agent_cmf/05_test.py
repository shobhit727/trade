"""Step 05 — THE TEST TOUCH. Run once, on the TRAIN-selected winner, unchanged.

Protocol discipline:
  * Only V5_p20_continuous_flipped is evaluated on TEST. The other four were
    TRAIN-only; evaluating them here would be a 5th touch of TEST and would
    destroy the out-of-sample claim.
  * The book is warmed up from 2023-07-01 so it is already invested on
    2024-01-01 (history, not TEST data), then metrics are read on TEST only.
  * Controls: buy-and-hold, random signal at the same liveness, nsealgo
    composite — all on the identical TEST window with identical costs.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics, yearly_returns
from nsealgo.costs import CostModel
from nsealgo.factors.core import build_composite_score, rank_cross_sectional

WARM = pd.Timestamp("2023-07-01", tz="Asia/Kolkata")   # pre-TEST, for warmup only
TEST0 = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST1 = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")
COST = CostModel(segment="delivery", slippage_bps=5)
CFG = PortfolioConfig()
RT_BPS = float(COST.all_in_round_trip_bps(__import__("decimal").Decimal("100000")))
N_SEEDS = 300


def cmf_panel(closes, highs, lows, vols, period):
    rng = (highs - lows).replace(0.0, np.nan)
    mfm = ((closes - lows) - (highs - closes)) / rng
    num = (mfm * vols).rolling(period, min_periods=period).sum()
    den = vols.rolling(period, min_periods=period).sum()
    return num / den.replace(0.0, np.nan)


def evaluate(res, lo, hi):
    r = res.returns.loc[lo:hi]
    eq = res.equity.loc[lo:hi]
    eq = eq / eq.iloc[0]
    m = compute_metrics(r, eq)
    return m


def fmt(name, m, extra=""):
    return (f"{name:34s} CAGR {m.cagr * 100:7.2f}%  Sh {m.sharpe:5.2f}  "
            f"MaxDD {m.max_drawdown * 100:7.2f}%  Cal {m.calmar:5.2f}  {extra}")


def main() -> None:
    closes = pd.read_pickle("research/agent_cmf/_closes.pkl")
    highs = pd.read_pickle("research/agent_cmf/_highs.pkl")
    lows = pd.read_pickle("research/agent_cmf/_lows.pkl")
    vols = pd.read_pickle("research/agent_cmf/_vols.pkl")

    print("=" * 78)
    print("TEST WINDOW 2024-01-01 -> 2026-10-01   (warmup from 2023-07-01)")
    print("Selected on TRAIN by max Sharpe: V5_p20_continuous_flipped")
    print("=" * 78)

    # ---------- the strategy, exactly as selected on TRAIN ----------
    cmf = cmf_panel(closes, highs, lows, vols, 20)
    score = rank_cross_sectional(-cmf)          # V5, unchanged
    res = run_backtest(closes.loc[WARM:TEST1], score.loc[WARM:TEST1], COST, CFG)
    m = evaluate(res, TEST0, TEST1)
    print("\n--- STRATEGY (TEST) ---")
    print(fmt("CMF(20) flipped, cross-sectional", m))
    print(f"    turnover {m.annual_turnover:.2f}x/yr  cost drag "
          f"{m.cost_drag_annual * 100:.2f}%/yr  rt {res.diag['round_trip_bps']} bps  "
          f"avg names {res.diag['avg_names']:.1f}  trades {m.trades_per_year:.1f}/yr")
    print(f"    avg top weight {res.diag['avg_top_weight'] * 100:.2f}%  "
          f"(cap {CFG.max_weight * 100:.0f}%)")
    yr = yearly_returns(res.returns.loc[TEST0:TEST1])
    print("    calendar years: "
          + ", ".join(f"{int(y)} {v * 100:+.1f}%" for y, v in yr.items()))
    print(f"    positive years {float((yr > 0).mean()) * 100:.0f}%")

    # ---------- buy-and-hold over the identical window ----------
    # Equal-weight all 48 names, held, with one full-book round trip charged on
    # entry and one on exit at the same all-in bps. No rebalancing, so no
    # intermediate turnover.
    r = closes.pct_change(fill_method=None).loc[WARM:TEST1].mean(axis=1).fillna(0.0)
    rate = RT_BPS / 10_000.0
    e = 1.0 - rate                       # pay to get in
    bh_daily, prev = [], e
    for i, dt in enumerate(r.index):
        if dt >= TEST0:
            e *= (1.0 + float(r.loc[dt]))
            bh_daily.append((dt, e / prev - 1.0))
            prev = e
    e *= (1.0 - rate)                   # pay to get out
    bh_daily[-1] = (bh_daily[-1][0], (1.0 + bh_daily[-1][1]) * (1.0 - rate) - 1.0)
    bh = pd.Series([x[1] for x in bh_daily], index=[x[0] for x in bh_daily])
    bh_eq = (1.0 + bh).cumprod()
    m_bh = evaluate(type("R", (), {"returns": bh, "equity": bh_eq})(), TEST0, TEST1)
    print("\n--- BUY-AND-HOLD (TEST), equal-weight all 48 names, net of one "
          "round trip each way ---")
    print(fmt("buy-and-hold EW universe", m_bh))

    # ---------- nsealgo composite ----------
    comp = build_composite_score(closes)
    rc = run_backtest(closes.loc[WARM:TEST1], comp.loc[WARM:TEST1], COST, CFG)
    m_c = evaluate(rc, TEST0, TEST1)
    print("\n--- BENCHMARK (TEST): nsealgo composite ---")
    print(fmt("nsealgo composite", m_c))
    print(f"    turnover {m_c.annual_turnover:.2f}x/yr  cost drag "
          f"{m_c.cost_drag_annual * 100:.2f}%/yr  avg names {rc.diag['avg_names']:.1f}")

    # ---------- random-signal control ----------
    # V5 holds a full book at all times, so the matched control is a random
    # cross-sectional ranking: same #names, same caps, same turnover budget,
    # same costs, zero information.
    rng = np.random.default_rng(20240601)
    cagrs, shs, dds = [], [], []
    sl = slice(WARM, TEST1)
    for _ in range(N_SEEDS):
        noise = pd.DataFrame(
            rng.random(closes.loc[sl].shape), index=closes.loc[sl].index,
            columns=closes.loc[sl].columns)
        rr = run_backtest(closes.loc[sl], noise, COST, CFG)
        mm = evaluate(rr, TEST0, TEST1)
        cagrs.append(mm.cagr * 100)
        shs.append(mm.sharpe)
        dds.append(mm.max_drawdown * 100)
    cagrs, shs, dds = np.array(cagrs), np.array(shs), np.array(dds)
    print(f"\n--- RANDOM-SIGNAL CONTROL (TEST), {N_SEEDS} seeds ---")
    print(f"    random rank    CAGR mean {cagrs.mean():6.2f}%  sd {cagrs.std():5.2f}  "
          f"p05 {np.percentile(cagrs, 5):6.2f}%  p95 {np.percentile(cagrs, 95):6.2f}%")
    print(f"    random rank    Sharpe mean {shs.mean():5.2f}  sd {shs.std():4.2f}  "
          f"p95 {np.percentile(shs, 95):5.2f}")
    print(f"    random rank    MaxDD mean {dds.mean():6.2f}%")
    pct = float((cagrs < m.cagr * 100).mean())
    pct_s = float((shs < m.sharpe).mean())
    print(f"    CMF beat {pct * 100:.1f}% of random seeds on CAGR "
          f"(p-value {pct:.3f})")
    print(f"    CMF beat {pct_s * 100:.1f}% of random seeds on Sharpe "
          f"(p-value {pct_s:.3f})")

    out = {
        "window": "2024-01-01 -> 2026-10-01",
        "strategy": m.as_dict(),
        "buy_hold": m_bh.as_dict(),
        "nsealgo_composite": m_c.as_dict(),
        "random_control": {
            "seeds": N_SEEDS,
            "cagr_mean": float(cagrs.mean()), "cagr_sd": float(cagrs.std()),
            "cagr_p05": float(np.percentile(cagrs, 5)),
            "cagr_p95": float(np.percentile(cagrs, 95)),
            "sharpe_mean": float(shs.mean()), "sharpe_sd": float(shs.std()),
            "maxdd_mean": float(dds.mean()),
            "p_cmf_beats_random_on_cagr": pct,
            "p_cmf_beats_random_on_sharpe": pct_s,
        },
        "strategy_extra": {
            "turnover_yr": res.metrics.annual_turnover,
            "cost_drag_yr": res.metrics.cost_drag_annual,
            "avg_names": res.diag["avg_names"],
            "round_trip_bps": res.diag["round_trip_bps"],
        },
        "calendar_years": {str(int(y)): float(v) for y, v in yr.items()},
    }
    with open("research/agent_cmf/test_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote research/agent_cmf/test_results.json")


if __name__ == "__main__":
    main()
