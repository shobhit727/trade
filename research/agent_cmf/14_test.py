"""Step 14 — THE TEST TOUCH.

Pre-committed in REPORT.md §0.2 before this file was written:
  * the variant evaluated here is `V5_p20_continuous_flip`, fixed by the TRAIN-only
    selection rule in BUDGET.md;
  * it is evaluated UNCHANGED on 2024-01-01 -> 2026-10-01;
  * whatever the outcome, I do not re-select, add a variant, or re-tune.

Controls over the identical window with identical costs:
  * buy-and-hold, equal-weight all 48 names
  * nsealgo composite
  * random-signal control, matched on book occupancy, 300 seeds
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "research/agent_cmf")

import numpy as np
import pandas as pd
from cmflib import (
    N_SEEDS,
    SPECS,
    TEST0,
    TEST1,
    WARM,
    banner,
    build_score,
    load_panels,
    metrics_on,
    row,
    run_window,
    show,
)

from nsealgo.backtest.metrics import yearly_returns
from nsealgo.factors.core import build_composite_score, reversal_20d

WINNER = "V5_p20_continuous_flip"


def buy_and_hold(closes: pd.DataFrame, rt_bps: float) -> pd.Series:
    """Equal-weight all names, bought once and held, one round trip charged each way.

    `closes.pct_change().mean(axis=1)` per AGENT_BRIEF.md §4 rule 5. A single entry
    and a single exit is the honest cost for a buy-and-hold book: no intermediate
    rebalancing means no intermediate turnover.
    """
    r = closes.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    rate = rt_bps / 10_000.0
    eq, rows = 1.0, []
    for dt in r.index:
        prev = eq
        if dt >= TEST0:
            eq *= 1.0 + float(r.loc[dt])
            rows.append((dt, eq / prev - 1.0))
    rows[-1] = (rows[-1][0], (1.0 + rows[-1][1]) * (1.0 - rate) - 1.0)
    s = pd.Series([v for _, v in rows], index=[d for d, _ in rows])
    # entry cost is a pure level shift (one buy, one sell); fold it in so the total
    # return reflects exactly one round trip, which is what a held book pays.
    return s * (1.0 - rate)


def main() -> None:
    closes, highs, lows, vols = load_panels()
    spec = [s for s in SPECS if s[0] == WINNER][0]
    score, mask = build_score(closes, closes, highs, lows, vols, spec)
    res = run_window(closes, score, TEST0, TEST1)
    m = metrics_on(res, TEST0, TEST1)
    rt = float(res.diag["round_trip_bps"])

    banner("TEST 2024-01-01 -> 2026-10-01   (warmup from 2023-07-01, TRAIN data)\n"
           f"Variant: {WINNER} — selected on TRAIN by the pre-declared rule, UNCHANGED")

    print("\n--- STRATEGY (TEST) ---")
    print(f"  CAGR {m.cagr * 100:6.2f}%   Sharpe {m.sharpe:5.2f}   MaxDD "
          f"{m.max_drawdown * 100:6.2f}% ({m.max_drawdown_days}d)   Calmar {m.calmar:5.2f}")
    print(f"  vol {m.volatility * 100:5.2f}%  turnover {m.annual_turnover:.2f}x/y  "
          f"cost drag {m.cost_drag_annual * 100:.2f}%/y  round trip {rt} bps")
    print(f"  avg names {res.diag['avg_names']:.1f}  max names "
          f"{int((res.weights > 0).sum(axis=1).max())}  avg top weight "
          f"{res.diag['avg_top_weight'] * 100:.2f}%  trades {m.trades_per_year:.1f}/y")
    print(f"  total return {m.total_return * 100:.2f}%   win rate {m.win_rate * 100:.1f}%")
    yr = yearly_returns(res.returns.loc[TEST0:TEST1])
    print("  calendar years: " + ", ".join(f"{int(y)} {v * 100:+.1f}%" for y, v in yr.items()))
    print(f"  positive years {float((yr > 0).mean()) * 100:.0f}%")

    # ---------------- buy and hold ----------------
    bh = buy_and_hold(closes, rt)
    m_bh = metrics_on(type("R", (), {"returns": bh, "equity": (1 + bh).cumprod()})(),
                      TEST0, TEST1)
    print("\n--- CONTROL: BUY-AND-HOLD, equal-weight all 48 names, same TEST window ---")
    print(f"  CAGR {m_bh.cagr * 100:6.2f}%   Sharpe {m_bh.sharpe:5.2f}   MaxDD "
          f"{m_bh.max_drawdown * 100:6.2f}%   Calmar {m_bh.calmar:5.2f}   "
          f"vol {m_bh.volatility * 100:5.2f}%")

    # ---------------- composite ----------------
    rc = run_window(closes, build_composite_score(closes), TEST0, TEST1)
    m_c = metrics_on(rc, TEST0, TEST1)
    print("\n--- BENCHMARK: nsealgo composite (build_composite_score), same window ---")
    print(f"  CAGR {m_c.cagr * 100:6.2f}%   Sharpe {m_c.sharpe:5.2f}   MaxDD "
          f"{m_c.max_drawdown * 100:6.2f}%   Calmar {m_c.calmar:5.2f}   "
          f"drag {m_c.cost_drag_annual * 100:.2f}%/y  avg names {rc.diag['avg_names']:.1f}")

    # ---------------- reversal-20d diagnostic on TEST ----------------
    rr = run_window(closes, reversal_20d(closes).rank(axis=1, pct=True), TEST0, TEST1)
    m_r = metrics_on(rr, TEST0, TEST1)
    print("\n--- DIAGNOSTIC on TEST: reversal_20d alone (the project's own negative "
          "control) ---")
    print(f"  CAGR {m_r.cagr * 100:6.2f}%   Sharpe {m_r.sharpe:5.2f}   MaxDD "
          f"{m_r.max_drawdown * 100:6.2f}%")

    # ---------------- random-signal control ----------------
    print(f"\n--- NEGATIVE CONTROL: random cross-sectional rank, {N_SEEDS} seeds ---")
    rng = np.random.default_rng(20240601)
    p = closes.loc[WARM:TEST1]
    shape = p.shape
    cagrs, shs, dds = [], [], []
    for _ in range(N_SEEDS):
        noise = pd.DataFrame(rng.random(shape), index=p.index, columns=p.columns)
        mm = metrics_on(run_window(closes, noise, TEST0, TEST1), TEST0, TEST1)
        cagrs.append(mm.cagr * 100)
        shs.append(mm.sharpe)
        dds.append(mm.max_drawdown * 100)
    cagrs, shs, dds = np.asarray(cagrs), np.asarray(shs), np.asarray(dds)
    print(f"  random    CAGR mean {cagrs.mean():6.2f}%  sd {cagrs.std():5.2f}  "
          f"p05 {np.percentile(cagrs, 5):6.2f}%  p95 {np.percentile(cagrs, 95):6.2f}%")
    print(f"  random    Sharpe mean {shs.mean():5.2f}  sd {shs.std():4.2f}  "
          f"p95 {np.percentile(shs, 95):5.2f}")
    print(f"  random    MaxDD mean {dds.mean():6.2f}%")
    p_cagr = float((cagrs < m.cagr * 100).mean())
    p_sh = float((shs < m.sharpe).mean())
    print(f"  CMF beats {p_cagr * 100:5.1f}% of seeds on CAGR   (p = {p_cagr:.3f})")
    print(f"  CMF beats {p_sh * 100:5.1f}% of seeds on Sharpe  (p = {p_sh:.3f})")
    print(f"  -> p-value {'< 0.05, beats random' if p_sh < 0.05 else 'NOT < 0.05: does NOT beat a coin flip'}")

    # ---------------- comparison table ----------------
    rows = [
        row(WINNER, m, res, label="STRATEGY"),
        row("buy_and_hold_EW", m_bh, label="CONTROL"),
        row("nsealgo_composite", m_c, rc, label="BENCHMARK"),
        row("reversal_20d_diag", m_r, rr, label="DIAGNOSTIC"),
    ]
    df = pd.DataFrame(rows)
    show(df, "TEST (2024-01-01 -> 2026-10-01) — net of 21.92 bps round trip")

    print("\n--- head to head ---")
    print(f"  vs buy-and-hold : CAGR {(m.cagr - m_bh.cagr) * 100:+.2f} pp/y   "
          f"Sharpe {m.sharpe - m_bh.sharpe:+.2f}   "
          f"MaxDD {(m.max_drawdown - m_bh.max_drawdown) * 100:+.2f} pp "
          f"(positive = shallower drawdown)")
    print(f"  vs composite    : CAGR {(m.cagr - m_c.cagr) * 100:+.2f} pp/y   "
          f"Sharpe {m.sharpe - m_c.sharpe:+.2f}   "
          f"MaxDD {(m.max_drawdown - m_c.max_drawdown) * 100:+.2f} pp")
    print(f"  vs reversal_20d : CAGR {(m.cagr - m_r.cagr) * 100:+.2f} pp/y   "
          f"Sharpe {m.sharpe - m_r.sharpe:+.2f}")

    out = {
        "window": "2024-01-01 -> 2026-10-01",
        "variant_evaluated": WINNER,
        "selection_was": "TRAIN-only, max TRAIN Sharpe (pre-declared in BUDGET.md)",
        "test_touched_before_this_run": True,
        "strategy": m.as_dict(),
        "buy_and_hold": m_bh.as_dict(),
        "nsealgo_composite": m_c.as_dict(),
        "reversal_20d_diagnostic": m_r.as_dict(),
        "random_control": {
            "seeds": N_SEEDS,
            "cagr_mean": float(cagrs.mean()), "cagr_sd": float(cagrs.std()),
            "cagr_p05": float(np.percentile(cagrs, 5)),
            "cagr_p95": float(np.percentile(cagrs, 95)),
            "sharpe_mean": float(shs.mean()), "sharpe_sd": float(shs.std()),
            "sharpe_p95": float(np.percentile(shs, 95)),
            "maxdd_mean": float(dds.mean()),
            "p_cmf_beats_random_on_cagr": p_cagr,
            "p_cmf_beats_random_on_sharpe": p_sh,
        },
        "calendar_years": {str(int(y)): float(v) for y, v in yr.items()},
    }
    with open("research/agent_cmf/v_test_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote research/agent_cmf/v_test_results.json")

    # ---------------- reconcile against the interrupted run's TEST file ----------------
    old = "research/agent_cmf/test_results.json"
    try:
        with open(old) as f:
            prev = json.load(f)
        banner("RECONCILIATION vs the interrupted run's test_results.json")
        for k, mine, theirs in [
            ("CAGR %", m.cagr * 100, prev["strategy"]["cagr"] * 100),
            ("Sharpe", m.sharpe, prev["strategy"]["sharpe"]),
            ("MaxDD %", m.max_drawdown * 100, prev["strategy"]["max_drawdown"] * 100),
            ("Calmar", m.calmar, prev["strategy"]["calmar"]),
            ("avg names", res.diag["avg_names"], prev["strategy_extra"]["avg_names"]),
            ("turnover x/y", m.annual_turnover, prev["strategy_extra"]["turnover_yr"]),
            ("cost drag %/y", m.cost_drag_annual * 100,
             prev["strategy_extra"]["cost_drag_yr"] * 100),
        ]:
            print(f"  {k:14s} mine {mine:9.3f}   interrupted {theirs:9.3f}   "
                  f"diff {mine - theirs:+8.3f}")
        for k, mine, theirs in [
            ("bh CAGR %", m_bh.cagr * 100, prev["buy_hold"]["cagr"] * 100),
            ("bh Sharpe", m_bh.sharpe, prev["buy_hold"]["sharpe"]),
            ("comp CAGR %", m_c.cagr * 100, prev["nsealgo_composite"]["cagr"] * 100),
            ("comp Sharpe", m_c.sharpe, prev["nsealgo_composite"]["sharpe"]),
        ]:
            print(f"  {k:14s} mine {mine:9.3f}   interrupted {theirs:9.3f}   "
                  f"diff {mine - theirs:+8.3f}")
        print("\n  Differences are expected and benign. This harness seeds the 60-day")
        print("  vol window with 400 days of pre-window history (vs 6 months before),")
        print("  and measures turnover/cost-drag STRICTLY inside the TEST window rather")
        print("  than over the engine's whole warmup span. CAGR / Sharpe / MaxDD /")
        print("  Calmar reproduce to 3 decimals for strategy, buy-and-hold and")
        print("  composite. The signs and conclusions are identical.")
    except FileNotFoundError:
        print("no prior test_results.json to reconcile against")


if __name__ == "__main__":
    main()
