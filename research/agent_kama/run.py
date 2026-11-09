"""kama_strategy on NSE NIFTY-50 daily bars.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31 (all tuning)
  TEST  2024-01-01 -> 2026-10-01 (touched once, at the end)

DECLARED parameter budget (5 variants; the only strategy parameter is `period`).
Rebalance freq (monthly) and momentum lookback (126d) are fixed harness settings.

  V1 20 (catalog default)  V2 10  V3 30  V4 55  V5 75

Selection rule, fixed in advance: max TRAIN Calmar.

Signal: close > KAMA(period) -> +1 else -1, KAMA replicated EXACTLY from
cryptobot.strategies.indicators.kama (verified bit-identical in verify_kama.py).

Costs: CostModel(delivery, slippage_bps=5) -> run_backtest charges all_in = 21.92 bps
round trip on Rs 1,00,000. EVERY number below is net of 21.92 bps unless the row is
explicitly labelled otherwise.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal as D

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
MOM_DAYS = 126
FWD_DAYS = 21
REBALANCE = "M"
N_RANDOM = 20

VARIANTS = {"V1_20": 20, "V2_10": 10, "V3_30": 30, "V4_55": 55, "V5_75": 75}

CFG = PortfolioConfig()
COST = CostModel(segment="delivery", slippage_bps=5)
RT_BPS = float(COST.all_in_round_trip_bps(100_000))


# --------------------------------------------------------------------------- #
# Indicator (verified against the catalog in verify_kama.py)
# --------------------------------------------------------------------------- #
def kama_panel(x: pd.DataFrame, period: int, fast: int = 2, slow: int = 30) -> pd.DataFrame:
    """Vectorised-across-symbols equivalent of cryptobot.strategies.indicators.kama."""
    a = x.to_numpy(dtype=float)
    T, _ = a.shape
    out = np.full(a.shape, np.nan)
    if T < period + 1:
        return pd.DataFrame(out, index=x.index, columns=x.columns)

    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    vol = np.abs(np.diff(a[: period + 1], axis=0)).sum(axis=0)
    kp = a[period].copy()
    out[period] = kp
    with np.errstate(invalid="ignore", divide="ignore"):
        for i in range(period + 1, T):
            vol = vol - np.abs(a[i - period] - a[i - period - 1]) + np.abs(a[i] - a[i - 1])
            change = np.abs(a[i] - a[i - period])
            er = np.where(vol == 0.0, 0.0, change / np.where(vol == 0.0, 1.0, vol))
            sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
            kp = kp + sc * (a[i] - kp)
            out[i] = kp
    return pd.DataFrame(out, index=x.index, columns=x.columns)


def kama_signal(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    k = kama_panel(panel, period)
    sig = pd.DataFrame(np.where(panel > k, 1, -1), index=panel.index, columns=panel.columns)
    sig[k.isna()] = 0  # warmup -> flat, exactly as `if e != e: return 0`
    return sig


def kama_score(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """126d trailing momentum ranked pct, only among names KAMA flags long."""
    return mom_score(panel, kama_signal(panel, period))


def mom_score(panel: pd.DataFrame, sig: pd.DataFrame | None = None) -> pd.DataFrame:
    mom = panel / panel.shift(MOM_DAYS) - 1.0
    if sig is None:
        return mom.rank(axis=1, pct=True)
    return mom.where(sig > 0).rank(axis=1, pct=True)


def random_score(panel: pd.DataFrame, sig: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: identical % of bars long, entries chosen by a coin flip."""
    rng = np.random.default_rng(seed)
    long_frac = float((sig > 0).to_numpy().mean())
    mask = pd.DataFrame(
        rng.random(sig.shape) < long_frac, index=sig.index, columns=sig.columns
    )
    return mom_score(panel, mask)


def bh_literal(panel: pd.DataFrame, window: tuple[str, str]) -> dict:
    """Brief section 4 rule 5, read literally: panel.pct_change().mean(axis=1).

    Daily equal-weight buy-and-hold of the whole universe, net of ONE full 21.92 bps
    round trip charged at entry (you pay to build the position once and never again).
    """
    p = panel.loc[window[0] : window[1]]
    g = p.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    eq = (1.0 + g).cumprod()
    eq.iloc[0] *= 1.0 - RT_BPS / 10_000.0  # entry cost, once
    r = eq.pct_change(fill_method=None).fillna(0.0)
    m = compute_metrics(r, eq, annual_turnover=2.0, cost_drag_annual=RT_BPS / 10_000.0,
                        trades_per_year=2.0)
    return {
        "cagr": round(m.cagr * 100, 2), "sharpe": round(m.sharpe, 2),
        "maxdd": round(m.max_drawdown * 100, 2), "calmar": round(m.calmar, 2),
        "total_ret_pct": round(m.total_return * 100, 1), "n_days": m.n_periods,
        "yearly": (yearly_returns(r) * 100).round(2).to_dict(),
        "returns": r,
    }


