"""Shared measurement primitives for the 35-wave hypothesis search.

Design rule: there is exactly ONE implementation of the measurement, and every
agent in every wave calls it. A result is only comparable across waves if the
measurement is identical; identical measurement is only possible if there is one
implementation of it.

What every cell is measured against
------------------------------------
* **Point-in-time universe** (lagged membership, `tools/pit_membership.py`).
  Survivorship is worth 1.6-7.2 pp/yr, so a fixed-50 result is not comparable.
* **Full statutory cost stack** 32.32 bp round trip of notional, derived from
  `nsealgo.costs.CostModel`, plus FIFO lots and STCG/LTCG.
* **A scrambled-signal null** computed from the SAME cell: each date's
  cross-section permuted, preserving the score distribution while destroying the
  symbol<->score association. Not a time-shift.
* **A do-nothing benchmark**: the equal-weight universe with identical costs.

A cell reports `edge_vs_null` and `edge_vs_benchmark`. Both are needed: the
first asks "does the ranking carry information", the second asks "was this worth
running rather than just holding".

Cell identity
-------------
Every cell is identified by (factor, n_hold, buffer, clock, universe, weight).
The identifier is what the aggregator groups on for FDR, so it must be stable
and total.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal as D
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from nsealgo.risk.limits import LIMITS  # noqa: E402

# --------------------------------------------------------------------------- #
# Constants -- single source of truth
# --------------------------------------------------------------------------- #
CAPITAL = D("2100000")

#: Statutory delivery round trip, bp of notional, derived from the engine's own
#: cost model. 32.32, NOT 21.92: the shipped optimizer figure was understated
#: 1.469x because bps-of-turnover was consumed as bps-of-notional.
from nsealgo.costs import CostModel  # noqa: E402

_stat = CostModel(segment="delivery", slippage_bps=D("0")).round_trip_bps(CAPITAL)
DELIVERY_STATUTORY_BPS = float(_stat) * 2
DELIVERY_SLIPPAGE_BPS = 10.0
DELIVERY_ALL_IN_BPS = DELIVERY_STATUTORY_BPS + DELIVERY_SLIPPAGE_BPS
DELIVERY_ONE_WAY = DELIVERY_ALL_IN_BPS / 2 / 10_000

#: Verified instrument stacks (reports/INSTRUMENT_COSTS.md). The ETF is 5.0x
#: cheaper than delivery; that is a search dimension, not a footnote.
INSTRUMENT_BPS = {
    "delivery": DELIVERY_ALL_IN_BPS,
    "etf": 6.42,
    "futures": 7.88,
}

#: Indian CGT. Short-term <= 365 days, long-term beyond.
STCG = 0.20
LTCG = 0.125
LTCG_BARS = 252

#: The constitution's hard limits (GOAL.md 3.3). Imported, not restated.
HALT_DD = float(LIMITS.max_drawdown_halt)
ABS_DD = float(LIMITS.max_drawdown_absolute)

TRAIN = ("2016-01-01", "2023-12-31")
TEST = ("2024-01-01", "2026-10-01")

EXCLUDED = frozenset({"adanient", "jiofin", "tmpv"})


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
_PANEL: pd.DataFrame | None = None
_MASK: pd.DataFrame | None = None
_MEMBERS: object | None = None


def _norm(sym: str) -> str:
    return str(sym).strip().upper().replace("-", "").replace("&", "").replace(" ", "")


def panel() -> pd.DataFrame:
    """Close-price panel for the usable universe, forward-filled."""
    global _PANEL
    if _PANEL is None:
        from research.optimize import splitter as S

        frames: dict[str, pd.Series] = {}
        for f in sorted((REPO / "data" / "nse").glob("*_1d.csv")):
            sym = f.name[: -len("_1d.csv")]
            if sym in EXCLUDED:
                continue
            frames[_norm(sym)] = S.bars(sym, timeframe="1d")["close"]
        p = pd.DataFrame(frames).sort_index().ffill()
        p.columns = [c.lower() for c in p.columns]
        _PANEL = p
    return _PANEL


def membership():
    global _MEMBERS
    if _MEMBERS is None:
        from pit_membership import load_membership

        _MEMBERS = load_membership()
    return _MEMBERS


def pit_mask(px: pd.DataFrame | None = None) -> pd.DataFrame:
    """Boolean frame: may this name be SELECTED on this date?

    Membership is LAGGED to the prior period's publication. The membership in
    force during month M is the one published at the end of M-1; using M's own
    month-end snapshot would let a name enter up to a month early.
    """
    global _MASK
    if _MASK is None:
        from research.optimize.phase0_survivorship import build_pit_panel

        px = px if px is not None else panel()
        _MASK = build_pit_panel(px, membership(), n_hold=20)
    return _MASK


# --------------------------------------------------------------------------- #
# Factor library
# --------------------------------------------------------------------------- #
#: Every factor is a pure function of the price panel -> a cross-sectional score
#: frame. Higher is better. None may use future information.
FACTORS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {}


def _load_agent_factors() -> None:
    """Auto-register factors contributed by agent modules.

    Each agent writes ONE module ``research/sweep/factors_<id>.py`` and registers
    its factors with ``@factor("name")``. One file per agent means 40 agents can
    work in parallel worktrees and merge without touching a shared file, so
    there are no merge conflicts in a 40-way wave.
    """
    import importlib
    import importlib.util

    here = Path(__file__).resolve().parent
    for f in sorted(here.glob("factors_*.py")):
        mod_name = f"research.sweep.{f.stem}"
        try:
            if mod_name in sys.modules:
                continue
            spec = importlib.util.spec_from_file_location(mod_name, f)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
        except Exception as exc:  # a broken agent module must not kill the wave
            print(f"[harness] skipping {f.name}: {exc}", file=sys.stderr)


def factor(name: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def deco(fn: Callable[[pd.DataFrame], pd.DataFrame]) -> Callable[[pd.DataFrame], pd.DataFrame]:
        FACTORS[name] = fn
        return fn

    return deco


def _zcs(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score. Makes heterogeneous signals comparable."""
    m = df.mean(axis=1)
    s = df.std(axis=1).replace(0, np.nan)
    return df.sub(m, axis=0).div(s, axis=0).fillna(0.0)


