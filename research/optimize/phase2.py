"""Phase 2 -- buffered cross-sectional rebalance.

Phase 1 isolated the binding constraint: a single-stock long/flat book spends ~55%
of its time in cash, and the only exposure bucket with a positive median CAGR is
the one above 60%. Cutting turnover 55x bought ~0.8%/yr and then stopped. Being
invested more is what matters.

A cross-sectional book fixes exposure by construction: rank the universe, always
hold the top N. But naive monthly rank-and-hold churns by construction, which is
what kills it on costs.

So: **hysteresis**. Sell a name only when it falls out of a wide exit band
(rank > N + buffer), not merely out of the top N. Entry is the tight top-N band,
exit is the loose outer band. Exposure decouples from turnover: ~100% invested,
~1 round trip per rebalance instead of n_hold.

Carries the signal-scrambled null, which Phase 1's documented multiple-comparison
problem (1 of 96 cells won post hoc) makes mandatory rather than optional.
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import splitter as S
from .metrics import compute

log = logging.getLogger(__name__)

CAP = float(C.CAPITAL_INR)
ONE_WAY = float(C.ALL_IN_ROUND_TRIP_BPS) / 2 / 10_000


# --------------------------------------------------------------------------- #
# Signals -- pure ranking functions.
#
# Phase 1 fed 16 catalog strategies as black boxes, each deciding its own
# entry/exit internally, so exposure was an accident of each strategy rather than
# a design choice. Here the signal only produces a ranking and the portfolio layer
# owns exposure entirely, which is what makes the cross-sectional comparison clean.
# --------------------------------------------------------------------------- #
def _momentum(px: pd.DataFrame) -> pd.DataFrame:
    """12-1 momentum: 12-month return excluding the most recent month.

    Skipping the last month is the standard construction -- naive 12-month momentum
    is contaminated by short-term reversal.
    """
    return px.pct_change(252) - px.pct_change(231)


def _trend(px: pd.DataFrame) -> pd.DataFrame:
    """Distance above the 200-day moving average."""
    return px / px.rolling(200, min_periods=100).mean() - 1.0


def _lowvol(px: pd.DataFrame) -> pd.DataFrame:
    """Negative annualised 63-day realised volatility: low vol ranks higher."""
    return -px.pct_change().rolling(63, min_periods=30).std() * np.sqrt(252)


def _reversal(px: pd.DataFrame) -> pd.DataFrame:
    """Negative 21-day return: the recent laggard ranks highest."""
    return -px.pct_change(21)


def _zcs(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score so heterogeneous signals can be weighted together."""
    m = df.mean(axis=1)
    s = df.std(axis=1).replace(0, np.nan)
    return df.sub(m, axis=0).div(s, axis=0).fillna(0.0)


def _composite(px: pd.DataFrame) -> pd.DataFrame:
    """Production composite: momentum, trend, low vol, reversal, liquidity-free."""
    z = _zcs(pd.concat(
        {"mom": _momentum(px), "trend": _trend(px),
         "lowvol": _lowvol(px), "rev": _reversal(px)},
        axis=1,
    ))
    # Final 0.20 is an intercept, not a factor: a constant ranks nothing, it only
    # keeps the composite from being dominated by whichever z has the fatter tails.
    return 0.30 * z["mom"] + 0.25 * z["trend"] + 0.15 * z["lowvol"] + 0.10 * z["rev"] + 0.20


def _scrambled(px: pd.DataFrame) -> pd.DataFrame:
    """The Phase 2 null: composite with each date's cross-section permuted.

    Preserves each date's score distribution while destroying any relationship
    between a symbol and its score. Isolates "is the ranking informative" from
    "did the market go up". Deliberately not a time-shift -- shifting in time
    smuggles real lagged information back in, so it is not a null.
    """
    base = np.array(_composite(px).to_numpy(), copy=True)
    rng = np.random.default_rng(20260101)
    for i in range(base.shape[0]):
        base[i] = rng.permutation(base[i])
    return pd.DataFrame(base, index=px.index, columns=px.columns)


SIGNALS = {
    "momentum": _momentum,
    "trend": _trend,
    "lowvol": _lowvol,
    "reversal": _reversal,
    "composite": _composite,
    "scrambled": _scrambled,
}

#: (n_hold, buffer) grid. n_hold fixes exposure; buffer fixes turnover. buffer=0 is
#: the naive rank-and-hold control that this whole phase is testing against.
GRID: tuple[tuple[int, int], ...] = (
    (10, 0), (10, 5), (10, 10), (10, 20),
    (15, 0), (15, 5), (15, 10), (15, 20),
    (20, 0), (20, 10), (20, 20),
)
CLOCKS: tuple[str, ...] = ("M", "Q", "2Q", "A")
WINDOWS = {"TRAIN": (C.TRAIN_START, C.TRAIN_END), "TEST": (C.TEST_START, C.TEST_END)}


@dataclass
class BookRow:
    signal: str
    rebalance: str
    n_hold: int
    buffer: int
    window: str
    cagr: float
    sharpe: float
    sortino: float
    max_dd: float
    calmar: float
    exposure: float
    turnover: float
    fees: float
    tax: float
    n_trades: int
    bh_cagr: float
    alpha: float


