"""macd_strategy (MACD line vs signal line) on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31   (all tuning / selection)
  TEST  2024-01-01 -> 2026-10-01   (touched exactly once, at the end)

DECLARED PARAMETER BUDGET (5 variants of (fast, slow, signal); rebalance fixed at
monthly because that is what the engine's evidence note supports -- not part of the
budget):

  V1  12/26/9    catalog default (MacdConfig)
  V2  12/26/5    signal axis alone, snappier confirmation
  V3   5/20/9    fast swing pair
  V4  20/50/9    slower swing pair
  V5  10/100/9   near-regime filter

Signal, transcribed from `MacdStrategy.signal`:
    line = ema(closes, fast) - ema(closes, slow)
    sig  = mean(line[-signal:])            # NOTE: simple mean, not an EMA signal line
    NaN on either side, or exact tie -> 0
    line > sig -> +1 else -1

The book is LONG-ONLY (no shorts in an Indian delivery account, GOAL.md 3.1), so only
the +1 branch is holdable and the -1 names are excluded, not shorted. The
cross-sectional score is 126d trailing momentum ranked only among names flagged long
that day (brief 5).

The vectorised transcription is verified bar-by-bar against the literal catalog call --
max absolute difference 0.0 for all five variants (see `_verify`).
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_macd")

import macd_lib as M  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")


def infra_hash() -> dict:
    """Hash the nsealgo modules this run depends on.

    NOT decoration. `src/nsealgo/backtest/engine.py` was rewritten by another agent
    *while this experiment was running*, and the rewrite changed every headline number
    materially (see REPORT.md section 10). Without a pin, none of these results are
    reproducible and "the same code" silently means something different tomorrow.
    """
    import hashlib
    import pathlib

    out = {}
    for m in ("backtest/engine.py", "backtest/metrics.py", "costs.py", "data/loader.py",
              "factors/core.py"):
        p = pathlib.Path("src/nsealgo") / m
        out[m] = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "MISSING"
    return out
MOM_DAYS = 126
REBALANCE = "M"

#: Declared budget. Exactly these five are tested.
VARIANTS: dict[str, tuple[int, int, int]] = {
    "V1_12_26_9": (12, 26, 9),
    "V2_12_26_5": (12, 26, 5),
    "V3_5_20_9": (5, 20, 9),
    "V4_20_50_9": (20, 50, 9),
    "V5_10_100_9": (10, 100, 9),
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)


def macd_score(panel: pd.DataFrame, fast: int, slow: int, sig: int) -> pd.DataFrame:
    """126d trailing momentum, cross-sectionally ranked among long-flagged names."""
    return M.score_from_signal(panel, M.signal_state(panel, fast, slow, sig), MOM_DAYS)


def random_score(panel: pd.DataFrame, long_frac: float, seed: int) -> pd.DataFrame:
    """Negative control: identical % of bars long, entries chosen by a coin flip."""
    rng = np.random.default_rng(seed)
    mask = rng.random(panel.shape) < long_frac
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(pd.DataFrame(mask, index=panel.index, columns=panel.columns)).rank(
        axis=1, pct=True
    )


def bh_literal(panel: pd.DataFrame, window: tuple[str, str]):
    """Buy-and-hold exactly as brief 4.5 specifies it.

    ``panel.pct_change().mean(axis=1)`` -- every name equal weight, no ranking, no
    rebalancing, so no turnover after entry. Cost charged once on the whole book at
    entry at the same all-in round-trip bps the engine uses (GOAL.md 6.4: costs may not
    be reduced to flatter a comparator either).
    """
    px = panel.loc[window[0] : window[1]]
    r = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(COST.all_in_round_trip_bps(100000)) / 10_000.0
    r.iloc[0] = r.iloc[0] - rate
    equity = (1.0 + r).cumprod()
    years = len(equity) / 244.0
    m = compute_metrics(r, equity, annual_turnover=rate, cost_drag_annual=rate / years)
    return m, equity


def mom_only_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Ablation: the same momentum book with the MACD gate removed.

    Ranking by 126d momentum and holding the top 22 is already a momentum portfolio, so
    the informative question for a MACD strategy is not 'does momentum work' but 'does
    the MACD gate add anything on top of momentum'. This is that control.
    """
    return (panel / panel.shift(MOM_DAYS) - 1.0).rank(axis=1, pct=True)


