# 2026-window revalidation (2026-01-01 → 2026-08-24)

Fresh Binance download into `data/2026/` (BTC+ETH × 5m/15m/4h/1d).
All prior conclusions re-tested on this unseen window.

## The validated trio — all PASS again

| config | OOS sharpe | OOS return | full period | verdict |
|---|---|---|---|---|
| dual_ma(5,50) BTC 1d | 0.61 | +4.8% | +27.5% / 0.85 / mdd 22.6% | **PASS** |
| time_series(60,.05) ETH 1d | **2.64** | +35.6% | +35.7% / 0.96 / mdd 21.5% | **PASS** |
| open_range(24) ETH 4h | 0.63 | +19.2% | +43.9% / 0.38 / mdd 21.6% | **PASS** |

time_series ETH is the standout on 2026 data (OOS Sharpe 2.64).

## Intraday maker replay — conclusion holds

Same 24-run grid as `34_Maker_Replay_Results.md`, now on 2026 bars:

- open_range 5m: BTC +11.8% / ETH +14.8% returns but Sharpe −0.96 / −0.72
- every other algo/timeframe: −15% to −87%, all negative Sharpe
- rsi_momentum still the worst (~−85% both symbols at 5m)

**Intraday OHLCV HFT remains dead on fresh data** — adverse selection at
maker fees is structural, not an artifact of the 2021–2025 sample.

## Bottom line

The production shortlist is unchanged and now double-validated:
dual_ma BTC 1d + time_series ETH 1d + open_range ETH 4h.
