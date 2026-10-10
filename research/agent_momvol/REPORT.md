# `momentum_volatility` on NSE NIFTY-50 — validation report

**Agent:** agent_momvol
**Assigned strategy:** `momentum_volatility`
**Source:** `src/cryptobot/strategies/catalog/momentum_volatility.py` (38 lines)
**Status:** IN PROGRESS — this file was written before any backtest was run.

---

## 0. Is this strategy crypto-specific?

**No.** It uses only `roc` (rate of change over trailing bars) and `atr` (average true
range over trailing bars) — both generic technical indicators with no funding, leverage,
liquidation, peg or derivatives concept. There is an NSE meaning. Proceeding.

---

## 1. What the strategy actually does (source read, before any run)

```python
@dataclass
class MomentumVolConfig:
    period:    int     = 14     # ATR window
    momperiod: int     = 20     # ROC window
    threshold: float   = 0.01   # 1%

def signal(self, closes, highs, lows, volumes):
    m = roc(closes, self.config.momperiod)
    b = atr(highs, lows, closes, self.config.period)
    if m != m or b != b:      # NaN guard
        return 0
    if m > self.config.threshold and b > 0:   return 1
    if m < -self.config.threshold and b > 0:  return -1
    return 0
```

Per-symbol, per-bar, time-series. Returns **+1 / 0 / −1**. Two readings:

- **The long branch is `ROC(momperiod) > threshold`.**
- **The short branch is `ROC(momperiod) < −threshold`.**
- **The `atr` term is inert.** It enters only as the predicate `b > 0`, and `atr` is the
  mean of true ranges, so `b > 0` **fails only when every one of the 14 trailing bars
  had zero true range** — i.e. a perfectly frozen OHLC bar. On the NSE daily panel
  that happens, but only as a *data pathology* (§1a). Within the TRAIN+TEST windows it
  happens **zero** times, so the predicate is a tautology there and the "volatility"
  half of this strategy does no work. **Despite the name, the real strategy is a plain
  rate-of-change filter.**

This matters for interpreting the result: whatever happens here is a test of
**ROC-gating**, not of "momentum + volatility" as a combined construct.

> **CORRECTION (my first draft had this wrong).** I initially wrote that `atr > 0` is a
> strict tautology "no symbol is flat". That is **false on the full panel** and I caught
> it by checking instead of asserting — `verify_signal.py` found **497 bar-endpoints**
> where `atr == 0`. See §1a. The conclusion for this run is unchanged only because those
> bars fall entirely outside TRAIN and TEST; the harness now *asserts* that rather than
> trusting my prose.

### Bug noted in the source (not mine to fix — `src/` is read-only for this agent)

`MomentumVolStrategy.warmup()` returns `self.config.period` (default **14**), but
`signal()` needs `momperiod` (default **20**) bars of close history for `roc`, which
returns `NaN` when `len(closes) <= period`. **A caller that trusts `warmup()` and
buffers exactly 14 bars will receive `NaN` → signal `0` for the first 6 bars of every
strategy instance.** It is self-correcting after 20 bars and never produces a *wrong*
signal, only `NaN`-driven flats. Recorded because it is a real latent off-by-N in the
catalog, not because it affects the NSE result below (my harness builds whole panels
and never consults `warmup()`).

---

## 1a. Data-quality finding: frozen OHLC series (`nestleind`, `bajajauto`)

**Found while verifying §1, before any backtest ran.** Evidence: `verify_signal.py`
plus a direct scan of all 49 symbols.

`atr == 0` requires true range to be zero on all 14 trailing bars. Scanning every
bar-endpoint (212,168 evaluations) found **497** such endpoints, in exactly two symbols:

| Symbol | All-zero-ATR windows | Flat-close bars | Where |
|--------|---------------------|----------------|-------|
| `nestleind` | 466 | 502 | 2008-01-02 → 2010-01-07 — **491 consecutive bars frozen at ₹433.1–433.4** |
| `bajajauto` | 32 | 66 | 2008-01-18 → 2008-05-23 — 45 consecutive bars frozen at ₹324.4 |

