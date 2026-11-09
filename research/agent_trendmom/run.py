"""trend_momentum_strategy on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31 (all tuning / selection)
  TEST  2024-01-01 -> 2026-10-01 (touched once, after the variant is frozen)

Declared parameter budget (5 variants of TrendMomentumConfig; everything else fixed):

  V1  fast=10  slow=40   mom=15  thr=0.01   <- catalog default
  V2  fast=20  slow=100  mom=60  thr=0.01
  V3  fast=50  slow=200  mom=60  thr=0.01
  V4  fast=10  slow=40   mom=15  thr=0.05
  V5  fast=5   slow=20   mom=10  thr=0.01

Selection rule fixed in advance: max TRAIN Sharpe (tie-break TRAIN Calmar).

Signal (verbatim semantics of TrendMomentumStrategy.signal):
  f = SMA(fast), s = SMA(slow), m = ROC(mom)
  +1 if f > s and m >  thr
  -1 if f < s and m < -thr
   0 otherwise

Long-only book -> only +1 is holdable. Cross-sectional score per brief section 5:
  score = (panel/panel.shift(126) - 1).where(signal > 0).rank(axis=1, pct=True)
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from decimal import Decimal as Dc
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
MOM_DAYS = 126
REBALANCE = "M"


@dataclass(frozen=True)
class Variant:
    fast: int
    slow: int
    mom: int
    thr: float

    @property
    def label(self) -> str:
        return f"V_{self.fast}_{self.slow}_{self.mom}_{self.thr}"


VARIANTS: dict[str, Variant] = {
    "V1": Variant(10, 40, 15, 0.01),
    "V2": Variant(20, 100, 60, 0.01),
    "V3": Variant(50, 200, 60, 0.01),
    "V4": Variant(10, 40, 15, 0.05),
    "V5": Variant(5, 20, 10, 0.01),
}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)
REF_NOTIONAL = 100_000


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def sma_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Rolling SMA including bar t — matches cryptobot's `sma()` (mean of last N)."""
    return panel.rolling(period, min_periods=period).mean()


def roc_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """Trailing return over `period` bars — matches cryptobot's `roc()` exactly."""
    return panel / panel.shift(period) - 1.0


def trend_mom_signal(panel: pd.DataFrame, v: Variant) -> pd.DataFrame:
    """+1 / -1 / 0 panel, replicating TrendMomentumStrategy.signal semantics."""
    f = sma_panel(panel, v.fast)
    s = sma_panel(panel, v.slow)
    m = roc_panel(panel, v.mom)
    up = (f > s) & (m > v.thr)
    dn = (f < s) & (m < -v.thr)
    sig = pd.DataFrame(
        np.where(up, 1, np.where(dn, -1, 0)), index=panel.index, columns=panel.columns
    )
    sig[f.isna() | s.isna() | m.isna()] = 0  # warmup == 0, matching NaN -> 0
    return sig


def tm_score(panel: pd.DataFrame, v: Variant) -> pd.DataFrame:
    """126d trailing momentum ranked cross-sectionally, only among names flagged +1."""
    sig = trend_mom_signal(panel, v)
    mom = roc_panel(panel, MOM_DAYS)
    return mom.where(sig > 0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Controls / benchmarks
# --------------------------------------------------------------------------- #


def bh_topn_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Engine-comparable benchmark: same book, same constraints, no signal gate.

    Buy-and-hold the top 22 by 126d momentum. This is the apples-to-apples comparison
    for "did the trend+momentum gate add anything over plain momentum exposure".
    """
    return roc_panel(panel, MOM_DAYS).rank(axis=1, pct=True)


def random_score(panel: pd.DataFrame, sig: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: entries chosen by a coin flip with the same % of bars long."""
    rng = np.random.default_rng(seed)
    frac = float((sig > 0).to_numpy().mean())
    mask = rng.random(sig.shape) < frac
    mom = roc_panel(panel, MOM_DAYS)
    return mom.where(pd.DataFrame(mask, index=panel.index, columns=panel.columns)).rank(
        axis=1, pct=True
    )


def equal_weight_bh(panel: pd.DataFrame, cost: CostModel, window: tuple[str, str]):
    """Literal brief section 4 rule 5 benchmark: panel.pct_change().mean(axis=1).

    Equal weight across every name in the universe, held throughout, so the only
    tradable cost is the single round trip to build the position. Net of the same
    CostModel the strategy pays.
    """
    px = panel.loc[window[0]:window[1]]
    daily = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    rate = float(cost.all_in_round_trip_bps(Dc(REF_NOTIONAL))) / 10_000.0
    daily.iloc[0] = daily.iloc[0] - rate  # one round trip to go from cash to invested
    return compute_metrics(daily, (1.0 + daily).cumprod())


# --------------------------------------------------------------------------- #
# Plumbing
# --------------------------------------------------------------------------- #


def run(panel, score, window, cfg=CFG, cost=COST):
    p = panel.loc[window[0]:window[1]]
    s = score.loc[p.index]
    return run_backtest(p, s, cost, cfg, rebalance=REBALANCE)


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
        "avg_top_weight": round(res.diag["avg_top_weight"], 4),
        "trades_y": round(m.trades_per_year, 1),
        "total_ret_pct": round(m.total_return * 100, 1),
        "n_days": m.n_periods,
        "yearly_pos_frac": round(float((yearly_returns(res.returns) > 0).mean()), 2),
    }


