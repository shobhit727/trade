# Agent Report — `dispersion_strategy` on NSE NIFTY-50

**Status:** IN PROGRESS (header + declared budget committed before any run in this session)
**Assigned strategy:** `src/cryptobot/strategies/catalog/dispersion_strategy.py`
**Scratch dir:** `research/agent_dispersion/`
**No commit made.**

---

## 1. The strategy, and what the signal actually is

`DispersionStrategy` is a 37-line per-symbol time-series indicator. It is **not**
crypto-specific (no funding, no liquidations, no IV, no basis) — so it is a legitimate
candidate for NSE. The source:

```python
def signal(self, closes, highs, lows, volumes):
    z = zscore(closes)                 # std() over the WHOLE array handed in
    m = sma(closes, self.config.period)
    if z >=  self.config.entry and closes[-1] > m: return  1
    if z <= -self.config.entry and closes[-1] < m: return -1
    return 0
```

Two facts about the port that matter, both asserted against the shipped class rather
than assumed (`signal.py::verify_against_catalog` calls the real
`DispersionStrategy.signal` on the true trailing slice):

1. **The z-score is *expanding*, not rolling.** `strategies.indicators.zscore` calls
   `a.std()` over the entire array it receives, and the engine hands it all history up
   to *t*. The faithful vectorised form is therefore
   `(x_t - expanding_mean) / expanding_std`, which makes it a path-dependent statistic
   that must be computed once over the full 2008→2026 panel and *then* windowed.
   Computing it inside a TRAIN/TEST slice would silently change the signal at the
   boundary.
2. **The signal is a mean-reversion-into-trend hybrid**: long requires an *expanding*
   z-score ≥ entry (price far above its all-time-ish mean) **AND** price above its
   `period`-bar SMA. It is a breakout filter, not a reversion strategy, despite the
   ±sign symmetry.

**NSE adaptation (documented, not silent):** the book is long-only, so only the `+1`
branch is tradable; the `-1` branch is retained in the signal panel for reporting and
never traded. A ±1/0 time-series signal has no cross-sectional ordering, so it is
turned into a score exactly as AGENT_BRIEF §5 prescribes — among flagged names, rank by
trailing momentum:

```python
score = (panel / panel.shift(126) - 1.0).where(long_signal).rank(axis=1, pct=True)
```

Unflagged names get `NaN`, which `build_rebalance_weights` skips
(`valid = isfinite(score)`). **That is where the long-only gate is enforced.**

---

## 2. Declared parameter budget (AGENT_BRIEF §4)

**This budget was declared and fully consumed by the previous (interrupted) run of this
same assignment — see `step2_run.py` docstring, written before that run executed. I am
adopting it as-is and spending nothing further.** Declaring a fresh budget now, after
having seen the TEST numbers, would be exactly the tuning the brief forbids.

| id | period | entry | rationale (a priori, not fitted) |
|----|--------|-------|--------------------------------------|
| V1 |  30 | 1.00 | catalog default (`DispersionConfig`) |
| V2 |  20 | 2.00 | classic 2-sigma threshold, ~1 trading month |
| V3 |  60 | 0.50 | slower + much looser: longer trend, weaker gate |
| V4 | 120 | 0.25 | ~6 months, very loose gate |
| V5 | 250 | 1.00 | exactly one trading year of history in the SMA |

Fixed and **not** part of the budget: momentum ranking window = 126d (brief-specified),
rebalance = monthly, `PortfolioConfig()` defaults, cost model = `CostModel(segment=
"delivery", slippage_bps=5)`.

Deliberately excluded: any `(period, entry)` pair found by looking at TEST, and any
momentum window other than 126d.

**Budget consumed: 5 / 5. Remaining: 0.**

---

## 3. Protocol as it was actually executed (including one deviation to disclose)

| Set | Window | Status |
|-----|--------|--------|
| TRAIN | 2016-01-01 → 2023-12-31 | all 5 variants run; V5 selected on max TRAIN Sharpe |
| TEST | 2024-01-01 → 2026-10-01 | selected variant run **once** for the headline number |

