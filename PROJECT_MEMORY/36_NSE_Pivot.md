# NSE pivot — Nifty50 pipeline + first sweep (2026-08-24)

Direction change: trade Indian equities (NSE Nifty50), not crypto.
Crypto gate v2 keeps running on :8081-8083 as the plumbing pilot.

## What's in place now

1. **Constituents**: official NSE list fetched to `tmp/nifty50.csv`
   (archives.nseindia.com ind_nifty50list.csv; 50 symbols, EQ series).
2. **Data**: `tools/download_nse.py` — yfinance `.NS` downloader, same CSV
   schema as crypto (ts,open,high,low,close,vol). Interval limits enforced
   (1m=7d, 5m/15m=60d, 1h=730d, 1d=max). All 50 daily files in
   `data/nse/` (~6,600 bars each, back to 2000).
3. **Sweep tooling**: `tools/matrix_sweep.py` now takes
   `--data-dir/--symbols/--timeframes/--fee-bps/--slip-bps/--out-suffix`;
   explicit fork context so CLI-patched globals reach workers (forkserver
   default was silently re-importing defaults).
4. **Cost model used** (delivery economics, per side): 11 bps fee
   (STT 0.1% both sides + txn/GST/stamp) + 1 bp slippage. Intraday would be
   ~2 bps/side (STT sell-only 2.5bps round trip).

## First sweep: 89 algos × 50 stocks × 1d = 4,450 runs, 0 errors

Raw: `30_hft_matrix_raw_nse50.json`. Headline after excluding the broken
volume_spike rows (#57):

| algo | wins | mean sharpe | median ret (26y) | verdict |
|---|---|---|---|---|
| **trend_following** | **46/50** | **0.36** | +682% (~7.5%/yr CAGR) | real edge, actively traded |
| open_range | 26/50 | 0.09 | +13% | marginal |
| dispersion | 26/50 | 0.05 | +3% | noise |

⚠️ volume_spike "50/50, Sharpe 0.49" is INVALID: precedence bug makes it a
one-time buy-and-hold (trades=0). Its returns ≈ the index itself. #57 filed.

## What live NSE trading still needs (not built yet)

1. **Broker adapter** — Zerodha Kite / Upstox / Angel One / Fyers REST for
   order placement. SimulatedVenue already covers paper mode (symbol-
   agnostic); ccxt venue is crypto-only.
2. **Market calendar** — 09:15–15:30 IST sessions, NSE holidays; LiveTrader
   currently assumes 24/7 crypto streams.
3. **Tick size** — ₹0.05 grid for price quantization.
4. **Long-only constraint** — cash-market delivery cannot short; catalog
   algos that flip short model futures instead. Decide per-strategy.
5. **Equity tax engine** — current tax.py is crypto §115BBH; equities need
   STCG 20% / LTCG 12.5% >₹1.25L with STT-paid treatment.

## Next steps

1. Walk-forward validate trend_following per stock (`tools/wf_validate.py
   --data-dir data/nse`) and pick the top basket.
2. Choose broker + build adapter behind the existing Venue protocol.
3. Market-hours-aware LiveTrader session loop.