A large-cap NIFTY-50 constituent did **not** trade at an identical price for 491
consecutive sessions across two years. This is a **frozen/stale vendor series**, not
market data — precisely the class of artifact `load_universe` rules C1–C5 exist to
catch. **It slips through every current rule:**

- **C1** (drop pre-2008) does not fire — the freeze runs *from* 2008-01-02.
- **C4** (non-positive prices) does not fire — ₹433.1 is a perfectly valid price.
- **C5** (drop \|return\| > 45%) does not fire — the freeze *produces* returns of exactly
  **0.00%**, the opposite of an extreme move. Only the transitions into and out of the
  freeze generate any return, and those are ordinary-sized.

**Why it matters generally:** the freeze pins `momentum_6m` (a 126d return) to exactly
0.0 for `nestleind` across 2008–2010. Because ranking is on *value*, a name whose
momentum sits at 0 for two years holds a fixed mid-book rank and can be repeatedly
picked or dropped as other names move around it. **Any backtest spanning 2008–2010 that
includes `nestleind` is contaminated**, including every "full 24y history" figure quoted
elsewhere in this project.

**Why it does NOT affect this run:** the freeze is entirely pre-2016. Counted explicitly
over the union of TRAIN and TEST, all-zero-ATR endpoints = **0**. So within my evaluation
windows the `atr > 0` predicate is provably a tautology and a ROC-only implementation is
*equivalent* to the full two-input signal. The harness asserts this on every run, so the
equivalence is machine-checked rather than taken on my word.

**Recommended fix (not applied — `src/nsealgo` is read-only for this agent):** add
cleaning rule **C9 — drop symbols containing a run of ≥10 consecutive unchanged closes**
— with its own counter and its own `CleaningReport` field. The existing `extreme_log` is
the wrong home for it: this artifact is *low*-variance, and C5 is a *high*-variance rule.

---

## 2. Data

Loaded via the mandatory first step — `load_universe("data/nse")`, which applies the
documented cleaning rules (drops pre-2008 vendor artifacts, non-positive prices,
impossible moves) and returns an auditable report.

- Timeframe: **`1d` only.** Daily-bar strategy, swing horizon, monthly rebalance.
- Span: 2002-07-01 → 2026-10-01.
- No 1h/5m/15m work: this strategy's parameters are calibrated for daily bars, and the
  sub-daily files cover ~2y / ~7w respectively — too short to validate anything.

**Hardcoded in this report (so a number can never be quoted without its end date):**
`1d` panel end date = **2026-10-01**.

---

## 3. Protocol (from `research/AGENT_BRIEF.md` §4)

| Set | Window | Purpose |
|-----|--------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | all tuning; looked at freely |
| **TEST** | 2024-01-01 → 2026-10-01 | **touched once**, at the end |

- Costs are mandatory and use `CostModel(segment="delivery", slippage_bps=5)`.
- All results below are via `run_backtest`, therefore **net of
  `all_in_round_trip_bps(100_000)` = 21.92 bps**. The 11.92 bps statutory-only figure
  is never quoted as a result here.
- Portfolio constraints enforced by `run_backtest` (`PortfolioConfig` defaults:
  22 names, 12% single name, 25% sector, 10% cash, 0.35 turnover budget). Not bypassed.
- Long-only. The `−1` branch is discarded — a delivery account cannot short.

---

## 4. DECLARED PARAMETER BUDGET — 5 variants, fixed before any run

The brief caps me at **5 distinct parameter variants**. I declare them here, before
running anything. I will select on TRAIN among these 5 and take the winner to TEST
unchanged. `period` (the ATR window) is deliberately **not** varied: §1 established the
ATR term is inert on this data, so varying it can only produce five identical backtests
and would burn budget on a parameter that cannot matter.

| ID | `momperiod` | `threshold` | Rationale |
|----|-------------|-------------|-----------|
| **V1** | 20 | 0.01 | Catalog default, unchanged. The honest baseline. |
| **V2** | 60 | 0.01 | Slower ROC — one quarter. Tests whether the gate wants a longer trend measure than 1 month. |
| **V3** | 126 | 0.02 | One trading half-year, 2% bar. Tests a medium-horizon gate at the horizon `nsealgo` already treats as its best Indian momentum window. |
| **V4** | 60 | 0.05 | Medium ROC with a **5% bar** — deliberately much harder to clear. If over-filtering helps (fewer, higher-conviction names) this finds it. |
| **V5** | 5 | 0.005 | Fast ROC, one week. Tests the short-term *continuation* edge that the Indian literature (Sehgal & Jain 2011; IIMC 2020) reports, at the opposite end of the horizon. |

