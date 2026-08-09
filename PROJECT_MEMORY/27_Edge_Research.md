# 27 — Edge Research: Findings & Gates (Phase 0–2)

Status: LIVE — updated continuously. Last update: 2026-08-09

## Objective

Find an edge that survives: (1) real Binance fees (incl. BNB discount tiers), (2)
robustness across time windows, (3) adequate sample size (≥30 trades ideally).
Research-first, paper-trade later, live only after gates.

## Phase 0 — Fee Reality (DONE)

| Venue | VIP0 taker/maker | With 25% BNB discount |
|---|---|---|
| Spot BTCUSDT/ETHUSDT | 10 / 10 bps | 7.5 / 7.5 bps |
| USDT-M Perp | 5 / 2 bps | 4.5 / 1.8 bps |

Funding-arb round-trip (spot taker + perp maker, 2 opens + 2 closes): **~18.6 bps**.

## Phase 1 — Venue Realism (DONE)

- `SimulatedVenue` now supports maker/taker commission split (`maker_commission_bps`):
  LIMIT fills = maker rate + no slippage; MARKET = taker rate + slippage.
- Funding-arb has a dedicated runner: `src/cryptobot/backtest/funding_sim.py`
  (real 8h funding timestamps, two legs, basis entry/exit, 4-fill fees).
  Validated to match the prototype exactly. Unit tests in
  `tests/unit/test_funding_sim.py`.

## Phase 2A — Funding Carry (VERDICT: REAL, REGIME-BOUND, SMALL NOW)

Full history at BNB fee tier (spot taker 7.5 + perp maker 1.8):

| Asset | Total | /yr | Trips | Sample |
|---|---|---|---|---|
| BTC | +33.95% | +4.92%/yr | 83 | 6.9y |
| ETH | +37.72% | +5.64%/yr | 110 | 6.7y |

Fee sensitivity: 5bps all-legs → BTC +31.6% / ETH +34.6%; 7.5bps → +15.0% / +12.6%;
10bps (no BNB discount, taker all legs) → **BTC -1.6% / ETH -9.4%** (edge dies).

Annual decomposition (BTC): 2019 +2.0%, 2020 +8.6%, 2021 +19.1%, 2022 0 trips,
2023 +0.4%, 2024 +4.0%, 2025 -0.6%, 2026 0 trips.
**All edge is 2020–2021 bull-regime basis.** Since 2024 the window bests are
+4.99% BTC (5 trips) / +6.37% ETH (4 trips) — small sample, mostly basis capture.

**Gate: MARGINAL PASS** — real but modest; not actionable while carry is quiet.

## Phase 2B — Stat Arb (VERDICT: REJECT)

BTC vs ETH 1m correlation-gated pair spread, vectorized sweep (lookback 30–240,
z_entry 1–3, corr≥0.5/0.8, 5bps taker per leg):

- Best config: +0.20% total (11 trades, lookback 120, z 2.0, corr 0.8).
- 240-lookback configs: ~0–1 trades. Most configs ≤ 0.
- Noise-level sample; spread reversion on 1m does not cover taker fees.

**Gate: FAIL.**

## Phase 2C — Market Making (VERDICT: REJECT)

Real BTCUSDT spot depth captured (524 snapshots @ 3s, 30 min, top-5 levels,
`/tmp/opencode/btc_depth_2h.json`). Live book spreads:

| Instrument | Live touch spread |
|---|---|
| BTCUSDT spot | 0.0015 bps (1 tick of 0.01) |
| BTCUSDT perp | 0.0154 bps |
| ETHUSDT perp | 0.0524 bps |

Fill model (quote at mid±half, fill when book crosses our quote): at 0.2bps
spread only 84 fills in 30 min; gross capture $54.6 vs adverse selection $253.7
(~4.6x gross) vs maker fees $1,965 (3.6bps round trip). At any spread ≥ 3.6bps
(to pay fees) fills collapse to ~1%.

**Gate: FAIL** — the top of book is already 1 tick wide; retail maker capture is
negative even before fees. The HFTs own the queue.

## Phase 2D — Daily Trend (VERDICT: REJECT)

EMA fast/slow + ATR chandelier stop on 9y daily BTC/ETH:

| Test | BTC trend | BTC buy&hold | ETH trend | ETH buy&hold |
|---|---|---|---|---|
| Full window | +238% | +1416% | +124% | +536% |
| Last 900 days | +5.4% | +24.6% | -10.8% | -33.4% |

**Gate: FAIL** — structurally underperforms holding; only "wins" by clipping the
mega-bull's tail.

## Overall Phase 2 Verdict

Nothing currently deployable. Funding carry is the only edge that survives fees,
and it is regime-bound (mostly dormant since 2022). Every other category
(1m price, ML, stat arb, daily trend, market making) measured negative or
noise after real fees on real data.

## Phase 3 — Paper Harness (LIVE)

