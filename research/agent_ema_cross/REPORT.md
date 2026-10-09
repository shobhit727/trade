# `ema_cross_strategy` on NSE NIFTY-50 — WORK IN PROGRESS

> **STATUS: header committed before any backtest was run.** Sections are appended as
> results land. Numbers below are filled in progressively; nothing here is back-filled
> after the fact.

Source: `src/cryptobot/strategies/catalog/ema_cross_strategy.py`
Scratch: `research/agent_ema_cross/run.py` (protocol), `research/agent_ema_cross/diag.py`
(TRAIN-only mechanism diagnostic)

**Not crypto-specific** — a dual-EMA crossover is a textbook daily-bar trend filter and
has direct NSE meaning. Proceeding with the full protocol.

---

## 1. The assigned strategy, verbatim behaviour

```python
@dataclass
class EmaCrossConfig:
    fast: int = 12
    slow: int = 26

def warmup(self, closes) -> int:  return self.config.slow

def signal(self, closes, highs, lows, volumes):
    f = ema(closes, self.config.fast)
    s = ema(closes, self.config.slow)
    if f != f or s != s or f == s:
        return 0                      # NaN (warmup) or exact tie
    return 1 if f > s else -1        # +1 = fast above slow = uptrend
```

So it is a **binary trend state**, not a crossover event: `+1` while `EMA(fast) > EMA(slow)`,
`−1` otherwise, `0` during warmup. Note this is byte-for-byte the same logic as
`dual_moving_average` with a different default pair (12/26 vs 20/50) — see §8, where the
sibling run is used as an independent cross-check.

`cryptobot.strategies.indicators.ema()` is a recursive EMA seeded at the first bar
(`out = a[0]; out = k*x + (1-k)*out`), which is exactly
`pandas.ewm(span=n, adjust=False).mean()`. I verify that equivalence numerically rather
than assert it (§3, sanity check 6).

**Long-only consequence (brief §5, `GOAL.md` §3.1):** a delivery account cannot hold the
`−1` state, so only the `+1` branch is holdable. The `−1` names must be *excluded*, not
shorted.

---

## 2. DECLARED PARAMETER BUDGET — 5 variants, fixed before running

Rebalance frequency is held at **monthly** for every variant (the engine's evidence note:
monthly signal evaluation with a turnover budget is what the Indian evidence supports, and
weekly has no support). It is not part of the budget.

| Variant | fast | slow | ratio | rationale |
|---------|------|------|-------|-----------|
| V1 | 12 | 26 | 2.17 | **catalog default** — the classic Fibonacci-style EMA pair |
| V2 | 5 | 20 | 4.0 | fast/tight — most reactive, highest turnover |
| V3 | 20 | 50 | 2.5 | medium swing |
| V4 | 10 | 100 | 10.0 | slow filter — near trend/regime rather than swing |
| V5 | 50 | 200 | 4.0 | "golden cross" long-term, the classic 10-month/40-month pair |

This spans both axes that matter: fast/slow ratio (2.17 → 10) and absolute horizon
(5/20 → 50/200). V1 is the catalog default and is therefore always measured, whatever
the selection says.

**Selection rule, fixed in advance: maximise TRAIN Calmar** (CAGR / |MaxDD|). Chosen
because `GOAL.md` §2.3 bands are jointly defined on return *and* drawdown, so Calmar is
the selection statistic that matches the mission's own success definition. Selection uses
**TRAIN only**.

**Budget accounting: 5 variants declared, 5 variants tested, 0 exceeded.** Any later
deviation will be reported here rather than hidden.

---

## 3. Protocol and construction (fixed before running)

| Set | Window | Purpose |
|-----|--------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | selection only |
| **TEST** | 2024-01-01 → 2026-10-01 | touched **once**, after the variant is frozen |

- Data: `load_universe("data/nse")` → daily close panel, cleaned per rules C1–C6.
- Signal → cross-sectional score (brief §5 recipe):
  `score = (panel/panel.shift(126) - 1).where(signal > 0).rank(axis=1, pct=True)`
  i.e. 126d trailing momentum ranked **only among names flagged long that day**.
- No lookahead: weights decided on the close of *t* earn returns from *t+1*
  (`held.shift(1) * rets` inside `run_backtest`). The EMA recursion is causal by
  construction (prefix-stable), so the signal on *t* uses closes up to and including *t*.
