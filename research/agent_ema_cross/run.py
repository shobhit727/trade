"""ema_cross_strategy (EMA fast>slow) on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31   (all tuning / selection)
  TEST  2024-01-01 -> 2026-10-01   (touched exactly once, at the end)

DECLARED PARAMETER BUDGET (5 variants, (fast, slow) EMA spans; rebalance fixed at
monthly because that is what the engine's evidence note supports -- not part of the
budget):

  V1  12/26   catalog default (EmaCrossConfig)
  V2   5/20   fast / tight
  V3  20/50   medium swing
  V4  10/100  slow filter
  V5  50/200  golden-cross, classic long-term pair

Signal, transcribed from `EmaCrossStrategy.signal`:
    f = ema(closes, fast); s = ema(closes, slow)
    NaN, or exact tie -> 0
    f > s -> +1 else -1
The book is LONG-ONLY (no shorts in an Indian delivery account, GOAL.md 3.1), so only
the +1 branch is holdable and the -1 names are excluded, not shorted. The cross-sectional
score is 126d trailing momentum ranked only among names flagged long that day (brief 5).

`cryptobot.strategies.indicators.ema()` is a recursive EMA seeded at the first bar, which
is exactly pandas `ewm(span=n, adjust=False).mean()`. Verified numerically to 0.0 max
absolute difference for spans 5/12/26/200 -- see `_verify_ema_equivalence`.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
MOM_DAYS = 126
REBALANCE = "M"

#: Declared budget. Exactly these five are tested.
VARIANTS: dict[str, tuple[int, int]] = {
    "V1_12_26": (12, 26),
    "V2_5_20": (5, 20),
    "V3_20_50": (20, 50),
    "V4_10_100": (10, 100),
    "V5_50_200": (50, 200),
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def ema_panel(panel: pd.DataFrame, span: int) -> pd.DataFrame:
    """Recursive EMA seeded at the first bar -- identical to cryptobot's `ema()`."""
    return panel.ewm(span=span, adjust=False).mean()


