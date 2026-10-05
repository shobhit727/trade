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

### 2.4 MEASURED RESULT — v2 (2026-10-06)

> Evidence: `reports/VALIDATION_v1.md` §0 (addendum) — the v1 measurement is retained
> there unchanged as the historical record. Reproduce: `research/validate.py`.

#### ⚠️ THE HEADLINE IS A FRAGILITY FINDING, NOT A NUMBER

**Twenty-seven extra trading days — about six weeks of data — moved OOS Sharpe from
0.66 to 0.44 and the band from C to D.** Nothing about the strategy changed between the
two measurements: same code, same costs, same parameters, same walk-forward design. Only
the end date moved.

That is a statement about the **strategy**, not about the data. A result whose band
depends on which six-week window you happen to stop on is not a result that gets capital.
Per §6.7 this is the bad news and therefore leads. It is recorded as the single most
important thing this project has learned about itself:

- A third of the measured risk-adjusted return was **sensitive to the last 6 weeks**.
- The v1 "Band C, one Sharpe point away from passing" reading was **not a stable
  property** — it was one draw of a noisy estimator.
- Any future number from this system must be quoted with the end date attached. A CAGR
  without a window is not a measurement.

**Walk-forward out-of-sample, 2008-01-01 → 2026-10-01 (19.0y), 48 symbols,
4,629 trading days, full Indian cost stack:**

| Metric | v1 (to 2026-08-25) | +27 days, pre-fix engine | **CURRENT (authoritative)** | Target | |
|--------|-------------------|------------------------|----------------------------|--------|---|
| Annualised net | 13.40% | 11.05% | **10.97%** | 42.6% | ❌ 3.9× short |
| **Monthly net** | +1.054% | +0.877% | **+0.871%** | 3.000% | ❌ |
| Sharpe | 0.66 | 0.45 | **0.44** | ≥ 0.7 | ❌ |
| Max drawdown | −15.41% | −12.90% | **−12.91%** | < 35% | ✅ |
| Calmar | 0.87 | 0.86 | **0.85** | — | ✅ |
| Positive years | 12/13 (92%) | 11/13 (85%) | **11/13 (85%)** | ≥ 60% | ✅ |
| All-in cost drag | 3.03%/yr | — | **3.11%/yr** | — | measured |
| **Band (§2.3)** | **C** | D | **D** | C or better | ❌ |

The third column isolates the data extension; the fourth is what the code on disk
produces today. **The fourth column is the only one that is a valid result.** The third
column is quoted because the gap between columns 2 and 3 is the fragility finding, and
because column 3 was briefly published as the headline before the engine bugs below were
found.

**Band D. FOUR gates fail ⇒ `GOAL.md` §5 default verdict: NO DEPLOY.** Not deployed, not
paper-promoted, not capital-ready.

| Gate | Requirement | Result | |
|------|-------------|--------|---|
| G3 | OOS CAGR ≥ 12% | 10.97% | ❌ |
| G3 | OOS Sharpe ≥ 0.7 | 0.44 | ❌ |
| G3 | OOS MaxDD < 35% | −12.91% | ✅ |
| G3 | Positive years ≥ 60% | 11/13 = 85% | ✅ |
| G4 | Beat benchmark CAGR | 10.97% vs 16.96% | ❌ |
| G4 | Beat benchmark Sharpe | 0.44 vs 0.67 | ❌ |

**Four failed.** The band itself is also now below the Band C that Gate 3 requires.

**Against the benchmark it beats on risk and loses on return:**
10.97% vs 16.96% CAGR (−6.00pp/yr), but −12.91% vs −37.97% max drawdown (+25.06pp) and
Calmar 0.85 vs 0.45.

#### ⚠️ The v1 numbers were partly earned by breaching our own risk limits

Two bugs in `src/nsealgo/backtest/engine.py` (fixed on disk, uncommitted) had been
letting the portfolio exceed §3.2:

1. **The 12% single-name cap was breached — worst observed weight 25.66%.** The sector cap
   redistributed weight without re-capping the names it spilled onto, so the single-name
   cap was applied first and then invalidated.
2. **Dead residual weights accumulated** — 48 names held against `max_positions` 30,
   because positions that fell below the material threshold were never removed.

After the fix: worst single weight **10.80%**, worst sector **22.50%**, max names **30**.
The fix cost 11.05% → 10.97% CAGR and 0.45 → 0.44 Sharpe.

**Stated plainly: part of the v1 result was not available under the portfolio rules this
constitution mandates.** A backtest that quietly holds 25% in one name is not the strategy
§3.2 describes, whatever it prints. Any return achieved by breaching a limit is not a
result — it is an artifact, and it is reported here as one.

#### What is already in this repo beats none of it