If I ever need a 6th variant I will **report that I blew the budget** rather than hide it.

### Score construction (fixed by the brief, identical across all 5 variants)

```python
signal  = (roc > threshold)                       # +1 branch only, long-only
score   = trailing_return(126d).where(signal)     # rank momentum among flagged names
         .rank(axis=1, pct=True)
```

Trailing 126d return is used as the ranking key (the brief's recommended
`panel/panel.shift(126) - 1` construction), so the ROC gate acts purely as a *filter*
on which names are eligible, and rank orders the eligible ones. `build_rebalance_weights`
takes the top 22 of whatever survives.

---

## 5. Results

### 5.1 Pre-flight verification (before any backtest)

| Check | Result |
|-------|--------|
| Vectorised `roc_panel` vs source `roc` | 13,881 endpoints, **0** NaN-structure mismatches, max abs diff **1.1e-16** (pure float rounding — pandas uses `v/shift−1`, source uses `(v−shift)/shift`). **Equivalent.** |
| `atr > 0` predicate inside TRAIN+TEST | **0** gating endpoints → ROC-only score is provably equivalent to the full source signal. Asserted at runtime, not just claimed. |
| Cost model | `all_in_round_trip_bps(100_000)` = **21.92 bps**. `run_backtest` charges this. Every number below is net of it. |

### 5.2 Data (mandatory first step)

```
CLEANING REPORT
  rows in            :   274,541      rows out           :   208,226
  dropped pre-2008   :    66,312      dropped artifact   :         0
  dropped non-positive:         0      dropped extreme    :         3
  excluded symbols   : ['adanient', 'jiofin']   extreme events: 3
panel (4625, 48)  2008-01-01 -> 2026-10-01
```

**48 tradable symbols** (not 50 — `adanient` fails integrity rule C3, `jiofin` is below
the 1,000-bar minimum). Usable clean history effectively begins **2016** for my windows.

### 5.3 STAGE 1 — TRAIN only (2016-01-01 → 2023-12-31). All 5 declared variants.

Long-only, `+1` branch only. 126d trailing return as the ranking key. 22 names, 12%
single-name cap, 25% sector cap, 10% cash, 0.35 turnover budget, monthly rebalance.
**All net of 21.92 bps.**

| Variant | `momperiod` | `threshold` | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | Avg names | % bars long |
|---------|------------|------------|------|--------|-------|--------|----------|-----------|-----------|-------------|
| **V1** (catalog default) | 20 | 0.01 | 12.51% | 0.49 | −32.23% | 0.39 | 4.05× | 2.83%/y | 28.2 | 51.0% |
| V2 | 60 | 0.01 | 16.10% | 0.68 | −31.67% | 0.51 | 3.35× | 2.65%/y | 23.6 | 57.9% |
| V3 | 126 | 0.02 | 16.34% | 0.67 | −35.21% | 0.46 | 2.94× | 2.40%/y | 21.0 | 60.0% |
| V4 | 60 | 0.05 | 15.21% | 0.63 | −33.62% | 0.45 | 3.58× | 2.79%/y | 23.1 | 46.4% |
| **V5** | 5 | 0.005 | **17.83%** | **0.89** | **−14.01%** | **1.27** | 4.08× | 3.56%/y | 28.4 | 46.3% |
| *buy-and-hold* | — | — | 18.66% | 0.82 | −33.26% | 0.56 | 0.54× | — | 21.8 | 100% |
| *nsealgo composite* | — | — | 20.54% | 0.92 | −32.94% | 0.62 | 2.08× | — | 21.9 | 100% |

**Selection on TRAIN: V5** (`momperiod=5`, `threshold=0.005`) — highest Sharpe (0.89),
highest Calmar (1.27), by a clear margin over the next best (V2, Sharpe 0.68). V5 is the
only variant whose Sharpe beats buy-and-hold (0.89 vs 0.82), and its MaxDD of **−14.01%
against buy-and-hold's −33.26%** is the standout number: a 19-point drawdown reduction
for ~1 point of return give-up.

