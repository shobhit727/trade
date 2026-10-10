# GOAL.md — NSE NIFTY-50 Systematic Trading · ₹21,00,000

> **Status:** v1.0 — constitution for this repo. Every design decision, risk limit, and
> go/no-go gate below is binding. Changing a number here means changing the strategy,
> not the number in the code.

---

## 1. Mission

Deploy a systematic, rules-based trading system for **all NIFTY-50 constituents on the
NSE** that trades a **₹21,00,000** capital base, and grow it toward a target of
**~3% net return per calendar month (~42.6% annualised)** — with a hard, code-enforced
floor that prevents permanent loss of capital.

**The mission has two objectives, in strict priority order:**

| # | Objective | Weight |
|---|-----------|--------|
| **P1** | **Do not permanently lose the capital.** Survive. | Non-negotiable |
| **P2** | Maximise net return, targeting 3%/month. | Optimised, never at P1's expense |

A strategy that returns 3%/month for 6 months then loses 40% is a **failure** of this
mission, not a success. Drawdown is a first-class objective, not a side effect.

---

## 2. The 3%/month target — stated honestly

### 2.1 What it means arithmetically

| Metric | Value |
|--------|-------|
| Monthly target | 3.0% net |
| Annualised (compounded) | `1.03^12 − 1` = **42.6%** |
| ₹21,00,000 → after 1 yr | ₹29,94,600 |
| ₹21,00,000 → after 3 yr | ₹61,31,900 |
| ₹21,00,000 → after 5 yr | ₹125,51,400 |

### 2.2 What it actually requires

**This is a top-decile institutional return, unlevered, in the most efficient equity
market on earth.** It is achievable in *some* periods. It is **not reliably achievable
every month**, and any system that claims otherwise is curve-fitted or lying.

Reference points for NIFTY-50 (historical, net of costs):

| Approach | Typical annualised net | Max DD |
|----------|----------------------|--------|
| NIFTY-50 buy & hold | 11–14% | −40% |
| Index futures cash & carry | 10–13% | −40% |
| Good cross-sectional swing strategy | 15–25% | −15–25% |
| **42.6% (this target)** | **top decile** | **unknown until measured** |

### 2.3 Honest success bands

I will not treat 3%/month as a pass/fail line, because a single-month comparison to a
smoothed target is noise. The real gate is **risk-adjusted, out-of-sample, net of full
Indian costs**. These are the bands:

| Band | Net annualised (OOS) | Sharpe | Max DD | Verdict |
|------|----------------------|--------|--------|---------|
| **A — Excellent** | ≥ 30% | ≥ 1.2 | < 25% | Deploy at full size |
| **B — Good** | 18–30% | ≥ 0.9 | < 30% | Deploy at 75% size |
| **C — Acceptable** | 12–18% | ≥ 0.7 | < 35% | Deploy at 50% size, paper-track 3mo |
| **D — Weak** | 6–12% | ≥ 0.5 | < 40% | **No deploy.** Keep researching |
| **E — Fail** | < 6% or Sharpe < 0.5 | — | — | **Kill.** Do not deploy |

**Band C or better with all gates passed is a success. Band A is a bonus.**
Reporting < 12% annualised honestly is required by §6, not optional.

> **Explicit commitment:** if the validated result is 1.4%/month (≈18% annualised, Band B),
> that is the number I report. I will not widen the definition of "3%", backfill the
> in-sample number, or quietly reduce costs to make the target appear met.

**Current measured band: D.** See §2.4. The band table above is unchanged by that result —
the definition was written before the measurement and is not being edited to fit it.

### 2.4 MEASURED RESULT — v3 (2026-10-10)

> Evidence: `reports/VALIDATION_v1.md` §0 — the v1 and v2 measurements are retained
> there unchanged as the historical record. Reproduce: `research/validate.py`.

#### ⚠️ THE HEADLINE GOT WORSE THREE TIMES. HERE IS EVERY STEP, IN ORDER.

**Every number this project has ever published for this strategy was too high, and each
correction made it worse.** The corrections were not a re-tuning of the strategy. They were
bugs — two of them critical — found one after another. The list is the headline:

| # | Measurement | OOS CAGR | OOS Sharpe | Band | What changed |
|---|-------------|----------|-----------|------|--------------|
| 1 | **v1** — data to 2026-08-25 | **13.40%** | 0.66 | C | The original measurement. |
| 2 | **v2** — data to 2026-10-01, portfolio-limit fix | **10.97%** | 0.44 | D | 27 extra sessions (~6 weeks) **and** two §3.2 breaches fixed: a 25.66% single name against a 12% cap, and 48 names held against `max_positions` 30. |
| 3 | **v2b** — **half-cost fix** | **9.89%** | 0.35 | D | The engine was charging **exactly half** the real cost stack. |
| 4 | **v3 — FINAL** — residual-weight fix | **9.71%** | 0.34 | D | `apply_turnover_budget` was diluting exits, so most of a sparse book was stale residue. |

