# 27 — Edge Research: Findings & Gates (Phase 0–2)

*Status: LIVE — updated continuously. Last update: 2026-08-06*

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

## Next

- Phase 3: paper-trading harness on live public WS data (spot/perp + funding,
  no API keys) so the funding carry (the one surviving edge) can be observed live
- Commit: ML bugfix, venue maker model, funding_sim.py, tests, research doc