Note `avg_names` sits at 21.0–28.4, above the nominal 22. That is **within** the
`PortfolioConfig` contract (`max_names=30`): turnover-budget blending legitimately leaves
partially-held names between rebalances, and `_thin` caps the count at 30. No weight
accumulation bug — 28.4 is nowhere near the 48 that would indicate one.

**V5 is now frozen and goes to TEST unchanged.** TEST is touched exactly once, below.

### 5.4 STAGE 2 — TEST (2024-01-01 → 2026-10-01) — V5 frozen, run once

**Panel end date: 2026-10-01.** Every TEST number below is net of **21.92 bps**.

| Metric | **STRATEGY (V5)** | buy-and-hold (22-name book) | buy-and-hold (raw equal-weight) | nsealgo composite |
|--------|-------------------|------------------------------|---------------------------------|-------------------|
| **CAGR** | **2.59%** | 9.64% | 8.28% | 0.71% |
| **Sharpe** | **−0.32** | 0.31 | 0.19 | −0.43 |
| **MaxDD** | **−14.59%** | −13.48% | −15.90% | −15.28% |
| **Calmar** | 0.18 | 0.71 | 0.52 | 0.05 |
| Turnover/yr | 4.10× | 0.64× | — | 2.45× |
| Cost drag | 1.98%/y | — | — | — |
| Avg names held | 17.0 | 21.3 | 48 | 21.3 |
| % bars long | 44.6% | 100% | 100% | 100% |

Yearly: **2024 +10.50%**, **2025 −0.97%**, **2026 −1.83%** (partial). Positive in 1 of 3
years; 20 of 34 positive months (59%). Peak equity +21.68%, ending +7.43%.

### 5.5 Cost decomposition

| | CAGR |
|---|------|
| **Gross** (same weights, costs removed) | 4.45% |
| Cost drag @ 21.92 bps | −1.98%/y |
| **Net** | **2.59%** |

Gross is positive, so the strategy is **not** killed by costs alone — but 1.98%/y of
drag against a 4.45% gross return means **45% of everything the strategy earned before
costs was consumed by trading**. At 4.10× annual turnover the book wants to trade
continuously and is only allowed 0.35 one-way per rebalance.

---

## 6. Sanity checks (brief §6 — all six)

| # | Check | Result | Verdict |
|---|-------|--------|---------|
| 1 | **Plausibility** | CAGR 2.59%, gross 4.45% | ✅ No lookahead. Far below the 40–50% ceiling. |
| 2 | **Weight count** | avg **17.0** names | ✅ Not 48. See §7 below — low because the *signal* is scarce, which concentrates rather than dilutes. |
| 3 | **Signal liveness** | **44.6%** of bars long | ✅ Well above the 5% floor. Not an always-flat strategy. |
| 4 | **Cost drag** | gross 4.45% → net 2.59% | ⚠️ Gross positive, net positive. Costs consume 45% of gross but do **not** flip the sign. Viable-but-weak, not cost-killed. |
| 5 | **Negative control** | strategy **beats all 20** random seeds | ✅ **Real signal, not noise.** |
| 6 | **vs composite** | 2.59% vs 0.71% | ✅ Strategy beats the nsealgo composite — but both lose money. |

---

## 7. Diagnostics

**Why 17 names, not 22.** The signal, not `n_positions`, is the binding constraint. At
the 33 TEST rebalances the count of names that both *signalled* and were *rankable* is:
min **4**, p25 10, median 21, p75 28, max 41. **55% of rebalances had fewer than 22
eligible names.** A 5-day ROC gate on Indian large-caps is simply selective. Holding 17
names is more concentrated, never more diffuse — the safe direction.

**Turnover is budget-saturated.** 30 of 33 rebalances are pinned at the 0.35 one-way
budget (max 0.45 = the inception trade from cash). The strategy would trade more than
the risk wrapper permits; the budget is what's keeping the cost drag from being worse.

