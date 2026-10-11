# `volatility_scaling` on NSE NIFTY-50 — validation report

**Status: IN PROGRESS.** This file is written incrementally. Numbers land here as they
are produced; the verdict at the bottom is the only thing that should be quoted.

## Provenance

| item | value |
|------|-------|
| Assigned strategy | `volatility_scaling` |
| Source | `src/cryptobot/strategies/catalog/volatility_scaling.py` (`VolScalingStrategy`, `name = "vol_scaling"`) |
| Data | `load_universe("data/nse")` — 48 symbols, 4,625 daily bars, 2008-01-01 → 2026-10-01 |
| Cleaning | 274,541 rows in → 208,226 out; dropped pre-2008 66,312, extreme 3; excluded `adanient`, `jiofin` |
| TRAIN | 2016-01-01 → 2023-12-31 |
| TEST | 2024-01-01 → 2026-10-01 |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| **Cost charged by `run_backtest`** | **`all_in_round_trip_bps(100_000)` = 21.92 bps** (11.92 statutory + 2 × 5 slippage) |
| Engine | `nsealgo.backtest.engine`, **`engine_sha = 970713f3eecf`** |
| Run date | 2026-10-10 |

> ⚠️ **Survivorship bias is present and uncorrected.** The NIFTY-50 panel is today's
> constituents backfilled to 2008. Every number inherits that bias. Quote with the
> end date attached.

> ⚠️ **Engine note.** The engine was fixed today (dead positions decayed slowly
> instead of exiting). Results here are produced by `engine_sha 970713f3eecf`; a number
> from an earlier engine is not comparable and this report does not use one.

## What the strategy actually does

`VolScalingStrategy.signal(closes, highs, lows, volumes)`:

```python
b = atr(highs, lows, closes, self.config.period)          # SMA of last `period` true ranges
if b != b:                                                # NaN warmup guard
    return 0
if b / max(closes[-1], 1e-9) > self.config.min_vol and closes[-1] > closes[-2]:
    return 1
if b / max(closes[-1], 1e-9) > self.config.min_vol and closes[-1] < closes[-2]:
    return -1
return 0
```

Defaults: `period=14`, `min_vol=0.001`.

Read literally this is a **high-volatility gate plus a one-bar direction test**:

- **gate:** `ATR(14)/close > min_vol`, i.e. the name is in a high-volatility regime.
- **direction:** `close[t] > close[t-1]` → `+1`, `<` → `-1`.

So the flag says "this name is volatile *and* it moved up today". The name
"volatility_scaling" is misleading: nothing here scales a position by volatility. It is
a binary volatility **filter** applied to a 1-bar momentum reading. `build_rebalance_weights`
does the only volatility scaling in this system, and it is applied to every strategy
equally (so it cannot be what distinguishes this one).

## DECLARED PARAMETER BUDGET — 5 variants, declared before any backtest ran

Written down first, per `AGENT_BRIEF.md` §4. Only TRAIN results are used to select; the
winner is frozen to `frozen.txt` and then evaluated once on TEST.

| # | name | `period` | `min_vol` | gate | direction test | ranking among flagged |
|---|------|---------|-----------|------|----------------|------------------------|
| V1 | `V1_shipped_mom126` | 14 | 0.001 (shipped) | `NATR>0.1%` | yes (1-bar) | 126d momentum |
| V2 | `V2_shipped_lowvol` | 14 | 0.001 (shipped) | `NATR>0.1%` | yes (1-bar) | −60d realised vol |
| V3 | `V3_gate_p50_mom126` | 14 | **TRAIN p50 NATR** | live gate | yes (1-bar) | 126d momentum |
| V4 | `V4_gateonly_mom126` | 14 | TRAIN p50 NATR | live gate | **no** — gate alone | 126d momentum |
| V5 | `V5_gate_p25_mom126` | 14 | **TRAIN p25 NATR** | live gate | yes (1-bar) | 126d momentum |

