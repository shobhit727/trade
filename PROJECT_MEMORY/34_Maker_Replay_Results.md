# Maker-execution replay results (2026-08-23)

Tool: `tools/maker_replay.py` (+ `tests/unit/test_maker_replay.py`).
Model: resting limit at signal-bar close, fills only when a later bar trades
through (adverse selection captured), unfilled entries expire, stuck exits
taker-out. Maker cost 1bp/side vs taker 8bps/side.

## Results — 24 runs (6 algos × {5m,15m} × {BTC,ETH})

| algo | best case | worst case | verdict |
|---|---|---|---|
| open_range | BTC 5m +10.6% (Sharpe **−0.97**) | BTC 15m −35.8% | only survivor, still negative Sharpe |
| vwap | BTC 15m −25.7% | ETH 5m −61.6% | dead |
| ema_cross | ETH 15m −12.1% | ETH 5m −57.8% | dead |
| bollinger | BTC 15m −40.1% | ETH 5m −74.9% | dead |
| mean_reversion family | — | — | dead |
| rsi_momentum | ETH 15m −76.1% | BTC 5m −87.2% | dead |

Every single run has **negative Sharpe**. The single positive return
(open_range BTC 5m) loses 28.5% max drawdown for a coin-flip edge.

## Why the fee-survival estimates were wrong

`31_Fee_Survival.md` flipped 43–73 algos "positive" by linearly re-pricing
taker backtests at maker fees. That ignores **adverse selection**: a resting
limit fills precisely when the market moves through your level — you are
systematically filled on the wrong side. The replay captures this and the
edge evaporates.

## Conclusion — the HFT question is answered

Bar-level OHLCV signals cannot trade profitably intraday on Binance at any
realistic fee structure:

- taker (5+3bps): catastrophic (-14,000% equity runs)
- maker (1bp, zero slip, honest adverse selection): breakeven-to-ruin,
  universally negative Sharpe

True HFT requires order-book microstructure (queue position, flow toxicity,
latency races) — a different data regime and a different engine than the 89
OHLCV algorithms. Out of scope for this system's current architecture.

## What survives validation overall

| config | status |
|---|---|
| dual_ma(5,50) BTC 1d | WF PASS (OOS +30.2%) — gate day 2 |
| time_series(60,.05) ETH 1d | WF PASS (OOS +67%) — gate day 2 |
| open_range(24) ETH 4h | WF PASS (OOS sharpe 0.51, +146.4%) |
| everything intraday | FAIL at taker AND maker |

Recommended production shape: multi-timeframe portfolio of the three PASS
configs via MultiAlgoTrader; revisit HFT only with L2 order-book data.
