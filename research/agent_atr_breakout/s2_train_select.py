"""Stage 2 — build the cross-sectional score and select on TRAIN.

Construction (per AGENT_BRIEF §5): the strategy is a per-symbol time-series
indicator returning +1/0/-1; the book is long-only and cross-sectional. So the
signal becomes a *gate*: among names the strategy flags long, rank by trailing
126-day momentum and buy the top of that set.

    score = mom126.where(signal > 0).rank(axis=1, pct=True)

Names the strategy does not flag get NaN, and `build_rebalance_weights` drops
non-finite scores — so the book only ever holds names the strategy actually
selected. Momentum uses closes up to day t inclusive; the engine holds those
weights from t+1, so no lookahead.

The short leg (-1) is discarded: shorting is not available in an Indian delivery
account (brief §5). That is a real cost to the strategy and is disclosed.

Selection happens on TRAIN only. TEST is not touched in this file.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

import signal as sigmod  # noqa: E402

import common  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

TRAIN = (pd.Timestamp("2016-01-01", tz="Asia/Kolkata"),
         pd.Timestamp("2023-12-31", tz="Asia/Kolkata"))
TEST = (pd.Timestamp("2024-01-01", tz="Asia/Kolkata"),
        pd.Timestamp("2026-10-01", tz="Asia/Kolkata"))

#: Declared BEFORE any run (brief §4). Five variants, period x ATR multiplier.
VARIANTS = [
    ("V1", 10, 1.0),
    ("V2", 14, 1.5),
    ("V3", 20, 2.0),
    ("V4", 14, 2.5),
    ("V5", 20, 3.0),
]

MOM_DAYS = 126
COST = CostModel(segment="delivery", slippage_bps=5)


@dataclass
class Row:
    tag: str
    cagr: float
    sharpe: float
    maxdd: float
    calmar: float
    turnover: float
    cost_drag: float
    avg_names: float
    n_rebal: int


def build_score(close: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    mom = close / close.shift(MOM_DAYS) - 1.0
    return mom.where(sig > 0).rank(axis=1, pct=True)


def evaluate(panel: pd.DataFrame, score: pd.DataFrame, idx, tag: str) -> Row:
    res = run_backtest(
        panel.loc[slice(*idx)],
        score.loc[slice(*idx)],
        COST,
        PortfolioConfig(),
        rebalance="M",
    )
    m = res.metrics
    return Row(
        tag=tag,
        cagr=m.cagr,
        sharpe=m.sharpe,
        maxdd=m.max_drawdown,
        calmar=m.calmar,
        turnover=m.annual_turnover,
        cost_drag=m.cost_drag_annual,
        avg_names=res.diag["avg_names"],
        n_rebal=int(res.diag["n_rebalances"]),
    )


def buy_and_hold(panel: pd.DataFrame, idx, tag: str) -> Row:
    """Equal-weight universe, held throughout. Charged one full round trip of
    entry+exit cost so the comparison is net of the same cost stack."""
    from nsealgo.backtest.metrics import compute_metrics

    sub = panel.loc[slice(*idx)]
    # Equal-weight across the universe, per the brief's definition of buy-and-hold.
    r = sub.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    eq = (1.0 + r).cumprod()
    rt = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0
    eq = eq * (1.0 - rt)
    r_net = eq.pct_change(fill_method=None).fillna(0.0)
    m = compute_metrics(r_net, eq)
    return Row("BH", m.cagr, m.sharpe, m.max_drawdown, m.calmar, 0.0, rt,
               float(sub.notna().sum(axis=1).mean()), 0)


def fmt(rows: list[Row]) -> str:
    out = [
        f"{'tag':>6} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} "
        f"{'Turn/y':>7} {'Cost/y':>7} {'Names':>6} {'Rebal':>5}"
    ]
    for r in rows:
        out.append(
            f"{r.tag:>6} {r.cagr * 100:>7.2f}% {r.sharpe:>7.2f} "
            f"{r.maxdd * 100:>7.2f}% {r.calmar:>7.2f} {r.turnover:>7.2f} "
            f"{r.cost_drag * 100:>6.2f}% {r.avg_names:>6.1f} {r.n_rebal:>5}"
        )
    return "\n".join(out)


def main() -> None:
    o, h, lo, c, syms = common.load()
    tr0, tr1 = TRAIN

    rows: list[Row] = []
    live_rows = []
    for tag, period, mult in VARIANTS:
        sig = sigmod.signal_panel(h, lo, c, period, mult)
        live_rows.append((tag, sigmod.liveness(sig, c.loc[tr0:tr1].index)))
        score = build_score(c, sig)
        rows.append(evaluate(c, score, (tr0, tr1), tag))

    rows.append(buy_and_hold(c, (tr0, tr1), "BH"))
    comp = build_composite_score(c)
    rows.append(evaluate(c, comp, (tr0, tr1), "COMPO"))

    print("=== TRAIN 2016-01-01 -> 2023-12-31 (selection set) ===")
    print("signal liveness (fraction of symbol-bars long): "
          + ", ".join(f"{t}={v:.2%}" for t, v in live_rows))
    print(fmt(rows))
    best = max((r for r in rows if r.tag.startswith("V")), key=lambda r: r.sharpe)
    print(f"\nSELECTED ON TRAIN (max Sharpe): {best.tag}  Sharpe={best.sharpe:.2f} "
          f"CAGR={best.cagr * 100:.2f}%")


if __name__ == "__main__":
    main()