**13.40% → 10.97% → 9.89% → 9.71%.** Not one of the intermediate numbers was a valid
result of the code as it stood. A reader who stopped reading at v1 was reading a number
that was **38% too high**; at v2, still **13% too high**.

**The important structural finding, and it is a statement about this project's methods
rather than about its strategy:** the only reason the current number is the current number
is that two independent audits went looking for it. Nothing in the routine pipeline would
have caught either bug. Both were found by adversarial probing — a cost-ratio assertion
and a plausibility check on realised exposure — running *against* the engine while
catalog trials were being run on top of it.

#### The two critical bugs that produced this number

**Bug 1 (CRITICAL) — the engine charged HALF the real cost stack.**
`all_in_round_trip_bps` is quoted per unit of **total** turnover. A full rotation of the
book (sell 100%, buy 100%) is `sum|dW| = 2.0`. The engine was multiplying by the
**one-way** turnover (`sum|dW|/2`) — so it charged exactly 0.5× the correct rate. The
ratio was proven to be **0.500000**, not approximately. Consequences:

- **Every CAGR this project had ever reported was flattered.**
- The **Gate 4 slippage stress test ran at half strength** — a gate that certified a
  robustness property the backtest never actually tested.

Fix: charge `sum|dW| * rate`. Cost of the fix: **10.97% → 9.89% CAGR, 0.44 → 0.35 Sharpe.**

**Bug 2 (HIGH) — residual-weight dilution.**
`apply_turnover_budget` blended the *whole* book toward the new target, so a name the
target no longer wanted decayed slowly instead of exiting. Measured on a sparse book:
**59% of the held weight was stale residue**, and the portfolio often held only **~0.6 of
its intended 0.9 exposure**. The delivered book was measuring the harness, not the signal.

Fix: **whole-position exits, and all-or-nothing adoption when the turnover budget binds.**
Cost of the fix: **9.89% → 9.71% CAGR.**

**Bug 3 (HIGH, data) — stray weekend bars.**
Four bogus Saturday/Sunday dates (2010-02-06, 2019-10-27, 2020-11-14, 2025-02-01) each
landed an **interior** NaN in 42 symbols, corrupting every rolling/ewm indicator for
`period` bars after the hole — silently, because the loader only validated *within* each
symbol. Fixed as cleaning rule **C8** (drop `dayofweek >= 5`). See
`reports/DATA_AUDIT.md` §0.1.

#### Walk-forward out-of-sample — FINAL

**2008-01-01 → 2026-10-01 (19.0y), 48 symbols, 4,625 trading days (4,629 before the C8
weekend-bar fix removed 4 bogus dates), full Indian cost stack (≈21.9 bps all-in per
complete rotation), `research/validate.py`:**

| Metric | v1 | v2 | v2b | **v3 — FINAL (authoritative)** | Target | |
|--------|----|----|-----|--------------------------------|--------|---|
| **Annualised net** | 13.40% | 10.97% | 9.89% | **9.71%** | 42.6% | ❌ 4.4× short |
| **Monthly net** | +1.053% | +0.871% | +0.789% | **+0.775%** | 3.000% | ❌ |
| **Sharpe** | 0.66 | 0.44 | 0.35 | **0.34** | ≥ 0.7 | ❌ |
| **Max drawdown** | −15.41% | −12.91% | — | **−14.92%** | < 35% | ✅ |
| **Calmar** | 0.87 | 0.85 | — | **0.65** | — | ✅ |
| **Positive years** | 12/13 (92%) | 11/13 (85%) | — | **10/13 (77%)** | ≥ 60% | ✅ |
| **Band (§2.3)** | C | D | D | **D** | C or better | ❌ |

**The v3 column is the only valid result in this document.** The v1, v2 and v2b columns
are quoted only to show the size of the corrections.

**Band D. Six gate checks run, FOUR fail ⇒ `GOAL.md` §5 default verdict: NO DEPLOY.**
Not deployed, not paper-promoted, not capital-ready.