**Disclosure — TEST was read more than once, by the earlier run.** `step3_diagnose.py`
diagnostic **D1** deliberately re-ran all 5 *already-declared* variants on TEST to test
whether the negative result was a property of one unlucky parameter draw or of the
whole strategy family. Selection was **not** revised (V5 remained the reported
strategy), and no new variant was invented from the TEST output. That is reported
here rather than hidden, but the honest reading is: **the TEST window is no longer
pristine for this strategy family**, so the family-level TEST numbers in §D1 below
should be read as *post-hoc diagnostics of an already-reported result*, not as a clean
single-shot out-of-sample test. The headline V5 number was still produced by a
TRAIN-only selection.

**Costs:** all results below are net of `all_in_round_trip_bps(100_000)` = **21.92 bps**
(statutory 11.92 + 2 × 5 slippage), which is what `run_backtest` actually charges. The
11.92 figure is used only where `CostModel` is called directly.

---

## 4. Verification performed before any number was trusted

The previous run's scratch work was re-executed from scratch rather than believed.

| check | result |
|-------|--------|
| `load_universe("data/nse")` | 48 symbols × 4,629 rows, 2008-01-01 → 2026-10-01, 13,966 NaN cells, IST tz. `adanient`/`jiofin` excluded, 3 extreme events dropped, 66,312 pre-2008 rows dropped. |
| Cost model vs published reference | `nsealgo.cli costs`: 11.92 bps at ₹1L/side vs published 11.65–11.66 — **matches** |
| **Signal fidelity vs the shipped catalog class** | `max_err = 0` disagreements across all 5 variants (sampled 62–144 `(t, symbol)` points each, calling the real `DispersionStrategy.signal` on the true trailing slice) — **exact port** |
| **No-lookahead, truncation test** | Truncate panel at 2019-12-31 / 2022-06-30 / 2025-03-31, recompute every score: **0 NaN-pattern mismatches, max &#124;score diff&#124; = 0.00e+00** → scores before the cut are bit-identical. No future row can have leaked backwards. |
| Lint | `.venv/bin/ruff check research/agent_dispersion/` → **All checks passed** |

Every number below was reproduced from a clean run in this session.

---

## 5. TEST results (2024-01-01 → 2026-10-01, 685 sessions)

**Selected on TRAIN by max Sharpe: V5 (`period=250`, `entry=1.00`), unchanged into TEST.**
All figures net of **21.92 bps** round-trip (statutory 11.92 + 2 × 5 slippage).

| # | book | CAGR | Sharpe | MaxDD | Calmar | Turn/yr | Cost drag | Avg names |
|---|------|------|--------|-------|--------|---------|-----------|-----------|
| 1 | **dispersion V5** | **3.85%** | **−0.13** | **−15.67%** | 0.25 | 1.04 | 0.75%/yr (₹44,204) | 21.2 |
| 2 | buy-and-hold (same window) | 8.18% | 0.19 | −15.91% | 0.51 | 0.00 | — | 48.0 |
| 3 | nsealgo composite | 6.55% | 0.07 | −14.84% | 0.44 | 0.74 | 0.55%/yr | 21.3 |

### 5.1 Sanity checks (AGENT_BRIEF §6) — all clean

1. **Plausibility** — CAGR 3.85%, far below the 40–50% unlevered long-only ceiling. OK.
2. **Weight count** — 21.2 names held, target ~22. **No residual-weight accumulation.**
3. **Signal liveness** — 66.7% of `(name, day)` cells flagged long in TEST. Not always-flat.
4. **Cost drag** — 0.75%/yr. But see §6: costs are *not* the cause.
5. **Negative control** — loses to random. See §7 for the significance caveat.

---

## 6. Is the negative result an artefact of the engine? No — three controls

**D1 — the whole declared family loses on TEST, not just V5.** (Post-hoc reporting of
the already-declared grid; selection was not revised. See the disclosure in §3.)