Held constant: monthly rebalance; `PortfolioConfig()` defaults (22 target / 30 max names,
12% single name, 25% sector, 10% cash, 35% turnover budget, 60d vol lookback);
`CostModel(segment="delivery", slippage_bps=5)`.

**V1 is the honest default**: it is what the shipped code does with shipped parameters.
V3/V5 exist because the shipped `min_vol=0.001` is tested for liveness in §1 — if the
gate is dead on NSE then V1 is a pure 1-bar momentum strategy and the strategy is not
really a volatility strategy at all. That is a property of the strategy to be *reported*,
not a defect to tune away.

Selection rule, fixed in advance: **highest TRAIN Sharpe**, tie-break Calmar. No
threshold is adjusted after seeing an equity curve.

## Results

### §1 The shipped `min_vol=0.001` gate is dead code on NSE

Verified mechanically that my vector reproduces the shipped class exactly — the real
`VolScalingStrategy` was run on 300 synthetic bars and its output compared bar-for-bar
against the vector, at four different `(period, min_vol)` settings so that neither
parameter can be quietly hard-coded:

| period | min_vol | bars matching |
|--------|---------|---------------|
| 14 | 0.001 | 260 / 260 |
| 14 | 0.020 | 260 / 260 |
| 5 | 0.010 | 260 / 260 |
| 20 | 0.030 | 260 / 260 |

Also confirmed ATR is an **SMA of the last 14 true ranges**, not Wilder's smoothing —
`rolling(14).mean()` equals the manual mean of the same 14 bars on 41/41 listed symbols.
That matters because Wilder ATR is ~1.5–2× larger than SMA ATR at the same period, so
getting this wrong would silently move every threshold.

**NATR(14) = ATR(14)/close on NSE, by set:**

| set | n name-days | min | p5 | p25 | **p50** | p75 | p95 | max |
|---|---|---|---|---|---|---|---|---|
| TRAIN | 91,246 | 0.959% | 1.547% | 2.032% | **2.528%** | 3.211% | 4.667% | 25.760% |
| TEST | 32,818 | 0.897% | 1.427% | 1.825% | **2.178%** | 2.646% | 3.624% | 10.150% |

The shipped threshold is `min_vol = 0.001` = **0.1%**. The *minimum* NATR ever observed
on NSE is 0.897% — **9× the shipped threshold**. So the gate is not merely loose, it is
unreachable-as-a-filter:

| `min_vol` | TRAIN name-days passing | TEST name-days passing |
|---|---|---|
| **0.100% (shipped)** | **96.35%** | **99.96%** |
| 1.5% | 92.60% | 92.76% |
| 2.0% | 73.85% | 62.32% |
| 2.5% | 49.49% | 31.54% |
| 3.0% | 30.10% | 13.82% |
| 4.0% | 9.78% | 2.84% |

**Consequence: as shipped, `volatility_scaling` is not a volatility strategy.** With the
gate passing 96–100% of name-days, `signal()` collapses to a pure one-bar direction
read — `+1` if the stock rose today, `0`/`-1` otherwise. The volatility component
contributes nothing. This is the single most important structural fact about the
strategy on this market, and it is a property of the shipped code, not of my
construction.

Note the second structural hazard: TEST volatility is **lower** than TRAIN (p50 2.18% vs
2.53%). Any threshold fixed on TRAIN admits systematically *fewer* names out of sample —
2.5% passes 49.5% of TRAIN but only 31.5% of TEST. A TRAIN-fitted gate is a different
rule in TEST.

### §2 Signal liveness (fraction of name-days flagged long)

| variant | TRAIN | TEST |
|---|---|---|
| shipped `min_vol=0.001`, 1-bar direction | 49.21% | 49.52% |
| `min_vol=0.001`, gate only | 96.35% | 99.96% |
| `min_vol=p50`, gate only | 48.17% | 30.24% |
| `min_vol=p50` + 1-bar direction | 23.90% | 14.95% |
| `min_vol=p25` + 1-bar direction | 36.34% | 29.57% |

