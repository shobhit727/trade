# NSE all-timeframe sweep results (2026-08-24)

Data: `data/nse/` — 50 Nifty50 stocks (ADANIENT intraday unavailable on
Yahoo; 49/50 for 15m+5m). Costs: intraday economics 2bps fee + 1bp slip
per side (STT sell-only round trip ≈ 3.5bps + slippage).
Raw JSON per tf: `30_hft_matrix_raw_nse50_{1h,15m,5m,1m}.json`.
Rows with ≤3 trades and the broken volume_spike (#57) excluded.

## Results by timeframe (89 algos × ~49 stocks)

| tf | active runs | profitable | best algo (wins, mean sharpe, median ret) |
|---|---|---|---|
| 1h | 3700 | 883 (24%) | zscore (29/50, **−0.20**, +6.7%) |
| 15m | 3536 | 597 (17%) | stablecoin_peg (35/49, −0.44, +3.5%) |
| 5m | 3507 | 232 (7%) | gaussian (25/49, −0.99, +0.6%) |
| 1m | 3267 | 77 (2%) | dual_ma (3/50, −2.73, −2.7%) |

**Every intraday timeframe has negative mean Sharpe across the board.**
The 1h "best" loses less than it wins; nothing is tradeable.

## Comparison with daily (delivery costs, from 36_NSE_Pivot)

| tf | character |
|---|---|
| **1d** | trend_following 46/50 wins, mean sharpe **+0.36**, median +682%/26y |
| 1h | everything negative |
| 15m | everything negative |
| 5m | everything negative |
| 1m | catastrophic |

## Conclusion

Same structural answer as crypto, now confirmed on Indian equities:
**the edge lives on daily bars with delivery-style holding; intraday OHLCV
signals die to costs + adverse selection at every frequency we can test.**
NSE intraday costs (~5bps round trip) are actually CHEAPER than crypto
taker (~16bps) and it still doesn't matter — the signals themselves carry
no intraday edge on bar data.

Production shape for NSE: trend_following basket on daily bars, delivery
holdings, WF-validate per stock before gate.