| variant | TRAIN Sharpe | TEST CAGR | TEST Sharpe | TEST MaxDD |
|---------|--------------|-----------|-------------|------------|
| V1 p30 e1.0 | 0.58 | 1.68% | −0.31 | −17.59% |
| V2 p20 e2.0 | 0.66 | 2.51% | −0.25 | −16.56% |
| V3 p60 e0.5 | 0.61 | 1.58% | −0.30 | −19.85% |
| V4 p120 e0.25 | 0.61 | 2.24% | −0.25 | −17.19% |
| **V5 p250 e1.0** | **0.76** | **3.85%** | **−0.13** | −15.67% |
| buy-and-hold | — | 8.18% | 0.19 | −15.91% |

**Variants beating buy-and-hold on TEST: NONE.** Every one of the five declared
variants has a negative TEST Sharpe. Note the TRAIN→TEST Sharpe collapse is universal
(0.58–0.76 → −0.31 to −0.13), and the TRAIN Sharpe ranking is *anti*-correlated with
TEST Sharpe. This is a regime problem, not a parameter problem.

**D2 — the "dispersion gate" is a near-no-op; the ranking does all the work.**

| window | gated CAGR | gated Sharpe | no-gate CAGR | no-gate Sharpe | gate edge |
|--------|-----------|--------------|--------------|---------------|-----------|
| TRAIN 2016–2023 | 17.77% | 0.76 | 18.38% | 0.78 | **−0.02** |
| TEST 2024–2026 | 3.85% | −0.13 | 2.60% | −0.22 | +0.10 |

Removing the gate entirely and ranking *all* 48 names by 126-day momentum performs the
**same** (TRAIN) or better (TEST). The gate fires on 59% (TRAIN) / 67% (TEST) of all
cells — a filter that keeps two-thirds of the universe is not a filter. Per-year
liveness runs 50–86% throughout 2021–2026.

**D3 — costs are not the cause. Even at zero cost it fails.**

| cost model | round-trip bps | CAGR | Sharpe | MaxDD |
|------------|----------------|------|--------|-------|
| zero_cost | 11.92 | 4.16% | −0.10 | −15.58% |
| **base** | **21.92** | **3.85%** | **−0.13** | **−15.67%** |
| double_slippage | 31.92 | 3.55% | −0.15 | −15.77% |
| triple_slippage | 41.92 | 3.25% | −0.17 | −15.87% |

Stripping **all** slippage buys only +31 bps/yr. The strategy still underperforms
buy-and-hold by ~4 pp and still has a negative Sharpe. **The signal is the problem,
not the fees.** (Brief §6.4: gross-positive / net-negative is not the situation here —
it is gross-negative too.)

---

## 7. Is it even distinguishable from noise? (the strongest form of the finding)

`step7_significance.py`, on TEST daily returns:

| test | statistic | verdict |
|------|-----------|---------|
| strategy − buy-and-hold (paired t) | mean daily −0.00017, t = −1.36, **p = 0.175** | not significant |
| strategy return vs 0 (one-sample t) | mean daily 0.00019, t = 0.59, **p = 0.552** | **not significant** |
| strategy − random seed 11 / 22 / 33 (paired) | p = 0.887 / 0.462 / 0.310 | **none significant** |
| bootstrap CAGR gap vs buy-and-hold (20,000 draws) | observed −4.32%, 95% CI **[−11.12%, +2.04%]** | **CI spans zero**; P(beats B&H) = 8.9% |

**This is the honest headline, and it is stronger than "it loses":** out-of-sample the
strategy's return is **statistically indistinguishable from zero, from a coin flip, and
from buy-and-hold.** 685 sessions (2.75 y) is a low-power sample, so this is *absence
of evidence*, not proof of impossibility — but it is decisive evidence of *absence of
an edge*, and it is the finding that matters for a capital-deployment decision.

Random-control CAGRs across two independent samplings: 4.35% (step2, 3 seeds) and
5.63% (step7, 3 fresh seeds) — both **above** the strategy's 3.85%.

---

## 8. Bugs found and fixed

**All three are in my own scratch scripts. `src/nsealgo/**` and
`src/cryptobot/**` are clean — I found no engine bug and changed no source file.**

