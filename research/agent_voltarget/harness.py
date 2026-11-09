"""Shared harness for the `volatility_target` NSE validation.

What the source strategy actually does
--------------------------------------
`cryptobot.strategies.catalog.volatility_target.VolTargetStrategy.signal` returns

    +1  if close[t] > close[t-1]  AND  ATR(period)/close[t] < 2 * target
    -1  if close[t] < close[t-1]  AND  ATR(period)/close[t] < 2 * target
     0  otherwise

with `period=14`, `target=0.01` by default. Unlike `adx_trend`, the ATR is NOT
discarded -- it gates both branches. So the strategy is a *low-volatility regime +
1-bar direction* flag. `verify_source_signal()` asserts this mechanically.

Construction into the NSE book
-----------------------------
Long-only: `-1` and `0` both become "not held". The engine needs a ranking, so a
cross-sectional ranking is chosen per variant (see VARIANTS in the report).

No lookahead: every input to the score on day t uses closes up to and including t.
`run_backtest` shifts held weights by one bar internally.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics, yearly_returns  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402

DATA_DIR = "data/nse"

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

REF_NOTIONAL = Decimal("100000")
COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
RT_BPS = float(COST_MODEL.all_in_round_trip_bps(REF_NOTIONAL))

PORTFOLIO = PortfolioConfig()

_panel: pd.DataFrame | None = None
_symbols: list[str] | None = None
_hl: tuple[pd.DataFrame, pd.DataFrame] | None = None


# --------------------------------------------------------------------------- #
# ENGINE PINNING
# --------------------------------------------------------------------------- #
# Another agent was editing src/nsealgo/backtest/engine.py WHILE this harness was
# running (file mtime moved mid-session, twice). That changed results under our
# feet: the same frozen variant scored 3.50% TEST CAGR at 14:0x and 2.09% at 14:1x,
# with no change to any input on our side.
#
# The pin is on the engine's *executable code*, not its raw bytes: another agent
# kept editing docstrings, and a byte hash would have aborted on comments that
# cannot change a number. Docstrings and comments are stripped from the AST before
# hashing, so re-pinning only happens when behaviour could actually differ.
#
# Every script in this directory calls assert_engine_pinned() before doing any
# work. Results produced under different code hashes must never be mixed.
# --------------------------------------------------------------------------- #
ENGINE_CODE_SHA256 = "773e723cf02402ad98f9796163cdd81d336bf6d8df107d7813f6a6b181e10fe8"


def engine_code_hash() -> str:
    """SHA-256 of the engine's executable code, ignoring docstrings/comments."""
    import ast
    import hashlib

    path = os.path.join("src", "nsealgo", "backtest", "engine.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    class _Strip(ast.NodeTransformer):
        def _s(self, node):
            self.generic_visit(node)
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(
                body[0].value, ast.Constant
            ) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
            return node

        visit_FunctionDef = _s
        visit_AsyncFunctionDef = _s
        visit_ClassDef = _s
        visit_Module = _s

    stripped = _Strip().visit(tree)
    return hashlib.sha256(
        ast.dump(ast.fix_missing_locations(stripped)).encode()
    ).hexdigest()


def assert_engine_pinned() -> str:
    """Abort loudly if the backtest engine's behaviour changed under us."""
    got = engine_code_hash()
    if got != ENGINE_CODE_SHA256:
        raise RuntimeError(
            "src/nsealgo/backtest/engine.py executable code changed since this "
            f"harness was pinned (expected {ENGINE_CODE_SHA256[:12]}, found "
            f"{got[:12]}). Results are not comparable. Re-pin deliberately and "
            "re-run every step from step0; do not mix numbers produced by "
            "different engine versions."
        )
    return got


def load_panel() -> tuple[pd.DataFrame, list[str]]:
    global _panel, _symbols
    if _panel is None:
        _panel, _symbols, _ = load_universe(DATA_DIR)
    return _panel, _symbols


def load_hl() -> tuple[pd.DataFrame, pd.DataFrame]:
    """High/low panels masked to exactly the rows the cleaning kept.

    The cleaned close panel is authoritative: any row dropped by the loader is NaN
    there, so masking by `panel.notna()` reproduces the audited row set without
    re-implementing a cleaning rule.
    """
    global _hl
    if _hl is None:
        panel, symbols = load_panel()
        highs, lows = {}, {}
        for s in symbols:
            df = pd.read_csv(os.path.join(DATA_DIR, f"{s}_1d.csv"))
            df.columns = [c.strip().lower() for c in df.columns]
            df["date"] = (
                pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
                .dt.tz_convert("Asia/Kolkata")
                .dt.normalize()
            )
            df = df.drop_duplicates("date").set_index("date").sort_index()
            highs[s] = df["high"]
            lows[s] = df["low"]
        h = pd.DataFrame(highs).reindex(panel.index)
        lo = pd.DataFrame(lows).reindex(panel.index)
        keep = panel.notna()
        _hl = (h.where(keep), lo.where(keep))
    return _hl


def atr_panel(panel: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """ATR matching `cryptobot.strategies.indicators.atr`: mean of the last `period`
    true ranges. Trailing, no lookahead."""
    high, low = load_hl()
    prev = panel.shift(1)
    tr = pd.concat(
        [
            (high - low).stack(future_stack=True),
            (high - prev).abs().stack(future_stack=True),
            (low - prev).abs().stack(future_stack=True),
        ],
        axis=1,
    ).max(axis=1).unstack()
    tr = tr.reindex(index=panel.index, columns=panel.columns)
    return tr.rolling(period, min_periods=period).mean()


def natr(panel: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """ATR / close -- the exact quantity the strategy thresholds."""
    return atr_panel(panel, period) / panel


# --------------------------------------------------------------------------- #
# The strategy signal
# --------------------------------------------------------------------------- #


def vol_regime(panel: pd.DataFrame, thresh: float = 0.02,
               period: int = 14) -> pd.DataFrame:
    """`ATR(period)/close < thresh` -- the volatility-regime half of the signal."""
    return (natr(panel, period) < thresh).astype(float).where(panel.notna())


def up_day(panel: pd.DataFrame) -> pd.DataFrame:
    """`close[t] > close[t-1]` -- the direction half of the signal."""
    return (panel > panel.shift(1)).astype(float).where(panel.notna())


def source_flag(panel: pd.DataFrame, thresh: float = 0.02,
                period: int = 14) -> pd.DataFrame:
    """The literal long-side flag: up-day AND calm-vol regime."""
    return ((up_day(panel) > 0) & (vol_regime(panel, thresh, period) > 0)).astype(float)


def realised_vol(panel: pd.DataFrame, days: int = 60) -> pd.DataFrame:
    return panel.pct_change(fill_method=None).rolling(days, min_periods=40).std()


# --------------------------------------------------------------------------- #
# DECLARED PARAMETER BUDGET -- see REPORT.md section 1. Five variants, no more.
# Selection rule: highest TRAIN Sharpe (tie-break Calmar), then freeze + run TEST once.
# --------------------------------------------------------------------------- #
VARIANTS: list[str] = [
    "V1_flag_mom126",
    "V2_flag_lowvol",
    "V3_flag_momvol",
    "V4_atronly_mom126",
    "V5_flag3pct_mom126",
]

DESCRIPTIONS: dict[str, str] = {
    "V1_flag_mom126": "flag=up-day & NATR14<2%; rank=126d momentum",
    "V2_flag_lowvol": "flag=up-day & NATR14<2%; rank=-60d realised vol",
    "V3_flag_momvol": "flag=up-day & NATR14<2%; rank=126d mom / 60d vol",
    "V4_atronly_mom126": "flag=NATR14<2% only (no 1-bar direction); rank=126d mom",
    "V5_flag3pct_mom126": "flag=up-day & NATR14<3% (target=0.015); rank=126d mom",
}


def build_score(name: str, panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional score for a named variant. Non-flagged names get NaN, which
    the engine treats as ineligible -- that is how -1/0 become 'do not hold'."""
    vol = realised_vol(panel, 60).replace(0.0, np.nan)
    mom = panel / panel.shift(126) - 1.0

    if name == "V1_flag_mom126":
        return mom.where(source_flag(panel) > 0)
    if name == "V2_flag_lowvol":
        return (-vol).where(source_flag(panel) > 0)
    if name == "V3_flag_momvol":
        return (mom / vol).where(source_flag(panel) > 0)
    if name == "V4_atronly_mom126":
        return mom.where(vol_regime(panel) > 0)
    if name == "V5_flag3pct_mom126":
        return mom.where(source_flag(panel, thresh=0.03) > 0)
    raise KeyError(name)


def random_score(panel: pd.DataFrame, seed: int, use_flag_p: float | None = None
                 ) -> pd.DataFrame:
    """Negative control A: random flag on the SAME unconditional frequency as the
    real signal, then the V1 ranking. Isolates the flag; ranking held constant."""
    rng = np.random.default_rng(seed)
    flag = source_flag(panel)
    p = float(flag.to_numpy().mean()) if use_flag_p is None else use_flag_p
    hit = rng.random(panel.shape) < p
    flags = pd.DataFrame(hit, index=panel.index, columns=panel.columns)
    return (panel / panel.shift(126) - 1.0).where(flags)


def random_score_mom_only(panel: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control A2: random flag, but NO ranking and NO 126d momentum input
    at all -- pure coin at the signal's own frequency. Kept distinct from
    `random_score_no_rank` (which uses random values as the score) so the two
    controls differ only in whether a momentum input is consulted."""
    rng = np.random.default_rng(seed)
    p = float(source_flag(panel).to_numpy().mean())
    hit = rng.random(panel.shape) < p
    flags = pd.DataFrame(hit, index=panel.index, columns=panel.columns)
    return pd.DataFrame(rng.random(panel.shape), index=panel.index,
                        columns=panel.columns).where(flags)


def random_score_no_rank(panel: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control B: pure coin, same % of name-days flagged, no ranking.
    Score is a random draw for flagged names, so selection among them is arbitrary."""
    rng = np.random.default_rng(seed)
    p = float(source_flag(panel).to_numpy().mean())
    hit = rng.random(panel.shape) < p
    flags = pd.DataFrame(hit, index=panel.index, columns=panel.columns)
    vals = pd.DataFrame(rng.random(panel.shape), index=panel.index,
                        columns=panel.columns)
    return vals.where(flags)


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, start, end, cash: float = 0.0) -> dict:
    """True buy-and-hold equal-weight basket over [start, end].

    Equal weight at the first bar, shares then held (weights drift). One round trip
    charged at entry against compounding equity, exactly as the engine does. No
    rebalancing, hence no rebalance drag -- the strongest form of the benchmark.
    """
    px = panel.loc[start:end]
    rets = px.pct_change(fill_method=None).fillna(0.0)
    w = pd.Series(0.0, index=px.columns)
    w[px.columns] = (1.0 - cash) / len(px.columns)
    gross = w * rets
    rate = RT_BPS / 10_000.0
    eq, daily = 1.0, []
    for dt in px.index:
        eq *= 1.0 + float(gross.loc[dt].sum())
        daily.append(eq)
    turn = float(w.sum())
    eq -= turn * eq * rate
    costs = turn * eq * rate
    daily[-1] = eq
    daily = pd.Series(daily, index=px.index)
    m = compute_metrics(daily.pct_change(fill_method=None).fillna(0.0), daily)
    return dict(
        metrics=m,
        equity=daily,
        annual_turnover=turn / max(len(px) / 244, 1e-9),
        cost_drag=costs / max(len(px) / 244, 1e-9),
    )


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


@dataclass
class Row:
    label: str
    set_name: str
    cagr: float
    sharpe: float
    maxdd: float
    calmar: float
    turnover: float
    cost_drag: float
    avg_names: float
    total: float
    years_win: float


def row_of(label: str, set_name: str, res) -> Row:
    m = res.metrics
    yr = yearly_returns(res.returns)
    return Row(
        label=label,
        set_name=set_name,
        cagr=m.cagr,
        sharpe=m.sharpe,
        maxdd=m.max_drawdown,
        calmar=m.calmar,
        turnover=m.annual_turnover,
        cost_drag=m.cost_drag_annual,
        avg_names=float(res.diag.get("avg_names", float("nan"))),
        total=m.total_return,
        years_win=float((yr > 0).mean()),
    )


HDR = (
    f"{'label':<24}{'set':<6}{'CAGR%':>9}{'Sharpe':>8}{'MaxDD%':>9}"
    f"{'Calmar':>8}{'Turn/y':>8}{'Cost/y%':>9}{'Names':>7}{'Total%':>10}{'Yr+':>6}"
)


def line(r: Row) -> str:
    return (
        f"{r.label:<24}{r.set_name:<6}{r.cagr * 100:>9.2f}{r.sharpe:>8.2f}"
        f"{r.maxdd * 100:>9.2f}{r.calmar:>8.2f}{r.turnover:>8.2f}"
        f"{r.cost_drag * 100:>9.2f}{r.avg_names:>7.1f}{r.total * 100:>10.1f}"
        f"{r.years_win * 100:>5.0f}%"
    )


def run(panel: pd.DataFrame, score: pd.DataFrame, start, end):
    return run_backtest(
        panel.loc[start:end], score.loc[start:end], COST_MODEL, PORTFOLIO,
        rebalance="M",
    )


def row_for_variant(label: str, set_name: str, variant: str, panel, start, end) -> Row:
    return row_of(label, set_name, run(panel, build_score(variant, panel), start, end))


def bh_row(label: str, set_name: str, panel, start, end) -> Row:
    b = buy_and_hold(panel, start, end)
    m = b["metrics"]
    yr = yearly_returns(b["equity"].pct_change(fill_method=None).fillna(0.0))
    return Row(
        label=label, set_name=set_name, cagr=m.cagr, sharpe=m.sharpe,
        maxdd=m.max_drawdown, calmar=m.calmar, turnover=b["annual_turnover"],
        cost_drag=b["cost_drag"], avg_names=float(panel.columns.size),
        total=m.total_return, years_win=float((yr > 0).mean()),
    )


def composite_score(panel: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(panel)


def verify_source_signal() -> dict:
    """Mechanically confirm the source signal is the two-part flag (direction AND
    volatility regime), and that BOTH `period` and `target` actually change it."""
    from cryptobot.strategies.catalog.volatility_target import (
        VolTargetConfig,
        VolTargetStrategy,
    )

    rng = np.random.default_rng(11)
    n = 500
    closes = list(100 + np.cumsum(rng.normal(0, 1.0, n)))
    highs = [c + abs(rng.normal(0, 0.6)) + 0.2 for c in closes]
    lows = [c - abs(rng.normal(0, 0.6)) - 0.2 for c in closes]
    vols = [1000.0] * n

    def sweep(cfg):
        s = VolTargetStrategy(cfg)
        return [
            s.signal(closes[: i + 1], highs[: i + 1], lows[: i + 1], vols[: i + 1])
            for i in range(60, n)
        ]

    base = sweep(VolTargetConfig(period=14, target=0.01))
    agree = 0
    for i, got in zip(range(60, n), base, strict=True):
        c, h, lo = closes[: i + 1], highs[: i + 1], lows[: i + 1]
        trs = [max(h[k] - lo[k], abs(h[k] - c[k - 1]), abs(lo[k] - c[k - 1]))
               for k in range(len(c) - 14, len(c))]
        b = float(np.mean(trs))
        want = 0
        if b / max(c[-1], 1e-9) < 0.02:
            want = 1 if c[-1] > c[-2] else (-1 if c[-1] < c[-2] else 0)
        agree += int(got == want)

    tight = sweep(VolTargetConfig(period=14, target=0.002))   # far stricter
    loose = sweep(VolTargetConfig(period=14, target=0.05))    # near-always calm
    slow = sweep(VolTargetConfig(period=60, target=0.01))     # longer ATR

    return dict(
        matches_two_part_flag=f"{agree}/{len(base)}",
        pct_long_default=float(np.mean(np.array(base) > 0)),
        pct_long_target_0002=float(np.mean(np.array(tight) > 0)),
        pct_long_target_0050=float(np.mean(np.array(loose) > 0)),
        pct_long_period_60=float(np.mean(np.array(slow) > 0)),
        target_is_live=bool(tight != base and loose != base),
        period_is_live=bool(slow != base),
    )
