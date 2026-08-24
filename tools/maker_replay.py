#!/usr/bin/env python3
"""Maker-execution replay (phase 3b): does intraday survive at maker fees?

Honest bar-level model of resting limit orders — no order book needed:

- When the strategy's target position changes at bar i's close, a LIMIT is
  placed at close_i (passive, maker fee, zero slippage).
- The limit fills during bars i+1..kill_bars only if price TRADES THROUGH
  it (buy: low <= limit; sell: high >= limit). Getting filled means the
  market moved against you first — adverse selection is captured.
- Unfilled entries expire silently (missed trade — the cost of passive
  entry).
- Exits expire into a TAKER market order at that close (exposure cap —
  what a real system does when it must be out).

Accounting (full notional, qty = cash/close at entry):
  long : open -> cash -= qty*px ; equity = cash + qty*mark
         close -> cash += qty*px
  short: open -> cash += qty*px ; equity = cash - qty*mark
         close -> cash -= qty*px

Usage:
  python3 tools/maker_replay.py --algo open_range --tf 5m --symbol ETHUSDT \
      [--param period=15] [--kill-bars 3]
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

logging.disable(logging.CRITICAL)

from cryptobot.backtest.metrics import PerformanceMetrics  # noqa: E402
from cryptobot.backtest.runner import OhlcvBar, make_strategy  # noqa: E402

TAKER_COST_BPS = Decimal("8")  # 5 fee + 3 slip per side
MAKER_COST_BPS = Decimal("1")


def collect_signal_targets(bars: list[OhlcvBar], strategy) -> list[int]:
    """Raw -1/0/+1 target per bar for SignalStrategy subclasses."""
    from cryptobot.strategies.signal_base import SignalStrategy

    assert isinstance(strategy, SignalStrategy), "maker_replay supports SignalStrategy algos"
    sym = "S"
    out: list[int] = []
    for bar in bars:
        c, h, lo, v = strategy._bufs(sym)
        c.append(float(bar.close))
        h.append(float(bar.high))
        lo.append(float(bar.low))
        v.append(float(bar.volume))
        closes, highs, lows, vols = list(c), list(h), list(lo), list(v)
        if len(closes) < strategy.warmup(closes):
            out.append(0)
            continue
        sig = strategy.signal(closes, highs, lows, vols)
        out.append(1 if sig > 0 else (-1 if sig < 0 else 0))
    return out


def maker_replay(
    bars: list[OhlcvBar],
    targets: list[int],
    initial_capital: float = 10_000.0,
    kill_bars: int = 3,
    maker_cost_bps: Decimal = MAKER_COST_BPS,
    taker_cost_bps: Decimal = TAKER_COST_BPS,
) -> dict:
    """Replay signal targets through resting-limit execution."""
    cash = initial_capital
    pos = 0            # -1/0/+1
    qty = 0.0          # units held (signed magnitude)
    pending: dict | None = None
    curve: list[float] = []
    stats = {"entries_filled": 0, "entries_missed": 0,
             "exits_maker": 0, "exits_taker": 0}

    def fee(notional: float, bps: Decimal) -> float:
        return notional * float(bps) / 10_000.0

    def open_position(side: int, px: float) -> None:
        nonlocal cash, pos, qty
        q = cash / px
        cash -= fee(q * px, maker_cost_bps)
        if side > 0:
            cash -= q * px          # buy: cash out
        else:
            cash += q * px          # short: credit proceeds
        pos, qty = side, q

    def close_position(px: float, bps: Decimal, kind: str) -> None:
        nonlocal cash, pos, qty
        cash -= fee(qty * px, bps)
        if pos > 0:
            cash += qty * px
        else:
            cash -= qty * px
        stats[kind] += 1
        pos, qty = 0, 0.0

    for i, bar in enumerate(bars):
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)

        # 1) fill-check resting limit against this bar's range
        if pending is not None:
            p = pending
            crossed = (lo <= p["limit"]) if p["side"] > 0 else (hi >= p["limit"])
            if crossed:
                px = p["limit"]
                if p["kind"] == "entry":
                    open_position(p["side"], px)
                    stats["entries_filled"] += 1
                else:
                    close_position(px, maker_cost_bps, "exits_maker")
                pending = None
            else:
                p["age"] += 1
                if p["age"] >= kill_bars:
                    if p["kind"] == "exit":
                        close_position(cl, taker_cost_bps, "exits_taker")
                    else:
                        stats["entries_missed"] += 1
                    pending = None

        # 2) react to target changes (place limits at THIS close; they can
        #    only fill from the NEXT bar onward)
        tgt = targets[i] if i < len(targets) else 0
        if pending is None and tgt != pos:
            if pos != 0:
                pending = {"kind": "exit", "side": -pos, "limit": cl, "age": 0}
            elif tgt != 0:
                pending = {"kind": "entry", "side": tgt, "limit": cl, "age": 0}

        # 3) mark to market
        eq = cash + (qty * cl if pos > 0 else -qty * cl if pos < 0 else 0.0)
        curve.append(eq)

    final = curve[-1] if curve else initial_capital
    pm = PerformanceMetrics()
    pm.add_value(curve[0])
    rets = [curve[i] / curve[i - 1] - 1.0 for i in range(1, len(curve)) if curve[i - 1] > 0]
    for r in rets:
        pm.add_value(curve[0] * (1 + r))
    sharpe = float(pm.calculate_sharpe_ratio(rets)) if rets else 0.0
    mdd = float(pm.calculate_drawdown(pd.Series(curve))) / 100.0 if curve else 0.0

    return {
        "final_equity": final,
        "return": final / initial_capital - 1.0,
        "sharpe": sharpe,
        "mdd": mdd,
        **stats,
    }


def load(symbol: str, tf: str) -> list[OhlcvBar]:
    df = pd.read_csv(f"data/{symbol.lower()}_{tf}.csv")
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def main() -> None:

    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", required=True)
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--symbol", default="ETHUSDT")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--kill-bars", type=int, default=3)
    args = ap.parse_args()

    params: dict[str, float] = {}
    for kv in args.param:
        k, v = kv.split("=", 1)
        params[k] = int(v) if v.isdigit() else float(v)

    bars = load(args.symbol, args.tf)
    strat = make_strategy(args.algo, **params)
    targets = collect_signal_targets(bars, strat)
    res = maker_replay(bars, targets, kill_bars=args.kill_bars)
    print(f"{args.algo} {args.symbol} {args.tf} maker-mode: "
          f"ret={res['return']:+.1%} sharpe={res['sharpe']:.2f} mdd={res['mdd']:.1%} "
          f"fills={res['entries_filled']} missed={res['entries_missed']} "
          f"taker_exits={res['exits_taker']}")


if __name__ == "__main__":
    main()
