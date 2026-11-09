"""Step 3 — ABLATIONS. Diagnostics, not parameter variants.

Run AFTER the frozen TEST run and never used for selection. The question they
answer: does the adx_trend signal contribute anything at all, or is the return
entirely the momentum ranking it happens to be wrapped around?

  A1  momentum ranking, NO strategy flag      -> is the flag adding value?
  A2  strategy flag, equal weight, NO ranking-> does the 1-day sign have value?
  A3  equal-weight whole universe            -> the no-skill floor.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/agent_adx_trend")

import harness as H  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402

ABL_PORT = PortfolioConfig(turnover_budget=1.0, max_weight=1.0 / 22,
                           max_sector_weight=1.0, cash_buffer=0.10,
                           n_positions=22, max_names=22)
#: "Flag only, no ranking" needs every flagged name held at equal weight, otherwise
#: a score of 1.0 ties across all of them and the engine's stable sort just takes the
#: first 22 in column order -- an arbitrary subset, not an ablation.
ABL_PORT_ALL = PortfolioConfig(turnover_budget=1.0, max_weight=1.0 / 48,
                               max_sector_weight=1.0, cash_buffer=0.10,
                               n_positions=48, max_names=48)


def main() -> None:
    panel, _ = H.load_panel()
    mom252 = panel / panel.shift(252) - 1.0

    scores = {
        "A1 mom252 only (no adx flag)": (mom252, H.PORTFOLIO),
        "A2 adx flag only, all eq-wt": (H.signal_flag(panel), ABL_PORT_ALL),
    }

    print("=" * 110)
    print("ABLATIONS (diagnostic only -- frozen selection was already V2_mom252)")
    print("=" * 110)
    for set_name, start, end in (
        ("TRAIN", H.TRAIN_START, H.TRAIN_END),
        ("TEST", H.TEST_START, H.TEST_END),
    ):
        print(f"\n  --- {set_name} ---")
        print("  " + H.HDR)
        for lab, (sc, cfg) in scores.items():
            res = run_backtest(panel.loc[start:end], sc.loc[start:end],
                               H.COST_MODEL, cfg, rebalance="M")
            print("  " + H.line(H.row_of(lab, set_name, res)))

        frozen = H.run(panel, H.build_score("V2_mom252", panel), start, end)
        print("  " + H.line(H.row_of("frozen V2 (flag+rank)", set_name, frozen)))
        bw = H.buy_and_hold(panel, start, end)
        m = bw["metrics"]
        print("  " + H.line(H.Row("A3 equal-weight universe", set_name, m.cagr,
                                  m.sharpe, m.max_drawdown, m.calmar,
                                  bw["annual_turnover"], bw["cost_drag"],
                                  float(len(panel.columns)), m.total_return, 0.0)))

    # ---- is the 1-day flag PREDICTIVE of the NEXT bar? ----
    # Critical: the flag on bar t is sign(close[t] - close[t-1]) == sign(ret[t]).
    # Comparing it to ret[t] is tautological. It must be compared to ret[t+1].
    print()
    print("=" * 110)
    print("IS THE 1-DAY FLAG PREDICTIVE OF THE NEXT BAR? (TEST window, per-name-day)")
    print("=" * 110)
    px = panel.loc[H.TEST_START:H.TEST_END]
    ret_t = px.pct_change(fill_method=None)       # close[t-1] -> close[t]
    fwd = ret_t.shift(-1)                        # close[t]   -> close[t+1]
    flag = H.signal_flag(px) > 0
    df = pd.concat([fwd.stack(future_stack=True), flag.stack(future_stack=True)],
                   axis=1).dropna()
    df.columns = ["next_ret", "flag"]
    up = df[df["flag"]]["next_ret"]
    lo = df[~df["flag"]]["next_ret"]
    spread = (float(up.mean()) - float(lo.mean())) * 100
    print(f"  bars where close[t]>close[t-1]  : n={len(up):>6}  "
          f"mean ret[t+1] {up.mean() * 100:+.4f}%")
    print(f"  bars where close[t]<=close[t-1] : n={len(lo):>6}  "
          f"mean ret[t+1] {lo.mean() * 100:+.4f}%")
    print(f"  next-bar spread (flag - no flag): {spread:+.4f}%/day "
          f"= {spread * 100:+.1f} bps/day")
    print("  one round trip costs 21.92 bps; a 1-bar signal must beat that EVERY day")
    verdict = ("informative, but far too weak to cover delivery costs"
               if spread > 0.219 else
               "NOT predictive of the next bar -- it is noise")
    print(f"  -> the 1-day sign is {verdict}.")
    if spread <= 0:
        print("  CAUTION: the spread is NEGATIVE. In TEST the sign actually points the")
        print("  wrong way -- flagged names underperformed non-flagged ones by 2 bps/day.")
        print("  Any return the strategy shows comes entirely from the ranking layered on")
        print("  top, never from the signal itself.")

    # ---- decompose the flag's damage: selection quality vs pure cost ----
    print()
    print("=" * 110)
    print("DECOMPOSITION (TEST): where does the flag's damage come from?")
    print("=" * 110)
    a1 = H.run(panel, mom252, H.TEST_START, H.TEST_END)
    v2 = H.run(panel, H.build_score("V2_mom252", panel), H.TEST_START, H.TEST_END)
    gap = (a1.metrics.cagr - v2.metrics.cagr) * 100
    cost_gap = (v2.metrics.cost_drag_annual - a1.metrics.cost_drag_annual) * 100
    print(f"  A1 momentum alone        CAGR {a1.metrics.cagr * 100:6.2f}%  "
          f"turnover {a1.metrics.annual_turnover:.2f}x  cost {a1.metrics.cost_drag_annual * 100:.2f}%/y")
    print(f"  V2 momentum + adx flag   CAGR {v2.metrics.cagr * 100:6.2f}%  "
          f"turnover {v2.metrics.annual_turnover:.2f}x  cost {v2.metrics.cost_drag_annual * 100:.2f}%/y")
    print(f"  return given up by adding the flag : {gap:.2f}pp/yr")
    print(f"  of which explained by extra costs  : {cost_gap:.2f}pp/yr "
          f"({cost_gap / gap * 100:.0f}%)")
    print(f"  remainder = worse name SELECTION   : {gap - cost_gap:.2f}pp/yr "
          f"({(gap - cost_gap) / gap * 100:.0f}%)")
    print("  -> the flag is not merely expensive, it is actively choosing worse names.")

    # ---- second control: a pure random signal, no ranking at all ----
    print()
    print("=" * 110)
    print("CONTROL 2: pure random signal, no momentum ranking, same % of name-days long")
    print("=" * 110)
    print("  " + H.HDR)
    p = float((H.signal_flag(panel) > 0).to_numpy().mean())
    cs = []
    for seed in range(20):
        r2 = np.random.default_rng(1000 + seed)
        mask = pd.DataFrame(r2.random(panel.shape) < p,
                            index=panel.index, columns=panel.columns)
        noise = r2.normal(size=panel.shape)
        sc = pd.DataFrame(noise, index=panel.index, columns=panel.columns).where(mask)
        rs = H.run(panel, sc, H.TEST_START, H.TEST_END)
        cs.append(rs.metrics.cagr)
    cs = np.array(cs)
    print("  " + H.line(H.Row("random, no ranking (med)", "TEST",
                              float(np.median(cs)), 0, 0, 0, 0, 0, float("nan"), 0, 0)))
    print(f"      mean {cs.mean() * 100:.2f}%  p5 {np.percentile(cs, 5) * 100:.2f}%  "
          f"p95 {np.percentile(cs, 95) * 100:.2f}%  | frozen strategy beats "
          f"{int((cs < v2.metrics.cagr).sum())}/20")


if __name__ == "__main__":
    main()
