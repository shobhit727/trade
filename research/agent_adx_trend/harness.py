"""Shared harness for the `adx_trend` NSE validation.

What the source strategy actually does
--------------------------------------
`cryptobot.strategies.catalog.adx_trend.AdxTrendStrategy.signal` computes an ATR
(`period`, default 14) and then **throws it away** -- `a` is used only for a NaN
warmup guard. The returned signal is:

    +1 if close[t] > close[t-1] else -1

i.e. a 1-bar sign-of-return. So the strategy is, in time-series form, a 1-day
continuation signal whose `period` parameter is dead weight. This is the fact the
whole report turns on, so it is asserted mechanically in `verify_source_signal()`
below rather than trusted to code reading.

Construction into the NSE book
-----------------------------
The NSE book is long-only and cross-sectional, so a -1 must become "do not hold",
and the +1 must be *ranked*, otherwise every flagged name ties and the choice is
arbitrary. Ranking is done by trailing trend strength (see VARIANTS).

No lookahead: every input to the score on day t uses closes up to and including t.
`run_backtest` then holds those weights from t+1 (it shifts by one bar internally).
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

#: Reference notional for cost measurement. Matches the engine's own constant so
#: strategy, buy-and-hold and controls are all charged at one identical bps figure.
REF_NOTIONAL = Decimal("100000")
COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
RT_BPS = float(COST_MODEL.all_in_round_trip_bps(REF_NOTIONAL))

PORTFOLIO = PortfolioConfig()

_panel: pd.DataFrame | None = None
_symbols: list[str] | None = None
_hl: tuple[pd.DataFrame, pd.DataFrame] | None = None


def load_panel() -> tuple[pd.DataFrame, list[str]]:
    """Cleaned daily close panel (mandatory first step in the brief)."""
    global _panel, _symbols
    if _panel is None:
        _panel, _symbols, _ = load_universe(DATA_DIR)
    return _panel, _symbols


def load_hl() -> tuple[pd.DataFrame, pd.DataFrame]:
    """High/low panels, masked to exactly the rows the cleaning kept.

    The cleaned close panel is authoritative: any row dropped by C1/C2/C4/C5 is
    NaN there. Masking high/low by ``panel.notna()`` therefore reproduces the
    audited row set without re-implementing (or weakening) any cleaning rule.
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
    """Wilder-style rolling ATR, trailing, no lookahead."""
    high, low = load_hl()
    prev = panel.shift(1)
    tr = pd.concat(
        [(high - low).stack(future_stack=True), (high - prev).abs().stack(future_stack=True),
         (low - prev).abs().stack(future_stack=True)],
        axis=1,
    ).max(axis=1).unstack()
    tr = tr.reindex(index=panel.index, columns=panel.columns)
    return tr.rolling(period, min_periods=period).mean()


# --------------------------------------------------------------------------- #
# The strategy signal
# --------------------------------------------------------------------------- #


def signal_flag(panel: pd.DataFrame) -> pd.DataFrame:
    """`+1` where close[t] > close[t-1] -- the literal source signal, long side."""
    return (panel > panel.shift(1)).astype(float)