def run_book(
    panel: pd.DataFrame,
    signal: str,
    *,
    n_hold: int,
    buffer: int,
    rebalance: str,
    start: str,
    end: str,
) -> BookRow | None:
    """Equal-weight top-N book with a hysteresis exit band. Full cost + CGT stack."""
    from .backtest import rebalance_dates

    px = panel.loc[start:end]
    if px.empty or len(px) < 30:
        return None
    score = SIGNALS[signal](panel).loc[px.index].reindex(columns=px.columns)
    if score.isna().all().all():
        return None

    rdates = set(rebalance_dates(px.index, rebalance))
    live = px.notna() & (px > 0)

    qty: dict[str, float] = {}
    cost: dict[str, float] = {}          # symbol -> total cost basis in Rs
    age: dict[str, int] = {}             # symbol -> bars held
    cash = CAP
    invested_bars = 0
    fees = tax = 0.0
    trades = 0
    curve: list[float] = []

    for when in px.index:
        if when in rdates:
            row = score.loc[when]
            row = row[live.loc[when]].replace([np.inf, -np.inf], np.nan).dropna()
            if row.empty:
                ranked = []
            else:
                ranked = list(row.sort_values(ascending=False).index)
            # Exit band: the outer (n_hold + buffer) ranks. buffer=0 degenerates to
            # "sell anything that left the top N", i.e. the naive control.
            drop = set(ranked[n_hold + buffer:])
            keep = [s for s in qty if s not in drop]
            for sym in ranked:
                if len(keep) >= n_hold:
                    break
                if sym not in qty and sym not in keep:
                    keep.append(sym)
            target = set(keep)

            for sym in list(qty):
                if sym in target:
                    continue
                p = float(px.at[when, sym])
                gross = qty.pop(sym) * p
                f = gross * ONE_WAY
                gain = gross - cost.pop(sym, 0.0)
                # >365 calendar-ish days held is long-term for Indian CGT; bars are a
                # good proxy here (252 bars ~ 1 trading year).
                rate = float(C.LTCG_RATE) if age.pop(sym, 0) > 252 else float(C.STCG_RATE)
                t = max(gain, 0.0) * rate
                cash += gross - f - t
                fees += f
                tax += t
                trades += 1

            for sym in target:
                if sym in qty:
                    continue
                p = float(px.at[when, sym])
                if p <= 0:
                    continue
                slots = n_hold - len(qty)
                if slots <= 0:
                    break
                budget = min(cash / slots, CAP / n_hold)
                q = (budget * (1 - ONE_WAY)) / p
                if q <= 0:
                    continue
                f = q * p * ONE_WAY
                cash -= q * p + f
                qty[sym] = q
                cost[sym] = q * p + f
                age[sym] = 0
                fees += f
                trades += 1

        for sym in qty:
            age[sym] += 1
        if qty:
            invested_bars += 1
        curve.append(cash + sum(q * float(px.at[when, s]) for s, q in qty.items()))

    eq = pd.Series(curve, index=px.index)
    if len(eq) < 30 or eq.iloc[-1] <= 0:
        return None
    # One-way turnover: traded notional / average book, i.e. the convention the
    # single-stock engine uses. Deriving it here keeps the two harnesses comparable.
    turnover = (fees / ONE_WAY) / CAP if ONE_WAY else 0.0
    m = compute(eq,
                exposure=invested_bars / len(eq),
                turnover=turnover,
                total_fees=fees,
                total_tax=tax,
                n_trades=trades)

    bh = px.mean(axis=1).pct_change().fillna(0.0)
    bh_eq = CAP * (1 + bh).cumprod()
    bh_cagr = float(compute(bh_eq).cagr)

    return BookRow(
        signal=signal, rebalance=rebalance, n_hold=n_hold, buffer=buffer,
        window="", cagr=m.cagr, sharpe=m.sharpe, sortino=m.sortino,
        max_dd=m.max_drawdown, calmar=m.calmar, exposure=float(m.exposure),
        turnover=turnover, fees=fees, tax=tax, n_trades=trades,
        bh_cagr=bh_cagr, alpha=m.cagr - bh_cagr,
    )


def _job(args: tuple) -> BookRow | None:
    signal, clock, n_hold, buffer, window = args
    start, end = WINDOWS[window]
    try:
        panel = _panel()
        row = run_book(panel, signal, n_hold=n_hold, buffer=buffer,
                       rebalance=clock, start=start, end=end)
    except Exception as exc:  # pragma: no cover
        log.debug("%s %s %s/%s failed: %s", signal, clock, n_hold, buffer, exc)
        return None
    if row is not None:
        row.window = window
    return row


_PANEL: pd.DataFrame | None = None


def _panel() -> pd.DataFrame:
    """Close-price panel for the usable universe, built once per worker."""
    global _PANEL
    if _PANEL is None:
        frames = {}
        for sym in S.available_symbols("1d"):
            df = S.bars(sym, timeframe="1d")
            frames[sym] = df["close"]
        _PANEL = pd.DataFrame(frames).sort_index().ffill()
    return _PANEL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, default=Path("tem/phase2/rows.jsonl"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    tasks = [
        (sig, clock, n, b, win)
        for sig in SIGNALS
        for clock in CLOCKS
        for n, b in GRID
        for win in WINDOWS
    ]
    log.info("Phase 2: %d signals x %d clocks x %d grids x %d windows = %d runs",
             len(SIGNALS), len(CLOCKS), len(GRID), len(WINDOWS), len(tasks))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex, args.out.open("w") as fh:
        for i, row in enumerate(ex.map(_job, tasks, chunksize=4), 1):
            if row is None:
                continue
            fh.write(json.dumps(asdict(row)) + "\n")
            kept += 1
            if i % 100 == 0:
                log.info("  %d/%d (%d kept)", i, len(tasks), kept)
    log.info("kept %d -> %s", kept, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