def run(panel, score, window, cfg=CFG, cost=COST, rebalance=REBALANCE):
    p = panel.loc[window[0] : window[1]]
    s = score.loc[p.index]
    return run_backtest(p, s, cost, cfg, rebalance=rebalance)


def row(label, res) -> dict:
    m = res.metrics
    return {
        "label": label,
        "cagr": round(m.cagr * 100, 2),
        "sharpe": round(m.sharpe, 2),
        "sortino": round(m.sortino, 2),
        "maxdd": round(m.max_drawdown * 100, 2),
        "calmar": round(m.calmar, 2),
        "vol": round(m.volatility * 100, 2),
        "turnover_x_y": round(m.annual_turnover, 2),
        "cost_drag_pct_y": round(m.cost_drag_annual * 100, 2),
        "avg_names": round(res.diag["avg_names"], 1),
        "trades_y": round(m.trades_per_year, 1),
        "total_ret_pct": round(m.total_return * 100, 1),
        "n_days": m.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(res.returns) > 0).mean()), 2),
    }


def live_frac(panel, params, window=None) -> float:
    st = M.signal_state(panel, *params)
    if window is not None:
        st = st.loc[window[0] : window[1]]
    return float((st > 0).to_numpy().mean())


def _hdr(title: str) -> None:
    print(f"\n=== {title} ===")
    print(
        f"{'variant':<12}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
        f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'Tr/y':>6}{'Live%':>7}"
    )


def _emit(r: dict, extra: str = "") -> None:
    print(
        f"{r['label']:<12}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
        f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}{r['cost_drag_pct_y']:>7.2f}"
        f"{r['avg_names']:>7.1f}{r['trades_y']:>6.1f}{extra}"
    )