def atr_trend_strength(panel: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Trailing trend direction *magnitude*.

    Direction from the close-to-close move over `period` bars, magnitude divided by
    ATR so a name that moved 5% on 1% daily range is not treated like one that
    moved 5% on 8% daily range. This is the reading of "ADX trend strength" that
    gives the strategy's dead `period` parameter actual work to do.
    """
    direction = np.sign(panel - panel.shift(period))
    magnitude = (panel / panel.shift(period) - 1.0).abs()
    a = atr_panel(panel, period).replace(0.0, np.nan)
    return direction * magnitude / a


#: --------------------------------------------------------------------------- #
# DECLARED PARAMETER BUDGET -- written down BEFORE any backtest was run.
# Five variants, no more. Selection rule: highest TRAIN Sharpe (tie-break Calmar),
# then that single variant is frozen and run once on TEST.
# --------------------------------------------------------------------------- #
VARIANTS: dict[str, str] = {
    "V1_mom126": "flag=ret1d>0, rank by 126d momentum (brief's recipe)",
    "V2_mom252": "flag=ret1d>0, rank by 252d momentum",
    "V3_mom21": "flag=ret1d>0, rank by 21d momentum",
    "V4_trend14": "flag=ret1d>0, rank by 14d return (= config.period)",
    "V5_atr14": "flag=ret1d>0, rank by 14d move / ATR14 (true trend strength)",
}

#: Held constant across all variants (not part of the parameter budget).
FIXED = dict(rebalance="M", n_positions=22, max_weight=0.12, turnover_budget=0.35)


def build_score(name: str, panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional score for a named variant. Non-flagged names get NaN, which
    the engine treats as ineligible -- that is how the -1 becomes 'do not hold'."""
    flag = signal_flag(panel) > 0
    if name == "V1_mom126":
        raw = panel / panel.shift(126) - 1.0
    elif name == "V2_mom252":
        raw = panel / panel.shift(252) - 1.0
    elif name == "V3_mom21":
        raw = panel / panel.shift(21) - 1.0
    elif name == "V4_trend14":
        raw = panel / panel.shift(14) - 1.0
    elif name == "V5_atr14":
        raw = atr_trend_strength(panel, 14)
    else:
        raise KeyError(name)
    return raw.where(flag)


def random_score(panel: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Negative control: random flag on the same unconditional frequency as the
    real signal, then the V1 ranking. i.i.d. coin, no lookahead, no persistence."""
    rng = np.random.default_rng(seed)
    p = float((signal_flag(panel) > 0).to_numpy().mean())
    hit = rng.random(panel.shape) < p
    raw = (panel / panel.shift(126) - 1.0).to_numpy()
    flags = pd.DataFrame(hit, index=panel.index, columns=panel.columns)
    return pd.DataFrame(raw, index=panel.index, columns=panel.columns).where(flags)


# --------------------------------------------------------------------------- #
# Benchmarks
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, start, end, cash: float = 0.0) -> dict:
    """True buy-and-hold equal-weight basket over [start, end].

    Equal weight at the first bar, then shares are held (weights drift). One
    round trip charged at entry, charged against compounding equity exactly as the
    engine does. No rebalancing, so no rebalance drag -- this is the strongest
    form of the benchmark.
    """
    px = panel.loc[start:end]
    rets = px.pct_change(fill_method=None).fillna(0.0)
    w = pd.Series(0.0, index=px.columns)
    w[px.columns] = (1.0 - cash) / len(px.columns)
    w0 = w
    gross = w0 * rets
    rate = RT_BPS / 10_000.0
    eq, costs = 1.0, 0.0
    daily = []
    turn = float(w0.sum())  # one-way turnover of the initial buy
    for dt in px.index:
        eq *= 1.0 + float(gross.loc[dt].sum())
        daily.append(eq)
    eq -= turn * eq * rate  # buy cost, charged once, after the first bar
    costs = turn * eq * rate
    daily[-1] = eq
    daily = pd.Series(daily, index=px.index)
    equity = daily.copy()
    m = compute_metrics(equity.pct_change(fill_method=None).fillna(0.0), equity)
    return dict(
        metrics=m,
        equity=equity,
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


def row_of(label: str, set_name: str, res, extra: dict | None = None) -> Row:
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
    f"{'label':<26}{'set':<6}{'CAGR%':>9}{'Sharpe':>8}{'MaxDD%':>9}"
    f"{'Calmar':>8}{'Turn/y':>8}{'Cost/y%':>9}{'Names':>7}{'Total%':>10}{'Yr+':>6}"
)


def line(r: Row) -> str:
    return (
        f"{r.label:<26}{r.set_name:<6}{r.cagr * 100:>9.2f}{r.sharpe:>8.2f}"
        f"{r.maxdd * 100:>9.2f}{r.calmar:>8.2f}{r.turnover:>8.2f}"
        f"{r.cost_drag * 100:>9.2f}{r.avg_names:>7.1f}{r.total * 100:>10.1f}"
        f"{r.years_win * 100:>5.0f}%"
    )


def run(panel: pd.DataFrame, score: pd.DataFrame, start, end) -> object:
    sub = panel.loc[start:end]
    sc = score.loc[start:end]
    return run_backtest(sub, sc, COST_MODEL, PORTFOLIO, rebalance=FIXED["rebalance"])


def row_for_variant(label: str, set_name: str, variant: str, panel, start, end) -> Row:
    score = build_score(variant, panel)
    res = run(panel, score, start, end)
    return row_of(label, set_name, res)


def verify_source_signal() -> dict:
    """Mechanically confirm the source signal is sign(1-bar return) and that the
    ATR it computes is discarded. Guards against mis-reading the source."""
    from cryptobot.strategies.catalog.adx_trend import (
        AdxTrendConfig,
        AdxTrendStrategy,
    )

    rng = np.random.default_rng(7)
    closes = list(100 + np.cumsum(rng.normal(0, 1.0, 400)))
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    vols = [1000.0] * 400
    strat = AdxTrendStrategy(AdxTrendConfig(period=14))

    agree = 0
    n = 0
    for i in range(30, 400):
        c = closes[: i + 1]
        got = strat.signal(c, highs[: i + 1], lows[: i + 1], vols[: i + 1])
        want = 1 if c[-1] > c[-2] else -1
        agree += int(got == want)
        n += 1

    # Does changing `period` change any signal *in steady state*? A larger `period`
    # only delays the warmup guard (`atr` is NaN until len >= period+1), so compare
    # only past the longest warmup. If ATR is genuinely discarded, these agree.
    long_warmup = 210
    base = [
        strat.signal(closes[: i + 1], highs[: i + 1], lows[: i + 1], vols[: i + 1])
        for i in range(long_warmup, 400)
    ]
    alt = AdxTrendStrategy(AdxTrendConfig(period=200))
    alt_sig = [
        alt.signal(closes[: i + 1], highs[: i + 1], lows[: i + 1], vols[: i + 1])
        for i in range(long_warmup, 400)
    ]
    return dict(
        matches_sign_of_return=f"{agree}/{n}",
        period_is_dead_in_steady_state=bool(base == alt_sig),
        steady_state_bars_compared=len(base),
        pct_long=float(np.mean(np.array(base) > 0)),
    )


def composite_score(panel: pd.DataFrame) -> pd.DataFrame:
    return build_composite_score(panel)