All variants clear the 5% "effectively always-flat" floor from `AGENT_BRIEF.md` §6.3,
so none of them is disqualified for being dead. Mean flagged names per monthly
rebalance: shipped 23.6, p25 17.4, p50 11.5.

### §3 TRAIN (2016-01-01 → 2023-12-31) — the selection set

```
label                   set      CAGR%  Sharpe   MaxDD%  Calmar  Turn/y  Cost/y%  Names   Total%   Yr+
V1_shipped_mom126       TRAIN    10.40    0.40   -20.58    0.51    4.06     0.24   19.1    122.5    88%
V2_shipped_lowvol       TRAIN     9.38    0.33   -21.30    0.44    4.07     0.23   19.3    106.4    88%
V3_gate_p50_mom126      TRAIN    12.48    0.57   -12.81    0.97    3.94     0.26   11.4    158.8   100%
V4_gateonly_mom126      TRAIN    15.88    0.65   -32.48    0.49    3.79     0.27   17.7    229.3    88%
V5_gate_p25_mom126      TRAIN    10.50    0.40   -20.17    0.52    4.07     0.23   16.2    124.2    75%
TRAIN_buy_and_hold      TRAIN    21.49    0.90   -36.66    0.59    0.12     0.13   46.3    382.8   100%

SELECTED: V4_gateonly_mom126  (Sharpe 0.65, Calmar 0.49)
FROZEN:   {'min_vol': 0.025284, 'ranking': 'mom126', 'period': 14, 'use_direction': False}
```

Three things visible on TRAIN and flagged, not acted on:

1. **The winner is the variant that DELETED the strategy's own signal.** V4 drops the
   1-bar direction test and keeps only the volatility gate; the other four keep both.
   Whatever V4 achieves on TRAIN is therefore attributable to the *ranking* (126d
   momentum), not to `volatility_scaling`'s own contribution.
2. **The volatility gate helps once it is calibrated to actually bind.** V1 (shipped,
   gate dead) 10.40% → V3 (gate at TRAIN p50) 12.48% → V4 (gate alone) 15.88%.
3. **Every variant loses to buy-and-hold on TRAIN** (by 5.6–12.1pp/yr).

TRAIN numbers are selection-set numbers. They are shown only so the TEST result can be
audited.

### §4 ⚠️ Harness bug I found and fixed — it nearly doubled the apparent TEST result

My first TEST run reported **11.56% CAGR vs 8.18% buy-and-hold, "+3.38 pp/yr"**. That
number was wrong, and the give-away was that TRAIN and TEST printed an *identical*
MaxDD of −32.48%.

Cause: I had the engine run over `[WARMUP, end]` so that 126d momentum was warm, but
then computed metrics over the **whole** curve. For the TEST run that curve began
2015-01-01, so the "TEST" CAGR was annualised across 11.75 years including all of
TRAIN, and the drawdown was measured from a pre-TEST peak.

Fix (now in `harness.run_on`): run the book over `[WARMUP, end]`, then slice returns to
`[start, end]` and recompute CAGR/Sharpe/MaxDD/Calmar/turnover/cost-drag on the eval
window only. Two things make the sliced numbers trustworthy rather than merely
convenient:

- **Turnover reconciles exactly.** Reconstructing per-date turnover from held weights
  gives `3.7827120156`/yr — identical to the engine's own `annual_turnover` on the full
  span. So the slicing is not silently changing the trade schedule.
- **The selection is stable.** I re-ran the whole TRAIN sweep after the fix. V4 wins on
  Sharpe under both the buggy and the corrected metrics, so the *choice* was not
  contaminated — only the reported TEST magnitudes were.

**The corrected TEST result loses to buy-and-hold.** Had I not caught this, this report
would have claimed a validated edge that does not exist. Recording it here because the
same class of bug is easy to repeat: any agent that runs the engine with warmup bars and
then reports the un-sliced metrics is reporting in-sample performance under a TEST label.