# --------------------------------------------------------------------------- #
def run(panel, score, window, cfg=CFG, cost=COST):
    p = panel.loc[window[0] : window[1]]
    s = score.loc[p.index]
    return run_backtest(p, s, cost, cfg, rebalance=REBALANCE)


def row(res) -> dict:
    m = res.metrics
    return {
        "cagr": round(m.cagr * 100, 2), "sharpe": round(m.sharpe, 2),
        "maxdd": round(m.max_drawdown * 100, 2), "calmar": round(m.calmar, 2),
        "turnover_x_y": round(m.annual_turnover, 2),
        "cost_drag_pct_y": round(m.cost_drag_annual * 100, 2),
        "avg_names": round(res.diag["avg_names"], 1),
        "max_top_w": round(res.diag["avg_top_weight"] * 100, 2),
        "total_ret_pct": round(m.total_return * 100, 1), "n_days": m.n_periods,
        "trades_y": round(m.trades_per_year, 1),
    }


HDR = (f"{'variant':<14}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>8}{'Calmar':>7}"
       f"{'Turn':>6}{'Cost%':>7}{'Names':>7}{'Long%':>7}{'topW%':>7}")


def show(name, r, live=None):
    extra = f"{live * 100:>6.1f}%" if live is not None else "      -"
    print(f"{name:<14}{r['cagr']:>8.2f}{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}"
          f"{r['calmar']:>7.2f}{r['turnover_x_y']:>6.2f}{r['cost_drag_pct_y']:>7.2f}"
          f"{r['avg_names']:>7.1f}{extra}{r['max_top_w']:>7.2f}")


# --------------------------------------------------------------------------- #
def signal_diagnostics(panel, sigs, window, label) -> dict:
    """Does the raw time-series flag carry any forward-return content at all?

    Independent of portfolio construction. TWO weightings are reported because they
    genuinely disagree and reporting only one would be cherry-picking:

    * **day-equal**  — mean over days of (cross-sectional mean among long names minus
      the same among short names). This is the statistic a daily-rebalanced book
      actually earns, and the one the t-stat belongs to.
    * **obs-equal** — every (day, symbol) observation weighted equally, i.e.
      `mean(all long fwd returns) - mean(all short fwd returns)`.

    They differ because the number of long/short names per day varies, so the two
    weight sparse-cross-section days differently. The day-equal version is the honest
    one for this report; the obs-equal version is shown so the gap is visible rather
    than hidden.
    """
    p = panel.loc[window[0] : window[1]]
    fwd = panel.shift(-FWD_DAYS) / panel - 1.0
    out = {}
    for name, _per in VARIANTS.items():
        s = sigs[name].loc[p.index]
        f = fwd.loc[p.index]
        L, S = f.where(s > 0), f.where(s < 0)
        long_m = L.to_numpy().ravel()
        long_m = long_m[np.isfinite(long_m)]
        short_m = S.to_numpy().ravel()
        short_m = short_m[np.isfinite(short_m)]
        daily = (L.mean(axis=1) - S.mean(axis=1)).dropna()
        t = float(daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily))))
        by_year = daily.groupby(daily.index.year).mean()
        out[name] = {
            "long_frac": round(float((s > 0).to_numpy().mean()), 4),
            "fwd21_long_pct": round(float(np.mean(long_m)) * 100, 4),
            "fwd21_short_pct": round(float(np.mean(short_m)) * 100, 4),
            "spread_obsequal_pct": round((np.mean(long_m) - np.mean(short_m)) * 100, 4),
            "spread_dayequal_pct": round(float(daily.mean()) * 100, 4),
            "median_dayequal_pct": round(float(daily.median()) * 100, 4),
            "t_stat": round(t, 2),
            "years_negative": int((by_year < 0).sum()),
            "n_years": int(len(by_year)),
            "hit_rate_long": round(float((long_m > 0).mean()), 4),
            "n_obs_long": int(long_m.size),
        }
        print(f"  {name:<7} long={out[name]['long_frac'] * 100:>5.1f}%  "
              f"fwd21 long={out[name]['fwd21_long_pct']:>6.3f}%  "
              f"short={out[name]['fwd21_short_pct']:>6.3f}%  |  "
              f"spread day-eq={out[name]['spread_dayequal_pct']:>7.3f}%  "
              f"obs-eq={out[name]['spread_obsequal_pct']:>7.3f}%  "
              f"t={out[name]['t_stat']:>6.2f}  negyrs={out[name]['years_negative']}"
              f"/{out[name]['n_years']}")
    print(f"  ({label}: 21-day forward return conditional on the KAMA flag; t is the "
          f"day-equal cross-sectional mean-difference t-stat, n={len(daily)} days)")
    return out


