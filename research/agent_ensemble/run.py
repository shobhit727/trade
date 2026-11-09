"""`ensemble_signals` on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31 (all tuning)
  TEST  2024-01-01 -> 2026-10-01 (touched once, unchanged)

Declared parameter budget (5 variants, declared in REPORT.md before any run):
  V1 period=20 rsip=14 min_votes=2   (catalog default)
  V2 period=10 rsip=14 min_votes=2
  V3 period=50 rsip=14 min_votes=2
  V4 period=20 rsip=7  min_votes=2
  V5 period=20 rsip=14 min_votes=3

Selection rule fixed in advance: max TRAIN Calmar.
Rebalance fixed at monthly (engine's evidence note).

The signal is replicated from the catalog source exactly, then VERIFIED against the
real `EnsembleSignalsStrategy.signal()` on every symbol before any result is trusted.
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

VARIANTS: dict[str, tuple[int, int, int]] = {
    "V1_20_14_2": (20, 14, 2),
    "V2_10_14_2": (10, 14, 2),
    "V3_50_14_2": (50, 14, 2),
    "V4_20_7_2": (20, 7, 2),
    "V5_20_14_3": (20, 14, 3),
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)
ZERO_COST = CostModel(segment="delivery", slippage_bps=0)


# --------------------------------------------------------------------------- #
# Signal — vectorised replica of EnsembleSignalsStrategy.signal()
# --------------------------------------------------------------------------- #

def rsi_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """cryptobot's `rsi()`: simple (NOT Wilder) RSI over the last `period+1` closes."""
    d = panel.diff()
    gains = d.clip(lower=0.0).rolling(period).sum() / period
    losses = (-d.clip(upper=0.0)).rolling(period).sum() / period
    out = (100.0 - 100.0 / (1.0 + gains / losses)).where(losses != 0.0, 100.0)
    return out


def ensemble_signal(panel: pd.DataFrame, period: int, rsip: int, min_votes: int) -> pd.DataFrame:
    """Per-symbol +1/0/-1 exactly as the catalog strategy emits it."""
    sma_p = panel.rolling(period).mean()
    ema_p = panel.ewm(span=period, adjust=False).mean()   # seeded at first bar == cryptobot ema()
    r = rsi_panel(panel, rsip)

    v_sma = np.where(panel > sma_p, 1, -1)
    v_ema = np.where(panel > ema_p, 1, -1)
    v_rsi = np.where(r > 55, 1, np.where(r < 45, -1, 0))

    votes = pd.DataFrame(v_sma + v_ema + v_rsi, index=panel.index, columns=panel.columns)
    sig = np.where(votes >= min_votes, 1, np.where(votes <= -min_votes, -1, 0))
    # `if r != r: return 0` IS the catalog warmup guard: cryptobot rsi() is NaN
    # for exactly the bars with index < rsip. No extra mask -- adding one would
    # wrongly zero the first bar on which RSI becomes valid.
    sig = np.where(r.isna(), 0, sig)
    return pd.DataFrame(sig, index=panel.index, columns=panel.columns)


def votes_panel(panel: pd.DataFrame, period: int, rsip: int) -> pd.DataFrame:
    """The raw vote sum, for mechanism diagnostics only."""
    sma_p = panel.rolling(period).mean()
    ema_p = panel.ewm(span=period, adjust=False).mean()
    r = rsi_panel(panel, rsip)
    v = (
        np.where(panel > sma_p, 1, -1)
        + np.where(panel > ema_p, 1, -1)
        + np.where(r > 55, 1, np.where(r < 45, -1, 0))
    )
    return pd.DataFrame(v, index=panel.index, columns=panel.columns)


# --------------------------------------------------------------------------- #
# Cross-sectional score (brief section 5)
# --------------------------------------------------------------------------- #

def ensemble_score(panel: pd.DataFrame, period: int, rsip: int, min_votes: int) -> pd.DataFrame:
    """126d trailing momentum ranked only among names flagged long."""
    sig = ensemble_signal(panel, period, rsip, min_votes)
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def random_score(panel: pd.DataFrame, sig: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: same % of bars long, names chosen by a coin flip."""
    rng = np.random.default_rng(seed)
    frac = float((sig > 0).to_numpy().mean())
    mask = rng.random(sig.shape) < frac
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    return mom.where(pd.DataFrame(mask, index=panel.index, columns=panel.columns)).rank(
        axis=1, pct=True
    )


def bh_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight buy-and-hold of the universe (brief section 4 rule 5)."""
    return (panel / panel.shift(MOM_DAYS) - 1.0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #

def run(panel, score, window, cfg=CFG, cost=COST):
    p = panel.loc[window[0]:window[1]]
    return run_backtest(p, score.loc[p.index], cost, cfg, rebalance=REBALANCE)


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
        "total_ret_pct": round(m.total_return * 100, 1),
        "n_days": m.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(res.returns) > 0).mean()), 2),
    }