### §5 TEST (2024-01-01 → 2026-10-01) — the reportable number

Frozen variant `V4_gateonly_mom126`, evaluated once, unchanged.

```
label                   set      CAGR%  Sharpe   MaxDD%  Calmar  Turn/y  Cost/y%  Names   Total%   Yr+
V4_gateonly_mom126      TEST      7.42    0.13   -14.55    0.51    3.79     0.61   16.2     22.2    33%
TEST_buy_and_hold       TEST      8.18    0.18   -15.90    0.51    0.36     0.10   48.0     24.6    67%
V4_gateonly_mom126      TRAIN    15.88    0.65   -32.48    0.49    3.79     0.27   17.7    229.3    88%
TRAIN_buy_and_hold      TRAIN    21.49    0.90   -36.66    0.59    0.12     0.13   46.3    382.8   100%

TEST vs buy-and-hold:
  CAGR    7.42%  vs  8.18%   ->  -0.75 pp/yr      (LOSES)
  Sharpe  0.13   vs  0.18    ->  -0.05            (LOSES)
  MaxDD  -14.55%  vs -15.90%  ->  shallower by 1.35 pp   (only metric it wins)
  Calmar  0.51   vs  0.51    ->  tie
  cost/y  0.61%  vs  0.10%
  names   16.2   vs  48.0

Calendar-year returns, TEST only:
  strategy : 2024 +25.10%, 2025 -2.14%, 2026 -0.15%   (1 of 3 years positive)
  buy&hold : 2024 +20.13%, 2025 +13.35%, 2026 -8.47%   (2 of 3 years positive)
```

**Gross vs net on the TEST window:**

| | gross (0 bps) | net (21.92 bps) | drag |
|---|---|---|---|
| CAGR | 8.24% | **7.42%** | 0.82 pp/yr |
| Sharpe | 0.20 | **0.13** | — |
| MaxDD | −14.19% | −14.55% | — |

This is the whole story in one table. **Gross of costs the strategy does 8.24% against
buy-and-hold's 8.18% — a statistical dead heat, i.e. no gross alpha at all.** The 21.92
bps stack on 3.79x/yr turnover then takes 0.82pp/yr, which is what turns "equal" into
"behind". The strategy is not a failed signal that costs killed; it is a signal that
never had anything to say, paying 0.61%/yr to say it.

**Sanity checks (`AGENT_BRIEF.md` §6):**

| check | result |
|---|---|
| Plausibility (≤40–50% CAGR unlevered) | ✅ 7.42% — no lookahead smell |
| Weight count (≈22, not 48) | ✅ 16.2 names avg; `avg_top_weight` 6.57% (inside the 12% cap) |
| Signal liveness (>5% long) | ✅ 30.2% of TEST name-days flagged |
| Cost drag reported | ✅ 0.82 pp/yr gross→net; 0.61%/yr steady-state |
| Random-signal control | see §6 |

### §6 Controls

**Random-signal control** (40 draws, identical construction, same 30.24% TEST liveness
as the strategy — measured on TEST, not on the full panel):

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| strategy | **7.42%** | **0.13** | −14.55% |
| random mean | 1.59% | −0.62 | −10.92% |
| random median | 1.66% | −0.59 | |
| random p10 / p90 | −0.39% / 3.18% | | |
| random max | 7.77% | | |

Strategy beat **39/40** random draws on CAGR and 39/40 on Sharpe; one-sided
Mann-Whitney **p < 0.0001**. **The volatility gate does carry information that a coin
flip does not.** That is a real, positive finding and it is worth stating plainly.

**nsealgo composite**, identical panel and window: CAGR **7.61%**, Sharpe 0.14,
MaxDD −15.22%, 21.8 names. Strategy **loses by 0.18 pp/yr** and Sharpe 0.13 vs 0.14 —
i.e. indistinguishable from the existing composite, and fractionally behind it.