`src/cryptobot/live/paper_harness.py` — `FundingPaperHarness` runs on live public data
(no API keys): spot bookTicker WS (combined `/stream`) + perp `premiumIndex`
(mark + lastFundingRate) via REST-poll fallback (`--poll-fapi`) because the
futures WS (`wss://fstream.binance.com`) is network-blocked in this environment.
- Gates on position state; accumulates carry at 8h cadence; appends to CSV log.
- CLI: `python -m cryptobot.cli.main paper-funder --symbols BTCUSDT,ETHUSDT --hours 6 --poll-fapi`
- Unit tests: `tests/unit/test_live_paper_harness.py` (8 tests). Two live bugs
  fixed during smoke: combined-stream messages arrive as aiohttp `WSMessage`
  (must read `.data`); `--symbols` comma-split.
- Live smoke confirmed: spot + perp prices flow, state advances to `no_signal`
  (current basis < 5bps entry threshold — quiet market).

## Phase 2E — Carry Re-derived with Correct Accounting (2026-08-09)

Re-derived the carry edge with explicit cash accounting (no basis double-count on
close; perp klines anchored to close-time not open-time). Spike-threshold
strategy: enter long-spot/short-perp when funding ≥ threshold, exit ≤ 0.005%:

| Asset | Full history (2019-26) | Walk-forward train (19-23) | Walk-forward test (24-26) |
|---|---|---|---|
| BTC (≤0.03%) | +97% | +87% (11 trips) | **+10.5% (3 trips)** |
| ETH (≤0.03%) | +223% | +209% (8 trips) | **+10.4% (3 trips)** |

- maxDD ~0.8-1.7% (delta-neutral by construction; only fee + basis residual).
- Fee sensitivity flat: 2 → 5bps maker barely moves returns (few trips/year).
- "Always-on" variant (hold whenever funding ≥ 0) is **not** robust: ETH 2025
  −31.6% (basis blowups while invested in a crash regime). Threshold filter is
  mandatory.
- Verdict: consistent with Phase 2A — real, regime-bound edge, ~4-5%/yr in the
  modern era, deployable only via the threshold-gated carry (now engine-wired).

## Next

- First engine run of the wired carry on real CSV data (2019-2026) and reconcile
  vs the Phase 2E standalone numbers (expect ~4-5%/yr modern regime). ✅ 2026-08-09 —
  see Phase 2F; absolute PnL is not directly comparable (fixed-qty legs vs scaled).
- Decide taker-on-exit vs maker-on-both-legs: exits should use taker fees for
  realism; re-run fee sensitivity at 10bps all-taker (Phase 2A says edge dies). ✅
  Engine run uses taker on all fills (SimulatedVenue MARKET = taker fee + slippage).
- Phase 3 live validation: run the paper harness for a multi-day window on BTC+ETH
  to observe basis excursions; log basis explicitly in JSON output for signal confirmation.
- If a real basis signal fires, inspect fill/pnl path end-to-end before any live capital.
- Revisit Phase 2A fee sensitivity: the edge only survives at BNB-discount taker+maker
  routing — validate BNB-hold status before live.

## Phase 2E2 — Engine-Wired Carry on Real Data (2026-08-09) ✅

First `run_carry` run from `BacktestEngine` with the CSV funding provider (real
Binance funding history, 2019-2026) and real spot 1h + perp 8h klines:

| Metric | Value |
|---|---|
| Window | 2019-09-08 .. 2026-08-06 (7573 × 8h bars) |
| Capital / leg | 10,000 USDT fixed qty (not risk-scaled) |
| Entry | funding ≥ 0.01%, basis ≥ 5bps; exit basis ≤ basis_exit or rate ≤ 0 |
| Final equity | 555,672 USDT (+5,456%) |

Per-year contract PnL: 2019 +92, 2020 +42,212, 2021 +227,284, 2022 +55,809,
2023 +52,788, 2024 +202,400, 2025 +89,276, 2026 +4,253. All legs execute at
MARKET (taker fee + slippage) inside SimulatedVenue.

Interpretation: the wired engine reproduces the Phase 2E trade series direction
(carry is real, regime-bound), but the absolute number is inflated vs the
standalone by (a) fixed-size ~1 BTC legs on a 10x price drift (position grows
with BTC price, compounding drift in a margin of the PnL), and (b) 2019–2021
basis blowouts that predate tight perp pricing. The reliable signal from both
the standalone and engine paths: **edge concentrates in the bull-regime basis
and is ~quiet since 2024** (2025 +2.3%/yr on a 10k base, 2026 quiet).

Tooling now available:
- CLI: `python -m cryptobot.cli.main carry --spot spot_1h.csv --perp perp_8h.csv
  --funding funding.csv --json` (auto-aligns spot 1h → perp 8h close instants).
- Script: `tools/run_carry_real.py` (same pipeline + per-year breakdown;
  defaults to `/tmp/opencode/spot_BTCUSDT_1h.csv`, `perp_BTCUSDT_8h.csv`,
  `funding_BTCUSDT.csv`).
- Alignment helper: `backtest.carry.align_spot_to_perp` — perp kline at U closes
  at U+8h; the contemporaneous spot 1h close is the bar opening at U+7h. Without
  this, spot legs price 7-8h stale and mint fake mismatch PnL. Tested across the
  sample: same-instant spot/perp within ~5 bps.
