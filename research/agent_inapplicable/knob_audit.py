"""Empirically identify inert config knobs in the seven assigned catalog strategies.

Method: perturb each declared config field across a wide range, replay the FULL
daily-bar history of a real symbol through the strategy's signal(), and compare
the emitted signal sequence byte-for-byte against the baseline. A knob whose
perturbation yields an IDENTICAL signal series is inert as far as signal() is
concerned (it may still be read by warmup()).

Run:  .venv/bin/python research/agent_inapplicable/knob_audit.py
"""

from __future__ import annotations

import csv
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, "src")

from cryptobot.strategies.catalog.basket import BasketConfig, BasketStrategy
from cryptobot.strategies.catalog.funding_basis_strategy import (
    FundingBasisConfig,
    FundingBasisStrategy,
)
from cryptobot.strategies.catalog.funding_trend_strategy import (
    FundingTrendConfig,
    FundingTrendStrategy,
)
from cryptobot.strategies.catalog.meta_strategy import MetaStrategy, MetaStrategyConfig
from cryptobot.strategies.catalog.nse_intraday_trading import (
    NseOrbConfig,
    NseOrbStrategy,
    VwapRevertConfig,
    VwapRevertStrategy,
)
from cryptobot.strategies.catalog.spot_futures_arbitrage import (
    SpotFuturesConfig,
    SpotFuturesStrategy,
)
from cryptobot.strategies.catalog.stablecoin_peg_strategy import (
    StablecoinPegConfig,
    StablecoinPegStrategy,
)

DATA = Path("data/nse")
SYMBOLS = [
    "reliance", "tcs", "hdfcbank", "icicibank", "tatasteel",
]


def load(symbol: str, tf: str = "1d"):
    path = DATA / f"{symbol}_{tf}.csv"
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    return (
        [float(r["close"]) for r in rows],
        [float(r["high"]) for r in rows],
        [float(r["low"]) for r in rows],
        [float(r["vol"]) for r in rows],
        [int(r["ts"]) for r in rows],
    )


def replay(cls, cfg_cls, override: dict, series, with_ts: bool):
    """Feed one symbol's bars through strategy.feed(); return signal sequence."""
    closes, highs, lows, vols, tss = series
    strat = cls(cfg_cls(**override))
    out = []
    for i in range(len(closes)):
        strat.feed(
            "SYM",
            closes[i],
            highs[i],
            lows[i],
            vols[i],
            ts=tss[i] if with_ts else None,
        )
        # Re-derive the raw signal (bypassing base-class position de-duplication,
        # which would mask a signal that toggles back and forth within one bar).
        if len(strat._closes["SYM"]) < strat.warmup([]):
            out.append(0)
            continue
        c, h, lo, v = strat.as_lists("SYM")
        s = strat.signal(c, h, lo, v)
        out.append(0 if s is None else s)
    return out


def summarise(seq):
    n = len(seq)
    longs = sum(1 for x in seq if x > 0)
    shorts = sum(1 for x in seq if x < 0)
    flats = sum(1 for x in seq if x == 0)
    flips = sum(1 for a, b in zip(seq, seq[1:], strict=False) if a != b)
    return n, longs, shorts, flats, flips


TARGETS = [
    ("funding_basis", FundingBasisStrategy, FundingBasisConfig,
     {"period": 20, "threshold": 0.0, "quantity": 1}),
    ("funding_trend", FundingTrendStrategy, FundingTrendConfig,
     {"period": 30, "threshold": 0.005, "quantity": 1}),
    ("spot_futures", SpotFuturesStrategy, SpotFuturesConfig,
     {"period": 30, "entry": 1.0, "quantity": 1}),
    ("stablecoin_peg", StablecoinPegStrategy, StablecoinPegConfig,
     {"period": 60, "entry": 2.0, "quantity": 1}),
    ("basket", BasketStrategy, BasketConfig,
     {"period": 20, "threshold": 0.015, "quantity": 1}),
    ("meta", MetaStrategy, MetaStrategyConfig, {"period": 20, "quantity": 1}),
]

PERTURBATIONS = {
    "period": [10, 20, 60],
    "threshold": [0.0, 0.005, 0.05],
    "entry": [0.0, 1.0, 5.0],
    "quantity": [1, 2, 1000],
}

print("=" * 78)
print("PART 1 — KNOB PERTURBATION ON DAILY BARS (5 NSE symbols, OHLCV only)")
print("=" * 78)
print("A knob is INERT if perturbing it leaves the signal series identical.")
print()

series_cache = {s: load(s) for s in SYMBOLS}