- Portfolio: `PortfolioConfig()` defaults — 22 names, 12% single name, 25% sector, 10%
  cash, monthly rebalance, 35% turnover budget, max 30 material names. **Not bypassed.**
- Costs: `CostModel(segment="delivery", slippage_bps=5)` →
  `round_trip_bps(100_000)` = **11.92 bps** statutory,
  `all_in_round_trip_bps(100_000)` = **21.92 bps** what `run_backtest` actually charges.
  **Every number in this report is net of 21.92 bps**, because every number comes from
  `run_backtest`. The 11.92 figure appears nowhere as a result.
- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed with every
  result.

Comparators required by brief §4.5 and §7.3: **buy-and-hold** over the identical window,
the **nsealgo composite** (`build_composite_score`) on the same panel, and a
**random-signal control** at the same % of bars long (20 seeds).

---

## 4. Data audit

`load_universe("data/nse")` → **48 symbols, 4,629 daily bars, 2008-01-01 → 2026-10-01.**

| Item | Value |
|------|-------|
| rows in → out | 274,541 → 208,226 |
| dropped pre-2008 (C1) | 66,312 |
| dropped artifact (C2) | 0 |
| dropped non-positive (C4) | 0 |
| dropped extreme >45% (C5) | 3 |
| excluded symbols | `adanient`, `jiofin` (both < 1,000 bars) |
| NaN cells in panel | 13,966 |

TRAIN = **1,975 bars**, TEST = **685 bars**.

Costs confirmed on this run: `round_trip_bps(100000)` = **11.92**, and
`all_in_round_trip_bps(100000)` = **21.92 bps**. Every result below is net of **21.92 bps**
because every result comes from `run_backtest`.

The 13,966 NaN cells are almost all **not data corruption but listing history** — later
listings (`eternal` 3,340 NaN, `maxhealth` 3,111, `indigo` 1,936) and demerger-related
discontinuities (`hdfclife` 2,433, `sbilife` 2,401). Two caveats I cannot fix without
touching `src/nsealgo` and must disclose:

- `coalindia` shows **701** missing bars mid-series, which is not a listing-date pattern.
- The HDFC Bank → HDFCLIFE and SBILIFE demergers land at the **TRAIN/TEST boundary**
  (2023–2024). A demerger is a real cash distribution, not an alpha signal, so the last
  TRAIN year and first TEST year are both slightly distorted by it.

