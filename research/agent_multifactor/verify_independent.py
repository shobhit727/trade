"""Independent re-derivation of the V1 TRAIN number.

Deliberately does NOT use harness.py — it re-reads the panel, rebuilds the
strategy signal from scratch, and calls run_backtest directly. Its purpose is
to arbitrate between two conflicting runs of the harness.
"""

import sys
from decimal import Decimal

import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.backtest.metrics import compute_metrics
from nsealgo.costs import CostModel
from nsealgo.data.loader import load_universe

CM = CostModel(segment="delivery", slippage_bps=5)
RATE = float(CM.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0
IST = "Asia/Kolkata"
T0 = pd.Timestamp("2016-01-01", tz=IST)
T1 = pd.Timestamp("2023-12-31", tz=IST)

panel, syms, _ = load_universe("data/nse")
print("panel", panel.shape, "symbols", len(syms))


def sma(p, n):
    return p.rolling(n, min_periods=n).mean()


def rsi(p, n):
    d = p.diff()
    g = d.clip(lower=0).rolling(n, min_periods=n).sum() / n
    loss = -d.clip(upper=0).rolling(n, min_periods=n).sum() / n
    rs = g / loss.where(loss > 0)
    out = 100 - 100 / (1 + rs)
    return out.where(loss > 0, 100.0)


def mask(period, rsip):
    t, r = sma(panel, period), rsi(panel, rsip)
    return ((panel > t) & (r > 50) & t.notna() & r.notna()).fillna(False)


cfg = PortfolioConfig()
print("PortfolioConfig defaults:", cfg)

for label, period, rsip in [("V1 p20/r14", 20, 14), ("V5 p20/r21", 20, 21)]:
    m = mask(period, rsip)
    mom = panel / panel.shift(126) - 1.0
    sc = mom.rank(axis=1, pct=True, na_option="keep").where(m)

    res = run_backtest(panel, sc, CM, cfg, rebalance="M")

    r = res.returns.loc[T0:T1]
    eq = (1 + r).cumprod()
    turn = (res.weights.diff().abs().sum(axis=1) / 2).loc[T0:T1].fillna(0.0)
    mm = compute_metrics(r, eq, annual_turnover=turn.sum() / (len(r) / 244))

    held = res.weights.loc[T0:T1]
    counts = (held > 0).sum(axis=1)
    print(
        f"\n{label} TRAIN: CAGR {mm.cagr*100:.2f}%  Sharpe {mm.sharpe:.2f}  "
        f"MaxDD {mm.max_drawdown*100:.2f}%  total {mm.total_return*100:.1f}%"
    )
    print(
        f"  avg names {counts.mean():.1f}  min {counts.min()}  max {counts.max()}  "
        f"flagged/day {(m.loc[T0:T1].sum(axis=1)).mean():.1f}"
    )
    w = held.iloc[len(held) // 2]
    print(f"  sum(weights) mid-window {w.sum():.4f}  n>0 {(w>0).sum()}")
    top = w[w > 0].nlargest(5)
    print("  top5 weights:", [round(float(x), 4) for x in top.values])