**Ablation — is the gate doing the work?** Removing the volatility filter and running
plain 126d momentum on the whole universe:

| | CAGR | Sharpe | MaxDD | names |
|---|---|---|---|---|
| no gate, plain 126d momentum | 3.14% | −0.18 | −18.82% | 21.8 |
| with volatility gate | **7.42%** | **0.13** | −14.55% | 16.2 |

The gate is worth **+4.28 pp/yr and +0.31 Sharpe**, and it deepens the return but
*shallows* the drawdown by 4.3pp. This is the strongest evidence in the report that the
strategy's core idea is sound — it just isn't strong enough to clear the bar.

**Statistical significance of the headline gap.** Strategy minus buy-and-hold, paired
daily returns over the 684 TEST days:

- mean excess **−0.420 bps/day**, stdev 41.79 bps/day
- **t = −0.26, two-sided p = 0.793**, 95% CI **[−3.55, +2.71] bps/day**
- strategy beat buy-and-hold on **exactly 50.0%** of TEST days

The TEST gap is **statistically indistinguishable from zero**. The honest reading is not
"it loses by 0.75pp" but "it is indistinguishable from holding the index, while paying
0.61%/yr in costs and taking a 16.6pp-deeper book than a 22-name maximum allows it to
avoid".

### §7 GOAL.md Gate 4 concentration — two hard fails

| Gate 4 check | measured | result |
|---|---|---|
| No single **stock** > 20% of total P&L | top name `eternal` = **23.3%** | ❌ **FAIL** |
| No single **year** > 35% of total P&L | 2024 = **110.1%** | ❌ **FAIL** |
| Cost-adjusted edge must survive turnover | survives (beats random) | ✅ pass |
| ≥ 4 of 6 neighbouring settings profitable | see disclosure below | ❌ fail |

Contribution profile over TEST (45 names with non-zero contribution):
top 1 = 23.3%, top 3 = 45.5%, top 5 = 59.8%, top 10 = **87.7%**. The best name
contributes +6.07pp and the worst −3.04pp. Ten of forty-five names carry nearly the
whole result. The 2024 figure exceeds 100% because 2025 and 2026 were both negative —
the entire TEST return is one calendar year, which is precisely the failure mode Gate 4
exists to catch.

### §8 Post-hoc disclosure — all five variants on TEST

**Not used for selection.** V4 was frozen before TEST was opened and the verdict was
fixed before these were run. Reported because V4 *deleted* the strategy's own direction
test, so a reader is entitled to see how the shipped configuration actually behaves.
These are four further looks at TEST and should be read as disclosure, not evidence.

| variant | TRAIN Sharpe | **TEST CAGR** | TEST Sharpe | TEST MaxDD | names |
|---|---|---|---|---|---|
| V1_shipped_mom126 (shipped defaults) | 0.40 | 4.35% | −0.16 | −12.37% | 19.1 |
| V2_shipped_lowvol | 0.33 | 5.02% | −0.14 | −12.38% | 19.3 |
| V3_gate_p50_mom126 | 0.57 | 3.57% | −0.24 | −11.93% | 10.3 |
| **V4_gateonly_mom126 (frozen)** | **0.65** | **7.42%** | **0.13** | −14.55% | 16.2 |
| V5_gate_p25_mom126 | 0.40 | 2.53% | −0.36 | −11.57% | 15.5 |
| *buy-and-hold* | *0.90* | *8.18%* | *0.18* | *−15.90%* | *48.0* |