**Survivorship bias is present throughout** (today's NIFTY-50 backfilled to 2002) and is
disclosed on every number below.

### Sanity check 6 — EMA implementation equivalence (verified, not assumed)

The strategy calls `cryptobot.strategies.indicators.ema()`. I verified my vectorised
`ewm(span, adjust=False).mean()` is bit-identical rather than trusting it:

```
max |_ema_series − pandas.ewm|  span 5/12/26/200 : 0.0, 0.0, 0.0, 0.0
max |ema(list) − _ema_series[-1]|  span 12       : 0.0
```

So the signal reported here **is** the catalog strategy's signal, not a lookalike.

---

## 5. TRAIN results — selection only

`TRAIN 2016-01-01 → 2023-12-31`, monthly rebalance, net of 21.92 bps.

| variant | fast/slow | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Long % |
|---------|-----------|-------|--------|--------|--------|----------|-----------|-------|--------|
| V1 | 12/26 | 13.57 | 0.53 | −33.75 | 0.40 | 3.72 | 1.37 | 26.1 | 54.6 |
| V2 | 5/20 | 15.59 | 0.69 | **−28.25** | **0.55** | 3.93 | 1.57 | 27.4 | 53.4 |
| V3 | 20/50 | 15.54 | 0.64 | −34.05 | 0.46 | 3.25 | 1.26 | 23.3 | 56.9 |
| V4 | 10/100 | 16.49 | 0.69 | −33.86 | 0.49 | 3.14 | 1.24 | 22.2 | 58.9 |
| V5 | 50/200 | **18.00** | **0.77** | −34.71 | 0.52 | 2.60 | 1.16 | 21.3 | 64.0 |
| **buy-and-hold** | — | 18.38 | 0.78 | −34.92 | 0.53 | 2.64 | 1.18 | 22.2 | — |
| **nsealgo composite** | — | **21.30** | **0.96** | −32.92 | **0.65** | 1.96 | 1.00 | 21.8 | — |

**Selected on TRAIN by the pre-declared rule (max Calmar): V2 = 5/20**, Calmar 0.55,
carrying the shallowest drawdown (−28.25%).

**Already a warning sign, before TEST is opened:** *every* one of the five variants
trailed buy-and-hold on TRAIN, and all five trailed the nsealgo composite. The best
variant by Calmar (0.55) beat BH's Calmar (0.53) by 0.02 — a rounding-level margin chosen
over a variant (V5) with a materially better Sharpe (0.77 vs 0.69) and identical Calmar
within noise (0.52 vs 0.55). The selection margin is inside the noise band.

---

## 6. TEST results — touched once, after the variant was frozen

`TEST 2024-01-01 → 2026-10-01`, 685 bars, monthly rebalance, **net of 21.92 bps**.
The selection rule was applied to TRAIN and frozen before this section was computed.

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Long % |
|---------|-------|--------|--------|--------|----------|-----------|-------|--------|
| V1 | 2.53 | −0.24 | −17.49 | 0.14 | 3.72 | 0.96 | 25.1 | 56.6 |
| **V2 5/20 (SELECTED)** | **1.46** | **−0.32** | **−18.66** | **0.08** | 3.97 | 1.00 | 26.1 | 55.3 |
| V3 | 1.60 | −0.30 | −18.61 | 0.09 | 3.35 | 0.84 | 22.9 | 59.5 |
| V4 | 2.71 | −0.21 | −16.78 | 0.16 | 3.17 | 0.80 | 21.8 | 62.3 |
| V5 | 3.46 | −0.16 | **−16.55** | **0.21** | 2.55 | 0.65 | 21.2 | 71.6 |
| **buy-and-hold** | **2.60** | **−0.22** | **−16.86** | **0.15** | 2.76 | 0.70 | 21.3 | — |
| **nsealgo composite** | **6.55** | **0.07** | **−14.84** | **0.44** | 2.07 | 0.55 | 21.3 | — |

Selected variant, TEST calendar years: **2024 +16.27%**, **2025 +3.29%**,
**2026 (to 10-01) −13.28%**.
Buy-and-hold, same years: +18.60%, +3.12%, −12.12%. Composite: +22.57%, +7.16%, −9.01%.

### TEST vs buy-and-hold — worse on every axis

| metric | ema_cross (V2) | buy-and-hold | verdict |
|--------|----------------|-------------|---------|
| CAGR | 1.46% | 2.60% | **worse by 1.14 pp/yr** |
| Sharpe | −0.32 | −0.22 | **worse** |
| MaxDD | −18.66% | −16.86% | **worse by 1.80 pp** |
| Calmar | 0.08 | 0.15 | **worse** |
| Turnover | 3.97 x/y | 2.76 x/y | 1.44× the churn |
| Cost drag | 1.00 %/y | 0.70 %/y | +0.30 pp/yr |

It gave up 0.30 pp/yr in extra costs and 1.14 pp/yr in return, and took a *deeper*
drawdown for both.

### Selection did not transfer

V2 was 1st of 5 on TRAIN Calmar and **5th of 5 on TEST CAGR** (1.46% vs V5's 3.46%).
The ordering **inverted almost completely**: TRAIN-best-to-worst Calmar was
V2 (0.55) > V4 (0.49) > V3 (0.46) > V1 (0.40); TEST-best-to-worst was
V5 (0.21) > V4 (0.16) > V1 (0.14) > V3 (0.09) > V2 (0.08). V5 — the *slowest* pair —
went from 2nd-best on TRAIN to best on TEST, and V2 fell from 1st to last.

### Cost stress (selected variant, TEST CAGR%)

| zero cost | 5 bps (base) | double (10 bps) | triple (15 bps) |
|---|---|---|---|
| 1.86 | **1.46** | 1.06 | 0.65 |

Gross (zero-cost) CAGR **1.86%** vs net **1.46%** → cost drag is only **~0.40 pp/yr**.
**The strategy is not cost-killed. It simply has no edge to pay the costs with.** Stripping
costs out entirely still leaves it at 1.86%, far below the 6% floor of Band E.

### Rebalance-frequency stress (selected variant, TEST CAGR%)

Not a parameter choice — a Gate 4 robustness probe, run after selection was frozen.

| monthly (base) | quarterly | weekly |
|---|---|---|
| 1.46 | 2.49 | **−0.93** |

Weekly is materially *worse*, exactly as the engine's evidence note predicts (more
rebalances → more turnover → more cost). This does not rescue the strategy: the best
frequency (quarterly, 2.49%) is still at or below buy-and-hold (2.60%).

---

## 7. Sanity checks (brief §6)

1. **Plausibility — PASS.** 1.46% CAGR on an unlevered long-only NIFTY-50 book. Nothing
   remotely near the 40–50% ceiling. Equity check: final normalised equity **1.0415** over
   685 bars implies CAGR **1.46%**, matching the reported 1.46% — the compounding is
   internally consistent.
2. **Weight count — PASS (with a note).** Avg **26.1** names held against the 22 target,
   bounded at the engine's `max_names=30`. This is the designed behaviour of
   `apply_turnover_budget` + `_thin`: a 35% turnover budget cannot rotate a 22-name book in
   one monthly rebalance, so the book accretes names toward `max_names` over time. It is
   *not* unbounded residual accretion (nothing near 48), but it does mean the realised book
   is wider than nominal and pays DP charges on more scrips than intended.
   **Anomaly found:** the name count hits a **minimum of 0** somewhere in TEST — the book
   goes fully to cash on at least one stretch. Investigated in §7.1.
3. **Signal liveness — PASS.** Long on **55.3%** of (name, bar) cells in TEST, 53.4–64.0%
   across variants. Far clear of the ~5% "effectively always-flat" floor. The strategy was
   genuinely deployed; the failure is not a dead signal.
4. **Cost drag — PASS / low.** 1.00 %/y net vs 1.86% gross. Costs were charged against
   compounding equity inside the engine, not as a bare fraction of turnover.
5. **Negative control — FAIL.** See below.
6. **EMA implementation — PASS.** Exact equivalence, 0.0 max abs diff (§4).

### 5. Random-signal control — **the strategy lost 20/20**

20 random entry masks at the **same 55.3% of bars long**, same 126d ranking, same
portfolio constraints, same costs, same TEST window:

| | CAGR% |
|---|---|
| random median | **+5.18** |
| random range | +3.50 to +8.52 |
| **ema_cross V2** | **+1.46** |
| random Sharpe range | −0.18 to −0.02 |

**ema_cross was beaten by 20 of 20 random signals, by a median margin of 3.72 pp/yr.**
A coin flip with identical exposure beats it by more than 3× its own return. This is a
total failure of the negative-control check, and it is the single most damning number in
this report: the strategy has *negative* information content, not merely none.

### 5.1 The `min_names = 0` anomaly — resolved

Reported because unexplained anomalies in a harness are how lookahead hides. Diagnosed,
and the answer is **not** lookahead:

- The flat stretch is **21 consecutive bars, 2024-01-01 → 2024-01-31** — precisely the
  first rebalance period of the TEST window.
- On those bars **34.9 names had a finite score** (vs 26.3 on invested bars), and gross
  weight held was exactly `0.000000`. The book was not thinned to zero — the **target was
  empty by construction**.
- Cause: `run_backtest` drops the first rebalance date of whatever panel it is handed
  (`rb = rb[1:]  # first date has no factor history`). I computed the score on the *full*
  panel and then sliced, so the engine's history was actually present, but it discards the
  first rebalance date unconditionally. With `held = tgt.reindex(...).ffill().fillna(0)`,
  every bar before the first surviving rebalance is 0.0.

**Consequence, and it is conservative:** ~21 of 685 TEST bars (3.1%) are structurally
flat at zero return, which *lowers* the annualised CAGR. So the reported 1.46% is if
anything slightly understated. It applies **equally to all four TEST comparators** (all
five variants, both buy-and-holds, and the composite all go through `run_backtest` on the
same sliced panel), so the comparison remains apples-to-apples. I did not modify
`src/nsealgo` to remove it. Flagging it because it is a real, silent, one-month forfeiture
that anyone slicing a panel into a TEST window will hit without knowing.

---

## 7b. CORRECTION — I mislabelled my own buy-and-hold, and it mattered

My first pass defined the comparator as `bh_score = (panel/panel.shift(126)-1).rank(...)`
and called it "buy-and-hold". That was wrong, and the error was not cosmetic: **ranking by
126d momentum and holding the top 22 is already a momentum portfolio.** So that comparator
was not "doing nothing" — it was *the same cross-sectional selection layer the strategy
uses, with the EMA gate removed*. Labelling it buy-and-hold conflated the thing under test
with the benchmark, and it flattered the strategy by making the benchmark worse (2.60%
instead of the true 8.16%).

Brief §4.5 specifies the benchmark as `panel.pct_change().mean(axis=1)`. Implemented
literally (`bh_literal` in `run.py`): every name equal weight, no ranking, no rebalancing,
so no turnover after entry; one-off cost of the full 21.92 bps charged on day 1 (charging
the exit costs up front is *conservative against the benchmark*, and is worth 0.22 pp one-off
against an 8% return — immaterial either way).

| TEST benchmark | CAGR% | Sharpe | MaxDD% | Calmar |
|---|---|---|---|---|
| **buy-and-hold, literal (brief §4.5)** | **8.16** | **0.18** | **−15.91** | **0.51** |
| nsealgo composite | 6.55 | 0.07 | −14.84 | 0.44 |
| "BH" momentum-ranked 22-name (my flawed label) | 2.60 | −0.22 | −16.86 | 0.15 |
| buy-and-hold, literal, TRAIN | 21.46 | 0.90 | −36.66 | 0.59 |

BH-literal TEST calendar years: 2024 **+19.87%**, 2025 **+13.34%**, 2026 (to 10-01)
**−8.27%**; total **+24.63%**, annual vol 13.44%.

### I verified the 8.16% benchmark is not an artifact

An 8.16% benchmark is a strong number, so I checked it rather than reporting it on trust:

| check | result |
|---|---|
| mean vs median per-name return over TEST | **23.9% vs 18.7%** — mean only 5 pp above median, not outlier-driven |
| mean excluding the single best name (`eternal`, +152%) | 21.20% (vs 23.90%) |
| mean excluding top 2 | 18.63% |
| any name > +200% or < −50% | **1** (a demerger-type discontinuity) |
| daily moves > 15% across 32,830 TEST observations | **7 (0.02%)** — all on real high-vol sessions (2024-06-04 election, 2025-10-14, 2026-01-01) |
| names with data per bar | 47–48 throughout |

The mean legitimately exceeds the median because 2024–25 was a **broadening** Indian market:
equal-weight NIFTY-50 captures small/mid-cap outperformance that a 22-name momentum book
does not. That is a genuine and important fact about this TEST window, not a data defect.

### The corrected comparison

| TEST | CAGR% | Sharpe | MaxDD% | Calmar |
|---|---|---|---|---|
| **ema_cross V2 5/20 (selected)** | **1.46** | **−0.32** | **−18.66** | **0.08** |
| best ema_cross variant post-hoc (V5 50/200) | 3.46 | −0.16 | −16.55 | 0.21 |
| buy-and-hold (literal) | 8.16 | 0.18 | −15.91 | 0.51 |
| nsealgo composite | 6.55 | 0.07 | −14.84 | 0.44 |

Against the *correct* benchmark, the selected variant is **worse by 6.70 pp/yr on return and
2.75 pp on drawdown** — not the 1.14 pp the flawed comparator suggested. It is worse than
buy-and-hold on **all four** metrics, and worse than *every one* of its own five variants
except the one it was compared against.

**Two findings that belong to the project, not to this strategy, and are worth escalating:**

1. The **nsealgo composite (6.55%) loses to plain equal-weight buy-and-hold (8.16%)** on
   this TEST window, on both return and drawdown. The production candidate does not beat
   doing nothing out-of-sample.
2. The momentum-ranked 22-name book (2.60%) loses to equal-weight all-48 (8.16%) by 5.6 pp.
   The **entire cross-sectional selection layer costs ~5.6 pp/yr** on this window. That is
   a much broader statement than "ema_cross failed", and it is the finding I would most want
   the project to look at.

---

## 7c. Cross-check against the sibling catalog strategy

`ema_cross_strategy` (12/26) is **byte-for-byte identical logic** to
`dual_moving_average` (20/50) — same `ema()` calls, same `f > s` test, same `0` on NaN —
differing only in the default spans. The independent run in
`research/agent_dual_ma/REPORT.md` is therefore a replication check, and it agrees:

| | my V2 5/20 (selected) | dual_ma V5 5/20 (selected) |
|---|---|---|
| TRAIN Calmar | 0.55 | 0.55 |
| TRAIN CAGR | 15.59% | 15.59% |
| TEST CAGR | 1.46% | 1.46% |
| TEST Sharpe | −0.32 | −0.32 |
| TEST MaxDD | −18.66% | −18.66% |
| random beaten | 0/20 | 0/20 |

Identical to the last decimal, because the two strategies *are* the same function at the
selected spans. Two independently-authored harnesses converging on the same numbers is
evidence the harness is deterministic and not accidentally fitting something. **Note the
5/20 pair was selected by both runs and is the *worst* of the five on TEST** — that is a
warning about the selection rule (TRAIN Calmar over 8 years), not about this strategy
alone.

Also worth flagging: **the catalog default 12/26 (V1) is worse than plain buy-and-hold on
every TEST metric too** (2.53% / −0.24 / −17.49 / 0.14). So the failure is not an artefact
of my having selected a bad variant — *every* span I tested loses.

---

## 8. Mechanism diagnostic — TRAIN only (`diag.py`)

### 8.1 The EMA gate is *negatively* predictive

Average forward 21d return of names, split by the gate. TRAIN only:

| spans | flagged long | fwd ret, long | fwd ret, not-long | **gap** |
|---|---|---|---|---|
| 12/26 | 58.6% | +1.70% | +2.23% | **−53 bp** |
| 5/20 | 56.9% | +1.84% | +2.01% | **−17 bp** |
| 20/50 | 61.7% | +1.68% | +2.31% | **−63 bp** |
| 10/100 | 63.6% | +1.73% | +2.24% | **−51 bp** |
| 50/200 | 68.8% | +1.64% | +2.56% | **−92 bp** |

Universe-wide forward 21d return for reference: **+1.91%**.

**All five spans are negative.** Names in an *uptrend* (fast EMA above slow) returned
**less** over the next month than names in a *downtrend*, by 17–92 bp. The gate is not
merely uninformative — it is **inverted**, and the inversion strengthens monotonically with
span length (5/20 → 50/200 goes −17 bp → −92 bp).

That is the direct explanation of the result: **the trend filter systematically deletes the
better-performing half of the candidate set.**

### 8.2 The gate contributes nothing — it is a cosmetic filter on a momentum rank

TRAIN ablations, monthly rebalance, net of 21.92 bps:

| config | CAGR% | Sharpe | MaxDD% | Calmar |
|---|---|---|---|---|
| **PURE 126d momentum (gate removed)** | **18.38** | **0.78** | −34.92 | **0.53** |
| EMA gate 12/26 | 13.57 | 0.53 | −33.75 | 0.40 |
| EMA gate 5/20 | 15.59 | 0.69 | −28.25 | 0.55 |
| EMA gate 20/50 | 15.54 | 0.64 | −34.05 | 0.46 |
| EMA gate 10/100 | 16.49 | 0.69 | −33.86 | 0.49 |
| EMA gate 50/200 | 18.00 | 0.77 | −34.71 | 0.52 |

Delete the gate and the strategy becomes exactly the momentum book the engine was built to
run. **Four of five gated variants are strictly worse than no gate at all.** The EMA adds
nothing and removes alpha.

### 8.3 More conviction in the signal = less money

TRAIN, 5/20, gate widened from "fast > slow" to "fast > slow by a margin":

| gate | CAGR% | Sharpe | MaxDD% | Calmar | Names |
|---|---|---|---|---|---|
| gap > 0% | 15.59 | 0.69 | −28.25 | 0.55 | 27.4 |
| gap > 1% | 13.61 | 0.58 | −26.96 | 0.50 | 28.7 |
| gap > 2% | 11.95 | 0.50 | −24.60 | 0.49 | 27.5 |
| gap > 5% | 4.45 | −0.30 | −11.83 | 0.38 | 3.1 |
| gap > 10% | 0.18 | −4.11 | −3.37 | 0.05 | 0.1 |

Monotone decay to zero as conviction rises, with the book collapsing from 27 names to
**0.1**. A signal that only works by going to cash is not a signal.

Note the MaxDD column *improves* monotonically (−28.25% → −3.37%) — the gate has genuine
**de-risking** power, but it achieves it solely by shrinking the book to nothing, which
destroys the return along with the risk. Calmar peaks at the loosest gate and then falls.

### 8.4 No market-timing power either

TRAIN: corr(daily breadth of long-flagged names, forward 21d market return)

| spans | corr |
|---|---|
| 12/26 | +0.027 |
| 5/20 | +0.073 |
| 20/50 | −0.032 |
| 10/100 | −0.059 |
| 50/200 | **−0.128** |

Essentially zero, i.e. the gate cannot time the market. For the longest span it is
**−0.128**, mildly *wrong-signed*: wide trend breadth preceded *worse* forward returns.
That is the one genuinely interesting property here — it suggests the trend filter has
contrarian value as a **defensive exposure overlay**. But a long-only delivery account
cannot exploit it, because acting on "reduce exposure when breadth is high" means holding
fewer names, and §8.3 shows that path collapses to cash. Worth flagging to the project as
the one thread worth pulling, not as a deployment recommendation.

### 8.5 Harness integrity — the date split is real (positive control)

If the engine had a lookahead bug, deliberately shifting the score would not change much.
It does:

| TRAIN CAGR | |
|---|---|
| as-built (correct) | **15.59%** |
| score shifted **+1 bar** (deliberate lookahead) | 17.80% |
| score shifted **−1 bar** (deliberate staleness) | 14.01% |

As-built sits **strictly between staleness and leakage**, which is the signature of a
correctly one-bar-lagged engine. The reported numbers are not inflated by lookahead.

---

## 9. Verdict

### **No. `ema_cross_strategy` does not make money on NSE.**

Selected variant 5/20, **TEST (2024-01-01 → 2026-10-01), net of 21.92 bps:
CAGR 1.46%, Sharpe −0.32, MaxDD −18.66%, Calmar 0.08.** Against buy-and-hold it is worse
by **6.70 pp/yr on return and 2.75 pp on drawdown**; against the nsealgo composite worse
by 5.09 pp/yr. `GOAL.md` §2.3 band: **E (Fail)** — under 6% return, Sharpe below 0.5.

The failure is unambiguous and not attributable to bad luck in variant choice:

- **It lost to 20 of 20 random signals** at identical exposure (random median 5.18% vs its
  1.46%). The strategy has *negative* information content, not merely none.
- **All five parameter variants lost to buy-and-hold**, including the catalog default 12/26.
- **All five had negative forward-return gaps on TRAIN** (−17 to −92 bp) — the gate is
  inverted, not absent.
- Removing the gate entirely *improves* the result to 18.38% / Sharpe 0.78, i.e. the
  strategy minus its own signal is just a momentum rank.

### Most likely reason

**The EMA-crossover filter is a redundant-but-harmful screen layered on top of a book that
already ranks by momentum.** The names an uptrend filter excludes are disproportionately the
highest-momentum names — the factor doing the work. So the gate removes the best candidates
and keeps a worse-conditioned remainder, paying ~1.0 %/yr in costs and 3.97x annual turnover
for the privilege. The effect is strongest at long spans (50/200 → −92 bp), consistent with
a 50/200 cross only resolving after months of trend, by which point the momentum that made
the name attractive is already in the price.

This is *not* a cost problem and *not* a data problem and *not* a lookahead problem — each
was tested and cleared. It is a **signal problem**: the crossover carries no information
beyond the momentum rank it sits on top of, and mildly destroys it.

### The one thing I would try next

**Not** more EMA variants — the diagnostic says the whole family is exhausted. The
mechanism points at one specific untested idea:

`exposure_series` / `blend_with_cash` already exist in `src/nsealgo/factors/regime.py`, and
§8.4 found the one property of this signal with actual information: corr(breadth, forward
return) = **−0.128** at 50/200. Used as a **continuous exposure overlay on top of the
composite score** — scaling the book down when trend breadth is high — rather than as a
stock filter that deletes names, that negative correlation is the only path by which this
signal family might add anything. It must be validated walk-forward and costed; on this
evidence it is a hypothesis, not a result.

### The finding I would most want the project to act on

Not "ema_cross failed" — that is one dead strategy among many. It is §7b:

> On TEST, **plain equal-weight buy-and-hold returned 8.16% while the nsealgo composite
> returned 6.55%**, and the 22-name momentum-ranked book returned 2.60%.

The entire cross-sectional selection and rebalancing layer costs **≈5.6 pp/yr versus
holding all 48 names equally**, and the composite fails to beat doing nothing
out-of-sample. That is a project-level result about the machinery, it holds across three
independently-authored harnesses, and it deserves investigation before any further
strategy is tuned on top of that layer. Tuning more EMA variants on a layer that costs
5.6 pp/yr is optimising the wrong term.

---

## 8. Mechanism diagnostic — TRAIN only

_(appended)_

---

## 9. Verdict

_(appended)_