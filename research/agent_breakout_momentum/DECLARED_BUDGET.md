# DECLARED PARAMETER BUDGET — `breakout_momentum_strategy` on NSE

**Written BEFORE any return/performance number was computed on either window.**
Only *firing rates* (signal liveness) and *data structure* were inspected beforehand,
because a variant whose signal never fires cannot be tuned at all. No CAGR, Sharpe,
drawdown or return was looked at before this file existed.

---

## 1. The strategy, as written

`src/cryptobot/strategies/catalog/breakout_momentum_strategy.py`

```
hh = donchian_high(highs, period)      # max(highs[-period:])  -- INCLUDES today's bar
m  = roc(closes, mom_period)           # close/close[-mom_period] - 1
+1 if close[-1] >= hh and m > 0
-1 if close[-1] <= ll and m < 0
```

Defaults: `period=20`, `mom_period=10`.

**Not crypto-specific.** No funding rate, no liquidations, no stablecoin peg, no options
IV, no spot-futures basis. It is a price-only Donchian breakout + ROC filter, which has
an unambiguous NSE meaning. Per brief §8 the "no NSE meaning" exit does not apply, so
the work proceeds.

## 2. Three structural facts established before declaring variants

**(a) The vectorised port is bit-exact.** I drove the real
`BreakoutMomentumStrategy.signal()` object bar-by-bar over 7,980 post-warmup bars of 3
real symbols and compared to my vectorised panel. Faithful variant: **0 mismatches**.

**(b) The faithful channel convention makes the signal near-dead.**
`donchian_high` takes `max(highs[-period:])` — it includes *today's* high. Since
`high ≥ close` always, `close[-1] >= hh` can only hold when today's close equals today's
high AND today's high is the 20-day maximum. Decomposition over all 208,226 finite
symbol-bars:

| condition | % of bars |
|---|---|
| `close == today's high` | 0.628% |
| `today's high == 20d high` | 14.475% |
| **both = the actual breakout test** | **0.267%** |
| both **and** `ROC(10) > 0` (the shipped signal) | **0.031%** |

65 symbol-bars in the whole 18.8-year sample, in only 49 distinct sessions, clustered in
2008 (16), 2009 (22), 2011 (2), 2012 (1) and 2026 (24).
**In the TRAIN window 2016-01-01 → 2023-12-31 it fires exactly ZERO times.**
This is far below the brief §6.3 liveness floor of ~5%: the shipped strategy is
effectively always-flat and cannot be tuned at all.

**(c) The ROC conjunct is logically redundant with the breakout condition.**
For the *excluded*-bar channel, `close[t] ≥ max(high[t-20..t-1])` implies
`close[t] ≥ high[t-k] ≥ close[t-k]` for every `k ≤ 20`, hence `ROC(k) ≥ 0` always. The
catalog's strict `ROC(k) > 0` therefore rejects *only* bars where `close[t] == close[t-k]`
exactly — i.e. completely flat price series. Verified exhaustively: of the breakout bars,
the ones the filter rejects number 493 (k=5), 488 (k=10), 478 (k=20), and **every one of
them has momentum shortfall exactly 0.0**. So for any `mom_period ≤ period`, the filter is
a stale-price guard and nothing else.

---

## 3. DECLARED BUDGET — exactly 5 variants, no more

A one-factor-at-a-time ladder outward from the catalog. Every step changes exactly one
thing, so each is attributable.

| # | name | channel | period | mom_period | what it changes vs the row above |
|---|------|---------|--------|------------|----------------------------------|
| V1 | `FAITHFUL` | incl | 20 | 10 | — the catalog, verbatim |
| V2 | `EXCL20` | excl | 20 | 10 | channel convention: prior-20d high instead of inclusive. *Expect:* alive (~7.3% of TRAIN bars) |
| V3 | `EXCL20_NOMOM` | excl | 20 | 0 | drop the ROC conjunct. *Expect:* **≡ V2**, per fact (c) |
| V4 | `EXCL55` | excl | 55 | 10 | channel length 20 → 55 (classic 3-month Donchian) |
| V5 | `EXCL55_MOM63` | excl | 55 | 63 | confirmation horizon 10 → 63 bars (1 quarter). First variant where the ROC filter genuinely bites (`mom > period`) |

Exceeding these 5 invalidates the run. If I run a 6th, I will report it rather than hide
it. I have not.

## 4. Fixed infrastructure — NOT counted as variants

Chosen by brief §5 and by the evidence already recorded in `nsealgo/factors/core.py`,
and held identical across all 5 variants so they cannot confound the comparison:

| Choice | Value | Why |
|---|---|---|
| Cross-sectional ranking | trailing 126-bar momentum percentile rank, among flagged names only | brief §5. 126d = 6m, which `factors/core.py` records as the best long-only risk-adjusted Indian momentum horizon (Nigam & Pandey 2023) |
| Rebalance | monthly (`rebalance="M"`) | `engine.py` docstring: monthly is what the Indian evidence supports; weekly is unsupported |
| Portfolio | `PortfolioConfig()` defaults — 22 names, 12% single, 25% sector, 10% cash, 35% turnover budget | `GOAL.md` §3.2. Enforced by the engine, not bypassed |
| Costs | `CostModel(segment="delivery", slippage_bps=5)` → 21.92 bps all-in round trip | brief §3. Costs mandatory, never reduced |
| Short leg | dropped entirely | Zerodha delivery cannot short |

## 5. Selection rule (fixed now, before seeing results)

Choose **one** variant by TRAIN net CAGR; tie-break on TRAIN Sharpe, then on TRAIN MaxDD.
The winner is then run **unchanged** on TEST, exactly once. No threshold is adjusted
until an equity curve looks good.