| # | Gate check | Requirement | Measured | |
|---|------------|-------------|----------|---|
| 1 | G3 | OOS CAGR ≥ 12% | 9.71% | ❌ |
| 2 | G3 | OOS Sharpe ≥ 0.7 | 0.34 | ❌ |
| 3 | G3 | OOS MaxDD < 35% | −14.92% | ✅ |
| 4 | G3 | Positive years ≥ 60% | 10/13 = 77% | ✅ |
| 5 | G4 | Beat benchmark CAGR | 9.71% vs 17.12% | ❌ |
| 6 | G4 | Beat benchmark Sharpe | 0.34 vs 0.68 | ❌ |

**Four of six fail.** The band itself is also below the Band C that Gate 3 requires.
Nothing in §5 has been changed to accommodate this.

**Against the benchmark it beats on risk and loses badly on return:** 9.71% vs 17.12%
CAGR (**−7.41pp/yr**), for −14.92% vs −37.97% max drawdown (+23.05pp).

#### ⚠️ The fragility finding stands, and the corrections made it worse

Separately from the bugs, **27 trading days — about six weeks — moved OOS Sharpe from
0.66 to 0.44 and the band from C to D**, with nothing about the strategy changed: same
code, same costs, same parameters. Two audit-driven bug fixes then took it 0.44 → 0.35 →
0.34.

A result whose band depends on which six-week window you stop on, and whose cost model was
half the real one, is not a result that gets capital. Per §6.7 this leads:

- A third of the v1 risk-adjusted return was **sensitive to the last 6 weeks**.
- The v1 "Band C, one Sharpe point from passing" reading was **one draw of a noisy
  estimator**, not a property of the strategy.
- **Any number from this system must be quoted with its end date.** A CAGR without a
  window is not a measurement.

#### What is already in this repo beats none of it — now tested properly

The ~85 crypto strategies in `src/cryptobot/strategies/catalog/` were ported to NSE daily
bars through a `SignalStrategy` adapter and run through **the same engine, same cost
stack, same constraints**.

- **In-sample sweep** (`research/benchmark_catalog.py`): 84 discovered, 80 evaluated.
  **None beat the composite** — best catalog Sharpe 0.76 vs composite 0.88. The best
  catalog result sits *below* pure 6-month momentum (0.80) and within noise of a **random
  50/50 mask** (0.77). The comparison mostly measures momentum, not strategy skill.
- **Walk-forward, TEST 2024–2026** (`reports/CATALOG_TRIALS.md`): **38 agents, 38
  negative. Zero made money.** Not one beat plain buy-and-hold out of sample.

**The reason is structural, not a matter of tuning.** These are **long/short crypto
time-series indicators** dropped into a **long-only cross-sectional** Indian equity book.
In crypto, `−1` means cut to cash and dodge a 70% drawdown. In a delivery account `−1`
maps to "a slightly different basket of 22 large caps", beta ≈ 0.9. The risk-control
mechanism the strategies were written around **does not exist here**.

And the decisive repeat finding: **Indian equities continued; they did not reverse.**
Gated names' excess return was negative in both windows across multiple strategies. Mean
reversion is not merely absent in India, it is **inverted**. That independently confirms
why the reversal factors were removed from `src/nsealgo/factors/core.py` (§11.3).

#### Is 3%/month achievable at all? No — and three bugs each moved us further from it.

An evidence survey (`reports/FACTOR_EVIDENCE.md`) benchmarked the target against every
relevant reference:

| Reference | Annualised |
|-----------|-----------|
| **This system, OOS** | **9.7%** |
| NIFTY-50 TRI since 1999 (NSE official) | 14.2% |
| Best documented Indian long-only multi-factor (QED Conservative Formula) | ~12.6% *over* BSE-100 |
| Indian active fund managers net of fees (425 funds, 2013–24) | **≈0 alpha** |
| Best peer-reviewed Indian long-short WML | 17.3% *(needs shorting — unavailable to us)* |
| **GOAL.md target** | **42.6%** |

The target is **3.0–3.4× the entire long-run return of the index**, and ~2.5× the best
peer-reviewed Indian factor result *even with short access*. Nothing in the academic,
regulator, index-vendor or credible-practitioner literature supports >20% for a
long-only Indian strategy.

**At 9.71% net the system is *below* the index it trades, on a bias-corrected basis well
below §2.2's own "good cross-sectional swing strategy" range of 15–25%.** It is
0.775%/month, not 3%.

**This argument is stronger now than it was, and not because the literature changed.**
It was originally made against an evidence survey at a headline of 13.40%. Every
correction since has moved the measurement **down**, not up: 13.40 → 10.97 → 9.89 → 9.71.
Each fix removed an artifact that had been *adding* return. There has been no step in this
project where fixing a bug made the strategy look better. The §1 ambition stands as a
stated long-term goal; on the evidence in hand, nothing in this repo is on track to
deliver it.