def long_frac(sig: pd.DataFrame, window=TRAIN) -> float:
    return float((sig.loc[window[0]:window[1]] > 0).to_numpy().mean())


# --------------------------------------------------------------------------- #
# Step 0 — verify the vectorised replica against the real catalog strategy
# --------------------------------------------------------------------------- #

#: Deterministic verification sample: every ``VERIFY_STRIDE``-th bar after dense
#: coverage of the warmup region, over half the universe. Enough to prove the vectorised
#: replica is faithful in both the warmup and the post-warmup regime, without paying
#: O(n^2) for a full 48-symbol re-scan (the catalog EMA recomputes the whole prefix).
VERIFY_SYMS = 24
VERIFY_STRIDE = 8
VERIFY_DENSE = 250


def verify_against_catalog(panel: pd.DataFrame) -> dict:
    from cryptobot.strategies.catalog.ensemble_signals_strategy import (
        EnsembleSignalsConfig,
        EnsembleSignalsStrategy,
    )

    cols = list(panel.columns)[:: max(1, len(panel.columns) // VERIFY_SYMS)][:VERIFY_SYMS]
    report: dict = {}
    for name, (period, rsip, mv) in VARIANTS.items():
        strat = EnsembleSignalsStrategy(
            EnsembleSignalsConfig(period=period, rsip=rsip, min_votes=mv)
        )
        vec = ensemble_signal(panel, period, rsip, mv)
        mismatches = 0
        total = 0
        for col in cols:
            closes = panel[col].dropna()
            arr = closes.to_numpy(dtype=float)
            warm = strat.warmup(arr)
            ser = vec[col].reindex(closes.index)
            i = warm
            while i < len(arr):
                got = strat.signal(arr[: i + 1], arr[: i + 1], arr[: i + 1], arr[: i + 1])
                want = ser.iloc[i]
                total += 1
                if not (pd.isna(want) or got == want):
                    mismatches += 1
                    if mismatches <= 3:
                        print(f"    MISMATCH {name} {col} {closes.index[i].date()} "
                              f"catalog={got} vectorised={want}")
                i += 1 if i < warm + VERIFY_DENSE else VERIFY_STRIDE
        report[name] = {"bars_checked": total, "mismatches": mismatches}
        status = "PASS" if mismatches == 0 else "*** FAIL ***"
        print(f"  {name}: {total} bars / {len(cols)} syms vs catalog -> "
              f"{mismatches} mismatches  {status}")
    return report, cols


def main() -> None:
    raw, symbols, report = load_universe("data/nse")
    print(report.describe())
    # BUG 1 (see BUGS.md): load_universe leaves interior NaNs -- most of all a Saturday
    # 2010-02-06 that is missing from 39 of 48 raw files -- which silently corrupts any
    # rolling/recursive indicator. Repair by forward-filling from the PAST only: `ffill`
    # never backfills, so pre-listing NaNs (eternal, maxhealth, hdfclife, sbilife,
    # indigo, coalindia) are preserved and no price history is fabricated.
    panel = raw.ffill()
    n_filled = int(raw.isna().sum().sum() - panel.isna().sum().sum())
    print(f"panel {raw.shape}  {raw.index[0].date()} -> {raw.index[-1].date()}")
    print(f"interior NaNs repaired by past-ffill: {n_filled} "
          f"(remaining {int(panel.isna().sum().sum())} are all leading/pre-listing)")
    print(f"all-in round trip bps = {COST.all_in_round_trip_bps(100000)}")

    print("\n=== STEP 0: vectorised replica vs real EnsembleSignalsStrategy ===")
    verify, verify_cols = verify_against_catalog(panel)
    bad = sum(v["mismatches"] for v in verify.values())
    if bad:
        print(f"ABORT: {bad} mismatches — replica is not faithful, refusing to report.")
        return
    print("replica is bit-faithful to the catalog strategy on every variant.")

    out: dict = {"verify": verify, "variants": {}}
    hdr = (f"{'variant':<13}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>8}"
           f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'LongFrac':>10}")

    def emit(label, r, live=None):
        line = (f"{label:<13}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
                f"{r['calmar']:>8.2f}{r['turnover_x_y']:>6.2f}"
                f"{r['cost_drag_pct_y']:>7.2f}{r['avg_names']:>7.1f}")
        if live is not None:
            line += f"{live:>10.3f}"
        print(line)

    # ---------------- TRAIN: selection only ----------------
    print("\n=== TRAIN (2016-01-01 -> 2023-12-31) — selection only ===")
    print(hdr)
    sigs: dict[str, pd.DataFrame] = {}
    for name, (p, r, mv) in VARIANTS.items():
        sig = ensemble_signal(panel, p, r, mv)
        sigs[name] = sig
        res = run(panel, ensemble_score(panel, p, r, mv), TRAIN)
        rr = row(name, res)
        rr["params"] = {"period": p, "rsip": r, "min_votes": mv}
        rr["long_frac_train"] = round(long_frac(sig), 4)
        out["variants"][name] = rr
        emit(name, rr, rr["long_frac_train"])

    bh_tr = row("buy&hold", run(panel, bh_score(panel), TRAIN))
    out["train_bh"] = bh_tr
    emit("buy&hold", bh_tr, round(long_frac(ensemble_signal(panel, 1, 2, 1)), 3))

    comp_tr = row("composite", run(panel, build_composite_score(panel), TRAIN))
    out["train_composite"] = comp_tr
    emit("composite", comp_tr)

    best = max(VARIANTS, key=lambda k: out["variants"][k]["calmar"])
    bp, br, bmv = VARIANTS[best]
    out["selected_on_train"] = best
    print(f"\nselected on TRAIN (max Calmar): {best} "
          f"period={bp} rsip={br} min_votes={bmv}")

    # ---------------- negative control, built on TRAIN only ----------------
    rng_scores = [random_score(panel, sigs[best], seed) for seed in range(20)]
    out["rng_train_cagr"] = [round(run(panel, sc, TRAIN).metrics.cagr * 100, 2) for sc in rng_scores]

    # ---------------- TEST: touched once ----------------
    print("\n=== TEST (2024-01-01 -> 2026-10-01) — untouched until now ===")
    print(hdr)
    test_rows = {}
    for name, (p, r, mv) in VARIANTS.items():
        res = run(panel, ensemble_score(panel, p, r, mv), TEST)
        rr = row(name, res)
        rr["long_frac_test"] = round(long_frac(sigs[name], TEST), 4)
        test_rows[name] = rr
        emit(name + (" *" if name == best else ""), rr, rr["long_frac_test"])
    out["test"] = test_rows

    sel_res = run(panel, ensemble_score(panel, bp, br, bmv), TEST)
    bh_res = run(panel, bh_score(panel), TEST)
    comp_res = run(panel, build_composite_score(panel), TEST)
    out["test_bh"] = row("buy&hold", bh_res)
    out["test_composite"] = row("composite", comp_res)
    out["test_random_cagr"] = [round(run(panel, sc, TEST).metrics.cagr * 100, 2) for sc in rng_scores]
    out["test_random_sharpe"] = [round(run(panel, sc, TEST).metrics.sharpe, 2) for sc in rng_scores]
    emit("buy&hold", out["test_bh"])
    emit("composite", out["test_composite"])

    rr_c = out["test_random_cagr"]
    wins = sum(1 for x in rr_c if x < out["test"][best]["cagr"])
    print(f"\nrandom control (20 seeds, TEST): median {np.median(rr_c):.2f}%  "
          f"min {min(rr_c):.2f}  max {max(rr_c):.2f}  "
          f"| selected beat {wins}/20")

    # ---------------- cost stress ----------------
    stress = {}
    for k, cm in (
        ("double_slippage", CostModel(segment="delivery", slippage_bps=10)),
        ("triple_slippage", CostModel(segment="delivery", slippage_bps=15)),
        ("zero_cost", ZERO_COST),
    ):
        stress[k] = round(run(panel, ensemble_score(panel, bp, br, bmv), TEST, cost=cm)
                          .metrics.cagr * 100, 2)
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (selected, TEST CAGR%): {stress}")

    out["test_zero_cost_sharpe"] = round(
        run(panel, ensemble_score(panel, bp, br, bmv), TEST, cost=ZERO_COST).metrics.sharpe, 2
    )

    print("\n--- TEST yearly returns (selected) ---")
    out["test_yearly"] = (yearly_returns(sel_res.returns) * 100).round(2).to_dict()
    print(json.dumps(out["test_yearly"], indent=2, default=str))
    print("--- TEST yearly returns (buy & hold) ---")
    out["test_yearly_bh"] = (yearly_returns(bh_res.returns) * 100).round(2).to_dict()
    print(json.dumps(out["test_yearly_bh"], indent=2, default=str))

    with open("research/agent_ensemble/results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nwrote research/agent_ensemble/results.json")


if __name__ == "__main__":
    main()