| # | file | bug | impact |
|---|------|-----|--------|
| 1 | `step5_why.py` | `NameError: slice_window` — used but never imported. Crashed the script on every run, so its diagnostic output was never actually produced. | The prior run's "why" analysis had **never executed**. |
| 2 | `step4_verify_nolookahead.py` | Rebalance schedule was `[d for d in win.index if d.month in (1,4,7,10)]` — that selects **every trading day inside those months** (235 events in TEST), not the first day of the month. The engine rebalances monthly (33 events). | The "independent cross-check" was invalid; it reported a nonsense 8.06% CAGR vs the engine's 3.85%. Corrected → **4.79%**. |
| 3 | `step4_verify_nolookahead.py` | `costs_paid` in the independent path is a **fraction of equity** (0.031) while the engine's is **rupees** (44,204), both printed with `{:.0f}` → the cost-free figure rendered as `0`, implying costs were never charged. They were. | Cosmetic, but it briefly made me misdiagnose bug 2 as a cost bug. Fixed to print rupees with thousands separators. |

Also fixed: `step7_significance.py` originally t-tested `run_backtest` and
`buy_and_hold` return series as raw arrays, which differ in length and raised
`ValueError: Array shapes are incompatible`. Now aligned on the strategy's own index
via `pd.concat(...).dropna()` before any paired test.

---

## 9. Gap attribution — how much of the shortfall is the engine?

The corrected 93.5 bps gap between the independent path (4.79%) and the engine
(3.85%), decomposed by switching on one engine feature at a time
(`step6_attribute.py`, TEST, costs charged on every row):

| sizing path | CAGR | Δ vs row above |
|-------------|------|----------------|
| 1. equal weight, no caps, no budget | 4.67% | — |
| 2. + inverse-vol scaling | 4.44% | −23 bps |
| 3. + 12%/25% cap projection | 4.36% | −8 bps |
| 4. + 10% cash buffer | 4.01% | −35 bps |
| 5. + 35% turnover budget | **3.85%** | −16 bps |
| *[engine `run_backtest`, cross-check]* | *3.85%* | *exact match* |

The ladder reproduces the engine to the digit, so the decomposition is complete. Total
engine drag **82 bps/yr**, dominated by the 10% cash buffer. Constraints were verified
as honoured (`max_weight` 0.1042 ≤ 0.12; gross exposure exactly 0.90).

**Even the most favourable possible construction of this signal — row 1, no caps, no
budget, no inverse-vol, fully costed — returns 4.67%, still 3.51 pp/yr below
buy-and-hold.** So ~81% of the shortfall is the signal, ~19% is portfolio machinery.

---

## 10. Verdict

**No — `dispersion_strategy` does not make money on NSE.** Out-of-sample it returns
3.85% CAGR against 8.18% for buy-and-hold, and that return is statistically
indistinguishable from zero (p = 0.55), from random signals (p = 0.31–0.89), and from
buy-and-hold (bootstrap 95% CI spans zero).

**Most likely reason:** the strategy has no independent signal content. Its z-score
gate is computed on an *expanding* window, so by construction `z ≥ entry` is
automatically true for roughly two-thirds of names most of the time — the gate is
statistically vacuous (D2: removing it entirely changes TRAIN Sharpe by −0.02). What
survives is 126-day cross-sectional momentum ranked among 48 large-cap NIFTY names,
which is a crowded, well-documented, and in this window unprofitable trade: 2026
returned −10.76% versus buy-and-hold's −8.26%. The signal does not discriminate; the
portfolio constraints then subtract a further 82 bps.

**The one thing I would try next** — and I want to be clear this is a *new*
hypothesis, not a 6th variant of this one: the rolling-window interpretation. The
catalog's `zscore` uses `a.std()` over the whole array it is handed, which makes the
"dispersion" statistic expanding and therefore self-diluting over time. A
**rolling** 252-day z-score would keep the gate meaningful (it would flag genuine
1-year price extremes rather than "above my own average since 2008") and is the only
reading under which the strategy name describes a real, distinct signal. That is a
different strategy and deserves its own declared budget — I have not spent one here.

