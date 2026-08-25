# NSE trend_following basket — walk-forward shortlist (2026-08-25)

Per-stock WF validation (trend_following fast=5 slow=12 tuned ±40%,
30 trials, 65/35 train/OOS split, delivery costs 11+1bps/side).
Full log: tmp/wf_trend_loop.log · dashboard: PROJECT_MEMORY/38.

## Result: 8 of 50 stocks PASS

| stock | OOS sharpe | OOS return |
|---|---|---|
| TATACONSUM | 0.45 | +195.9% |
| BEL | 0.43 | +111.3% |
| TITAN | 0.41 | +127.7% |
| APOLLOHOSP | 0.40 | +86.2% |
| TATASTEEL | 0.38 | +69.7% |
| ULTRACEMCO | 0.37 | +98.2% |
| CIPLA | 0.25 | +31.2% |
| ADANIENT | 0.21 | +34.3% |

42/50 fail out-of-sample — the sweep's raw "46/50 profitable" collapses
under honest validation, exactly as it should. These 8 are the real
candidates.

## Basket proposal (paper gate next)

Equal-weight across the top 5-8 names, daily bars, delivery holdings,
long-only (no shorts in cash market). Per-name risk caps; portfolio
kill-switch at −25%; same 60-day paper gate rules as the crypto gate.

## Mid-frequency research verdict (same day)

nse_orb / vwap_revert on 49 stocks @15m with realistic intraday costs:
best mean sharpe −1.32 — naive session algos don't survive either.
Consistent with the bar-data finding: intraday edge needs order-book
information, not more bar-data algos.


## Recheck on adjusted data (2026-08-25, post-#58 fix)

All 8 original PASSes confirmed; ONGC (+0.88 sharpe!) and SUNPHARMA join.
**10/50 pass.** Log: tmp/wf_adjusted.log.

| stock | OOS sharpe | OOS ret |
|---|---|---|
| ONGC | 0.88 | +162.5% |
| APOLLOHOSP * | 0.59 | +144.0% |
| TATASTEEL * | 0.59 | +126.6% |
| CIPLA * | 0.51 | +60.8% |
| BEL * | 0.50 | +141.7% |
| TATACONSUM * | 0.46 | +198.3% |
| TITAN * | 0.42 | +129.2% |
| ULTRACEMCO * | 0.37 | +97.0% |
| ADANIENT * | 0.24 | +39.5% |
| SUNPHARMA | 0.22 | +46.4% |

(* = in original list; none dropped.)