def main() -> None:  # noqa: C901, PLR0915
    out: dict = {"declared_budget": len(VARIANTS), "variants_tested": 0}
    out["infra_hash"] = infra_hash()
    print("INFRA HASHES:", json.dumps(out["infra_hash"]))

    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(
        f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}  "
        f"n_symbols={len(symbols)}"
    )
    print(f"NaN cells in panel: {int(panel.isna().sum().sum())}")
    print(
        f"round_trip_bps={COST.round_trip_bps(100000)}  "
        f"all_in_round_trip_bps={COST.all_in_round_trip_bps(100000)}  "
        "(every result below is net of the all-in figure)"
    )
    print(
        f"TRAIN bars {panel.loc[TRAIN[0] : TRAIN[1]].shape[0]}  "
        f"TEST bars {panel.loc[TEST[0] : TEST[1]].shape[0]}"
    )

    # ---- sanity check 6: the vectorised signal IS the catalog signal ----
    ver = M.verify_against_catalog(
        panel, ["tcs", "reliance", "sbin"], list(VARIANTS.values())
    )
    print(f"\nvectorised-vs-catalog verification: {ver}")
    out["catalog_verification"] = ver
    assert all(v["max_abs_diff_on_defined_bars"] == 0.0 for v in ver.values()), ver
    assert all(v["invented_signal_bars"] == 0 for v in ver.values()), ver

    scores = {k: macd_score(panel, *v) for k, v in VARIANTS.items()}
    sigs = {k: M.signal_state(panel, *v) for k, v in VARIANTS.items()}

    # ---------------- TRAIN: selection only ---------------- #
    _hdr(f"TRAIN {TRAIN[0]} -> {TRAIN[1]} -- selection only")
    out["train"] = {}
    out["train_live_frac"] = {}
    for name in VARIANTS:
        res = run(panel, scores[name], TRAIN)
        r = row(name, res)
        lf = round(live_frac(panel, VARIANTS[name], TRAIN), 4)
        out["train"][name] = {"params": list(VARIANTS[name]), **r, "live_frac": lf}
        out["variants_tested"] += 1
        _emit(r, f"{lf * 100:>6.1f}%")

    bh_tr = run(panel, mom_only_score(panel), TRAIN)
    out["train_mom_only"] = row("MOM_ONLY", bh_tr)
    _emit(out["train_mom_only"])
    comp_tr = run(panel, build_composite_score(panel), TRAIN)
    out["train_composite"] = row("COMPOSITE", comp_tr)
    _emit(out["train_composite"])

    # ---- selection, TRAIN only, rule fixed in advance: max TRAIN Calmar ---- #
    best = max(VARIANTS, key=lambda k: out["train"][k]["calmar"])
    bf, bs, bsg = VARIANTS[best]
    out["selected"] = best
    out["selected_params"] = [bf, bs, bsg]
    print(f"\nSELECTED on TRAIN (max Calmar): {best} (fast={bf}, slow={bs}, signal={bsg})")

    sel_lf = round(live_frac(panel, VARIANTS[best], TEST), 4)
    out["selected_live_frac_test"] = sel_lf
    print(f"selected variant, TEST long fraction: {sel_lf * 100:.1f}% of (name, bar) cells")

    # ======================= TEST: touched ONCE, from here ======================= #
    _hdr(f"TEST {TEST[0]} -> {TEST[1]} -- untouched until this point")
    out["test"] = {}
    for name in VARIANTS:
        res = run(panel, scores[name], TEST)
        r = row(name, res)
        r["is_selected"] = name == best
        lf = round(live_frac(panel, VARIANTS[name], TEST), 3)
        out["test"][name] = r
        _emit(r, f"{lf * 100:>6.1f}%{'  *' if name == best else ''}")

    sel_res = run(panel, scores[best], TEST)
    mom_res = run(panel, mom_only_score(panel), TEST)
    comp_res = run(panel, build_composite_score(panel), TEST)
    out["test_mom_only"] = row("MOM_ONLY", mom_res)
    out["test_composite"] = row("COMPOSITE", comp_res)
    _emit(out["test_mom_only"])
    _emit(out["test_composite"])

    bh_m, bh_eq = bh_literal(panel, TEST)
    out["test_bh_literal"] = {
        "label": "BH_LITERAL",
        "cagr": round(bh_m.cagr * 100, 2),
        "sharpe": round(bh_m.sharpe, 2),
        "maxdd": round(bh_m.max_drawdown * 100, 2),
        "calmar": round(bh_m.calmar, 2),
        "vol": round(bh_m.volatility * 100, 2),
        "total_ret_pct": round(bh_m.total_return * 100, 1),
        "n_days": bh_m.n_periods,
    }
    print(
        f"{'BH_LITERAL':<12}{bh_m.cagr * 100:>8.2f}{bh_m.sharpe:>8.2f}"
        f"{bh_m.max_drawdown * 100:>8.2f}{bh_m.calmar:>7.2f}"
        f"{'--':>6}{'--':>7}{'48.0':>7}{'0.0':>6}"
    )

    # ---- random-signal control, 20 seeds, same % of bars long ---- #
    rr = []
    for s in range(20):
        m = run(panel, random_score(panel, sel_lf, s), TEST).metrics
        rr.append(
            {
                "cagr": round(m.cagr * 100, 2),
                "sharpe": round(m.sharpe, 2),
                "maxdd": round(m.max_drawdown * 100, 2),
            }
        )
    out["test_random"] = rr
    sel_cagr = out["test"][best]["cagr"]
    sel_sh = out["test"][best]["sharpe"]
    wins_c = sum(1 for x in rr if sel_cagr > x["cagr"])
    wins_s = sum(1 for x in rr if sel_sh > x["sharpe"])
    out["random_beaten_cagr"] = f"{wins_c}/20"
    out["random_beaten_sharpe"] = f"{wins_s}/20"
    print(
        f"\nrandom control (20 seeds, TEST): CAGR median "
        f"{np.median([x['cagr'] for x in rr]):.2f}%  range "
        f"[{min(x['cagr'] for x in rr):.2f}, {max(x['cagr'] for x in rr):.2f}]"
    )
    print(f"  MACD beat {wins_c}/20 on CAGR and {wins_s}/20 on Sharpe")

    # ---- cost stress, selected variant only ---- #
    from decimal import Decimal as Dc

    stress = {
        k: round(run(panel, scores[best], TEST, cost=cm).metrics.cagr * 100, 2)
        for k, cm in (
            ("zero_cost", CostModel(segment="delivery", slippage_bps=Dc("0"))),
            ("double_slippage", CostModel(segment="delivery", slippage_bps=Dc("10"))),
            ("triple_slippage", CostModel(segment="delivery", slippage_bps=Dc("15"))),
        )
    }
    stress["base_21.92bps"] = sel_cagr
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (TEST CAGR%): {stress}")

    # ---- rebalance-frequency robustness: NOT a parameter choice, a Gate 4 stress ---- #
    freq = {
        rb: round(run(panel, scores[best], TEST, rebalance=rb).metrics.cagr * 100, 2)
        for rb in ("M", "Q", "W")
    }
    out["test_rebalance_freq_cagr"] = freq
    print(f"rebalance-frequency stress (TEST CAGR%): {freq}")

    # ---- calendar years ---- #
    print("\n--- TEST calendar years (%, selected variant) ---")
    yr_sel = (yearly_returns(sel_res.returns) * 100).round(2)
    yr_mom = (yearly_returns(mom_res.returns) * 100).round(2)
    yr_cmp = (yearly_returns(comp_res.returns) * 100).round(2)
    yr_bh = (yearly_returns(bh_eq.pipe(lambda e: e / e.iloc[0] - 1.0)) * 100).round(2)
    print(pd.DataFrame({"macd": yr_sel, "mom_only": yr_mom, "composite": yr_cmp}).to_string())
    out["test_yearly"] = {
        "macd": {str(k): float(v) for k, v in yr_sel.items()},
        "mom_only": {str(k): float(v) for k, v in yr_mom.items()},
        "composite": {str(k): float(v) for k, v in yr_cmp.items()},
        "bh_literal": {str(k): float(v) for k, v in yr_bh.items()},
    }

    # ---- equity sanity: normalised, must end near (1+cagr)**years ---- #
    eqn = sel_res.equity
    implied = eqn.iloc[-1] ** (244 / len(eqn)) - 1
    out["equity_final"] = round(float(eqn.iloc[-1]), 4)
    out["equity_implied_cagr"] = round(float(implied) * 100, 2)
    out["equity_reported_cagr"] = sel_cagr
    out["max_names_ever"] = int((sel_res.weights > 0).sum(axis=1).max())
    out["min_names_ever"] = int((sel_res.weights > 0).sum(axis=1).min())
    out["max_single_weight"] = round(float(sel_res.weights.max().max()), 4)
    out["max_sector_weight"] = round(
        float(
            pd.DataFrame(
                {
                    s: [
                        sel_res.weights.loc[d][
                            [c for c in sel_res.weights.columns if _sector(c) == s]
                        ].sum()
                        for d in sel_res.weights.index
                    ]
                    for s in {_sector(c) for c in sel_res.weights.columns}
                }
            ).max().max()
        ),
        4,
    )
    print(
        f"\nequity check: final {eqn.iloc[-1]:.4f} -> implied CAGR {implied * 100:.2f}% "
        f"vs reported {sel_cagr:.2f}%"
    )
    print(
        f"names over TEST: min {out['min_names_ever']} max {out['max_names_ever']} | "
        f"max single weight {out['max_single_weight'] * 100:.2f}% (cap 12%) | "
        f"max sector {out['max_sector_weight'] * 100:.2f}% (cap 25%)"
    )

    # ---- signal chop: how often does the state flip? (the cost driver) ---- #
    flips = {
        k: round(
            float((sig.loc[TEST[0] : TEST[1], :].diff().abs() > 0).to_numpy().mean()), 4
        )
        for k, sig in sigs.items()
    }
    out["test_state_flip_rate"] = flips
    print(f"\nTEST signal state-flip rate per (name, bar): {flips}")

    with open("research/agent_macd/results.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote research/agent_macd/results.json")


def _sector(c: str) -> str:
    from nsealgo.backtest.engine import sector_of

    return sector_of(c)


if __name__ == "__main__":
    main()