for name, cls, cfg_cls, base in TARGETS:
    print(f"--- {name}  (defaults: {base}) ---")
    fields = {f.name for f in dataclasses.fields(cfg_cls)}
    for knob in sorted(fields):
        if knob not in PERTURBATIONS:
            continue
        changed, identical, total_trials = 0, 0, 0
        for s in SYMBOLS:
            base_seq = replay(cls, cfg_cls, base, series_cache[s], with_ts=True)
            for val in PERTURBATIONS[knob]:
                if val == base[knob]:
                    continue
                trial = {**base, knob: val}
                t_seq = replay(cls, cfg_cls, trial, series_cache[s], with_ts=True)
                total_trials += 1
                if t_seq == base_seq:
                    identical += 1
                else:
                    changed += 1
        verdict = (
            f"INERT      ({identical}/{total_trials} perturbations identical)"
            if identical == total_trials
            else f"live       ({changed}/{total_trials} perturbations changed output)"
        )
        print(f"    {knob:<10} {verdict}")
    print()

# Live-signal summary for the two runnable candidates.
print("=" * 78)
print("PART 2 — DAILY-BAR SIGNAL LIVENESS (fraction of bars long / flat)")
print("=" * 78)
for name, cls, cfg_cls, base in TARGETS:
    longs = shorts = flats = total = flips = 0
    for s in SYMBOLS:
        seq = replay(cls, cfg_cls, base, series_cache[s], with_ts=True)
        n, lo, sh, fl, fp = summarise(seq)
        longs += lo
        shorts += sh
        flats += fl
        total += n
        flips += fp
    print(
        f"  {name:<16} long={longs/total:6.2%}  short={shorts/total:6.2%}  "
        f"flat={flats/total:6.2%}  flips={flips:>6}  bars={total}"
    )

print()
print("=" * 78)
print("PART 3 — INTRADAY STRATEGIES ON DAILY BARS (ts IS supplied)")
print("=" * 78)
for name, cls, cfg_cls, base in [
    ("nse_orb", NseOrbStrategy, NseOrbConfig, {"range_bars": 2, "quantity": 1}),
    ("vwap_revert", VwapRevertStrategy, VwapRevertConfig, {"z_entry": 2.0, "quantity": 1}),
]:
    longs = shorts = flats = total = 0
    for s in SYMBOLS:
        seq = replay(cls, cfg_cls, base, series_cache[s], with_ts=True)
        n, lo, sh, fl, _ = summarise(seq)
        longs += lo
        shorts += sh
        flats += fl
        total += n
    print(
        f"  {name:<16} long={longs/total:6.2%}  short={shorts/total:6.2%}  "
        f"flat={flats/total:6.2%}  (n={total})"
    )

print()
print("=" * 78)
print("PART 4 — SILENT-FAILURE CHECK: ts OMITTED (base-class default path)")
print("=" * 78)
for name, cls, cfg_cls, base in [
    ("nse_orb", NseOrbStrategy, NseOrbConfig, {"range_bars": 2, "quantity": 1}),
    ("vwap_revert", VwapRevertStrategy, VwapRevertConfig, {"z_entry": 2.0, "quantity": 1}),
]:
    longs = shorts = flats = total = 0
    for s in SYMBOLS:
        seq = replay(cls, cfg_cls, base, series_cache[s], with_ts=False)
        n, lo, sh, fl, _ = summarise(seq)
        longs += lo
        shorts += sh
        flats += fl
        total += n
    print(
        f"  {name:<16} long={longs/total:6.2%}  short={shorts/total:6.2%}  "
        f"flat={flats/total:6.2%}  (n={total}, ts=None)"
    )

print()
print("=" * 78)
print("PART 5 — INTRADAY STRATEGIES ON 15m BARS (the only bar size with session stamps)")
print("=" * 78)
for name, cls, cfg_cls, base in [
    ("nse_orb", NseOrbStrategy, NseOrbConfig, {"range_bars": 2, "quantity": 1}),
    ("vwap_revert", VwapRevertStrategy, VwapRevertConfig, {"z_entry": 2.0, "quantity": 1}),
]:
    longs = shorts = flats = total = 0
    for s in SYMBOLS:
        series = load(s, "15m")
        seq = replay(cls, cfg_cls, base, series, with_ts=True)
        n, lo, sh, fl, _ = summarise(seq)
        longs += lo
        shorts += sh
        flats += fl
        total += n
    print(
        f"  {name:<16} long={longs/total:6.2%}  short={shorts/total:6.2%}  "
        f"flat={flats/total:6.2%}  (n={total})"
    )