def main() -> None:
    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"panel {panel.shape}  {panel.index[0].date()} -> {panel.index[-1].date()}  "
          f"symbols {len(symbols)}")
    print(f"\nPROVENANCE {provenance()}")
    print(f"cost model: round_trip_bps(1e5)={COST.round_trip_bps(100_000)}  "
          f"all_in_round_trip_bps(1e5)={COST.all_in_round_trip_bps(100_000)}  "
          f"-> run_backtest charges {RT_BPS} bps (all-in, incl. 2x slippage)")

    out: dict = {"provenance": provenance(), "rt_bps_all_in": RT_BPS,
                 "variants": {}}
    sigs = {n: kama_signal(panel, p) for n, p in VARIANTS.items()}
    scores = {n: mom_score(panel, sigs[n]) for n in VARIANTS}

    print("\n=== SIGNAL DIAGNOSTIC (raw flag, no portfolio) ===")
    print("TRAIN:")
    out["sig_train"] = signal_diagnostics(panel, sigs, TRAIN, "TRAIN")

    # ---------------- TRAIN: selection ----------------
    print(f"\n=== TRAIN ({TRAIN[0]} -> {TRAIN[1]}) — selection only ===")
    print(HDR)
    for name in VARIANTS:
        res = run(panel, scores[name], TRAIN)
        live = float((sigs[name].loc[TRAIN[0] : TRAIN[1]] > 0).to_numpy().mean())
        r = row(res)
        out["variants"][name] = {"period": VARIANTS[name], "train": r,
                                 "train_long_frac": round(live, 4)}
        show(name, r, live)

    out["train_bh_engine"] = row(run(panel, mom_score(panel), TRAIN))
    out["train_bh_literal"] = bh_literal(panel, TRAIN)
    out["train_composite"] = row(run(panel, build_composite_score(panel), TRAIN))
    show("BH-engine", out["train_bh_engine"])
    show("composite", out["train_composite"])
    print(f"  BH-literal (panel.pct_change().mean(axis=1), net of one 21.92bps entry): "
          f"CAGR {out['train_bh_literal']['cagr']:.2f}%  Sharpe {out['train_bh_literal']['sharpe']:.2f}"
          f"  MaxDD {out['train_bh_literal']['maxdd']:.2f}%  "
          f"Calmar {out['train_bh_literal']['calmar']:.2f}")

    # TRAIN-only ablation: is the KAMA filter adding anything to momentum alone?
    mom_only = row(run(panel, mom_score(panel), TRAIN))
    out["train_mom_only"] = mom_only
    print(f"  ablation (TRAIN, momentum only, no KAMA filter): CAGR {mom_only['cagr']:.2f}% "
          f"Sharpe {mom_only['sharpe']:.2f} MaxDD {mom_only['maxdd']:.2f}% "
          f"Calmar {mom_only['calmar']:.2f}   [same as BH-engine row]")

    best = max(VARIANTS, key=lambda k: out["variants"][k]["train"]["calmar"])
    out["selected_on_train"] = best
    print(f"\nSELECTED on TRAIN (max Calmar): {best} (period={VARIANTS[best]})")

    rng_scores = [random_score(panel, sigs[best], seed) for seed in range(N_RANDOM)]
    out["rng_train_cagr"] = [round(run(panel, sc, TRAIN).metrics.cagr * 100, 2)
                             for sc in rng_scores]
    print(f"random control TRAIN CAGR median {np.median(out['rng_train_cagr']):.2f}%")

    # ---------------- TEST: touched exactly once, here ----------------
    print(f"\n=== TEST ({TEST[0]} -> {TEST[1]}) — untouched until now ===")
    print(HDR)
    test_rows = {}
    for name in VARIANTS:
        res = run(panel, scores[name], TEST)
        r = row(res)
        test_rows[name] = r
        live = float((sigs[name].loc[TEST[0] : TEST[1]] > 0).to_numpy().mean())
        show(name + (" *" if name == best else ""), r, live)
        r["long_frac"] = round(live, 4)
    out["test"] = test_rows

    bh_e = run(panel, mom_score(panel), TEST)
    comp = run(panel, build_composite_score(panel), TEST)
    out["test_bh_engine"] = row(bh_e)
    out["test_bh_literal"] = bh_literal(panel, TEST)
    out["test_composite"] = row(comp)
    show("BH-engine", out["test_bh_engine"])
    show("composite", out["test_composite"])
    print(f"  BH-literal (panel.pct_change().mean(axis=1), net of one 21.92bps entry): "
          f"CAGR {out['test_bh_literal']['cagr']:.2f}%  Sharpe {out['test_bh_literal']['sharpe']:.2f}"
          f"  MaxDD {out['test_bh_literal']['maxdd']:.2f}%  Calmar {out['test_bh_literal']['calmar']:.2f}")

    out["test_rng_cagr"] = [round(run(panel, sc, TEST).metrics.cagr * 100, 2)
                            for sc in rng_scores]
    out["test_rng_sharpe"] = [round(run(panel, sc, TEST).metrics.sharpe, 2)
                              for sc in rng_scores]
    sel = out["test"][best]
    rr = out["test_rng_cagr"]
    out["test_rng_beaten"] = int(sum(1 for x in rr if x < sel["cagr"]))
    print(f"\nRANDOM CONTROL ({N_RANDOM} seeds, same % bars long, TEST): "
          f"CAGR median {np.median(rr):.2f}%  min {min(rr):.2f}  max {max(rr):.2f}")
    print(f"  selected {best} TEST CAGR {sel['cagr']:.2f}% -> beat {out['test_rng_beaten']}/{N_RANDOM}"
          f" random draws")

    # cost stress (selected, TEST)
    stress = {}
    for k, cm in (("zero_slippage_11.92bps", CostModel(segment="delivery", slippage_bps=D("0"))),
                  ("base_21.92bps", COST),
                  ("slip10_31.92bps", CostModel(segment="delivery", slippage_bps=D("10"))),
                  ("slip15_41.92bps", CostModel(segment="delivery", slippage_bps=D("15")))):
        stress[k] = {"rt_bps": float(cm.all_in_round_trip_bps(100_000)),
                     "cagr": round(run(panel, scores[best], TEST, cost=cm).metrics.cagr * 100, 2)}
    out["test_cost_stress"] = stress
    print("\nCOST STRESS (selected, TEST CAGR%):")
    for k, v in stress.items():
        print(f"  {k:<24} rt={v['rt_bps']:>5.2f}bps  CAGR {v['cagr']:>6.2f}%")

    out["test_yearly"] = {
        "kama": (yearly_returns(run(panel, scores[best], TEST).returns) * 100).round(2).to_dict(),
        "bh_engine": (yearly_returns(bh_e.returns) * 100).round(2).to_dict(),
        "composite": (yearly_returns(comp.returns) * 100).round(2).to_dict(),
        "bh_literal": out["test_bh_literal"]["yearly"],
    }
    print("\nTEST yearly returns %:")
    for k, v in out["test_yearly"].items():
        print(f"  {k:<10} {v}")

    w = run(panel, scores[best], TEST).weights
    out["test_weights"] = {
        "sum_mean": round(float(w.sum(axis=1).mean()), 4),
        "sum_min": round(float(w.sum(axis=1).min()), 4),
        "sum_max": round(float(w.sum(axis=1).max()), 4),
        "names_max": int((w > 0).sum(axis=1).max()),
        "names_min": int((w > 0).sum(axis=1).min()),
        "max_weight": round(float(w.to_numpy().max()), 4),
        "gross_mean": round(float(w.abs().sum(axis=1).mean()), 4),
    }
    print(f"\nweights: sum mean {out['test_weights']['sum_mean']:.3f} "
          f"(min {out['test_weights']['sum_min']:.3f} / "
          f"max {out['test_weights']['sum_max']:.3f})  "
          f"max single {out['test_weights']['max_weight']:.4f}  "
          f"names {out['test_weights']['names_min']}-{out['test_weights']['names_max']}  "
          f"gross mean {out['test_weights']['gross_mean']:.4f}")

    with open("research/agent_kama/results.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nwrote research/agent_kama/results.json")


if __name__ == "__main__":
    main()