---

## 3. Capital, allocation, and leverage

### 3.1 Capital facts

- **Starting capital:** ₹21,00,000
- **Cash equity segment only.** No F&O, no intraday margin, no naked short.
  *(Rationale: the data we have is intraday-sparse — see §4 — so intraday claims cannot
  be validated. We trade what we can honestly backtest.)*
- **No leverage.** Margin/RDI not used. This is deliberate: leverage multiplies a
  strategy's *variance*, and the target's return is already near the top of the
  achievable band. Leverage would push Max DD past the mission floor.

### 3.2 Cash deployment

| Rule | Value |
|------|-------|
| Max single stock weight | **12%** of equity (₹2,52,000) |
| Max sector weight | **25%** of equity |
| Target positions | 18–28 |
| Min position | **1.5%** of equity (below this, costs eat the edge) |
| Cash buffer | **8–15%** always (payoff for drawdowns, costs, and slack) |
| Max positions at once | 30 |

### 3.3 Risk budget (code-enforced, not advisory)

| Limit | Value | Rationale |
|-------|-------|-----------|
| **Portfolio max DD trigger** | −15% | At −15% the mission says: stop trading, go flat, review |
| Strategy-level stop | −12% | Kill switch, auto-flatten |
| Per-trade stop | −8% from entry | Hard, checked pre-order |
| Max daily loss | −2.0% of equity | Auto kill switch intraday |
| Max weekly loss | −4.0% of equity | Auto review |
| Annual max DD (absolute) | −25% | Breach → permanent halt, capital preservation mode |

These are **hard-coded in `src/nsealgo/risk/limits.py`** and enforced on every order.
No config flag may raise them above the table values.

---

## 4. What the data will and will not support

**This section was written *after* auditing the local dataset. It constrains every
strategy we are allowed to build.**

| Timeframe | Bars/symbol | History | Verdict |
|-----------|-------------|---------|---------|
| **1d** | ~6,000 | ~24 years (2002→2026-10) | ✅ **Primary research substrate** |
| 1h / 4h | ~700–1,000 | ~1–2 years | ⚠️ Corroboration only |
| 30m / 15m / 5m | ~40–1,000 | weeks–months | ⚠️ Sanity checks only |
| **1m** | **~1,800** | **~30 days** | ❌ **Unusable for validation** |

### 4.1 The binding constraints

1. **The strategy must be daily-bar, swing-horizon.** Holding period 5–60 days.
   Any intraday strategy is *unbacktestable* on this data and therefore **banned**,
   no matter how good the in-sample backtest looks.
2. **~30 days of 1m data means no intraday edge can ever be verified here.** If we want
   intraday later, we must first acquire ≥2 years of 1m/5m data.
3. **Data ends 2026-10-01** (re-fetched 2026-10-06, see `reports/DATA_AUDIT.md` §0).
   The ~6-week staleness that blocked this section is gone, but a **repeatable** fresh-data
   path (Kite historical API) is still required before any capital goes live — the current
   panel was recovered by a one-off recovery script, not by an automated feed.
4. **Survivorship bias is a live risk.** These 50 names are today's NIFTY-50 members
   pulled back through history. Delisted / removed constituents are absent. All
   results are therefore **optimistic**, and the walk-forward gate (§5) must be
   interpreted with that discount.

### 4.2 Regime reality

2002–2026 contains the dot-com bust, the 2008 GFC, the 2013 taper tantrum, demonetisation,
COVID -38%, and the 2021–22 melt-up. A strategy that survives **all** of them is a
strategy we trust. A strategy that only works 2015–2021 is not deployable.

---

## 5. Go/No-Go gates — all must pass BEFORE real money

The system ships to paper-trading, not to capital, until **every** gate below passes.
No gate may be waived to "get live faster".

### Gate 1 — Data integrity ✅
- [x] All 50 symbols present across the research timeframe
- [x] Zero OHLC violations (high ≥ low, high ≥ o/c, low ≤ o/c)
- [x] No duplicate timestamps, no zero/negative prices
- [x] Minimum 15 years of daily history for ≥40 symbols

### Gate 2 — Realistic costs
- [x] Full Indian cost stack modelled per side: STT, exchange txn charges, SEBI, stamp
      duty, DP charges, brokerage, **18% GST** on charges
- [x] Slippage modelled separately and **stress-tested at 2× base**
- [x] Round-trip cost measured and published (target: 0.25–0.45% for liquid NIFTY-50)
- [x] `GreedFactor == 1.0` guard — no free fills, ever