**Every variant degrades out of sample, and four of five have a negative TEST Sharpe.**
TRAIN Sharpe 0.33–0.65 collapses to −0.36…+0.13. The TRAIN→TEST Sharpe rank correlation
across the five variants is **Spearman ρ = +0.21 (p = 0.74)** — i.e. *no* reliable
relationship. V4 happened to be best on TRAIN and best on TEST, but with n = 5 that
agreement is not evidence that selection works; V3 ranked 2nd on TRAIN and 4th on TEST.
The honest statement is that selecting on TRAIN bought nothing here: the ordering did
not carry over. A threshold fitted on TRAIN volatility is the wrong threshold in TEST,
exactly as §1 predicted — TEST NATR p50 is 2.18% against TRAIN's 2.53%.

**Not one variant, including the shipped configuration, beats buy-and-hold.**

---

## VERDICT

**No. `volatility_scaling` does not make money on NSE NIFTY-50.**

On the held-out TEST window (2024-01-01 → 2026-10-01, 684 bars), net of the full Indian
delivery stack at 21.92 bps, the frozen variant returned **7.42% CAGR / 0.13 Sharpe
against buy-and-hold's 8.18% / 0.18**. It is behind on return by 0.75pp/yr, behind on
Sharpe, exactly tied on Calmar, and ahead only on MaxDD by 1.35pp. The gap is **not
statistically significant (p = 0.793)** — it neither beats nor meaningfully loses the
benchmark. It is also behind the existing nsealgo composite by 0.18pp/yr, and it fails
two of `GOAL.md`'s Gate 4 concentration checks.

**Most likely reason it fails:** the strategy has a *real but small and already-priced*
signal, wrapped in a construction that spends 0.61%/yr to harvest it. Gross of costs it
returns 8.24% against buy-and-hold's 8.18% — a dead heat, i.e. **no gross alpha at
all**; the entire deficit is the 21.92 bps stack applied to 3.79x/yr turnover. Meanwhile
the volatility gate that gives the strategy its identity is calibrated to TRAIN
volatility and is the wrong threshold out of sample, because TEST volatility is 14%
lower (NATR p50 2.18% vs 2.53%).

**The one thing I would try next — not a threshold tweak.** The ablation is the clue:
plain 126d momentum returns 3.14% (Sharpe −0.18); adding the volatility gate takes it to
7.42% (Sharpe 0.13). Volatility conditioning on momentum is doing real work and is the
only part of this strategy that survives contact with a random control. The failure is
*how* it is traded, not *what* it knows. Specifically:

1. **Drop the monthly rebalance for a slower one.** 3.79x/yr turnover against a monthly
   strategy is high, and it costs 0.82pp/yr of a 8.24% gross return. Holding the
   high-volatility cohort quarterly, and only rotating when a name *leaves* the cohort,
   should recover a large share of that 0.82pp without touching the signal.
2. **Drop the momentum ranking, or make the gate the entire signal.** V4 won by deleting
   the direction test; the surviving signal is "high NATR", which is a *risk* attribute,
   not an alpha one. Ranking that cohort by momentum re-introduces the project's
   existing momentum factor and explains why V4 lands within 0.18pp of the composite —
   V4 may be little more than the composite with extra costs.
3. **Re-anchor the threshold to a trailing, self-updating percentile** rather than a
   TRAIN-fitted constant, so a regime change in volatility does not silently invert the
   rule — the exact failure that took TRAIN Sharpe 0.65 down to TEST 0.13.

I would not try more `min_vol` values on this TEST window. That would be fitting to the
holdout, and §6's whole point is that this strategy's apparent TRAIN edge is already
mostly noise.

---

## Reproduction

```bash
cd research/agent_volscaling
../../.venv/bin/python step0_audit.py        # data audit, source-signal verification, gate liveness
../../.venv/bin/python step1_train.py        # 5 declared variants on TRAIN -> frozen.txt
../../.venv/bin/python step2_test.py         # frozen variant on TEST, once
../../.venv/bin/python step3_controls.py     # random control, composite, no-gate ablation
../../.venv/bin/python step4_significance.py # significance, Gate 4 concentration, disclosure
```

