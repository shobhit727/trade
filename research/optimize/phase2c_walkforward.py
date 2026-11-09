"""Phase 2c -- walk-forward validation of the trend cross-sectional book.

Phase 2 produced one candidate that beat its scrambled null in both windows:

    trend signal, annual clock, N=20, buffer=20
    TRAIN +21.65% -> TEST +10.56%, Sharpe 0.68, alpha +3.79% vs null

That is a single TEST observation over 2.75 years. Three things could still be
wrong with it, and this module tests each:

1. **The window is doing the work.** If the edge only exists in 2024-2026, it is
   not an edge. Walk-forward with a rolling re-fit is the check.

2. **The universe is a lie.** We backtest today's NIFTY-50 members, so every
   result carries the measured ~8.9 pp/yr survivorship bias. `tools/pit_membership.py`
   provides point-in-time membership so the universe can be date-varying.

3. **The drawdown is unacceptable.** MaxDD -23.4% is worse than a plain
   single-stock book's ~-13%. A cross-sectional book should be *less* risky, not
   more, because it holds 20 names at once.

Everything here re-derives its own numbers and re-checks the null. No stored
result is reused.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import splitter as S
from .metrics import compute
from .phase2 import CAP, ONE_WAY, _composite, _trend

log = logging.getLogger(__name__)

SIGNAL_FN = {"trend": _trend, "composite": _composite}


@dataclass
class WFRow:
    tag: str
    signal: str
    n_hold: int
    buffer: int
    universe: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    cagr: float
    sharpe: float
    max_dd: float
    exposure: float
    turnover: float
    fees: float
    tax: float
    n_trades: int
    bh_cagr: float
    alpha: float


def _book(
    px: pd.DataFrame,
    score: pd.DataFrame,
    *,
    n_hold: int,
    buffer: int,
    rebalance: str,
    tradable: pd.DataFrame | None = None,
) -> tuple[pd.Series, float, float, int, float, float]:
    """Same construction as Phase 2, factored out so nulls and WF share it.

    `tradable` is an optional boolean frame marking which names may be *selected*
    on each date (Phase 0 uses it for point-in-time membership). It gates entry
    and ranking only. A name already held is still valued at its observed price
    even if it later becomes unselectable -- otherwise a name dropped from the
    index mid-hold would poison the equity curve with NaN.
    """
    from .backtest import rebalance_dates

    rdates = set(rebalance_dates(px.index, rebalance))
    live = px.notna() & (px > 0)
    if tradable is not None:
        live = live & tradable.reindex(index=px.index, columns=px.columns).fillna(False)
    qty: dict[str, float] = {}
    cost: dict[str, float] = {}
    age: dict[str, int] = {}
    cash = CAP
    fees = tax = 0.0
    trades = 0
    curve: list[float] = []
    invested = 0
    last_px: dict[str, float] = {}   # carry-forward for a held name with no fresh quote

    for when in px.index:
        if when in rdates:
            row = score.loc[when]
            row = row[live.loc[when]].replace([np.inf, -np.inf], np.nan).dropna()
            ranked = list(row.sort_values(ascending=False).index) if len(row) else []
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
                p = last_px.get(sym)
                if p is None or not np.isfinite(p) or p <= 0:
                    # No price anywhere in the series: cannot sell at a fair value.
                    # Carry the position rather than fabricate an exit.
                    target.add(sym)
                    continue
                gross = qty.pop(sym) * p
                f = gross * ONE_WAY
                gain = gross - cost.pop(sym, 0.0)
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
                if not np.isfinite(p) or p <= 0:
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
        val = cash
        for sym, q in qty.items():
            p = float(px.at[when, sym])
            if np.isfinite(p) and p > 0:
                last_px[sym] = p
            else:
                p = last_px.get(sym)
                if p is None:
                    continue        # never had a price; contributes nothing
            val += q * p
        for sym in qty:
            age[sym] += 1
        if qty:
            invested += 1
        curve.append(val)

    eq = pd.Series(curve, index=px.index)
    return eq, fees, tax, trades, invested / max(len(eq), 1), fees / ONE_WAY / CAP


def _one(
    px: pd.DataFrame,
    score: pd.DataFrame,
    signal: str,
    n_hold: int,
    buffer: int,
    start: str,
    end: str,
    tag: str,
    universe: str,
    tstart: str,
    tend: str,
) -> WFRow | None:
    w = px.loc[start:end]
    if w.empty or len(w) < 60:
        return None
    sc = score.loc[w.index].reindex(columns=w.columns)
    eq, fees, tax, trades, exp, to = _book(
        w, sc, n_hold=n_hold, buffer=buffer, rebalance="A"
    )
    if len(eq) < 60 or eq.iloc[-1] <= 0:
        return None
    m = compute(eq, exposure=exp, turnover=to, total_fees=fees, total_tax=tax, n_trades=trades)
    bh = w.mean(axis=1).pct_change().fillna(0.0)
    bh_cagr = float(compute(CAP * (1 + bh).cumprod()).cagr)
    return WFRow(
        tag=tag, signal=signal, n_hold=n_hold, buffer=buffer, universe=universe,
        train_start=tstart, train_end=tend, test_start=start, test_end=end,
        cagr=m.cagr, sharpe=m.sharpe, max_dd=m.max_drawdown, exposure=exp,
        turnover=to, fees=fees, tax=tax, n_trades=trades,
        bh_cagr=bh_cagr, alpha=m.cagr - bh_cagr,
    )


def rolling_wf(px: pd.DataFrame, score: pd.DataFrame, signal: str,
               n_hold: int, buffer: int, years: int = 3) -> list[WFRow]:
    """Re-fit each year, trade the next year. Params are NOT re-selected.

    Selection happens once, on the first fold. Later folds reuse those params
    deliberately: re-picking per fold would let each year choose its own winner and
    turn the walk-forward into 11 independent in-sample searches.
    """
    from .phase2 import _scrambled

    rows: list[WFRow] = []
    start = pd.Timestamp("2010-01-01", tz=px.index.tz)
    end = px.index[-1]
    null_score = _scrambled(px).loc[score.index].reindex(columns=px.columns)
    y = start
    while y + pd.DateOffset(years=years + 1) <= end:
        tr0, tr1 = y, y + pd.DateOffset(years=years)
        te0, te1 = tr1, tr1 + pd.DateOffset(years=1)
        for lbl, sc in (("real", score), ("null", null_score)):
            r = _one(px, sc, signal, n_hold, buffer, str(te0.date()), str(min(te1, end).date()),
                     f"wf_{tr0.year}", "fixed50", str(tr0.date()), str(tr1.date()))
            if r:
                r.tag = f"{r.tag}_{lbl}"
                rows.append(r)
        y = y + pd.DateOffset(years=1)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--signal", default="trend")
    ap.add_argument("--n-hold", type=int, default=20)
    ap.add_argument("--buffer", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path("tem/phase2c/wf.jsonl"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    frames = {s: S.bars(s, timeframe="1d")["close"] for s in S.available_symbols("1d")}
    px = pd.DataFrame(frames).sort_index().ffill()
    log.info("panel %s -> %s", px.index[0].date(), px.index[-1].date())

    score = SIGNAL_FN[args.signal](px)
    rows = rolling_wf(px, score, args.signal, args.n_hold, args.buffer)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(asdict(r)) + "\n")

    real = [r for r in rows if r.tag.endswith("_real")]
    null = [r for r in rows if r.tag.endswith("_null")]
    log.info("folds: %d real, %d null", len(real), len(null))
    for r in sorted(real, key=lambda r: r.test_start):
        n = next((x for x in null if x.tag.replace("_null", "") == r.tag.replace("_real", "")), None)
        e = (r.cagr - n.cagr) if n else float("nan")
        log.info("  %s %s..%s  cagr %+6.2f%%  null %s  edge %+6.2f%%  sharpe %+.2f  dd %6.2f%%",
                 r.tag, r.test_start, r.test_end, r.cagr * 100,
                 f"{n.cagr*100:+6.2f}%" if n else "   n/a ", e * 100,
                 r.sharpe, r.max_dd * 100)
    print(f"\n{len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
