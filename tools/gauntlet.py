"""Out-of-sample gauntlet for trend candidates: instrument + time splits.

For each candidate (strategy, params, timeframe) this runs:
  1. ETHUSDT full period          (different instrument)
  2. BTCUSDT year-1 / year-2      (time stability)
  3. ETHUSDT year-1 / year-2
  4. Walk-forward OOS Sharpe + Monte Carlo p-value on equity returns

Usage:
    python3 tools/gauntlet.py [--workers 8]

Expects data/{btcusdt,ethusdt}_{1h,4h,1d}.csv (see COMMANDS.md).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

logging.disable(logging.CRITICAL)

CANDIDATES = [
    ("trend_following", {"fast": 20, "slow": 50}, "4h"),
    ("trend_following", {"fast": 50, "slow": 200}, "4h"),
    ("ema_cross", {}, "1d"),
    ("dual_ma", {}, "1d"),
]

FILES = {
    "btc_1h": "data/btcusdt_1h.csv",
    "btc_4h": "data/btcusdt_4h.csv",
    "btc_1d": "data/btcusdt_1d.csv",
    "eth_1h": "data/ethusdt_1h.csv",
    "eth_4h": "data/ethusdt_4h.csv",
    "eth_1d": "data/ethusdt_1d.csv",
}

_CACHE: dict = {}


def load_bars(path, t0=None, t1=None):
    from cryptobot.backtest.runner import OhlcvBar

    df = pd.read_csv(path)
    if t0 is not None:
        df = df[df["ts"] >= t0]
    if t1 is not None:
        df = df[df["ts"] < t1]
    return [
        OhlcvBar(timestamp=datetime.fromtimestamp(int(r.ts) / 1000, tz=UTC),
                 open=float(r.open), high=float(r.high), low=float(r.low),
                 close=float(r.close), volume=float(r.vol))
        for r in df.itertuples(index=False)
    ]


def bh(bars):
    return bars[-1].close / bars[0].close - 1


def run_one(job):
    name, params, key, split = job
    path = FILES[key]
    try:
        from cryptobot.backtest.runner import make_strategy, run_backtest

        if (path, split) not in _CACHE:
            if split == "full":
                _CACHE[(path, split)] = load_bars(path)
            elif split == "y1":
                _CACHE[(path, split)] = load_bars(path, t1=1754006400000)   # < 2025-08-01
            else:
                _CACHE[(path, split)] = load_bars(path, t0=1754006400000)   # >= 2025-08-01
        bars = _CACHE[(path, split)]
        strat = make_strategy(name, **params)
        res = asyncio.run(run_backtest(bars, strategy=strat,
                                       initial_capital=Decimal("10000"),
                                       collect_trades=True, risk_fraction=1.0,
                                       slippage_bps=3, commission_bps=5))
        peak, mdd = 0.0, 0.0
        for _, eq in res.equity_curve:
            v = float(eq)
            peak = max(peak, v)
            if peak > 0:
                mdd = max(mdd, (peak - v) / peak)

        # statistical validation on per-bar equity returns
        ec = res.equity_curve
        rets = []
        for i in range(1, len(ec)):
            p, c = float(ec[i - 1][1]), float(ec[i][1])
            if p > 0:
                rets.append((c - p) / p)
        wf = mc_p = None
        if len(rets) >= 30:
            from cryptobot.backtest.validation import run_validation
            v = run_validation(rets, n_splits=5, n_permutations=100)
            wf = v["walk_forward"]["oos_sharpe"]
            mc = v["monte_carlo"]["p_value"]
            mc_p = mc

        return {"label": f"{name}{('/' + str(params['fast']) + '-' + str(params['slow'])) if params else ''}",
                "key": key, "split": split, "ret": res.total_return, "trades": res.n_trades,
                "mdd": mdd, "wf": wf, "mc_p": mc_p, "bh": bh(bars), "n_bars": len(bars)}
    except Exception as e:  # noqa: BLE001
        return {"label": name, "key": key, "split": split, "err": str(e)[:60]}


def main():
    jobs = []
    for name, params, tf in CANDIDATES:
        for inst in ("btc", "eth"):
            for split in ("full", "y1", "y2"):
                jobs.append((name, params, f"{inst}_{tf}", split))

    out = {}
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()

    with ProcessPoolExecutor(max_workers=args.workers or os.cpu_count() or 4) as ex:
        for _job, r in zip(jobs, ex.map(run_one, jobs, chunksize=1), strict=True):
            out[(r["label"], r["key"], r["split"])] = r

    print(f"{'candidate':<26}{'dataset':<12}{'ret':>9}{'MDD':>8}{'trades':>8}"
          f"{'wfSharpe':>10}{'MCp':>7}{'b&h':>9}{'bars':>7}")
    print("-" * 96)
    for label, params, tf in CANDIDATES:
        lab = f"{label}{('/' + str(params['fast']) + '-' + str(params['slow'])) if params else ''}"
        for inst in ("btc", "eth"):
            for split in ("full", "y1", "y2"):
                r = out.get((lab, f"{inst}_{tf}", split))
                if r is None or "err" in r:
                    print(f"{lab:<26}{inst + '/' + split:<12}ERR {r.get('err', '') if r else 'missing'}")
                    continue
                wf = f"{r['wf']:+.2f}" if r["wf"] is not None else "-"
                mcp = f"{r['mc_p']:.3f}" if r["mc_p"] is not None else "-"
                print(f"{lab:<26}{inst + '/' + split:<12}{r['ret'] * 100:+8.1f}%"
                      f"{r['mdd'] * 100:>7.1f}%{r['trades']:>8d}{wf:>10}{mcp:>7}"
                      f"{r['bh'] * 100:+8.1f}%{r['n_bars']:>7d}")
        print()


if __name__ == "__main__":
    main()