Files: `harness.py`, `step0_audit.py`, `step1_train.py`, `step2_test.py`,
`step3_controls.py`, `step4_significance.py`, `frozen.txt`, `REPORT.md`.
Lint: `.venv/bin/ruff check research/agent_volscaling/` → clean.

### Protocol compliance

| rule (`AGENT_BRIEF.md`) | status |
|---|---|
| Parameter budget declared before running | ✅ 5 variants, §"DECLARED PARAMETER BUDGET" |
| ≤ 5 variants tested | ✅ exactly 5 |
| Parameters chosen on TRAIN only | ✅ thresholds = TRAIN p25/p50 of NATR14 |
| TEST touched once, at the end | ✅ `step2_test.py`; §8 disclosure is flagged as 4 further looks |
| No lookahead | ✅ all factors trailing; engine shifts held weights one bar |
| Costs mandatory (21.92 bps via `run_backtest`) | ✅ gross/net both reported |
| Buy-and-hold over identical window | ✅ 8.18% CAGR |
| Random-signal control | ✅ 39/40, p < 0.0001 |
| Composite comparison | ✅ loses by 0.18pp/yr |
| `engine_sha` recorded | ✅ `970713f3eecf` |
| Scratch confined to `research/agent_volscaling/` | ✅ no edits to `src/` or tests |
| Not committed | ✅ nothing committed |

### Reproducibility note — a concurrent edit to `loader.py` mid-session

At **06:29:23**, partway through this run, another agent modified
`src/nsealgo/data/loader.py` to add a **C9 rule** (drop frozen closes — runs of repeated
consecutive closes from a stalled vendor feed). My step-0 audit had run at ~06:27,
*before* that edit; every headline number was produced *after* it. The engine docstring
warns that exactly this has silently corrupted results in this project before, so it is
worth stating what happened rather than hoping.

I re-ran `step0_audit.py` under the modified loader and compared:

- **Panel shape unchanged**: 4,625 × 48, 2008-01-01 → 2026-10-01, both before and after.
- **Every NATR percentile identical to four decimals** — TRAIN p25 2.032%, p50 2.528%;
  TEST p50 2.178%. So the thresholds declared in this report re-derive identically, and
  the declaration was not invalidated by the edit.
- **Gate-liveness table and every TEST metric byte-identical.**
- C9 removed 539 per-symbol rows (274,541 → 207,687), but these are *intra-symbol*
  repeats of dates already present in the wide panel, so no calendar date disappeared.

Conclusion: the edit did **not** affect any number in this report. Had it changed the
panel, the declared TRAIN thresholds would have needed re-deriving — which would have
been a re-tune after the fact, and I would have reported the run as compromised rather
than quietly refreshing the numbers.

`engine_sha 970713f3eecf` is unchanged from the first run to the last.

### Known limitations of this report

- **Survivorship bias is uncorrected.** Today's NIFTY-50 backfilled to 2008. `eternal`
  (a 2021 IPO) is both the largest single contributor (+6.07pp) and 23.3% of the result;
  under a point-in-time universe the TEST book would have differed materially.
- **TEST is 2.75 years.** 684 bars is short for a Sharpe estimate. This is why the
  p = 0.793 non-result should be read as "no evidence of an edge", not as "evidence of
  no edge".
- **The verdict rests on V4, not on the shipped configuration.** V4 won selection, but it
  discarded the strategy's direction test, so it measures "volatility gate + momentum
  ranking" more than it measures `volatility_scaling`. §8 gives the shipped variant's
  TEST number (4.35% CAGR, Sharpe −0.16) for that reason; if you want the shipped
  configuration to be the *declared* subject, it must be declared as such before TEST is
  opened, which it was not.
- **Warmup-window choice affects early weights.** I build the book from 2015-01-01 and
  report on the eval window only; slicing the panel to the eval window instead (as the
  prior `agent_voltarget` harness does) starts the book part-cash and would change
  numbers slightly. My choice is documented and the turnover reconciliation proves the
  trade schedule is internally consistent.