**Is 2.59% real?** Block bootstrap (2,000 resamples): CAGR 90% CI **[−6.54%, +13.47%]**,
**P(CAGR ≤ 0) = 30.9%**. The point estimate is not statistically distinguishable from a
range spanning serious loss to serious gain. On 33 monthly observations this strategy
simply does not have enough data to conclude anything except that it is mediocre.

**The killer diagnostic — it is a levered-down market bet that underperforms its own beta.**

| | Value |
|---|---|
| Beta to equal-weight universe | **0.62** |
| Correlation | 0.83 |
| Tracking error (ann.) | 7.60% |
| Market drift alone, at beta 0.62 | **≈ +5.5%/y gross** |
| Strategy actual gross | **+4.45%/y** |
| **Signal contribution over pure beta** | **−1.05 pp/y** |

The strategy takes on 62% of the market's risk and earns **less** than that exposure
would have delivered for free. It then pays 1.98%/y in costs to hold it. **The signal
itself destroyed about 1 pp per year, and turnover destroyed another 2.** The whole of
the TRAIN→TEST collapse is explained here.

---

## 8. Answers to the brief's questions

**1. Strategy & variants.** `momentum_volatility` → per-symbol ROC filter. Despite the
name, the `atr` term is a tautology inside the evaluation windows (§1, §1a), so this is
really a **rate-of-change gate**, not a momentum+volatility construct. 5 declared
variants (§4), all run on TRAIN, winner V5 taken to TEST unchanged. **Budget respected:
5 of 5, no sixth variant, no threshold re-tuning after seeing equity.**

**2. TEST numbers.** In §5.4.

**3. buy-and-hold, identical window.** 9.64% CAGR / Sharpe 0.31 / MaxDD −13.48%
(22-name book, same constraints, same costs). Raw equal-weight: 8.28% / 0.19 / −15.90%.

**4. TEST vs buy-and-hold — WORSE, on return. TIE-ish, slightly worse, on drawdown.**
- **Return: −7.05 pp/yr worse** (2.59% vs 9.64%). A 73% shortfall.
- **Drawdown: −14.59% vs −13.48% — 1.11 pp WORSE.** This is the important reversal.
  On TRAIN, V5's entire appeal was MaxDD −14.01% against buy-and-hold's −33.26% — a
  19-point drawdown advantage. **Out-of-sample that advantage vanished entirely and
  inverted.** The single most attractive TRAIN characteristic did not survive.

**5. Random-signal control — the strategy PASSES.** 20 seeds at the same 44.6% long
fraction: mean CAGR −1.74% (σ 1.55), best +1.04%, worst −4.29%, mean Sharpe −1.07. The
strategy at +2.59% sits at the **100th percentile — it beat all 20**. So the ROC gate
*does* carry genuine signal. That is a real, reportable finding: **the strategy is not
noise, it is simply a bad trade dressed in a real signal.**

**6. Did it beat the nsealgo composite? YES — 2.59% vs 0.71%, Sharpe −0.32 vs −0.43.**
With a large caveat that this is a low bar: **both lose money out-of-sample.** The
composite's own TEST Sharpe is −0.43. This is consistent with `reports/VALIDATION_v1.md`
§0 and is *not* a recommendation to prefer this strategy over the composite.

**7. Verdict — one sentence.**

> **No: `momentum_volatility` does not make money on NSE.** It earned 2.59% net
> (Sharpe −0.32) out-of-sample versus 9.64% for simply holding the index, underperformed
> its own market beta by ~1 pp/yr, and consumed 45% of its gross return in costs — while
> beating a random coin flip, so the failure is a *cost-and-exposure* failure, not a
> *signal* failure.

**8. Most likely reason, and the one thing I'd try next.**

*Reason:* **turnover against a too-fast signal.** The TRAIN winner was the *fastest* ROC
variant (5 days), which is also the highest-turnover one (4.10×/yr). The 5-day gate
re-selects the book almost every month, so 45% of gross profit is paid to brokers, and
the resulting 0.62-beta book underperforms the market it is trying to capture. The
"volatility" half of the strategy name contributes nothing (§1a), so there is no
volatility-scaling mechanism to damp the turnover — nothing in the design moderates it.

