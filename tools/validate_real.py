"""Validate catalog strategies against REAL Binance BTCUSDT 1h data."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptobot.backtest.runner import OhlcvBar, make_strategy, run_backtest
from cryptobot.backtest.validation import run_validation

logging.disable(logging.CRITICAL)


def load_bars(path):
    data = json.loads(Path(path).read_text())
    bars = []
    for k in data:
        ts = datetime.fromtimestamp(k["ts"] / 1000, tz=UTC)
        bars.append(OhlcvBar(
            timestamp=ts, open=k["open"], high=k["high"],
            low=k["low"], close=k["close"], volume=k["volume"],
        ))
    return bars


def run_one(bars, name):
    try:
        strat = make_strategy(name)
    except Exception as e:
        return {"error": f"make: {e}"[:40]}
    result = asyncio.run(run_backtest(bars, strat, collect_trades=False))
    ec = result.equity_curve
    rets = []
    for i in range(1, len(ec)):
        prev, cur = float(ec[i - 1][1]), float(ec[i][1])
        if prev > 0:
            rets.append((cur - prev) / prev)
    if len(rets) < 30:
        return {"trades": result.n_trades, "ret": result.total_return, "n_rets": len(rets)}
    v = run_validation(rets, n_splits=5, n_permutations=200, n_trials=50)
    return {
        "trades": result.n_trades,
        "ret": result.total_return,
        "wf": v["walk_forward"]["oos_sharpe"],
        "ds": v["deflated_sharpe"]["deflated_sharpe"] if isinstance(v["deflated_sharpe"], dict) else v["deflated_sharpe"],
        "mc_p": v["monte_carlo"]["p_value"],
        "passed": bool(v["passed"]),
    }


CATALOG_NAMES = sorted({(Path(p).stem) for p in Path("src/cryptobot/strategies/catalog").glob("*.py") if p.stem != "__init__"})


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/btcusdt_1h.json"
    bars = load_bars(data_path)
    print(f"Loaded {len(bars)} real BTCUSDT 1h bars ({bars[0].timestamp.date()} → {bars[-1].timestamp.date()})")
    print(f"Price range: ${bars[0].close:.0f} → ${bars[-1].close:.0f}\n")
    print(f"{'name':<22} {'ret':>8} {'wf':>8} {'ds':>6} {'mc_p':>6} {'pass':>5} {'trades':>6}")
    print("-" * 70)
    rows = []
    for name in CATALOG_NAMES:
        try:
            r = run_one(bars, name)
        except Exception as e:
            print(f"{name:<22}  ERR {e}"[:80])
            continue
        if "wf" not in r:
            rows.append((name, r.get("ret", 0), 0, 0, 1, False, r.get("trades", 0), False))
            continue
        rows.append((name, r["ret"], r["wf"], r["ds"], r["mc_p"], r["passed"], r["trades"], True))
        print(f"{name:<22} {r['ret']:+8.3f} {r['wf']:+8.2f} {r['ds']:+6.2f} {r['mc_p']:>6.3f} {str(r['passed']):>5} {r['trades']:>6d}")

    # Filter survivors
    passed = [r for r in rows if r[7] and r[5]]
    if passed:
        print(f"\n✓ SURVIVORS ({len(passed)}):")
        for name, ret, wf, ds, mc_p, _ok, trades, _ in sorted(passed, key=lambda r: r[1], reverse=True):
            print(f"  {name:<22} ret={ret*100:+6.2f}%  wf={wf:+.2f}  ds={ds:+.2f}  mc_p={mc_p:.3f}  trades={trades}")
    print(f"\nSummary: {len(passed)}/{len(rows)} strategies passed walk-forward + MC gauntlet on REAL Binance BTCUSDT data")


if __name__ == "__main__":
    main()