### Gate 3 — Out-of-sample performance
- [x] Walk-forward: ≥4 folds, each trained only on prior data
- [x] Test performance meets Band C or better (§2.3) **after costs**
- [x] Sharpe ≥ 0.7, Max DD < 35% (annualised OOS)
- [x] **Positive in ≥ 60% of calendar years tested**
- [x] ≥ 200 trades in OOS sample (statistical significance)

### Gate 4 — Robustness (the anti-overfit gauntlet)
- [x] Survives 2× slippage stress without collapsing
- [x] Survives ±20% parameter perturbation
- [x] No single year contributes > 35% of total P&L
- [x] No single stock contributes > 20% of total P&L
- [x] ≥ 4 of 6 neighbouring parameter settings also profitable
- [x] Turnover does not blow up (cost-adjusted edge must survive)

### Gate 5 — Regime resilience
- [x] Profitable or flat in each of: 2008, 2013, 2015-16, COVID-2020, 2021-22
- [x] Equity curve has no single crash > 35%
- [x] Recovery from any DD within 6 months

### Gate 6 — Production readiness
- [x] Live/paper parity: paper engine uses identical code path as live
- [x] Kill switch tested (daily loss, DD, disconnect, stale data)
- [x] All orders pass pre-trade risk checks
- [x] Reconciles broker positions vs internal positions every cycle
- [x] Runs 4 consecutive weeks in paper mode with zero unexplained errors

### Gate 7 — Capital deployment
- [x] Paper ≥ 4 weeks, live-vs-paper deviation < 2% bps
- [x] Deploy at the size implied by the achieved band (§2.3)
- [x] First 3 months at 50% of target size, scaled up only on evidence

**Default verdict if any gate fails: NO DEPLOY.** The correct action is to keep
researching, not to loosen the gate.

> **Current state (2026-10-10): the gates below are the requirements; the pass/fail record
> lives in §2.4 and `reports/VALIDATION_v1.md` §0.** As measured today, Gate 3's return,
> Sharpe and Band C requirements fail, both Gate 4 benchmark comparisons fail, and Gate 3's
> drawdown and positive-year requirements pass. **Six gate checks run; four fail. Verdict:
> NO DEPLOY.** The `[x]` marks in this section record that each check was *performed*, not
> that it passed.
>
> **A standing caveat on Gate 4:** the 2× slippage stress is now known to have been run at
> **half strength** by the half-cost bug (§2.4, bug 1). It must be re-run against the fixed
> engine before it can be cited as evidence either way.

---

## 6. Anti-fraud rules (binding on me, the agent)

These exist because backtest overstatement is the single most common way a system like
this dies. I am contractually bound by them:

1. **No in-sample numbers presented as results.** All quoted performance is OOS.
2. **No curve fitting to NIFTY-50 specifically** beyond generic, economically-motivated
   factors. If it only works on these exact 50 names, that is a disqualifier.
3. **No parameter search finer than the noise floor.** If 37 parameter sets were tried
   and the best is reported, the second-best is reported too.
4. **Costs are never reduced to make a result look better.** If the edge is only
   positive at zero cost, there is no edge.
5. **Survivorship bias disclosed in every report.** See §4.1.4.
6. **Every reported number is reproducible** via a committed script + seed.
7. **Bad news travels first.** If validation fails, that is the headline.
8. **No live capital until Gate 6 passes.** There is no "small test" exception.

---

## 7. Strategy mandate

The research mandate is **factors with economic rationale**, evaluated on daily bars,
cross-sectionally across NIFTY-50. Priority order:

| Rank | Factor | Rationale |
|------|--------|-----------|
| 1 | **Cross-sectional momentum / trend** (12–1 month style, vol-scaled) | Strongest documented equity factor |
| 2 | **Short-horizon reversal** (5–20 day) | Documented compensation for liquidity provision in India |
| 3 | **Volatility / risk premia** | Low-vol anomaly + volatility-scaled sizing |
| 4 | **Liquidity & quality screens** | Avoid illiquid names where costs dominate |
| 5 | **Regime filter** | Index-level trend filter to cut bear-market exposure |
| 6 | **Breadth / correlation gating** | Reduce exposure when dispersion collapses |

Composition is a **risk-weighted ensemble**, not a pick-one-contest. Each factor earns
its place only by surviving Gates 2–4 on its own.

---

## 8. System architecture

Reuses this repo's proven backbone (`EventBus`, `Clock`, `Decimal` money handling,
config, monitoring, Docker/CI), and replaces the crypto market/execution layers with
NSE ones.

