"""TEST evaluation — touched EXACTLY ONCE, with the TRAIN-selected variant V4.

Includes, over the identical TEST window:
  * the selected strategy (V4, period=126, thr=0.00) — unchanged from TRAIN
  * the catalog default (V1) for reference (not re-selected, just reported)
  * buy-and-hold benchmark (the brief's definition)
  * the nsealgo composite benchmark
  * a random-signal negative control with the same % of bars long
  * a static-beta book control

No parameter is chosen here. V4 is fixed from TRAIN.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "agent_timeseries"))

from harness import (  # noqa: E402
    ENGINE_SHA,
    TEST_END,
    TEST_START,
    buy_and_hold,
    fmt_row,
    load_panel,
    metrics_of,
    roc_panel,
    run_window,
    score_from_signal,
    yearly_table,
)

from nsealgo.factors.core import build_composite_score  # noqa: E402

SELECTED_PERIOD = 126
SELECTED_THRESHOLD = 0.00
DEFAULT_PERIOD = 40


def random_score_like(panel: pd.DataFrame, period: int, threshold: float, seed: int):
    """Random signal with the SAME per-bar long fraction as the real strategy.

    Each (day, name) that the real strategy flags long is kept with probability
    equal to the strategy's overall flag rate, drawn i.i.d. from a fixed seed.
    Then rank the survivors randomly. This is the coin-flip bar: a real edge must
    beat this, not just beat nothing.
    """
    real = roc_panel(panel, period) > threshold
    valid = panel.notna() & panel.shift(period).notna()
    flagged = real & valid
    rate = float(flagged.sum().sum() / valid.sum().sum())
    rng = np.random.default_rng(seed)
    draw = rng.random(real.shape)
    sel = flagged & (draw < rate)
    score = pd.DataFrame(np.where(sel, rng.random(real.shape), np.nan),
                         index=panel.index, columns=panel.columns)
    return score, rate


def static_beta_score(panel: pd.DataFrame) -> pd.DataFrame:
    """A constant-beta book: every name eligible, ranked by a fixed jitter.

    Same engine, same caps, same costs, no directional view. If the strategy
    cannot beat this, the alpha claim fails regardless of buy-and-hold.
    """
    rng = np.random.default_rng(7)
    n = panel.shape[1]
    jitter = rng.random((1, n))
    return pd.DataFrame(np.tile(jitter, (len(panel), 1)),
                        index=panel.index, columns=panel.columns)


def main() -> None:
    panel, symbols = load_panel()
    print(f"ENGINE_SHA = {ENGINE_SHA}")
    print(f"TEST window {TEST_START.date()} -> {TEST_END.date()}")
    print(f"SELECTED (from TRAIN): period={SELECTED_PERIOD} "
          f"threshold={SELECTED_THRESHOLD}\n")

    out = {"engine_sha": ENGINE_SHA, "window": [str(TEST_START), str(TEST_END)]}

    # -- selected strategy (the headline)
    sc_sel = score_from_signal(panel, SELECTED_PERIOD, SELECTED_THRESHOLD)
    res_sel = run_window(panel, sc_sel, TEST_START, TEST_END)
    m_sel = metrics_of(res_sel)
    print(fmt_row("SELECTED V4 (p126)", m_sel))
    print("  yearly:", yearly_table(res_sel.returns))

    # -- catalog default, for reference only
    sc_def = score_from_signal(panel, DEFAULT_PERIOD, 0.0)
    res_def = run_window(panel, sc_def, TEST_START, TEST_END)
    m_def = metrics_of(res_def)
    print(fmt_row("catalog default V1 (p40)", m_def))

    # -- buy-and-hold
    bh = buy_and_hold(panel, TEST_START, TEST_END)
    print(fmt_row("BENCH buy-and-hold", bh))
    bh_daily = (panel.loc[TEST_START:TEST_END].pct_change(fill_method=None)
                .fillna(0.0).mean(axis=1))
    bh_daily.iloc[0] -= 0.002192
    print("  yearly:", yearly_table(bh_daily))

    # -- nsealgo composite
    comp = build_composite_score(panel)
    res_comp = run_window(panel, comp, TEST_START, TEST_END)
    m_comp = metrics_of(res_comp)
    print(fmt_row("BENCH nsealgo composite", m_comp))

    # -- static beta control
    res_beta = run_window(panel, static_beta_score(panel), TEST_START, TEST_END)
    m_beta = metrics_of(res_beta)
    print(fmt_row("CONTROL static-beta book", m_beta))

    # -- random signal control (seed 42; also run a few seeds for spread)
    rnd_rows = []
    for seed in (42, 43, 44, 45, 46):
        rsc, rate = random_score_like(panel, SELECTED_PERIOD,
                                      SELECTED_THRESHOLD, seed)
        rr = run_window(panel, rsc, TEST_START, TEST_END)
        mr = metrics_of(rr)
        rnd_rows.append({"seed": seed, "flag_rate": rate, **mr})
    print(f"\nRANDOM control ({len(rnd_rows)} seeds, same ~{rnd_rows[0]['flag_rate']*100:.0f}% long):")
    for r in rnd_rows:
        print(fmt_row(f"  random seed={r['seed']}", r))
    r_cagr = [r["cagr"] for r in rnd_rows]
    r_sharpe = [r["sharpe"] for r in rnd_rows]
    rnd_summary = {
        "cagr_mean": float(np.mean(r_cagr)), "cagr_std": float(np.std(r_cagr)),
        "sharpe_mean": float(np.mean(r_sharpe)),
        "sharpe_max": float(np.max(r_sharpe)),
    }
    print(f"  random mean CAGR {rnd_summary['cagr_mean']*100:.2f}% "
          f"(sd {rnd_summary['cagr_std']*100:.2f}%), "
          f"mean Sharpe {rnd_summary['sharpe_mean']:.2f}")

    out.update({
        "selected": m_sel, "default": m_def, "buy_hold": bh,
        "composite": m_comp, "static_beta": m_beta,
        "random_runs": rnd_rows, "random_summary": rnd_summary,
    })
    (ROOT / "research" / "agent_timeseries" / "test_results.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    print("\nwrote test_results.json")


if __name__ == "__main__":
    main()
