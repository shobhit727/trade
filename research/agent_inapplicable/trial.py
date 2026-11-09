"""Protocol trial for the two genuinely runnable candidates: `basket` and `meta`.

Protocol per research/AGENT_BRIEF.md:
  TRAIN 2016-01-01 -> 2023-12-31   (choose variants here, and only here)
  TEST  2024-01-01 -> 2026-10-01   (read exactly once, at the end)
  Costs: full Indian delivery stack via run_backtest -> 21.92 bps all-in.
  Controls: random signal at matched % bars long, and buy-and-hold on the same window.

DECLARED PARAMETER BUDGET (written before any run):
  basket : 5 variants  -- period in {10, 20, 60, 120} at threshold=0.015, plus
                          period=20 at threshold=0.05 (1 combo variant).
  meta   : 5 variants  -- period in {10, 20, 50, 100, 200}, threshold absent by design.
No further variants may be run. Exceeding this invalidates the run.

Run: .venv/bin/python research/agent_inapplicable/trial.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.costs import CostModel

DATA = Path("data/nse")
TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")
RNG = np.random.default_rng(20261012)


# ---------------------------------------------------------------- data
def load_panel():
    frames = {}
    for f in sorted(DATA.glob("*_1d.csv")):
        sym = f.stem.replace("_1d", "")
        df = pd.read_csv(f, index_col="ts")
        df.index = pd.to_datetime(df.index, unit="ms", utc=True).tz_convert("Asia/Kolkata")
        frames[sym] = df["close"]
    panel = pd.DataFrame(frames).sort_index()
    panel = panel.loc["2008-01-01":]  # post-vendor-artifact per GOAL.md
    return panel


def signal_panel(panel, kind, period, threshold):
    """Broadcast the catalog strategy's signal to every symbol, point-in-time.

    Each symbol's signal is computed from its OWN close history only, replicating
    exactly what SignalStrategy.signal() sees. The SMA/ROC lookback uses only bars
    <= t (no lookahead). No shift is applied here because the score is built from
    trailing closes and the engine earns returns from t+1 onward.
    """
    if kind == "basket":  # roc(closes, period) > threshold -> +1 ; < -threshold -> -1
        roc = panel / panel.shift(period) - 1.0
        out = np.where(roc.abs() > threshold, np.sign(roc), np.nan)
        return pd.DataFrame(out, index=panel.index, columns=panel.columns)

    if kind == "meta":  # close > sma(period) -> +1 else -1  (never flat)
        ma = panel.rolling(period).mean()
        out = np.where(panel > ma, 1.0, -1.0)
        return pd.DataFrame(out, index=panel.index, columns=panel.columns)

    raise ValueError(kind)


def cross_sectional_score(panel, sig):
    """Brief §5: rank the signalled names by trailing momentum; long-only."""
    mom = panel / panel.shift(126) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def random_score(panel, sig, target_frac):
    """Negative control: random long/flat with the SAME % of bars long."""
    r = np.random.default_rng(12345)
    mask = r.random(panel.shape) < target_frac
    sig_r = np.where(mask, 1.0, 0.0)
    mom = panel / panel.shift(126) - 1.0
    return mom.where(sig_r > 0).rank(axis=1, pct=True)


def run(score, lo, hi, cfg, cost_model):
    """Slice panel AND score to the same window, then run the shared engine."""
    idx = panel.index.intersection(score.index)
    idx = idx[(idx >= pd.Timestamp(lo, tz=idx.tz)) & (idx <= pd.Timestamp(hi, tz=idx.tz))]
    return run_backtest(panel.loc[idx], score.loc[idx], cost_model, cfg)


# ---------------------------------------------------------------- main
panel = load_panel()
print(f"panel: {panel.shape[0]} rows x {panel.shape[1]} syms  "
      f"{panel.index[0].date()} -> {panel.index[-1].date()}")

cfg = PortfolioConfig()
cost = CostModel(segment="delivery", slippage_bps=5)
print(f"cost: round_trip={cost.round_trip_bps(100_000):.2f} bps  "
      f"all_in={cost.all_in_round_trip_bps(100_000):.2f} bps  "
      "(run_backtest charges all_in: engine folds in slippage)")
print()

BASKET_VARIANTS = [
    ("basket", "p10_t0.015", 10, 0.015),
    ("basket", "p20_t0.015", 20, 0.015),
    ("basket", "p60_t0.015", 60, 0.015),
    ("basket", "p120_t0.015", 120, 0.015),
    ("basket", "p20_t0.05", 20, 0.05),
]
META_VARIANTS = [
    ("meta", "p10", 10, None),
    ("meta", "p20", 20, None),
    ("meta", "p50", 50, None),
    ("meta", "p100", 100, None),
    ("meta", "p200", 200, None),
]

rows = []
fracs = {}
for kind, label, period, threshold in BASKET_VARIANTS + META_VARIANTS:
    th = 0.0 if threshold is None else threshold
    sig = signal_panel(panel, kind, period, th)
    sig = sig.where(sig.notna())
    frac = float((sig > 0).sum().sum() / (sig.notna().sum().sum() or 1))
    fracs[label] = frac
    score = cross_sectional_score(panel, sig)
    res = run(score, *TRAIN, cfg, cost)
    m = res.metrics
    rows.append(dict(strategy=kind, variant=label, split="TRAIN",
                     cagr=m.cagr, sharpe=m.sharpe, maxdd=m.max_drawdown,
                     calmar=m.calmar, turnover=m.annual_turnover, costs=res.costs_paid,
                     names=res.diag.get("avg_names", np.nan),
                     longfrac=frac))

print("=" * 108)
print("TRAIN (2016-01-01 -> 2023-12-31) — parameter selection window")
print("=" * 108)
print(f"{'strategy':<10}{'variant':<12}{'CAGR':>8}{'Sharpe':>9}{'MaxDD':>9}"
      f"{'Calmar':>8}{'Turn/yr':>9}{'Costs':>10}{'Names':>8}{'Long%':>8}")
for r in rows:
    print(f"{r['strategy']:<10}{r['variant']:<12}{r['cagr']:>8.2%}{r['sharpe']:>9.2f}"
          f"{r['maxdd']:>9.2%}{r['calmar']:>8.2f}{r['turnover']:>9.2f}"
          f"{r['costs']:>10.3f}{r['names']:>8.1f}{r['longfrac']:>8.1%}")

# --- pick the single TRAIN-best variant per strategy, on TRAIN only ---
best = {}
for kind in ("basket", "meta"):
    cand = [r for r in rows if r["strategy"] == kind]
    best[kind] = max(cand, key=lambda r: r["sharpe"])["variant"]

print()
print(f"TRAIN-selected variant per strategy (by Sharpe, TRAIN only): {best}")
print("Now reading TEST for the first time.")
print()

# ---------------------------------------------------------------- TEST
test_rows = []
for kind, label, period, threshold in BASKET_VARIANTS + META_VARIANTS:
    th = 0.0 if threshold is None else threshold
    sig = signal_panel(panel, kind, period, th).where(lambda d: d.notna())
    score = cross_sectional_score(panel, sig)
    res = run(score, *TEST, cfg, cost)
    m = res.metrics
    test_rows.append(dict(strategy=kind, variant=label, split="TEST",
                          cagr=m.cagr, sharpe=m.sharpe, maxdd=m.max_drawdown,
                          calmar=m.calmar, turnover=m.annual_turnover, costs=res.costs_paid,
                          names=res.diag.get("avg_names", np.nan),
                          longfrac=fracs[label]))

print("=" * 108)
print("TEST (2024-01-01 -> 2026-10-01) — read once")
print("=" * 108)
print(f"{'strategy':<10}{'variant':<12}{'CAGR':>8}{'Sharpe':>9}{'MaxDD':>9}"
      f"{'Calmar':>8}{'Turn/yr':>9}{'Costs':>10}{'Names':>8}{'Long%':>8}{'SEL':>5}")
for r in test_rows:
    sel = "  <-- TRAIN-selected" if r["variant"] == best[r["strategy"]] else ""
    print(f"{r['strategy']:<10}{r['variant']:<12}{r['cagr']:>8.2%}{r['sharpe']:>9.2f}"
          f"{r['maxdd']:>9.2%}{r['calmar']:>8.2f}{r['turnover']:>9.2f}"
          f"{r['costs']:>10.3f}{r['names']:>8.1f}{r['longfrac']:>8.1%}{sel}")

# ---------------------------------------------------------------- controls
print()
print("=" * 108)
print("CONTROLS on TEST (identical window)")
print("=" * 108)

# buy-and-hold, per brief: panel.pct_change().mean(axis=1)
bh_ret = panel.pct_change().mean(axis=1).loc[TEST[0]:TEST[1]]
bh = compute_metrics(bh_ret)
print("  buy-and-hold (equal-weight, pct_change().mean(axis=1))")
print(f"    CAGR={bh.cagr:.2%}  Sharpe={bh.sharpe:.2f}  MaxDD={bh.max_drawdown:.2%}  "
      f"Calmar={bh.calmar:.2f}")

for kind in ("basket", "meta"):
    sel = [v for v in BASKET_VARIANTS + META_VARIANTS if v[1] == best[kind]][0]
    _, label, period, threshold = sel
    th = 0.0 if threshold is None else threshold
    sig = signal_panel(panel, kind, period, th).where(lambda d: d.notna())
    score = cross_sectional_score(panel, sig)
    rf = random_score(panel, sig, fracs[label])
    res = run(rf, *TEST, cfg, cost)
    m = res.metrics
    print(f"  random-signal control ({kind}, {label}, {fracs[label]:.1%} bars long)")
    print(f"    CAGR={m.cagr:.2%}  Sharpe={m.sharpe:.2f}  MaxDD={m.max_drawdown:.2%}")

# nsealgo composite
try:
    from nsealgo.factors.core import build_composite_score
    comp = build_composite_score(panel)
    cres = run(comp, *TEST, cfg, cost)
    print("  nsealgo composite (build_composite_score)")
    print(f"    CAGR={cres.metrics.cagr:.2%}  Sharpe={cres.metrics.sharpe:.2f}  "
          f"MaxDD={cres.metrics.max_drawdown:.2%}")
except Exception as e:  # noqa: BLE001
    print(f"  nsealgo composite: unavailable ({type(e).__name__}: {e})")