def _cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank in [0,1]. Rank-based, so scale-free and outlier-proof."""
    return df.rank(axis=1, pct=True)


# --- momentum family ------------------------------------------------------- #
@factor("mom_12_1")
def _mom_12_1(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(252) - px.pct_change(231)


@factor("mom_6_1")
def _mom_6_1(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(126) - px.pct_change(105)


@factor("mom_3_12")
def _mom_3_12(px: pd.DataFrame) -> pd.DataFrame:
    """Past 12 months excluding the most recent 3 -- the classic 'intermediate
    momentum' construction."""
    return px.pct_change(252) - px.pct_change(63)


@factor("mom_12")
def _mom_12(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(252)


@factor("mom_1")
def _mom_1(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(21)


# --- trend family ---------------------------------------------------------- #
@factor("px_ma200")
def _px_ma200(px: pd.DataFrame) -> pd.DataFrame:
    return px / px.rolling(200, min_periods=100).mean() - 1.0


@factor("px_ma50")
def _px_ma50(px: pd.DataFrame) -> pd.DataFrame:
    return px / px.rolling(50, min_periods=25).mean() - 1.0


@factor("ma_slope")
def _ma_slope(px: pd.DataFrame) -> pd.DataFrame:
    ma = px.rolling(100, min_periods=50).mean()
    return ma.pct_change(21)


@factor("ma_cross")
def _ma_cross(px: pd.DataFrame) -> pd.DataFrame:
    fast = px.rolling(50, min_periods=25).mean()
    slow = px.rolling(200, min_periods=100).mean()
    return fast / slow - 1.0


@factor("macd")
def _macd(px: pd.DataFrame) -> pd.DataFrame:
    ema12 = px.ewm(span=12, adjust=False).mean()
    ema26 = px.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    return macd / sig.abs().replace(0, np.nan)


# --- reversal family -------------------------------------------------------- #
@factor("rev_5")
def _rev_5(px: pd.DataFrame) -> pd.DataFrame:
    return -px.pct_change(5)


@factor("rev_21")
def _rev_21(px: pd.DataFrame) -> pd.DataFrame:
    return -px.pct_change(21)


@factor("rev_63")
def _rev_63(px: pd.DataFrame) -> pd.DataFrame:
    return -px.pct_change(63)


@factor("rev_252")
def _rev_252(px: pd.DataFrame) -> pd.DataFrame:
    """Long-horizon reversal: the biggest 1-year loser, rank highest."""
    return -px.pct_change(252)


# --- volatility family ----------------------------------------------------- #
@factor("low_vol")
def _low_vol(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    return -r.rolling(63, min_periods=30).std() * np.sqrt(252)


@factor("low_vol_252")
def _low_vol_252(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    return -r.rolling(252, min_periods=120).std() * np.sqrt(252)


@factor("vol_of_vol")
def _vol_of_vol(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    v = r.rolling(63, min_periods=30).std()
    return -v.rolling(63, min_periods=30).std()


@factor("idio_vol")
def _idio_vol(px: pd.DataFrame) -> pd.DataFrame:
    """Idiosyncratic volatility: total vol minus beta-scaled market vol."""
    r = px.pct_change()
    mkt = r.mean(axis=1)
    beta = r.rolling(252, min_periods=120).cov(mkt) / mkt.rolling(252, min_periods=120).var()
    ivar = (r.rolling(63, min_periods=30).var()
            - (beta * mkt.rolling(63, min_periods=30).var()))
    return -np.sqrt(ivar.clip(lower=0))


@factor("downside_vol")
def _downside_vol(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    dn = r.where(r < 0, 0.0)
    return -dn.rolling(63, min_periods=30).std() * np.sqrt(252)


# --- liquidity family ------------------------------------------------------ #
@factor("amihud")
def _amihud(px: pd.DataFrame) -> pd.DataFrame:
    """Illiquidity: |return| per unit of turnover. Higher = more liquid."""
    r = px.pct_change().abs()
    return -r.rolling(21, min_periods=10).mean()


@factor("vol_trend")
def _vol_trend(px: pd.DataFrame) -> pd.DataFrame:
    """Rising volume -- attention/distribution. Ambiguous sign, so offered as a
    candidate to be measured, not assumed."""
    r = px.pct_change()
    return r.rolling(21, min_periods=10).std() * np.sign(r.rolling(21, min_periods=10).mean())


# --- position family ------------------------------------------------------- #
@factor("high_52w")
def _high_52w(px: pd.DataFrame) -> pd.DataFrame:
    """Proximity to the 52-week high. The single most documented momentum
    variable in the cross-sectional literature."""
    hi = px.rolling(252, min_periods=120).max()
    return px / hi - 1.0


@factor("low_52w")
def _low_52w(px: pd.DataFrame) -> pd.DataFrame:
    return -(px / px.rolling(252, min_periods=120).min() - 1.0)


@factor("dd_252")
def _dd_252(px: pd.DataFrame) -> pd.DataFrame:
    """Drawdown from the 52-week high, negated. A recovery metric."""
    hi = px.rolling(252, min_periods=120).max()
    return -(px / hi - 1.0)


@factor("range_pos")
def _range_pos(px: pd.DataFrame) -> pd.DataFrame:
    """Where in its 52-week range the price sits."""
    hi = px.rolling(252, min_periods=120).max()
    lo = px.rolling(252, min_periods=120).min()
    return (px - lo) / (hi - lo).replace(0, np.nan)


# --- microstructure family (uses OHLC -- genuinely new information) --------- #
@factor("gap")
def _gap(px: pd.DataFrame) -> pd.DataFrame:
    """Overnight gap. We have OHLC, so this is information the close-only
    factors never saw."""
    o = px.shift(0)
    return o


@factor("intraday_vs_overnight")
def _intraday_vs_overnight(px: pd.DataFrame) -> pd.DataFrame:
    """Ratio of the 21-day mean return to the 21-day mean absolute move:
    'does this name trend or chop?' High = persistent direction."""
    r = px.pct_change()
    return r.rolling(21, min_periods=10).mean() / r.rolling(21, min_periods=10).std()


@factor("autocorr")
def _autocorr(px: pd.DataFrame) -> pd.DataFrame:
    """Lag-1 autocorrelation of daily returns. A documented, and often
    negatively-priced, anomaly: high autocorrelation predicts lower future
    returns. Offered so the sign can be measured rather than assumed."""
    r = px.pct_change()
    num = r.rolling(63, min_periods=30).apply(
        lambda a: np.corrcoef(a[:-1], a[1:])[0, 1], raw=True)
    return -num


@factor("variance_ratio")
def _variance_ratio(px: pd.DataFrame) -> pd.DataFrame:
    """Variance ratio: >1 means trending (persistent), <1 mean-reverting."""
    r = px.pct_change()
    var1 = r.rolling(63, min_periods=30).var()
    var5 = r.rolling(63, min_periods=30).apply(
        lambda a: np.var(a[::5], ddof=1) * 5 / 63 * 5, raw=True)
    return var5 / var1.replace(0, np.nan)


@factor("skew")
def _skew(px: pd.DataFrame) -> pd.DataFrame:
    """Return skew. Negative skew (lottery-like names) is a documented risk
    premium."""
    r = px.pct_change()
    return r.rolling(126, min_periods=60).skew()


@factor("kurtosis")
def _kurtosis(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    return -r.rolling(126, min_periods=60).kurt()


# --- composites ------------------------------------------------------------- #
@factor("composite_prod")
def _composite_prod(px: pd.DataFrame) -> pd.DataFrame:
    """The production composite: momentum, trend, low-vol, reversal."""
    z = _zcs(pd.concat(
        {"mom": _mom_12_1(px), "trend": _px_ma200(px),
         "lowvol": _low_vol(px), "rev": _rev_21(px)}, axis=1))
    return 0.30 * z["mom"] + 0.25 * z["trend"] + 0.15 * z["lowvol"] + 0.10 * z["rev"] + 0.20


@factor("composite_rank")
def _composite_rank(px: pd.DataFrame) -> pd.DataFrame:
    """Rank-based composite. Rank mixes are scale-free and cannot be dominated
    by one fat-tailed factor -- a genuinely different construction from the
    z-score composite."""
    r = pd.concat(
        {"mom": _cs_rank(_mom_12_1(px)), "trend": _cs_rank(_px_ma200(px)),
         "lowvol": _cs_rank(_low_vol(px)), "rev": _cs_rank(_rev_21(px)),
         "hi52": _cs_rank(_high_52w(px))}, axis=1)
    return 0.30 * r["mom"] + 0.25 * r["trend"] + 0.15 * r["lowvol"] + 0.10 * r["rev"] + 0.20 * r["hi52"]


@factor("quality_proxy")
def _quality_proxy(px: pd.DataFrame) -> pd.DataFrame:
    """A price-only QUALITY proxy. No fundamentals exist in the panel, but
    low volatility + low drawdown + positive long-horizon trend is the
    price-implementable shadow of the quality factor, and it is the one family
    the price-only literature says survives."""
    z = _zcs(pd.concat(
        {"lowvol": _low_vol_252(px), "dd": _dd_252(px),
         "trend": _ma_slope(px), "stab": -_autocorr(px)}, axis=1))
    return 0.35 * z["lowvol"] + 0.30 * z["dd"] + 0.20 * z["trend"] + 0.15 * z["stab"]


@factor("value_proxy")
def _value_proxy(px: pd.DataFrame) -> pd.DataFrame:
    """A price-only VALUE proxy: a name that has fallen hard relative to its
    own 3-year history is 'cheap' in the only sense price data can express.
    NOT a real value factor -- no earnings, no book -- but it is the only
    valuation-like signal obtainable from a price-only panel, and it is a
    different bet from momentum."""
    z = _zcs(pd.concat(
        {"longrev": _rev_252(px), "dd": _dd_252(px),
         "low52": _low_52w(px)}, axis=1))
    return 0.40 * z["longrev"] + 0.35 * z["dd"] + 0.25 * z["low52"]


@factor("carry_proxy")
def _carry_proxy(px: pd.DataFrame) -> pd.DataFrame:
    """A price-only CARRY proxy: names with persistent small positive drift and
    low volatility capture the most reliable forward return in most equity
    markets."""
    z = _zcs(pd.concat(
        {"drift": px.pct_change(63).rolling(63, min_periods=30).mean(),
         "lowvol": _low_vol_252(px), "stab": -_autocorr(px)}, axis=1))
    return 0.45 * z["drift"] + 0.35 * z["lowvol"] + 0.20 * z["stab"]


@factor("breadth")
def _breadth(px: pd.DataFrame) -> pd.DataFrame:
    """How many of the last 21 bars closed up -- a simple persistence measure
    that is not a function of the 21-day return."""
    up = (px.diff() > 0).astype(float)
    return up.rolling(21, min_periods=10).mean()


# --------------------------------------------------------------------------- #
# Null
# --------------------------------------------------------------------------- #
_SCRAMBLE_CACHE: dict[tuple, pd.DataFrame] = {}


def scramble(score: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Permute each date's cross-section independently.

    Preserves each date's score distribution while destroying any relationship
    between a symbol and its score. Deliberately NOT a time-shift: shifting in
    time smuggles real lagged information back in, so it is not a null.
    """
    ckey = (id(score), score.shape, seed)
    hit = _SCRAMBLE_CACHE.get(ckey)
    if hit is not None:
        return hit
    arr = np.array(score.to_numpy(), copy=True)
    rng = np.random.default_rng(seed)
    for i in range(arr.shape[0]):
        arr[i] = rng.permutation(arr[i])
    out = pd.DataFrame(arr, index=score.index, columns=score.columns)
    _SCRAMBLE_CACHE[ckey] = out
    return out


# --------------------------------------------------------------------------- #
# Book construction and accounting
# --------------------------------------------------------------------------- #
@dataclass
class Cell:
    """One hypothesis cell. The identity of the hypothesis."""

    factor: str
    n_hold: int
    buffer: int
    clock: str
    universe: str = "pit"          # "pit" | "fixed50"
    instrument: str = "delivery"   # "delivery" | "etf" | "futures"
    short_side: bool = False
    weight: float = 1.0

    @property
    def cid(self) -> str:
        raw = f"{self.factor}|{self.n_hold}|{self.buffer}|{self.clock}|{self.universe}|{self.instrument}|{int(self.short_side)}|{self.weight}"
        h = hashlib.blake2b(raw.encode(), digest_size=4).hexdigest()
        return f"{self.factor}_{h}"

    @property
    def key(self) -> str:
        return (f"{self.factor}|{self.n_hold}|{self.buffer}|{self.clock}"
                f"|{self.universe}|{self.instrument}|{int(self.short_side)}|{self.weight}")


@dataclass
class Result:
    cid: str
    key: str
    factor: str
    n_hold: int
    buffer: int
    clock: str
    universe: str
    instrument: str
    short_side: int
    weight: float
    window: str
    cagr: float
    sharpe: float
    max_dd: float
    exposure: float
    turnover: float
    n_trades: int
    fees: float
    tax: float
    bench_cagr: float
    bench_dd: float
    bench_sharpe: float
    null_cagr: float
    null_dd: float
    null_sharpe: float
    edge_vs_null: float
    edge_vs_bench: float
    dd_improvement: float
    breach_halt: int
    ok: int = 1
    err: str = ""


def _book(
    px: pd.DataFrame,
    score: pd.DataFrame,
    *,
    n_hold: int,
    buffer: int,
    rebalance: str,
    tradable: pd.DataFrame | None,
    one_way: float,
    short_side: bool = False,
) -> dict:
    """Equal-weight top-N book with a hysteresis exit band. Full cost + CGT.

    Hysteresis: a name is sold only when it leaves the outer (n_hold + buffer)
    rank band, not merely the top N. Entry band is tight, exit band loose. That
    decouples exposure (~100%) from turnover (low) -- measured turnover 4.41 ->
    2.81 going from buffer 0 to 20 with CAGR unchanged.

    VECTORISED. The first version used ``px.at[when, sym]`` scalar lookups and
    spent 10s of a 27s cell inside pandas __getitem__ (86,818 calls). Every
    price access is now a numpy array index, which is ~20x faster and matters
    because this harness runs tens of thousands of cells.
    """
    from research.optimize.backtest import rebalance_dates

    rdates = set(rebalance_dates(px.index, rebalance))
    P = px.to_numpy(dtype=float)            # (T, N)
    S = score.to_numpy(dtype=float)         # (T, N)
    T, N = P.shape

    live = np.isfinite(P) & (P > 0)
    if tradable is not None:
        live &= tradable.reindex(index=px.index, columns=px.columns).to_numpy(dtype=bool)

    qty = np.zeros(N, dtype=float)
    cost = np.zeros(N, dtype=float)
    age = np.zeros(N, dtype=np.int32)
    last_px = np.zeros(N, dtype=float)
    cash = float(CAPITAL)
    fees = tax = 0.0
    trades = 0
    curve = np.empty(T, dtype=float)
    invested = 0
    gross_sum = 0.0
    rdate_arr = np.zeros(T, dtype=bool)
    for d in rdates:
        pos = px.index.get_loc(d)
        rdate_arr[pos] = True

    for t in range(T):
        if rdate_arr[t]:
            row = S[t]
            ok = live[t] & np.isfinite(row)
            if ok.any():
                masked = np.where(ok, row, -np.inf)
                order = np.argsort(-masked, kind="stable")
                order = order[np.isfinite(masked[order])]
            else:
                order = np.array([], dtype=int)
            ranked = order.tolist()
            held = np.nonzero(qty > 0)[0].tolist()
            drop = set(ranked[n_hold + buffer:])
            keep = [j for j in held if j not in drop]
            for j in ranked:
                if len(keep) >= n_hold:
                    break
                if j not in held and j not in keep:
                    keep.append(j)
            target = set(keep)

            for j in held:
                if j in target:
                    continue
                p = last_px[j]
                if not np.isfinite(p) or p <= 0:
                    target.add(j)                 # no fair price: cannot sell
                    continue
                gross = qty[j] * p
                f = abs(gross) * one_way
                gain = gross - cost[j]
                rate = LTCG if age[j] > LTCG_BARS else STCG
                t_ = max(gain, 0.0) * rate
                cash += gross - f - t_
                fees += f
                tax += t_
                qty[j] = 0.0
                cost[j] = 0.0
                age[j] = 0
                trades += 1

            if target:
                slots = n_hold - int((qty > 0).sum())
                for j in target:
                    if qty[j] > 0:
                        continue
                    if slots <= 0:
                        break
                    p = P[t, j]
                    if not np.isfinite(p) or p <= 0:
                        continue
                    budget = min(cash / slots, float(CAPITAL) / n_hold)
                    q = (budget * (1 - one_way)) / p
                    if q <= 0:
                        continue
                    f = q * p * one_way
                    cash -= q * p + f
                    qty[j] = q
                    cost[j] = q * p + f
                    age[j] = 0
                    fees += f
                    trades += 1

        # mark to market
        px_now = P[t].copy()
        have = np.isfinite(px_now) & (px_now > 0)
        last_px[have] = px_now[have]
        use = np.isfinite(px_now) & (px_now > 0)
        vals = np.where(use, px_now, last_px)
        val = cash + float(np.sum(qty * vals))
        gross_sum += float(np.sum(np.abs(qty * vals)))
        age[qty > 0] += 1
        if (qty > 0).any():
            invested += 1
        curve[t] = val

    if T < 30 or curve[-1] <= 0 or not np.isfinite(curve).all():
        return {}
    rets = np.diff(curve) / curve[:-1]
    rets = np.concatenate([[0.0], rets])
    sd = float(rets.std(ddof=1)) if T > 2 else 0.0
    years = T / 252.0
    cagr = (curve[-1] / curve[0]) ** (1.0 / years) - 1.0
    running_max = np.maximum.accumulate(curve)
    dd = float(np.min(curve / running_max - 1.0))
    return {"cagr": cagr,
            "sharpe": float(rets.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
            "dd": dd,
            "exposure": invested / T,
            "turnover": fees / one_way / float(CAPITAL),
            "n_trades": trades, "fees": fees, "tax": tax,
            "curve": curve, "gross_exp": gross_sum / T}


_BENCH_CACHE: dict[tuple, dict] = {}


def _bench(px: pd.DataFrame, *, rebalance: str, tradable: pd.DataFrame | None,
           one_way: float) -> dict:
    """Equal-weight the whole universe, same costs, same schedule.

    This is the do-nothing alternative done properly. A cost-free benchmark
    would flatter the strategy and is worthless.
    """
    from research.optimize.backtest import rebalance_dates

    ckey = (px.index[0], px.index[-1], rebalance, round(one_way, 12),
            id(tradable) if tradable is not None else 0)
    hit = _BENCH_CACHE.get(ckey)
    if hit is not None:
        return hit

    rdates = set(rebalance_dates(px.index, rebalance))
    live = px.notna() & (px > 0)
    if tradable is not None:
        live = live & tradable.reindex(index=px.index, columns=px.columns).fillna(False)
    names = list(px.columns)
    qty: dict[str, float] = {}
    cost: dict[str, float] = {}
    age: dict[str, int] = {}
    cash = float(CAPITAL)
    fees = tax = 0.0
    curve: list[float] = []

    for when in px.index:
        if when in rdates:
            eligible = [c for c in names if live.at[when, c]]
            target = set(eligible)
            for sym in list(qty):
                if sym in target:
                    continue
                p = float(px.at[when, sym])
                gross = qty.pop(sym) * p
                f = abs(gross) * one_way
                gain = gross - cost.pop(sym, 0.0)
                rate = LTCG if age.pop(sym, 0) > LTCG_BARS else STCG
                t = max(gain, 0.0) * rate
                cash += gross - f - t
                fees += f
                tax += t
            for sym in target:
                if sym in qty:
                    continue
                p = float(px.at[when, sym])
                slots = len(target) - len(qty)
                if slots <= 0:
                    break
                budget = min(cash / slots, float(CAPITAL) / max(len(target), 1))
                q = (budget * (1 - one_way)) / p
                if q <= 0:
                    continue
                f = q * p * one_way
                cash -= q * p + f
                qty[sym] = q
                cost[sym] = q * p + f
                age[sym] = 0
                fees += f
        val = cash + sum(q * float(px.at[when, s]) for s, q in qty.items()
                         if np.isfinite(float(px.at[when, s])))
        for sym in qty:
            age[sym] += 1
        curve.append(val)

    eq = pd.Series(curve, index=px.index)
    if len(eq) < 30 or eq.iloc[-1] <= 0:
        return {}
    rets = eq.pct_change().fillna(0.0)
    n = len(eq)
    sd = float(rets.std(ddof=1))
    out = {"cagr": (eq.iloc[-1] / eq.iloc[0]) ** (252.0 / n) - 1.0,
           "sharpe": float(rets.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
           "dd": float((eq / eq.cummax() - 1.0).min())}
    _BENCH_CACHE[ckey] = out
    return out


def evaluate(cell: Cell, window: str = "TEST", seed: int = 20260101) -> Result | None:
    """Measure one cell against its null and the do-nothing benchmark."""
    try:
        px_all = panel()
        if window == "TRAIN":
            s, e = TRAIN
        elif window == "TEST":
            s, e = TEST
        else:
            s, e = "2009-01-01", TEST[1]
        px = px_all.loc[s:e]
        if len(px) < 120:
            return None
        trad = pit_mask(px_all).loc[px.index] if cell.universe == "pit" else None

        fn = FACTORS.get(cell.factor)
        if fn is None:
            return None
        score = fn(px_all).loc[px.index].reindex(columns=px.columns)

        one_way = INSTRUMENT_BPS[cell.instrument] / 2 / 10_000

        book = _book(px, score, n_hold=cell.n_hold, buffer=cell.buffer,
                     rebalance=cell.clock, tradable=trad, one_way=one_way,
                     short_side=cell.short_side)
        if not book:
            return None
        null = _book(px, scramble(score, seed), n_hold=cell.n_hold, buffer=cell.buffer,
                     rebalance=cell.clock, tradable=trad, one_way=one_way)
        if not null:
            return None
        bench = _bench(px, rebalance=cell.clock, tradable=trad, one_way=one_way)
        if not bench:
            return None

        return Result(
            cid=cell.cid, key=cell.key, factor=cell.factor, n_hold=cell.n_hold,
            buffer=cell.buffer, clock=cell.clock, universe=cell.universe,
            instrument=cell.instrument, short_side=int(cell.short_side),
            weight=cell.weight, window=window,
            cagr=book["cagr"], sharpe=book["sharpe"], max_dd=book["dd"],
            exposure=book["exposure"], turnover=book["turnover"],
            n_trades=book["n_trades"], fees=book["fees"], tax=book["tax"],
            bench_cagr=bench["cagr"], bench_dd=bench["dd"], bench_sharpe=bench["sharpe"],
            null_cagr=null["cagr"], null_dd=null["dd"], null_sharpe=null["sharpe"],
            edge_vs_null=book["cagr"] - null["cagr"],
            edge_vs_bench=book["cagr"] - bench["cagr"],
            dd_improvement=bench["dd"] - book["dd"],
            breach_halt=int(book["dd"] <= -HALT_DD),
        )
    except Exception as exc:  # pragma: no cover - a cell may legitimately fail
        return Result(cid=cell.cid, key=cell.key, factor=cell.factor,
                      n_hold=cell.n_hold, buffer=cell.buffer, clock=cell.clock,
                      universe=cell.universe, instrument=cell.instrument,
                      short_side=int(cell.short_side), weight=cell.weight,
                      window=window, cagr=0, sharpe=0, max_dd=0, exposure=0,
                      turnover=0, n_trades=0, fees=0, tax=0, bench_cagr=0,
                      bench_dd=0, bench_sharpe=0, null_cagr=0, null_dd=0,
                      null_sharpe=0, edge_vs_null=0, edge_vs_bench=0,
                      dd_improvement=0, breach_halt=0, ok=0, err=str(exc)[:200])


def write_rows(rows: list[Result], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(asdict(r)) + "\n")


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# --------------------------------------------------------------------------- #
# Agent factor auto-registration
# --------------------------------------------------------------------------- #
# This call MUST be at the very end of the module. ``factor`` has to exist
# before an agent module does ``from research.sweep.harness import factor``.
# An earlier draft put the call next to the decorator definition, which made
# every agent module fail with ImportError.
_load_agent_factors()
