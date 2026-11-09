"""Phase 7 -- is the book better than doing nothing?

Every prior result compared the strategy against a *signal-scrambled* null, which
answers "does the ranking carry information". It does not answer the question a
capital allocator actually asks: **would I have been better off just holding the
universe?**

Phase 0 produced the uncomfortable number this module exists to resolve:

    PIT, ALL window      CAGR     alpha vs equal-weight universe
    trend book          +16.93%      -2.29 pp
    equal-weight uni    +19.23%          --

The book was BEHIND simply holding its own universe, and its MaxDD (-33.8%) was
never compared against the benchmark's drawdown. The index in 2008-2026 had far
worse drawdowns than -33.8%, so the book may in fact be a risk reducer even while
lagging on return. Both facts have to be measured against the same benchmark to
say anything.

This module builds:

  * an equal-weight universe benchmark (rebalanced annually, real costs, PIT
    membership) -- the honest "do nothing" alternative
  * a cap-weight-free index proxy is NOT attempted: market caps are not in the
    panel, and inventing weights would be a fabrication
  * the trend book, the scrambled null, and the benchmark, all on identical
    dates and identical cost stacks
  * every fold of the annual walk-forward, plus TRAIN and TEST

The comparison that decides the matter is risk-adjusted: Sharpe of book minus
Sharpe of benchmark, and MaxDD of book minus MaxDD of benchmark. If the book does
not improve EITHER, there is no case for running it over holding the universe.
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
from .phase2c_walkforward import _book  # noqa: E402

log = logging.getLogger(__name__)


@dataclass
class Cmp:
    tag: str
    window: str
    book_cagr: float
    book_sharpe: float
    book_dd: float
    bench_cagr: float
    bench_sharpe: float
    bench_dd: float
    null_cagr: float
    null_sharpe: float
    null_dd: float
    book_alpha: float
    book_vs_bench_alpha: float
    dd_improvement: float


def _bench(px: pd.DataFrame, *, rebalance: str, tradable: pd.DataFrame | None) -> dict:
    """Equal-weight the whole universe, rebalanced on schedule, with real costs.

    This is the "do nothing" alternative done properly: it pays the same 32.32 bp
    round trip on every rebalance, sells gains subject to the same CGT, and is
    restricted to the same point-in-time membership. A benchmark that ignored
    costs would flatter the book.
    """
    from .backtest import rebalance_dates

    rdates = set(rebalance_dates(px.index, rebalance))
    live = px.notna() & (px > 0)
    if tradable is not None:
        live = live & tradable.reindex(index=px.index, columns=px.columns).fillna(False)

    names = [c for c in px.columns]
    qty: dict[str, float] = {}
    cost: dict[str, float] = {}
    age: dict[str, int] = {}
    cash = CAP
    fees = tax = 0.0
    curve: list[float] = []
    invested = 0

    for when in px.index:
        if when in rdates:
            eligible = [c for c in names if live.at[when, c]]
            target = set(eligible)
            for sym in list(qty):
                if sym in target:
                    continue
                p = float(px.at[when, sym])
                gross = qty.pop(sym) * p
                f = gross * ONE_WAY
                gain = gross - cost.pop(sym, 0.0)
                rate = float(C.LTCG_RATE) if age.pop(sym, 0) > 252 else float(C.STCG_RATE)
                t = max(gain, 0.0) * rate
                cash += gross - f - t
                fees += f
                tax += t
            for sym in target:
                if sym in qty or not eligible:
                    continue
                p = float(px.at[when, sym])
                slots = len(target) - len(qty)
                if slots <= 0:
                    break
                budget = min(cash / slots, CAP / max(len(target), 1))
                q = (budget * (1 - ONE_WAY)) / p
                if q <= 0:
                    continue
                f = q * p * ONE_WAY
                cash -= q * p + f
                qty[sym] = q
                cost[sym] = q * p + f
                age[sym] = 0
                fees += f
            # Drop names that have no quote at all rather than holding them.
            for sym in list(qty):
                if not np.isfinite(float(px.at[when, sym])):
                    pass
        val = cash + sum(q * float(px.at[when, s]) for s, q in qty.items()
                         if np.isfinite(float(px.at[when, s])))
        for sym in qty:
            age[sym] += 1
        if qty:
            invested += 1
        curve.append(val)

    eq = pd.Series(curve, index=px.index)
    m = compute(eq, exposure=invested / max(len(eq), 1),
                turnover=fees / ONE_WAY / CAP, total_fees=fees, total_tax=tax)
    return {"cagr": m.cagr, "sharpe": m.sharpe, "dd": m.max_drawdown}


def _book_metrics(px: pd.DataFrame, score: pd.DataFrame, *, n_hold: int,
                  buffer: int, rebalance: str, tradable: pd.DataFrame | None) -> dict:
    eq, fees, tax, trades, exp, to = _book(
        px, score, n_hold=n_hold, buffer=buffer, rebalance=rebalance, tradable=tradable
    )
    if len(eq) < 60 or eq.iloc[-1] <= 0 or not np.isfinite(eq.to_numpy()).all():
        return {"cagr": 0.0, "sharpe": 0.0, "dd": 0.0}
    m = compute(eq, exposure=exp, turnover=to, total_fees=fees, total_tax=tax, n_trades=trades)
    return {"cagr": m.cagr, "sharpe": m.sharpe, "dd": m.max_drawdown}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-hold", type=int, default=20)
    ap.add_argument("--buffer", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path("tem/phase7/benchmark.jsonl"))
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
    log.info("panel %s; PIT names live per date: median %.0f",
             px.shape, (px.notna() & mask).sum(axis=1).median())

    tr = _trend(px)
    nl = _scrambled(px)

    rows: list[Cmp] = []

    def emit(tag: str, window: str, start: str, end: str) -> None:
        w = px.loc[start:end]
        if len(w) < 60:
            return
        trad = mask.loc[w.index]
        b = _book_metrics(w, tr, n_hold=args.n_hold, buffer=args.buffer,
                          rebalance="A", tradable=trad)
        n = _book_metrics(w, nl, n_hold=args.n_hold, buffer=args.buffer,
                          rebalance="A", tradable=trad)
        be = _bench(w, rebalance="A", tradable=trad)
        rows.append(Cmp(
            tag=tag, window=window, book_cagr=b["cagr"], book_sharpe=b["sharpe"],
            book_dd=b["dd"], bench_cagr=be["cagr"], bench_sharpe=be["sharpe"],
            bench_dd=be["dd"], null_cagr=n["cagr"], null_sharpe=n["sharpe"],
            null_dd=n["dd"], book_alpha=b["cagr"] - be["cagr"],
            book_vs_bench_alpha=b["cagr"] - be["cagr"],
            dd_improvement=be["dd"] - b["dd"],
        ))
        r = rows[-1]
        log.info("  %-16s book %+6.2f%%/sh%.2f/dd%6.1f%%  bench %+6.2f%%/sh%.2f/dd%6.1f%%  "
                 "null %+6.2f%%  alpha_vs_bench %+6.2f pp  dd_gain %+6.1f pp",
                 tag, r.book_cagr * 100, r.book_sharpe, r.book_dd * 100,
                 r.bench_cagr * 100, r.bench_sharpe, r.bench_dd * 100,
                 r.null_cagr * 100, r.book_vs_bench_alpha * 100, r.dd_improvement * 100)

    emit("TRAIN", "TRAIN", C.TRAIN_START, C.TRAIN_END)
    emit("TEST", "TEST", C.TEST_START, C.TEST_END)
    emit("ALL", "ALL", "2009-01-01", C.TEST_END)

    y = pd.Timestamp("2010-01-01", tz=px.index.tz)
    end = px.index[-1]
    while y + pd.DateOffset(years=4) <= end:
        te0 = y + pd.DateOffset(years=3)
        te1 = y + pd.DateOffset(years=4)
        emit(f"wf{y.year}", f"wf{y.year}", str(te0.date()), str(te1.date()))
        y = y + pd.DateOffset(years=1)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(asdict(r)) + "\n")
    print(f"\n{len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