def ema_cross_signal(panel: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """+1 / -1 / 0 state panel, a vectorised transcription of `EmaCrossStrategy.signal`.

    Differences from a naive `f > s`, all in the direction of *withholding* a position:

    * ``0`` for the first ``slow`` bars. The catalog's `ema()` returns NaN while
      ``len(closes) < period``, so `signal` returns 0 until the slow EMA is defined.
    * ``0`` where either EMA is NaN or the two are exactly equal (the catalog's
      ``f == s`` guard).
    * ``0`` where the close itself is NaN. There is no price to trade that day, so the
      name is not holdable. This makes no difference to the book (the 126d momentum is
      also NaN there, so the score is NaN and `build_rebalance_weights` already excludes
      it); it only keeps the liveness diagnostic honest.
    """
    f = ema_panel(panel, fast)
    s = ema_panel(panel, slow)

    valid = f.notna() & s.notna() & (f != s) & panel.notna()
    sig = pd.DataFrame(np.where(f > s, 1, -1), index=panel.index, columns=panel.columns)
    sig = sig.where(valid, 0)
    # warmup: the catalog emits 0 until `slow` bars have been seen
    warm = panel.index[max(fast, slow) - 1:]
    sig.loc[warm, :] = sig.loc[warm, :].where(
        f.loc[warm, :].notna() & s.loc[warm, :].notna(), 0
    )
    return sig.astype(int)


def ema_cross_score(panel: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """126d trailing momentum, cross-sectionally ranked among long-flagged names."""
    sig = ema_cross_signal(panel, fast, slow)
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def random_score(panel: pd.DataFrame, long_frac: float, seed: int) -> pd.DataFrame:
    """Negative control: identical % of bars long, entries chosen by a coin flip."""
    rng = np.random.default_rng(seed)
    mask = rng.random(panel.shape) < long_frac
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(
        pd.DataFrame(mask, index=panel.index, columns=panel.columns)
    ).rank(axis=1, pct=True)


def bh_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Secondary comparator: the 22-name, inverse-vol, *momentum-ranked* book.

    NOTE this is NOT the brief's buy-and-hold. Ranking by 126d momentum and holding the
    top 22 is already a momentum portfolio, so this is really "the book with the EMA gate
    removed" -- a useful ablation, but calling it 'buy and hold' conflates the very thing
    under test with the benchmark. `bh_literal` below is the brief's actual benchmark.
    """
    return (panel / panel.shift(MOM_DAYS) - 1.0).rank(axis=1, pct=True)


def bh_literal(panel: pd.DataFrame, window: tuple[str, str]):
    """Buy-and-hold exactly as brief 4.5 specifies it.

    ``panel.pct_change().mean(axis=1)`` -- every name held with equal weight, no ranking,
    no rebalancing, so there is no turnover after the initial purchase. Costs are charged
    once, on the full book at entry, at the same all-in round-trip bps the engine uses
    (GOAL.md 6.4: costs may not be reduced to flatter a comparator either).
    """
    from nsealgo.backtest.metrics import compute_metrics

    px = panel.loc[window[0]:window[1]]
    rets = px.pct_change(fill_method=None).fillna(0.0)
    r = rets.mean(axis=1)

    # One-off entry cost on the whole book, charged on the first bar like the engine
    # charges its first rebalance.
    rate = float(COST.all_in_round_trip_bps(100000)) / 10_000.0
    r.iloc[0] = r.iloc[0] - rate

    equity = (1.0 + r).cumprod()
    years = len(equity) / 244.0
    m = compute_metrics(r, equity, annual_turnover=rate, cost_drag_annual=rate / years)
    return m, equity


# --------------------------------------------------------------------------- #
# Plumbing
# --------------------------------------------------------------------------- #


def run(panel, score, window, cfg=CFG, cost=COST, rebalance=REBALANCE):
    p = panel.loc[window[0]:window[1]]
    s = score.loc[p.index]
    return run_backtest(p, s, cost, cfg, rebalance=rebalance)


def row(label, res) -> dict:
    m = res.metrics
    return {
        "label": label,
        "cagr": round(m.cagr * 100, 2),
        "sharpe": round(m.sharpe, 2),
        "maxdd": round(m.max_drawdown * 100, 2),
        "calmar": round(m.calmar, 2),
        "turnover_x_y": round(m.annual_turnover, 2),
        "cost_drag_pct_y": round(m.cost_drag_annual * 100, 2),
        "avg_names": round(res.diag["avg_names"], 1),
        "trades_y": round(m.trades_per_year, 1),
        "total_ret_pct": round(m.total_return * 100, 1),
        "n_days": m.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(res.returns) > 0).mean()), 2),
    }


def long_frac(panel, fast, slow, window=None) -> float:
    sig = ema_cross_signal(panel, fast, slow)
    if window is not None:
        sig = sig.loc[window[0]:window[1]]
    return float((sig > 0).to_numpy().mean())


def _verify_ema_equivalence() -> dict:
    """Numerically prove pandas ewm == cryptobot's recursive `ema()`. No assertion taken
    on faith -- this is sanity check 6 in the report."""
    from cryptobot.strategies.indicators import _ema_series, ema

    rng = np.random.default_rng(0)
    px = np.cumprod(rng.normal(1.0, 0.02, 600)) * 100.0
    out = {}
    for span in (5, 12, 26, 200):
        mine = _ema_series(px, span)
        theirs = pd.Series(px).ewm(span=span, adjust=False).mean().to_numpy()
        out[f"span_{span}"] = float(np.max(np.abs(mine - theirs)))
    out["streaming_last_bar_span_12"] = float(
        abs(ema(list(px), 12) - _ema_series(px, 12)[-1])
    )
    return out


def _hdr(title: str) -> None:
    print(f"\n=== {title} ===")
    print(
        f"{'variant':<12}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
        f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'Tr/y':>6}"
    )


def _emit(r: dict, extra: str = "") -> None:
    print(
        f"{r['label']:<12}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
        f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}{r['cost_drag_pct_y']:>7.2f}"
        f"{r['avg_names']:>7.1f}{r['trades_y']:>6.1f}{extra}"
    )


def main() -> None:  # noqa: C901, PLR0915
    out: dict = {"declared_budget": len(VARIANTS), "variants_tested": 0}

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
        "(results below are net of the all-in figure)"
    )
    print(f"TRAIN bars {panel.loc[TRAIN[0]:TRAIN[1]].shape[0]}  "
          f"TEST bars {panel.loc[TEST[0]:TEST[1]].shape[0]}")

    eq = _verify_ema_equivalence()
    print(f"\nEMA equivalence vs cryptobot.strategies.indicators: {eq}")
    out["ema_equivalence_max_abs_diff"] = eq

    scores = {k: ema_cross_score(panel, f, s) for k, (f, s) in VARIANTS.items()}
    sigs = {k: ema_cross_signal(panel, f, s) for k, (f, s) in VARIANTS.items()}

    # ---------------- TRAIN: selection only ---------------- #
    _hdr(f"TRAIN {TRAIN[0]} -> {TRAIN[1]} -- selection only")
    out["train"] = {}
    out["live_frac_full_sample"] = {}
    for name in VARIANTS:
        res = run(panel, scores[name], TRAIN)
        r = row(name, res)
        out["train"][name] = {"fast": VARIANTS[name][0], "slow": VARIANTS[name][1], **r}
        out["variants_tested"] += 1
        lf = round(long_frac(panel, *VARIANTS[name]), 4)
        out["live_frac_full_sample"][name] = lf
        _emit(r, f"{lf * 100:>7.1f}%")

    bh_tr = run(panel, bh_score(panel), TRAIN)
    out["train_bh"] = row("BH", bh_tr)
    _emit(out["train_bh"])

    comp_tr = run(panel, build_composite_score(panel), TRAIN)
    out["train_composite"] = row("COMPOSITE", comp_tr)
    _emit(out["train_composite"])

    # ---- selection, TRAIN only, rule fixed in advance: max TRAIN Calmar ---- #
    best = max(VARIANTS, key=lambda k: out["train"][k]["calmar"])
    bf, bs = VARIANTS[best]
    out["selected"] = best
    out["selected_fast_slow"] = [bf, bs]
    print(f"\nSELECTED on TRAIN (max Calmar): {best} (fast={bf}, slow={bs})")

    # ---- negative controls built once, evaluated on TEST after selection ---- #
    sel_lf = round(long_frac(panel, bf, bs, window=TEST), 4)
    out["selected_long_frac_test"] = sel_lf
    print(f"selected variant, TEST long fraction: {sel_lf * 100:.1f}% of bars")

    # ======================= TEST: touched ONCE, from here ======================= #
    _hdr(f"TEST {TEST[0]} -> {TEST[1]} -- untouched until this point")
    out["test"] = {}
    for name in VARIANTS:
        res = run(panel, scores[name], TEST)
        r = row(name, res)
        r["is_selected"] = name == best
        out["test"][name] = r
        lf = round(long_frac(panel, *VARIANTS[name], window=TEST), 3)
        _emit(r, f"{lf * 100:>6.1f}%{' *' if name == best else ''}")

    sel_res = run(panel, scores[best], TEST)
    bh_res = run(panel, bh_score(panel), TEST)
    comp_res = run(panel, build_composite_score(panel), TEST)
    out["test_bh"] = row("BH", bh_res)
    out["test_composite"] = row("COMPOSITE", comp_res)
    _emit(out["test_bh"])
    _emit(out["test_composite"])

    # ---- random-signal control, 20 seeds, same % of bars long ---- #
    rng_scores = [random_score(panel, sel_lf, s) for s in range(20)]
    rr_cagr, rr_sharpe, rr_dd = [], [], []
    for sc in rng_scores:
        m = run(panel, sc, TEST).metrics
        rr_cagr.append(round(m.cagr * 100, 2))
        rr_sharpe.append(round(m.sharpe, 2))
        rr_dd.append(round(m.max_drawdown * 100, 2))
    out["test_random_cagr"] = rr_cagr
    out["test_random_sharpe"] = rr_sharpe
    out["test_random_maxdd"] = rr_dd
    sel_cagr = out["test"][best]["cagr"]
    wins = sum(1 for x in rr_cagr if sel_cagr > x)
    out["test_random_beaten_by_strategy"] = wins
    out["test_random_n"] = len(rr_cagr)
    print(
        f"\nrandom control (20 seeds, TEST): CAGR median {np.median(rr_cagr):.2f}%  "
        f"range [{min(rr_cagr):.2f}, {max(rr_cagr):.2f}]"
    )
    print(f"  selected EMA variant beat by {wins}/20 random signals "
          f"(strategy CAGR {sel_cagr:.2f}%)")

    # ---- cost stress, selected variant only ---- #
    from decimal import Decimal as Dc

    stress = {}
    for k, cm in (
        ("zero_cost", CostModel(segment="delivery", slippage_bps=Dc("0"))),
        ("double_slippage", CostModel(segment="delivery", slippage_bps=Dc("10"))),
        ("triple_slippage", CostModel(segment="delivery", slippage_bps=Dc("15"))),
    ):
        stress[k] = round(run(panel, scores[best], TEST, cost=cm).metrics.cagr * 100, 2)
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (TEST CAGR%): {stress}")

    # ---- rebalance-frequency robustness: NOT a parameter choice, a Gate 4 stress ---- #
    freq = {}
    for rb in ("M", "Q", "W"):
        freq[rb] = round(run(panel, scores[best], TEST, rebalance=rb).metrics.cagr * 100, 2)
    out["test_rebalance_freq_cagr"] = freq
    print(f"rebalance-frequency stress (TEST CAGR%): {freq}")

    # ---- calendar years ---- #
    print("\n--- TEST calendar years ---")
    yr_sel = (yearly_returns(sel_res.returns) * 100).round(2)
    yr_bh = (yearly_returns(bh_res.returns) * 100).round(2)
    yr_cmp = (yearly_returns(comp_res.returns) * 100).round(2)
    tbl = pd.DataFrame({"ema_cross": yr_sel, "buy_hold": yr_bh, "composite": yr_cmp})
    print(tbl.to_string())
    out["test_yearly"] = {
        "ema_cross": {str(k): float(v) for k, v in yr_sel.items()},
        "buy_hold": {str(k): float(v) for k, v in yr_bh.items()},
        "composite": {str(k): float(v) for k, v in yr_cmp.items()},
    }

    # ---- equity sanity: normalised, must end near (1+cagr)**years ---- #
    eqn = sel_res.equity
    implied = eqn.iloc[-1] ** (244 / len(eqn))
    out["equity_final"] = float(eqn.iloc[-1])
    out["equity_implied_cagr"] = round(float(implied - 1) * 100, 2)
    out["equity_reported_cagr"] = sel_cagr
    out["max_names_ever"] = int((sel_res.weights > 0).sum(axis=1).max())
    out["min_names_ever"] = int((sel_res.weights > 0).sum(axis=1).min())
    out["max_single_weight"] = round(float(sel_res.weights.max().max()), 4)
    print(
        f"\nequity check: final {eqn.iloc[-1]:.4f} -> implied CAGR "
        f"{float(implied - 1) * 100:.2f}% vs reported {sel_cagr:.2f}%"
    )
    print(
        f"name count over TEST: min {out['min_names_ever']} max {out['max_names_ever']} "
        f"| max single weight {out['max_single_weight'] * 100:.2f}% (cap 12%)"
    )

    # ---- signal turnover: how often does the state flip? (chop is the cost driver) ---- #
    flips = {
        k: round(
            float(
                (sig.loc[TEST[0]:TEST[1], :].diff().abs() > 0).to_numpy().mean()
            ),
            4,
        )
        for k, sig in sigs.items()
    }
    out["test_state_flip_rate"] = flips
    print(f"\nTEST signal state-flip rate per (name, bar): {flips}")

    with open("research/agent_ema_cross/results.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote research/agent_ema_cross/results.json")


if __name__ == "__main__":
    main()