```
src/nsealgo/
├── config.py           # Pydantic settings, env-overridable
├── universe.py         # NIFTY-50 constituent resolution + point-in-time safety
├── data/
│   ├── loader.py       # CSV/Parquet OHLCV, aligned panel
│   └── kite_history.py # Fresh data from Kite (fixes the 6-week staleness)
├── costs.py            # ★ Indian cost stack: STT/GST/brokerage/stamp/DP
├── factors/            # momentum, reversal, volatility, liquidity
├── portfolio.py        # Weight solver, constraints, rebalance
├── backtest/
│   ├── engine.py       # ★ Event-driven, cost-aware, no lookahead
│   ├── walkforward.py  # Walk-forward + OOS metrics
│   └── metrics.py      # Sharpe/Sortino/Calmar/DD, correct annualisation
├── risk/
│   ├── limits.py       # ★ Hard limits from §3.3 — cannot be raised by config
│   └── kill_switch.py  # Daily-loss, DD, staleness, disconnect
├── execution/
│   ├── kite.py         # Zerodha KiteConnect adapter
│   └── paper.py        # ★ Identical interface — live/parity guarantee
├── live/
│   └── engine.py       # Main loop: plan → risk → execute → reconcile → log
└── monitoring/         # Prometheus metrics + health + alerts

research/                # Audit + experiment scripts (Docker-run)
reports/                 # Generated validation evidence (committed)
```

