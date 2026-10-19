"""Phase 0 -- quantify the survivorship bias, and test whether it changes any conclusion.

Phase 1 and Phase 2 ran on a panel of *today's* NIFTY-50 backfilled to 2008.
`tools/pit_membership.py` provides the real membership history, validated 9/9
against archive.org snapshots of the NSE file. This measures what that bias is
worth, and re-runs the Phase 2 conclusion under the corrected universe.

Two universes are compared on identical dates, identical signals, identical costs:

  fixed50   today's members only -- what every prior result used
  pit       only the names actually in the index on that date

The catch, and it is a real one: only 68.8% of point-in-time members have price
history in our panel, rising from 23/50 in 2009 to 47/50 in 2026. So `pit` is NOT
a clean correction -- it is biased OPTIMISTICALLY, because the names we cannot
price are disproportionately the collapsed and delisted ones (SATYAMCOMP, VSNL,
MCDOWELL-N, STER have no obtainable history). Every figure here is therefore a
FLOOR on the true bias, not an estimate of it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from . import config as C  # noqa: E402
from . import splitter as S  # noqa: E402
from .phase2 import CAP, _composite, _scrambled, _trend  # noqa: E402
from .phase2c_walkforward import _book  # noqa: E402

log = logging.getLogger(__name__)

SIGNALS = {"trend": _trend, "composite": _composite, "scrambled": _scrambled}


def _pit_members(m, when: pd.Timestamp) -> set[str]:
    try:
        return set(m.members(when))
    except Exception:
        return set()


def build_pit_panel(px: pd.DataFrame, m, *, n_hold: int) -> pd.DataFrame:
    """Restrict the *ranking universe* each month to point-in-time index members.

    Returns a boolean mask, NOT a masked price panel.

    An earlier version NaN'd the non-members out of the price frame directly.
    That was wrong twice over: a name dropped from the index on 1 June is still
    held by an annual-rebalance book until the next January, so valuing it as
    `q * NaN` poisoned the whole equity curve (206 NaN bars, MaxDD reported as a
    nonsense -100%). And a discretionary book may legitimately keep holding a name
    the index has dropped, selling it at its real market price.

    So membership gates *selection* only. Prices are always the observed ones.
    """
    mask = pd.DataFrame(False, index=px.index, columns=px.columns)
    months = pd.to_datetime(px.index, utc=True).tz_convert("Asia/Kolkata").to_period("M")
    for mth in months.unique():
        rows = px.index[months == mth]
        keep = _pit_members(m, rows[-1])
        norm = {s.upper().replace("-", "").replace("&", "").replace(" ", "") for s in keep}
        for col in px.columns:
            if col.upper() in norm:
                mask.loc[rows, col] = True
    return mask


def _bh_cagr(px: pd.DataFrame) -> float:
    s = px.mean(axis=1).pct_change().fillna(0.0)
    if s.empty:
        return 0.0
    eq = CAP * (1 + s).cumprod()
    n = len(eq)
    return float((eq.iloc[-1] / eq.iloc[0]) ** (C.TRADING_DAYS / n) - 1.0)


def run(px: pd.DataFrame, score: pd.DataFrame, *, n_hold: int, buffer: int,
        start: str, end: str, tag: str,
        tradable: pd.DataFrame | None = None) -> dict:
    w = px.loc[start:end]
    sc = score.loc[w.index].reindex(columns=w.columns)
    if w.notna().sum().sum() == 0:
        return {}
    eq, fees, tax, trades, exp, to = _book(
        w, sc, n_hold=n_hold, buffer=buffer, rebalance="A", tradable=tradable
    )
    if len(eq) < 60 or eq.iloc[-1] <= 0 or not np.isfinite(eq.to_numpy()).all():
        return {"tag": tag, "error": "equity curve not finite"}
    from .metrics import compute

    m = compute(eq, exposure=exp, turnover=to, total_fees=fees, total_tax=tax, n_trades=trades)
    return {"tag": tag, "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
            "exposure": exp, "turnover": to, "n_trades": trades,
            "bh_cagr": _bh_cagr(w), "alpha": m.cagr - _bh_cagr(w)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-hold", type=int, default=20)
    ap.add_argument("--buffer", type=int, default=20)
    ap.add_argument("--out", type=Path, default=Path("tem/phase0/survivorship.jsonl"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from pit_membership import _norm, load_membership

    m = load_membership()
    log.info("membership: %d months, %d symbols, %d changes", len(m.table),
             len(m.symbols), len(m.rebalance_dates()))

    frames = {}
    for f in sorted(Path("data/nse").glob("*_1d.csv")):
        sym = f.name[:-len("_1d.csv")]
        if sym in S.EXCLUDED_SYMBOLS:
            continue
        frames[_norm(sym)] = S.bars(sym, timeframe="1d")["close"]
    fixed = pd.DataFrame(frames).sort_index().ffill()
    fixed.columns = [c.lower() for c in fixed.columns]
    log.info("fixed panel %s", fixed.shape)

    mask = build_pit_panel(fixed, m, n_hold=args.n_hold)
    live_per_date = (fixed.notna() & mask).sum(axis=1)
    log.info("pit universe: %.0f names median (min %d, max %d) of %d panel cols",
             live_per_date.median(), live_per_date.min(), live_per_date.max(),
             fixed.shape[1])

    windows = {"TRAIN": (C.TRAIN_START, C.TRAIN_END),
               "TEST": (C.TEST_START, C.TEST_END),
               "ALL": ("2009-01-01", C.TEST_END)}
    rows: list[dict] = []
    for win, (s, e) in windows.items():
        for uni, tradable in (("fixed50", None), ("pit", mask)):
            panel = fixed
            for sig, fn in SIGNALS.items():
                # The score is computed on the FULL price panel in both cases, then
                # membership gates which names are selectable. Computing the signal on
                # an already-masked panel would let a name's own history change when
                # it joined the index -- a look-ahead in the opposite direction.
                r = run(panel, fn(panel), n_hold=args.n_hold, buffer=args.buffer,
                        start=s, end=e, tag=f"{win}|{uni}|{sig}", tradable=tradable)
                if r.get("error"):
                    log.warning("  %-24s SKIPPED (%s)", r["tag"], r["error"])
                    continue
                r["window"], r["universe"], r["signal"] = win, uni, sig
                rows.append(r)
                log.info("  %-24s cagr %+7.2f%%  bh %+7.2f%%  alpha %+7.2f%%  sharpe %+.2f  dd %6.2f%%",
                         r["tag"], r["cagr"] * 100, r["bh_cagr"] * 100,
                         r["alpha"] * 100, r["sharpe"], r["max_dd"] * 100)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"\n{len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
