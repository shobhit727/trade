"""Phase 8 -- the DEPLOYABLE version: make money AND stay inside the constitution.

The blocker found in Phase 7 is not a signal problem, it is a mandate problem.

`nsealgo/risk/limits.py` hard-codes (GOAL.md §3.3, not configurable):
    max_drawdown_halt     -15%   -> flatten and stop trading
    max_drawdown_absolute  -25%   -> permanent capital-preservation mode

The Phase 2/7 book has MaxDD -33.8% over 2009-2026. **Deployed, the kill switch
would flatten the account and then sit in cash forever.** So that book is not
deployable, however good its return looks.

A risk control is therefore mandatory, and it must satisfy a hard trade-off:
  * cut drawdown below -15%, AND
  * keep exposure high, because Phase 1 proved the return comes from being
    invested (>60% exposure is the only profitable bucket)

The current live engine already has a regime overlay, but it is configured for
126-day lookback / 0.35 threshold, and Phase 1 showed that kind of frequent
exposure-cutting is exactly what produced median CAGR 0.000 at 45% exposure.

This module tests the overlay that reconciles the two requirements:

    index-level (market) regime filter -- go to cash only when the MARKET is in a
    severe downtrend, not when individual names are

Market-level filtering is the right instrument because it can be checked without
look-ahead, it cuts the 2008/2020-style crashes that produce the -15% breach, and
it does not churn: a handful of cash/market switches per decade, not per stock.

Variants tested, all on the point-in-time universe with full costs and CGT:
  bench          equal-weight universe, annual rebalance  (the do-nothing baseline)
  bench_reg      benchmark + market regime filter
  trend          top-20 by distance-above-200dma, buffered
  trend_reg      trend book + market regime filter
  each with a scrambled-signal null

The acceptance gate is explicit and mechanical:
  1. MaxDD must stay inside -15% (the halt limit) with margin
  2. CAGR must be positive net of all costs and tax
  3. the book must beat the null
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from . import config as C  # noqa: E402
from . import splitter as S  # noqa: E402
from .metrics import compute  # noqa: E402
from .phase0_survivorship import build_pit_panel  # noqa: E402
from .phase2 import CAP, ONE_WAY, _scrambled, _trend  # noqa: E402

log = logging.getLogger(__name__)

#: The constitution. `nsealgo/risk/limits.py` hard-codes these; this module
#: imports the real values rather than restating them, so a change to the
#: constitution automatically changes the acceptance test.
from nsealgo.risk.limits import LIMITS  # noqa: E402

HALT = float(LIMITS.max_drawdown_halt)
ABS = float(LIMITS.max_drawdown_absolute)


@dataclass
class Row:
    tag: str
    window: str
    variant: str
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
    null_cagr: float
    null_dd: float
    alpha_vs_bench: float
    alpha_vs_null: float


def market_regime(px: pd.DataFrame, lookback: int, threshold: float) -> pd.Series:
    """1.0 when the market may be invested, 0.0 when it must be flat.

    Market-level, computed on the equal-weight universe (not on any single
    name), so it is a regime read rather than a stock pick. The signal is the
    fraction of the last `lookback` bars the market spent above its own moving
    average: a persistently falling market scores low and we sit in cash.

    A deliberately slow, high-threshold filter. The Phase 1 lesson is that
    frequent exposure cutting is what destroys these returns.
    """
    mkt = px.mean(axis=1)
    ma = mkt.rolling(lookback, min_periods=lookback // 2).mean()
    above = (mkt > ma).astype(float)
    score = above.rolling(lookback, min_periods=lookback // 2).mean()
    return (score >= threshold).astype(float)


def run_book(
    px: pd.DataFrame,
    score: pd.DataFrame,
    *,
    n_hold: int,
    buffer: int,
    rebalance: str,
    tradable: pd.DataFrame | None,
    regime: pd.Series | None = None,
) -> dict:
    """Equal-weight top-N book with hysteresis, optional market regime overlay."""
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
    last_px: dict[str, float] = {}

    for when in px.index:
        flat = regime is not None and regime.at[when] < 0.5
        if when in rdates:
            if flat:
                target: set[str] = set()
            else:
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

            if not flat:
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
                    continue
            val += q * p
        for sym in qty:
            age[sym] += 1
        if qty:
            invested += 1
        curve.append(val)

    eq = pd.Series(curve, index=px.index)
    m = compute(eq, exposure=invested / max(len(eq), 1),
                turnover=fees / ONE_WAY / CAP, total_fees=fees, total_tax=tax,
                n_trades=trades)
    return {"cagr": m.cagr, "sharpe": m.sharpe, "dd": m.max_drawdown,
            "exposure": invested / max(len(eq), 1), "turnover": fees / ONE_WAY / CAP,
            "n_trades": trades, "fees": fees, "tax": tax}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-hold", type=int, default=20)
    ap.add_argument("--buffer", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path("tem/phase8/deployable.jsonl"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from pit_membership import _norm, load_membership

    m = load_membership()
    frames: dict[str, pd.Series] = {}
    for f in sorted(Path("data/nse").glob("*_1d.csv")):
        sym = f.name[: -len("_1d.csv")]
        if sym in S.EXCLUDED_SYMBOLS:
            continue
        frames[_norm(sym)] = S.bars(sym, timeframe="1d")["close"]
    px = pd.DataFrame(frames).sort_index().ffill()
    px.columns = [c.lower() for c in px.columns]
    mask = build_pit_panel(px, m, n_hold=args.n_hold)
    log.info("panel %s | halt limit %.0f%% | absolute %.0f%%",
             px.shape, HALT * 100, ABS * 100)

    tr = _trend(px)
    nl = _scrambled(px)
    # Slow, high-threshold market filter. 252d lookback, require the market to
    # have spent 60% of the last year above its own 252d average.
    regime = market_regime(px, 252, 0.60)
    log.info("regime: invested %.0f%% of bars, %d switches",
             regime.mean() * 100, int((regime.diff().abs() > 0).sum()))

    windows = [("TRAIN", C.TRAIN_START, C.TRAIN_END), ("TEST", C.TEST_START, C.TEST_END),
               ("ALL", "2009-01-01", C.TEST_END)]
    y = pd.Timestamp("2010-01-01", tz=px.index.tz)
    while y + pd.DateOffset(years=4) <= px.index[-1]:
        windows.append((f"wf{y.year}", str((y + pd.DateOffset(years=3)).date()),
                        str((y + pd.DateOffset(years=4)).date())))
        y = y + pd.DateOffset(years=1)

    rows: list[Row] = []
    for tag, s, e in windows:
        w = px.loc[s:e]
        if len(w) < 60:
            continue
        trad = mask.loc[w.index]
        sc_tr = tr.loc[w.index].reindex(columns=w.columns)
        sc_nl = nl.loc[w.index].reindex(columns=w.columns)
        rg = regime.loc[w.index]

        bench = run_book(w, pd.DataFrame(1.0, index=w.index, columns=w.columns),
                         n_hold=len(w.columns), buffer=0, rebalance="A",
                         tradable=trad, regime=None)
        bench_reg = run_book(w, pd.DataFrame(1.0, index=w.index, columns=w.columns),
                             n_hold=len(w.columns), buffer=0, rebalance="A",
                             tradable=trad, regime=rg)
        book = run_book(w, sc_tr, n_hold=args.n_hold, buffer=args.buffer,
                        rebalance="A", tradable=trad, regime=None)
        book_reg = run_book(w, sc_tr, n_hold=args.n_hold, buffer=args.buffer,
                            rebalance="A", tradable=trad, regime=rg)
        null_reg = run_book(w, sc_nl, n_hold=args.n_hold, buffer=args.buffer,
                            rebalance="A", tradable=trad, regime=rg)

        for name, b, n in (("bench", bench, None), ("bench_reg", bench_reg, None),
                           ("trend", book, None), ("trend_reg", book_reg, null_reg)):
            rows.append(Row(
                tag=tag, window=tag, variant=name, cagr=b["cagr"], sharpe=b["sharpe"],
                max_dd=b["dd"], exposure=b["exposure"], turnover=b["turnover"],
                n_trades=b["n_trades"], fees=b["fees"], tax=b["tax"],
                bench_cagr=bench["cagr"], bench_dd=bench["dd"],
                null_cagr=n["cagr"] if n else 0.0, null_dd=n["dd"] if n else 0.0,
                alpha_vs_bench=b["cagr"] - bench["cagr"],
                alpha_vs_null=(b["cagr"] - n["cagr"]) if n else 0.0,
            ))
            r = rows[-1]
            flag = "OK " if r.max_dd > HALT else "BREACH"
            log.info("  %-8s %-10s cagr %+6.2f%%  sh %+.2f  dd %6.1f%% [%s]  exp %3.0f%%  "
                     "to %5.1f  a_bench %+5.2f  a_null %+5.2f",
                     tag, name, r.cagr * 100, r.sharpe, r.max_dd * 100, flag,
                     r.exposure * 100, r.turnover, r.alpha_vs_bench * 100,
                     r.alpha_vs_null * 100)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(asdict(r)) + "\n")
    print(f"\n{len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