def hdr() -> str:
    names = ("variant", "CAGR%", "Sharpe", "MaxDD%", "Calmar", "Turn", "Cost%", "Names")
    w = (14, 8, 8, 8, 7, 6, 7, 7)
    return (
        "".join(f"{n:>{x}}" for n, x in zip(names, w, strict=True))
        + f"{'Live%':>7}{'YrPos':>7}"
    )


def line(label, r, live=None, mark=""):
    s = (
        f"{label:<14}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
        f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}{r['cost_drag_pct_y']:>7.2f}"
        f"{r['avg_names']:>7.1f}"
    )
    if live is not None:
        s += f"{live * 100:>6.1f}%"
    s += f"{r['yearly_pos_frac']:>7.2f}{mark}"
    return s


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"n_symbols={len(symbols)}")
    rt = COST.all_in_round_trip_bps(REF_NOTIONAL)
    print(f"all-in round-trip bps on {REF_NOTIONAL:,} = {rt}  (statutory "
          f"{COST.round_trip_bps(REF_NOTIONAL)})")
    assert float(rt) == 21.92, f"unexpected cost model: {rt}"

    # ---- engine fingerprint --------------------------------------------------
    # `src/nsealgo/backtest/engine.py` was edited by another process *during* this
    # agent's session (mtime 2026-10-09 14:05:28): `apply_turnover_budget` was
    # rewritten to separate forced exits from budget-scaled adoptions. Numbers
    # produced before and after that edit are NOT comparable. Pin the exact engine
    # every number in this report was produced with.
    eng = Path("src/nsealgo/backtest/engine.py")
    fingerprint = hashlib.sha256(eng.read_bytes()).hexdigest()
    print(f"engine.py sha256 = {fingerprint}")

    out: dict = {
        "panel": {"shape": list(panel.shape),
                  "start": str(panel.index[0].date()), "end": str(panel.index[-1].date())},
        "cleaning": report.summary(),
        "cost_all_in_bps": float(rt),
        "engine_sha256": fingerprint,
        "variants": {k: vars(v) for k, v in VARIANTS.items()},
    }

    scores = {k: tm_score(panel, v) for k, v in VARIANTS.items()}
    sigs = {k: trend_mom_signal(panel, v) for k, v in VARIANTS.items()}

    # ---------------- TRAIN ---------------- #
    print("\n=== TRAIN 2016-01-01 -> 2023-12-31 (selection only) ===")
    print(hdr())
    out["train"] = {}
    for k in VARIANTS:
        res = run(panel, scores[k], TRAIN)
        r = row(k, res)
        out["train"][k] = r
        live = float((sigs[k].loc[TRAIN[0]:TRAIN[1]] > 0).to_numpy().mean())
        out["train"][k]["live_frac"] = round(live, 4)
        print(line(k, r, live))

    bh_tr = run(panel, bh_topn_score(panel), TRAIN)
    out["train_bh_topn"] = row("BH_top22", bh_tr)
    print(line("BH_top22", out["train_bh_topn"]))

    ew_tr = equal_weight_bh(panel, COST, TRAIN)
    out["train_ew_bh"] = {
        "cagr": round(ew_tr.cagr * 100, 2), "sharpe": round(ew_tr.sharpe, 2),
        "maxdd": round(ew_tr.max_drawdown * 100, 2), "calmar": round(ew_tr.calmar, 2),
    }
    print(f"{'EW_BH(all50)':<14}{ew_tr.cagr * 100:>8.2f}{ew_tr.sharpe:>8.2f}"
          f"{ew_tr.max_drawdown * 100:>8.2f}{ew_tr.calmar:>7.2f}")

    comp_tr = run(panel, build_composite_score(panel), TRAIN)
    out["train_composite"] = row("COMPOSITE", comp_tr)
    print(line("COMPOSITE", out["train_composite"]))

    best = max(VARIANTS, key=lambda k: out["train"][k]["sharpe"])
    bv = VARIANTS[best]
    out["selected"] = best
    out["selected_cfg"] = vars(bv)
    print(f"\nSELECTED on TRAIN (max Sharpe): {best} -> {bv}")

    # ---------------- negative control (built on TRAIN, evaluated later) -------- #
    rng_scores = [random_score(panel, sigs[best], seed) for seed in range(20)]
    out["random_train_cagr"] = [round(run(panel, s, TRAIN).metrics.cagr * 100, 2)
                                for s in rng_scores]

    # ---------------- TEST (touched once) ---------------- #
    print("\n=== TEST 2024-01-01 -> 2026-10-01 (untouched until now) ===")
    print(hdr())
    out["test"] = {}
    for k in VARIANTS:
        res = run(panel, scores[k], TEST)
        r = row(k, res)
        out["test"][k] = r
        live = float((sigs[k].loc[TEST[0]:TEST[1]] > 0).to_numpy().mean())
        r["live_frac"] = round(live, 4)
        print(line(k, r, live, " *" if k == best else ""))

    sel_res = run(panel, scores[best], TEST)
    bh_te = run(panel, bh_topn_score(panel), TEST)
    out["test_bh_topn"] = row("BH_top22", bh_te)
    print(line("BH_top22", out["test_bh_topn"]))

    ew_te = equal_weight_bh(panel, COST, TEST)
    out["test_ew_bh"] = {
        "cagr": round(ew_te.cagr * 100, 2), "sharpe": round(ew_te.sharpe, 2),
        "maxdd": round(ew_te.max_drawdown * 100, 2), "calmar": round(ew_te.calmar, 2),
    }
    print(f"{'EW_BH(all50)':<14}{ew_te.cagr * 100:>8.2f}{ew_te.sharpe:>8.2f}"
          f"{ew_te.max_drawdown * 100:>8.2f}{ew_te.calmar:>7.2f}")

    comp_te = run(panel, build_composite_score(panel), TEST)
    out["test_composite"] = row("COMPOSITE", comp_te)
    print(line("COMPOSITE", out["test_composite"]))

    rr = [round(run(panel, s, TEST).metrics.cagr * 100, 2) for s in rng_scores]
    rs = [round(run(panel, s, TEST).metrics.sharpe, 2) for s in rng_scores]
    out["test_random_cagr"] = rr
    out["test_random_sharpe"] = rs

    sel_cagr = out["test"][best]["cagr"]
    sel_sh = out["test"][best]["sharpe"]
    wins = sum(1 for x in rr if x < sel_cagr)
    win_sh = sum(1 for x in rs if x < sel_sh)
    print(f"\nrandom control (20 seeds, TEST): CAGR median {np.median(rr):.2f}% "
          f"range [{min(rr):.2f}, {max(rr):.2f}]")
    print(f"  selected {best} beat {wins}/20 random seeds on CAGR, {win_sh}/20 on Sharpe")
    out["random_beaten_cagr"] = wins
    out["random_beaten_sharpe"] = win_sh

    # ---------------- cost stress (selected variant only) ---------------- #
    stress = {}
    for name, cm in (
        ("double_slippage_10bps", CostModel(segment="delivery", slippage_bps=Dc("10"))),
        ("triple_slippage_15bps", CostModel(segment="delivery", slippage_bps=Dc("15"))),
        ("zero_cost", CostModel(segment="delivery", slippage_bps=Dc("0"))),
    ):
        stress[name] = round(run(panel, scores[best], TEST, cost=cm).metrics.cagr * 100, 2)
    out["test_cost_stress_cagr"] = stress
    print(f"cost stress (TEST CAGR%): {stress}")

    # ---------------- yearly returns ---------------- #
    print("\n--- TEST yearly returns ---")
    out["test_yearly_selected"] = {
        str(k): round(v * 100, 2) for k, v in yearly_returns(sel_res.returns).items()}
    out["test_yearly_bh_topn"] = {
        str(k): round(v * 100, 2) for k, v in yearly_returns(bh_te.returns).items()}
    out["test_yearly_ew_bh"] = {
        str(k): round(v * 100, 2) for k, v in yearly_returns(
            panel.loc[TEST[0]:TEST[1]].pct_change(fill_method=None).fillna(0.0)
            .mean(axis=1)).items()}
    for nm in ("test_yearly_selected", "test_yearly_bh_topn", "test_yearly_ew_bh"):
        print(f"{nm:<22}", out[nm])

    # ---------------- cross-sectional detail of the selected variant ---------------- #
    w = sel_res.weights
    n_flagged_test = sigs[best].loc[TEST[0]:TEST[1]].gt(0).sum(axis=1)
    out["test_weight_detail"] = {
        "max_names_observed": int((w > 0).sum(axis=1).max()),
        "min_names_observed": int((w > 0).sum(axis=1).min()),
        "median_names": float((w > 0).sum(axis=1).median()),
        "invested_mean": round(float(w.sum(axis=1).mean()), 4),
        "max_single_weight": round(float(w.to_numpy().max()), 4),
        "flagged_names_mean": round(float(n_flagged_test.mean()), 1),
        "flagged_names_min": int(n_flagged_test.min()),
        "flagged_names_max": int(n_flagged_test.max()),
        "total_ret_pct": round(
            float(((1 + sel_res.returns).prod() - 1) * 100), 2),
    }
    print("\nweight detail:", out["test_weight_detail"])

    with open("research/agent_trendmom/results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nwrote research/agent_trendmom/results.json")


if __name__ == "__main__":
    main()