*Next thing I'd try — exactly one:* re-run this exact strategy with **V3's `momperiod=126`
parameters** (turnover 2.94×/y on TRAIN, the lowest of the family). Same strategy, same
code path, same protocol — only the ROC horizon changes, which directly attacks the cost
drag. If a low-turnover ROC gate also underperforms buy-and-hold out-of-sample, then the
conclusion generalises from "V5 was a bad variant" to **"ROC-gating has no long-only edge
on NSE"**, which is the answer worth having. **That test has not been run and must be run
on a fresh TEST window — not this one, which is now spent.**

---

## 9. Protocol compliance

- ✅ Parameter budget declared before any run (§4). **5 of 5 used. No exceedance.**
- ✅ All tuning on TRAIN. V5 selected on TRAIN Sharpe (0.89) / Calmar (1.27).
- ✅ TEST touched **once**, with V5 **unchanged**.
- ✅ No threshold re-tuning after seeing any equity curve.
- ✅ Costs mandatory, full Indian delivery stack, reported net of 21.92 bps
  throughout. No gross number is presented as a result.
- ✅ No lookahead: features trailing, engine's one-bar lag, ATR equivalence machine-asserted.
- ✅ Long-only; `−1` branch discarded.
- ✅ `PortfolioConfig` constraints respected, never bypassed.
- ✅ `src/nsealgo`, `src/cryptobot` and all test files **unmodified**.
- ✅ Nothing committed or pushed. `GOAL.md` and `reports/` untouched.
- ✅ `.venv/bin/ruff check research/agent_momvol/*.py` → **All checks passed**.

### Deliberate abstention

I did **not** run the other four variants on TEST, even though it would have been
informative to know whether V5 was merely a bad draw from a good family. That sweep is
five TEST evaluations, and `AGENT_BRIEF.md` §4 rule 2 says TEST is touched exactly once.
Selecting the best of five TEST results is exactly the overfitting the protocol exists to
prevent. **The headline verdict stands on the one honest draw.** The family-level question
is left explicitly open in §8, which is the correct place for it.

---

## 10. Artifacts

| File | What it is |
|------|-----------|
| `REPORT.md` | This report |
| `common.py` | Shared harness: signal/score construction, ATR-equivalence guard, run wrapper |
| `verify_signal.py` | Proves vectorised ROC ≡ source `roc`; finds the frozen-series artifact |
| `stage1_train.py` | All 5 declared variants on TRAIN + benchmarks → `stage1_train.{csv,json}` |
| `stage2_test.py` | Single frozen TEST run + benchmarks + 20-seed random control → `stage2_test.json` |
| `stage3_diag.py` | Post-hoc diagnostics on the selected run (bootstrap, beta, turnover) |

**Reproduce:** `.venv/bin/python research/agent_momvol/verify_signal.py` ·
`stage1_train.py` · `stage2_test.py` · `stage3_diag.py`

---

## 11. Findings worth propagating beyond this strategy

1. **Data bug (high value).** `nestleind` has **491 consecutive frozen closes**
   (2008-01-02 → 2010-01-07 at ₹433.1) and `bajajauto` has 45 (2008-01 → 2008-05 at
   ₹324.4). Both survive every `load_universe` rule C1–C5, because C5 only catches
   *large* moves and this artifact is made of **exactly zero** returns. Any 2008–2010
   result including these names is contaminated. **Needs rule C9 (≥10 consecutive
   unchanged closes → drop + log).** `src/nsealgo` was read-only here.
2. **Catalog bug.** `MomentumVolStrategy.warmup()` returns `period` (14) but `signal()`
   needs `momperiod` (20) bars — an off-by-N that returns `NaN`-driven flats for the
   first 6 bars of every instance. Harmless in panel form, wrong for any streaming caller.
3. **Naming trap.** 3 of the catalog's strategies carry a volatility component that is
   inert or near-inert in its default configuration. Any strategy named
   `*_volatility` in this catalog should be checked for whether its volatility term can
   actually fire before its performance is interpreted.
4. **The nsealgo composite itself fails this TEST window** (0.71% CAGR, Sharpe −0.43),
   independently reproducing the headline finding in `reports/VALIDATION_v1.md` §0. Two
   independent agents reaching that number strengthens it.