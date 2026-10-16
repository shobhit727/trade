"""Phase 1 -- does the rebalance clock decide whether this book makes money?

Why this experiment exists
---------------------------
A previous sweep concluded "turnover is the constraint" from a *cross-sectional*
correlation: across 4,032 strategy/stock pairs, `corr(turnover, alpha) = -0.065`,
and the 910 pairs below 1x turnover per year still had median CAGR 0.00%.

That inference is confounded. Low-turnover pairs traded rarely *because the
strategy had little signal to act on*, not because holding a position paid. Any
correlation measured across pairs with different signals mixes "holding is
profitable" with "this strategy is dead".

The only clean test holds the signal fixed and varies nothing but the clock.
That is what this module does:

* a fixed subset of catalog strategies (one config each -- no search),
* every usable symbol,
* six rebalance frequencies from daily to annual,
* TRAIN and TEST scored separately and never mixed.

Everything else is held constant: Rs21L book, full statutory cost stack,
18% GST, FIFO lots, STCG/LTCG, and the C10-repaired panel.

Read the output as a *cost schedule* experiment, not a strategy search. The
question it answers is narrow: at what number of decisions per year does the
cost bill fall below the measured gross edge?
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from decimal import Decimal as D
from pathlib import Path

from . import config as C
from . import splitter as S
from .backtest import run_single_stock
from .catalog import discover
from .metrics import compute

log = logging.getLogger(__name__)

#: One representative strategy per family, plus the exposure outliers identified
#: in the per-stock decomposition. Chosen for FAMILY COVERAGE, not performance --
#: picking the best performers here would pre-select the answer.
SUBSET: tuple[str, ...] = (
    # trend / moving average
    "kama_strategy",
    "macd_strategy",
    "supertrend_strategy",
    "ema_cross_strategy",
    "triple_moving_average",
    "hull_moving_average",
    # momentum
    "rsi_momentum_strategy",
    "momentum_factor_strategy",
    "volume_momentum_strategy",
    # mean reversion
    "rsi_strategy",
    "bollinger_bands",
    "zscore_strategy",
    # volatility / risk
    "volatility_scaling",
    "volatility_target",
    # cross-sectional / multi-factor
    "cross_sectional_strategy",
    "multi_factor_strategy",
)

FREQS: tuple[str, ...] = ("D", "W", "M", "Q", "2Q", "A")
WINDOWS = {"TRAIN": (C.TRAIN_START, C.TRAIN_END), "TEST": (C.TEST_START, C.TEST_END)}


@dataclass
class Row:
    strategy: str
    symbol: str
    rebalance: str
    window: str
    cagr: float
    sharpe: float
    sortino: float
    max_dd: float
    calmar: float
    exposure: float
    turnover: float
    total_fees: float
    total_tax: float
    n_trades: int


def _one(args: tuple) -> Row | None:
    spec, symbol, freq, window = args
    start, end = WINDOWS[window]
    try:
        bars = S.bars(symbol)
    except Exception as exc:  # pragma: no cover - data guard
        log.debug("bars(%s) failed: %s", symbol, exc)
        return None
    try:
        res = run_single_stock(bars, spec, {}, rebalance=freq, start=start, end=end)
    except Exception as exc:
        log.debug("%s/%s/%s/%s failed: %s", spec.name, symbol, freq, window, exc)
        return None
    if res is None or len(res.equity) < 2:
        return None

    m = compute(res.equity)
    return Row(
        strategy=spec.name,
        symbol=symbol,
        rebalance=freq,
        window=window,
        cagr=m.cagr,
        sharpe=m.sharpe,
        sortino=m.sortino,
        max_dd=m.max_drawdown,
        calmar=m.calmar,
        exposure=float(res.invested_bars / max(res.n_bars, 1)),
        turnover=res.turnover,
        total_fees=float(res.total_fees),
        total_tax=float(res.total_tax),
        n_trades=len(res.trades),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=Path("tem/phase1/rows.jsonl"))
    ap.add_argument("--limit-symbols", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    specs = [s for s in discover() if s.name in SUBSET]
    missing = set(SUBSET) - {s.name for s in specs}
    if missing:
        log.warning("catalog lacks %s -- continuing", sorted(missing))

    symbols = S.available_symbols("1d")
    if args.limit_symbols:
        symbols = symbols[: args.limit_symbols]

    tasks = [
        (spec, sym, freq, win)
        for spec in specs
        for sym in symbols
        for freq in FREQS
        for win in WINDOWS
    ]
    log.info("Phase 1: %d specs x %d symbols x %d freqs x %d windows = %d runs",
             len(specs), len(symbols), len(FREQS), len(WINDOWS), len(tasks))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[Row] = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex, args.out.open("w") as fh:
        for i, row in enumerate(ex.map(_one, tasks, chunksize=16), 1):
            if row is None:
                continue
            rows.append(row)
            fh.write(json.dumps(asdict(row)) + "\n")
            if i % 2000 == 0:
                log.info("  %d/%d (%d kept)", i, len(tasks), len(rows))

    log.info("kept %d rows -> %s", len(rows), args.out)
    print(f"\nrows={len(rows)}  ->  {args.out}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())