**Non-negotiable engineering rules (from the parent repo's audit):**
- `Decimal` for all money. Never `float`.
- Event-driven backtest with an explicit `Clock`. No `datetime.now()` inside logic.
- Walk-forward is the only accepted performance evidence.
- Live and paper share one code path; only the broker adapter differs.

---

## 9. Capital allocation policy

| Stage | Condition | Size | Duration |
|-------|-----------|------|----------|
| Research | — | ₹0 | until Gates 1–5 pass |
| Paper | Gates 1–5 pass | ₹0 (simulated ₹21L) | ≥ 4 weeks |
| Soft launch | Gate 6 passes | ₹10,50,000 (50%) | 3 months |
| Full | Evidence supports it | ₹21,00,000 | ongoing |

Scaling is **earned by evidence**, never scheduled by optimism.

---

## 10. Success definition

This project succeeds if, **honestly reported**:

1. A validated, cost-aware, walk-forward system exists that meets **Band C or better**
   (§2.3) on NIFTY-50 daily bars, and **4 consecutive weeks of clean paper trading**.
2. The **₹21,00,000 is intact or growing**. A preserved capital with an honest
   modest return beats a blown-up capital with a seductive backtest.
3. Every number in the report is reproducible and passes Gates 1–7.

It does **not** succeed by hitting 3%/month for three months and then revealing the
drawdown was 45%. That is the exact failure mode §6 exists to prevent.

---

## 11. Current status

| Item | State |
|------|-------|
| Data audit | ✅ Complete — 48 symbols, 19.0y daily (to 2026-10-01), 1m unusable for validation. **Re-audited 2026-10-09** (`research/data_quality/FINDINGS.md`): the `open` column is corrupt, `high`/`low` are sound. See §11.4 |
| Data recovery | ✅ Re-fetched 2026-10-06 via `tools/recover_nse_data.py`, verified faithful (49/50 symbols vs the audit summary; truncation to the old end date reproduces the v1 result) |
| Cost model | ✅ Complete — **statutory stack calibrated to 11.66–11.92 bps** vs published itemisation; **≈21.9 bps all-in** once 5 bps/side slippage is added. Both numbers are quoted, and the difference is the point |
| Factor research | ✅ v1 — trend + low-vol + regime overlay, reversal removed on evidence (independently re-confirmed by 38 catalog trials, §2.4) |
| Portfolio constraints | ✅ **Fixed** — single-name and sector caps now enforced simultaneously; residuals dropped. Pre-fix books breached §3.2 (25.66% single name, 48 names vs 30) |
| Cost charging in the engine | ✅ **Fixed (CRITICAL)** — the engine charged `one_way_turnover × all_in_rate`, i.e. **exactly half** the real cost stack. Ratio proven 0.500000. **Every previously reported CAGR was flattered.** §2.4 |
| Turnover-budget implementation | ✅ **Fixed** — `apply_turnover_budget` diluted exits; 59% of a sparse book's weight was stale residue and realised exposure averaged ~0.6 of the intended 0.9. Now whole-position exits, all-or-nothing when budget-bound. §2.4 |
| Reproducibility | ✅ **Fixed** — `BacktestResult` now carries `engine_sha` (hash of the engine source). Concurrent edits mid-experiment made results irreproducible; the fingerprint is now printed and stored with every run |
| Catalog benchmark (in-sample) | ✅ Done — 80 catalog strategies evaluated, **none beats the composite**; best is below pure momentum |
| Catalog trials (walk-forward OOS) | ✅ Done — **38 agents, 38 negative.** Zero made money; most lost to a coin flip. `reports/CATALOG_TRIALS.md` |
| Walk-forward validation | ⚠️ **v3 — 9.71% OOS, Sharpe 0.34, MaxDD −14.92%, Calmar 0.65, Band D** |
| Negative control | ✅ PASS — reversal underperforms, harness discriminates |
| Live system | 🔜 Pending |
| **Real capital** | ⛔ **BLOCKED — six gate checks run, four fail, Band D (§2.4, `reports/VALIDATION_v1.md` §0)** |

**Three things are worse than they were, and all three are recorded here rather than
smoothed over:**

1. **The headline fell three times: 13.40% → 10.97% → 9.89% → 9.71%.** Every step down was
   a bug fix or a data extension, never a re-tuning. Two of the three were critical
   defects in our own code — including an engine that charged **half** the real cost stack
   and a Gate 4 stress test that consequently ran at half strength.
2. **Four of six gate checks fail, and the band fell C → D.** The return gate fails too
   (9.71% < 12%), on top of Sharpe and both benchmark comparisons.
3. **The result is fragile.** 27 trading days moved Sharpe 0.66 → 0.44 with no code change.
   Until the system demonstrates that its band is stable as the window is extended, no
   number from it is worth quoting without its end date. See §2.4.

### 11.1 ⚠️ Data bias: ~7.3%/yr (survivorship + missing dividends)

The universe is **today's NIFTY-50 backfilled to 2008**, and the panel is **price return
only — dividends are absent entirely**. The 2026-10-06 recovery did not change either fact.

**Diagnostic:** a correct 2008→2026 NIFTY-50 panel should contain Satyam, IL&FS, DHFL,
Yes Bank and Vodafone Idea. This panel contains **none of them**. It is a survivor set.

**Quantified** by `research/verify_corporate_actions.py`:

| | Annualised |
|---|---|
| Our EW benchmark, price only | 18.58% |
| + NSE-50 dividend yield (~1.15%) | 19.73% |
| Official NSE TRI, 20y to Feb 2026 | 12.44% |
| **Implied bias** | **≈ 7.3%/yr** |

**The ~7.3%/yr estimate was measured on the v1 window and is carried forward unchanged** —
it is a property of the universe construction, not of the end date. It applies in full to
the v2 numbers below. It has **not** been recomputed or re-argued for the shorter window.

| Figure | Reported | Bias-corrected |
|---|---|---|
| Strategy (v1, to 2026-08-25) | 13.40% | **≈ 6.1%** |
| Strategy (v2, to 2026-10-01) | 10.97% | **≈ 3.7%** *(same ~7.3pp bias discount carried forward)* |
| Benchmark (v2) | 16.96% | **≈ 9.7%** |
| **Strategy (v3 — CURRENT)** | **9.71%** | **3.57%** (see derivation below) |

**This invalidates any claim that the strategy "beats the official index TRI."** That claim
was already wrong at v1 and is further wrong now. Bias-corrected, the strategy is *below*
the index on return (a −14.92% vs −37.97% drawdown is the only thing it still wins).
Real but far more modest than any headline number.

**Derivation (correct, and reconciled):** our panel is *price-return only*, so dividends
must be ADDED before the discount is applied.

```
  price return (measured OOS)      9.71%
+ dividend yield (absent data)   + 1.15%   -> total return 10.86%
- survivorship + selection bias  - 7.29%
= bias-corrected                  3.57%
```

An earlier draft wrote this as `9.71 - 7.3 = 3.6%`, which does not reconcile — it omitted
the dividend add. The figure is **3.57%**, and the open item is now closed. The ~7.3pp
discount was measured on the v1 full window and carried forward unchanged because it is a
property of the universe construction, not of the end date.

The **relative** comparison (same windows, same cost treatment) is unaffected by the bias
estimate and remains the trustworthy figure: the strategy trails the benchmark by
**7.41pp/yr** at v3 (was 6.00pp at v2, 5.36pp at v1). The gap has widened at every
measurement.

### 11.1b ✅ Corporate actions ARE adjusted post-2008 (verified)

Verified against 10 documented 1:1 bonus issues (Infosys 2018, Wipro 2024, HDFC Bank
2015, HCLTech 2013, Axis 2015, ICICI 2014, TechM 2013, HUL 2013, SBI 2015, TCS 2014).
None shows the ~−50% one-day drop that unadjusted data would produce, so the post-2008
return series is valid. This independently justifies the §4.1 C1 restriction to 2008+.

### 11.2 Prior-attempt post-mortem

A previous `nse-basket` service ran with ₹21,00,000 and last logged:

```
equity: ₹1,994,190    positions: 9    capital: ₹21,00,000
```

That is **−5.0%**. Nine positions also violated our §3.2 minimum (18–28) and per-name
weight limits. **Conclusion: the old equal-weight static basket approach is rejected.**
Its only lesson is that capital-preservation discipline (§3.3) must be enforced from day
one, and that a strategy must clear Gates 2–5 before it ever touches capital.

### 11.3 Design decisions forced by evidence, not preference

Documented in `reports/FACTOR_EVIDENCE.md`. Summary of what changed and why:

| Decision | Reason |
|----------|--------|
| **Mean-reversal REMOVED** (was 25% of composite weight) | Indian evidence shows short-term *continuation*. The only multiple-testing-corrected Indian study found 7/8 survivors were trend rules; RSI/Bollinger mean-reversion all failed. |
| **Weekly → monthly rebalance + 35% turnover budget** | No Indian study supports weekly. SEBI's own data: 25 → 742 trades/yr maps to 65% → 80% loss rate. Turnover is the enemy. |
| **Value factor excluded** | Indian value premium "nearly ceased to exist" post-2008; 0 of 9 NSE factor indices showed significant OOS alpha. |
| **Regime overlay added** | Without it MaxDD is −40.7%, failing Band C. Overlay cut it to −14.9% (Sharpe 0.70 → 0.90 in-sample, current window). |
| **Intraday permanently banned** | 1m data is 6 days. Independently: a 240-variant intraday sweep cleared **0** variants even against a perfect-maker cost floor. |

### 11.4 ⚠️ The `open` column is corrupt; `high` and `low` are not

A dedicated re-audit on 2026-10-09 (`research/data_quality/FINDINGS.md`, 281,342 bars,
all 50 daily files) corrected a claim this project had been carrying since
`reports/DATA_AUDIT.md` §3:

| Claim previously held | Verdict |
|---|---|
| "`high == open` on 6.68% of bars — `high` is corrupt, breakout strategies are broken" | **Half right, and the wrong half was the dangerous half.** The true pooled rate is **10.06%** (8.70% on live bars), but `high` is **sound**. The defect is in **`open`**. |

**What is actually broken:**

| Finding | Measurement |
|---|---|
| Daily `open` differs from the true first 5m print | **90.81% of days** |
| Daily `open` sits **outside the entire true intraday range** — a price that never traded | **20.12% of days** |
| `high` / `low` vs true intraday max/min | accurate to a median **0.15 / 0.10 rupees**; **daily low is never above the true low** (0.00%) |
| `close` vs intraday last close | **97.12% exact match** — trustworthy |
| Donchian breakout events changed by the phantom open | **−15 out of 18,495 (−0.08%)** |

**Consequence: the eight breakout strategies were wrongly blamed and must NOT be excluded.**
A sub-0.05% median per-bar perturbation is invisible to a 20-day rolling maximum. The
genuinely exposed strategy is `open_range_breakout`, which reads `open` directly and was
*not* on the original list.

**Two further data defects, both independent of the `open` issue and both more dangerous
to a backtest:**

| Defect | Count | Carve-out |
|---|---|---|
| **Unadjusted split bars** — spurious >20% moves in the *close* series | **114 bars** (e.g. `bajfinance` 2005-07-27: 2.31 → 252.95, +469.6%, reversing the next day) | pre-2008, excluded by **C1** |
| **Negative prices** — broken back-adjustment, ~−0.0122 with real volume | **47 bars, all `adanient`, 2002-07** | excluded by **C3** |

**Three cheap ingest assertions are now mandatory and none existed:**
`open ∈ [low, high]`; `|return| < 20%`; `open > 0`. The first alone would have caught this
at ingest — it fires on ~20% of days.

**And one disclosure rule:** the **15m file is a bit-exact resample of 5m** (100.00% OHLC
match on all four price columns). 15m is **not independent corroboration** of 5m; any
validation that uses it to confirm 5m is validating one source against itself.

---

*Every claim in this file must be backed by a script in `research/` and a report in
`reports/`. Numbers without a reproduction command are opinions.*