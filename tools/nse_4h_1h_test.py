#!/usr/bin/env python3
"""NSE 4h & 1h timeframe test — trend_following family, honest costs.

Yahoo has no native 4h interval for NSE, so 4h bars are built by
resampling 1h bars WITHIN each trading day (bar A = first four hours,
bar B = remainder of the session). No bar ever spans an overnight gap.

Two cost models per timeframe because holding period decides the tax
regime:
  - INTRADAY (MIS): 2bps fee + 1bp slip per side
  - DELIVERY (CNC): 11bps fee + 1bp slip per side

Writes PROJECT_MEMORY/41_NSE_4h_1h_Test.md.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

logging.disable(logging.CRITICAL)

from cryptobot.backtest.metrics import PerformanceMetrics  # noqa: E402
from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest  # noqa: E402

OUT_MD = Path("PROJECT_MEMORY/41_NSE_4h_1h_Test.md")
ALGOS = [("trend_following", {"fast": 5, "slow": 12}),
         ("dual_ma", {"fast": 20, "slow": 50}),
         ("macd", {})]
COST_MODES = {"intraday(MIS)": (2, 1), "delivery(CNC)": (11, 1)}


def load_1h(symbol: str) -> list[OhlcvBar]:
    df = pd.read_csv(f"data/nse/{symbol.lower()}_1h.csv")
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def resample_session_4h(bars: list[OhlcvBar]) -> list[OhlcvBar]:
    """Group each IST trading day's hourly bars into two session-aligned
    4h-ish buckets: first 4 hours, then the rest."""
    from collections import defaultdict

    days: dict[str, list[OhlcvBar]] = defaultdict(list)
    ist = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
    for b in bars:
        d = b.timestamp.astimezone(ist).date().isoformat()
        days[d].append(b)
    out: list[OhlcvBar] = []
    for d in sorted(days):
        hrs = sorted(days[d], key=lambda b: b.timestamp)
        for chunk in (hrs[:4], hrs[4:]):
            if not chunk:
                continue
            out.append(OhlcvBar(
                timestamp=chunk[0].timestamp,
                open=chunk[0].open,
                high=max(b.high for b in chunk),
                low=min(b.low for b in chunk),
                close=chunk[-1].close,
                volume=sum(b.volume for b in chunk),
            ))
    return out


def metrics(curve) -> tuple[float, float, float]:
    v = [float(x) for _t, x in curve]
    if len(v) < 2:
        return 0.0, 0.0, 0.0
    pm = PerformanceMetrics()
    pm.add_value(v[0])
    rets = [v[i] / v[i - 1] - 1.0 for i in range(1, len(v))]
    for r in rets:
        pm.add_value(v[0] * (1 + r))
    sharpe = float(pm.calculate_sharpe_ratio(rets))
    mdd = float(pm.calculate_drawdown(pd.Series(v))) / 100.0
    return v[-1] / v[0] - 1.0, sharpe, mdd


async def run_one(sym: str, bars, algo: str, params: dict,
                  fee: int, slip: int) -> dict:
    strat = make_strategy(algo, **params)
    res = await run_backtest(bars, strat, symbol=sym,
                             initial_capital=Decimal("10000"),
                             risk_fraction=1.0,
                             slippage_bps=slip, commission_bps=fee)
    ret, sharpe, mdd = metrics(res.equity_curve)
    return {"symbol": sym, "algo": algo, "ret": ret, "sharpe": sharpe,
            "mdd": mdd, "trades": res.n_trades}


async def main() -> None:
    symbols = sorted(p.stem.split("_")[0].upper()
                     for p in Path("data/nse").glob("*_1h.csv"))
    print(f"{len(symbols)} stocks", flush=True)

    # preload + build 4h once
    data_1h: dict[str, list] = {}
    data_4h: dict[str, list] = {}
    for sym in symbols:
        try:
            h1 = load_1h(sym)
            if len(h1) > 100:
                data_1h[sym] = h1
                data_4h[sym] = resample_session_4h(h1)
        except Exception as exc:  # noqa: BLE001
            print(f"{sym}: load fail {exc}", flush=True)

    results: list[dict] = []
    for tf_name, dataset in (("1h", data_1h), ("4h(session)", data_4h)):
        for mode, (fee, slip) in COST_MODES.items():
            for sym in symbols:
                bars = dataset.get(sym)
                if not bars:
                    continue
                for algo, params in ALGOS:
                    try:
                        r = await run_one(sym, bars, algo, params, fee, slip)
                        r.update(tf=tf_name, mode=mode)
                        results.append(r)
                    except Exception as exc:  # noqa: BLE001
                        results.append({"tf": tf_name, "mode": mode,
                                        "symbol": sym, "algo": algo,
                                        "error": str(exc)[:80]})
            print(f"done {tf_name} {mode}", flush=True)

    # aggregate
    lines = ["# NSE 4h & 1h test — trend_following family",
             "",
             f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} · "
             f"{len(symbols)} stocks · 4h = session-aligned resample of 1h "
             "(no native Yahoo 4h for NSE)",
             "",
             "| tf | costs | algo | wins | mean sharpe | median ret | trades |",
             "|---|---|---|---|---|---|---|"]
    groups: dict[tuple, list[dict]] = {}
    for r in results:
        groups.setdefault((r["tf"], r["mode"], r["algo"]), []).append(r)
    import statistics as st
    for key in sorted(groups, key=str):
        rs = [r for r in groups[key] if "error" not in r]
        if not rs:
            continue
        wins = sum(1 for r in rs if r["ret"] > 0)
        mean_sh = sum(r["sharpe"] for r in rs) / len(rs)
        med = st.median([r["ret"] for r in rs])
        trades = sum(r["trades"] for r in rs)
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {wins}/{len(rs)} "
                     f"| {mean_sh:.2f} | {med:+.1%} | {trades} |")

    lines += ["", "## Per-stock detail", ""]
    for key in sorted(groups, key=str):
        lines.append(f"### {key[0]} · {key[1]} · {key[2]}")
        lines.append("")
        lines.append("| symbol | ret | sharpe | mdd | trades |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(groups[key], key=lambda x: x.get("sharpe", 0),
                        reverse=True):
            if "error" in r:
                continue
            lines.append(f"| {r['symbol']} | {r['ret']:+.1%} | {r['sharpe']:.2f} "
                         f"| {r['mdd']:.1%} | {r['trades']} |")
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    asyncio.run(main())