The ~85 existing crypto strategies in `src/cryptobot/strategies/catalog/` were ported to
NSE daily bars through a `SignalStrategy` adapter and run through **the same engine, the
same cost stack and the same constraints**. **84 discovered, 80 evaluated** (2 never
signalled, 2 crypto-only, 0 errors). **None beat the nsealgo composite** — best catalog
Sharpe 0.76 vs composite 0.88; best Calmar 0.91 vs 0.95.

**The comparison is mostly measuring momentum, not strategy skill.** The adapter gives each
catalog strategy the benefit of momentum ranking, and the top of the sweep is not a set of
distinct strategies at all: the leading rows produce numerically identical books. For
scale, pure 6-month momentum through the same harness returns Sharpe **0.80**, and a
**random 50/50 mask** returns **0.77**. The best catalog strategy sits *below* pure
momentum.

The honest finding: **no existing catalog strategy adds anything over momentum, and none
beats the composite.** The composite's own advantage over this field is 0.12 Sharpe — of
the same order as the 0.22 the 27-day data extension destroyed.

#### Is 3%/month achievable at all? No — and this is now evidence, not opinion.

An evidence survey (`reports/FACTOR_EVIDENCE.md`) benchmarked the target against every
relevant reference:

| Reference | Annualised |
|-----------|-----------|
| **This system, OOS** | **11.0%** |
| NIFTY-50 TRI since 1999 (NSE official) | 14.2% |
| Best documented Indian long-only multi-factor (QED Conservative Formula) | ~12.6% *over* BSE-100 |
| Indian active fund managers net of fees (425 funds, 2013–24) | **≈0 alpha** |
| Best peer-reviewed Indian long-short WML | 17.3% *(needs shorting — unavailable to us)* |
| **GOAL.md target** | **42.6%** |

The target is **3.0–3.4× the entire long-run return of the index**, and ~2.5× the best
peer-reviewed Indian factor result *even with short access*. Nothing in the academic,
regulator, index-vendor or credible-practitioner literature supports >20% for a
long-only Indian strategy.

**At 11.0% net the system is now *below* the index it trades, on a bias-corrected basis
below §2.2's own "good cross-sectional swing strategy" range of 15–25%.** It is
0.87%/month, not 3%. The §1 ambition stands as a stated long-term goal; on the evidence
in hand, nothing in this repo is on track to deliver it.

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

> **Current state (2026-10-06): the gates below are the requirements; the pass/fail record
> lives in §2.4 and `reports/VALIDATION_v1.md` §0.** As measured today, Gate 3's return,
> Sharpe and Band C requirements fail, both Gate 4 benchmark comparisons fail, and Gate 3's
> drawdown and positive-year requirements pass. **Four gate checks fail. Verdict: NO DEPLOY.**
> The `[x]` marks in this section record that each check was *performed*, not that it passed.

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
| Data audit | ✅ Complete — 48 symbols, 19.0y daily (to 2026-10-01), 1m unusable for validation |
| Data recovery | ✅ Re-fetched 2026-10-06 via `tools/recover_nse_data.py`, verified faithful (49/50 symbols vs the audit summary; truncation to the old end date reproduces the v1 result) |
| Cost model | ✅ Complete — calibrated to 11.66 bps vs published itemisation |
| Factor research | ✅ v1 — trend + low-vol + regime overlay, reversal removed on evidence |
| Portfolio constraints | ✅ **Fixed** — single-name and sector caps now enforced simultaneously; residuals dropped. Pre-fix books breached §3.2 (25.66% single name, 48 names vs 30) |
| Catalog benchmark | ✅ Done — 80 catalog strategies evaluated, **none beats the composite**; best is below pure momentum |
| Walk-forward validation | ⚠️ v2 — **10.97% OOS, Sharpe 0.44, MaxDD −12.91%, Band D** |
| Negative control | ✅ PASS — reversal underperforms, harness discriminates |
| Live system | 🔜 Pending |
| **Real capital** | ⛔ **BLOCKED — FOUR gates fail, Band D (§2.4, `reports/VALIDATION_v1.md` §0)** |

**Two things are worse than they were, and both are recorded here rather than smoothed
over:**

1. **Four gates fail, not three.** The return gate now fails too (10.97% < 12%), on top of
   Sharpe and both benchmark comparisons. The band fell C → D.
2. **The result is fragile.** 27 trading days moved Sharpe 0.66 → 0.44. Until the system
   demonstrates that its band is stable as the window is extended, no number from it is
   worth quoting without its end date. See §2.4.

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

**This invalidates any claim that the strategy "beats the official index TRI."** That claim
was already wrong at v1 and is further wrong at v2. Bias-corrected, the strategy is
*below* the index on return (−12.91% vs −38.0% drawdown is the only thing it still wins).
Real but far more modest than any headline number.

The **relative** comparison (same windows, same cost treatment) is unaffected and remains
the trustworthy figure: the strategy trails the benchmark by **6.00pp/yr** in v2 (was
5.36pp/yr in v1).

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

---

*Every claim in this file must be backed by a script in `research/` and a report in
`reports/`. Numbers without a reproduction command are opinions.*