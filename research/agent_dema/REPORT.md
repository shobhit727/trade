# agent_dema — `DemaStrategy` on NSE NIFTY-50

**Status: COMPLETE — verified, reproduced, negative result.**

---

## ⚠️ PROTOCOL DISCLOSURE — read this before any number below

**The TEST window (2024-01-01 → 2026-10-01) has already been read.**

A previous, interrupted run of this agent completed *all three* stages and left its
artifacts on disk (`sweep_train.py`, `train_results.json`, `selected.json`,
`evaluate_test.py`, `test_results.json`, `test_run.log`). It then died before writing
this report. The TEST numbers were therefore already on disk when this session
started.

What that means, stated precisely:

| Question | Answer |
|----------|--------|
| Was the variant selected using TEST? | **No.** `selected.json` (V1) was written by `sweep_train.py`, which only ever loads `panel.loc[TRAIN_START:TRAIN_END]` as its price window and prints "TEST … has NOT been touched". Selection used best TRAIN Sharpe. |
| How many times was TEST evaluated? | **Once**, by `evaluate_test.py`, on the already-frozen V1. |
| Did anything get re-tuned after seeing TEST? | **No.** No code in the repo re-selects after TEST; `evaluate_test.py` reads `selected.json` and does not write it. |
| Has this session changed the strategy, parameters, or harness? | **No.** This session's job is *verification*, not iteration. No parameter variant has been added. |

**I am therefore treating TEST as spent.** I will not change the variant, the period,
the book construction, or the score form in response to anything I see on TEST. What
this session does:

1. Independently re-verify the DEMA implementation (exactness vs the crypto reference,
   no-lookahead, liveness).
2. Independently re-run the TRAIN sweep and the TEST evaluation and confirm the prior
   run's numbers **reproduce bit-for-bit**. Non-reproducible scratch work gets thrown.
3. Audit the harness for the failure modes the brief names (§6.1–6.5).
4. Post-mortem the result honestly — including the possibility that the prior run was
   wrong.

A residual caveat I cannot remove: this session's author (me) has now seen the TEST
outcome before doing any of my own verification. If verification had turned up a
harness bug, fixing it and re-running would have been contaminated by that knowledge.
**I checked for that specifically** — see §Verification log — and no code change was
needed, so the TEST result stands as a single clean evaluation. Had I found a bug, I
would have said so loudly rather than re-running.

---

## 1. Assignment

| Field | Value |
|-------|-------|
| Strategy | `DemaStrategy` (`src/cryptobot/strategies/catalog/dema_strategy.py`) |
| Class / `name` | `DemaStrategy` / `"dema"` |
| Signal | `+1 if close[-1] > DEMA(close, period) else -1` (0 during warmup) |
| Free parameters | **one**: `period` (`DemaConfig.period`, default 20). `quantity` is unused by the signal. |
| Crypto-specific? | **No.** A double-exponential moving average is a plain price-trend filter. It has direct meaning on NSE daily bars, so the brief's §9 "no NSE meaning → stop" clause does not apply. Proceeding. |

Indicator definition used (replicated from `cryptobot.strategies.indicators.dema`):
`DEMA = 2·EMA₁ − EMA(EMA₁, period)`, `k = 2/(period+1)`, EMA recursion seeded at the
first valid close.

## 2. Data

| Item | Value |
|------|-------|
| Source | `data/nse/<symbol>_1d.csv`, via `nsealgo.data.loader.load_universe("data/nse")` |
| Timeframe | `1d` only (brief §2: intraday is banned) |
| Symbols | 48 after cleaning (loader drops pre-2008 vendor artifacts) |
| Bars | 2008-01-01 → 2026-10-01 |
| Price used | cleaned **close** panel |
| Survivorship bias | **present** — today's NIFTY-50 backfilled. Disclosed on every result. |
| Forward-fill | interior gaps only, forward-filled **from the past** (brief §4.6). Leading NaNs (pre-listing) left as NaN so no price is fabricated. |

## 3. Split

| Set | Window | Bars | Purpose |
|-----|--------|------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | ~1,950 | everything tuned on |
| **TEST** | 2024-01-01 → 2026-10-01 | 685 (2.81y) | evaluated **once**, after selection froze |

## 4. PARAMETER BUDGET — 5 declared variants (the maximum allowed)

Declared in `PLAN.md` **before** the prior run executed. Re-declared here unchanged.
The strategy has exactly one knob (`period`); V5 exists to test whether that knob is
doing anything at all or whether the momentum overlay is silently carrying the result.

| # | `period` | cross-sectional score | role |
|---|----------|----------------------|------|
| V1 | 20 (catalog default) | DEMA>0 gate, then rank survivors by 126d momentum | candidate |
| V2 | 50 | DEMA>0 gate, then rank by 126d momentum | candidate |
| V3 | 100 | DEMA>0 gate, then rank by 126d momentum | candidate |
| V4 | 200 | DEMA>0 gate, then rank by 126d momentum | candidate |
| V5 | 20 | **pure DEMA**: rank by `close/DEMA − 1`, no momentum overlay | **control, not selectable** |

Fixed, not tuned, identical in every run:
rebalance = monthly (`"M"`); `PortfolioConfig(n_positions=22)` with engine defaults
(12% single name, 25% sector, 10% cash, 0.35 turnover budget, `max_names=30`);
`CostModel(segment="delivery", slippage_bps=5)`; momentum lookback 126d
(`nsealgo.factors.core.momentum_6m`).

**Selection rule, fixed in advance:** best TRAIN Sharpe, ties broken by best TRAIN
MaxDD. Then that one variant, unchanged, on TEST.

**Budget consumed: 5 of 5. No sixth variant will be run.** Any post-hoc diagnostic
below is labelled *diagnostic* and is never selectable.

## 5. Cost convention

Every result below is net of **21.92 bps of turnover** — what `run_backtest` actually
charges (`all_in_round_trip_bps(100_000)` = 11.92 statutory + 2 × 5 bps slippage,
because the engine folds slippage into the round trip). 11.92 is quoted only where
`CostModel` is called directly. The two are never mixed.

---

## 6. Verification log

The prior run's artifacts were treated as untrusted. Every claim below was recomputed
from scratch by this session.

| # | Check | Result |
|---|-------|--------|
| 1 | Cost model sanity (`.venv/bin/python -m nsealgo.cli costs`) | 11.92 bps round trip at ₹1,00,000 — matches published reference 11.65–11.66. ✅ |
| 2 | DEMA **exactness** vs `cryptobot.strategies.indicators.dema`, 5 periods × 240 stratified bars | **1,200 comparisons, max relative error 0.000e+00** (bit-identical). ✅ |
| 3 | DEMA **no-lookahead** vs truncated-history reference, 2 periods × 3 symbols × 3 dates | all 18 rel diffs `0.0e+00`. ✅ |
| 4 | Seed washout at the TRAIN start | 7.19e-08 — the EMA seed cannot influence any traded bar. ✅ |
| 5 | DEMA liveness | finite on 93.7% of cells (rest is pre-listing). ✅ |
| 6 | Re-run TRAIN sweep | **bit-identical** to `train_results.PRIOR.json`; independently re-selected **V1**. ✅ |
| 7 | Re-run TEST evaluation | **bit-identical** to `test_results.PRIOR.json` and to the full stdout log. ✅ |
| 8 | Independent recomputation of every headline metric vs the prior run | all reconcile to `1e-12`. ✅ |
| 9 | Audit script self-review | **two bugs found in my own audit and fixed before use** — see §9.1. |
| 10 | `ruff check research/agent_dema/*.py` | All checks passed. |

I changed **no** parameter, no score form, and no engine call. The TEST result is a
single clean evaluation and stands.

## 7. Sanity checks (brief §6), recomputed from scratch

| Check | Value | Verdict |
|-------|-------|---------|
| §6.1 plausibility | CAGR 6.86% | ✅ far below the 40–50% unlevered ceiling |
| §6.2 weight count | avg 28.6 names; **peak 30 on any single day** | ✅ the `max_names=30` cap holds; no residual-accretion bug. The >22 average is the turnover-budget blend tail, not accumulation |
| §6.2 weight caps | mean top weight 0.0577, max single name 0.0819 | ✅ under the 0.12 cap |
| §6.3 signal liveness | **48.7%** of name-days long | ✅ far above the ~5% floor — not an always-flat strategy |
| §6.4 cost drag | 1.10%/y on 4.10x/y turnover, 21.92 bps rt | ✅ net CAGR is positive, so **costs are not what kills this** |
| §6.5 negative control | 200 seeds — see §9 | ❌ **FAILS** |

## 8. The headline result

### TEST (out-of-sample, 2024-01-01 → 2026-10-01, 685 bars / 2.81y)
Net of the full Indian delivery stack, **21.92 bps** of turnover.

| Book | CAGR | Sharpe | MaxDD | Calmar | Total ret | Turnover | Cost drag | Avg names |
|------|------|--------|-------|--------|-----------|----------|-----------|-----------|
| **DEMA V1 (p=20)** | **6.86%** | **0.087** | **−12.88%** | **0.53** | **+20.5%** | 4.10×/y | 1.10%/y | 28.6 |
| buy & hold (equal-weight) | 8.21% | 0.185 | −15.91% | 0.52 | +24.8% | 0.36×/y | 0.04%/y | 48 |
| nsealgo composite | 6.55% | 0.070 | −14.84% | 0.44 | +19.5% | 2.07×/y | 0.55%/y | — |

### TEST vs buy-and-hold

| Metric | DEMA V1 | buy & hold | Delta | |
|--------|---------|-----------|-------|---|
| CAGR | 6.86% | 8.21% | **−1.35 pp** | ❌ **worse** |
| Sharpe | 0.087 | 0.185 | **−0.098** | ❌ **worse** |
| MaxDD | −12.88% | −15.91% | **+3.03 pp** | ✅ better drawdown control |
| Calmar | 0.53 | 0.52 | +0.01 | ➖ a wash |

**Verdict on the comparison: worse on return, better on drawdown, net neutral.** This
is not a hidden win dressed up — on return it lost.

Yearly (TEST):

| Year | buy & hold | DEMA V1 | alpha |
|------|-----------|---------|-------|
| 2024 | +20.13% | +18.14% | −2.00 pp |
| 2025 | +13.34% | +10.89% | −2.44 pp |
| 2026 | −8.26% | −8.04% | **+0.21 pp** |

The one year it won was the only down year. It earned its keep by losing less in a
bear tape, not by compounding.

### TRAIN vs TEST decay

| | TRAIN (2016–2023) | TEST (2024–2026) |
|---|---|---|
| DEMA V1 CAGR | 17.49% | 6.86% |
| DEMA V1 Sharpe | 0.903 | 0.087 |
| DEMA V1 MaxDD | −14.01% | −12.88% |
| buy & hold CAGR | **22.19%** | **8.21%** |
| buy & hold Sharpe | **0.907** | 0.185 |

Sharpe decayed **−0.82**; CAGR **−10.63 pp**. See §10 — the decay is the whole story,
and it started on TRAIN.

## 9. Controls

### 9.1 My own audit script had two bugs — found and fixed before use

Recording these because a silently-wrong audit is worse than no audit.

1. **0.0% overlap.** I compared `set(np.flatnonzero(...))` (integer positions) against
   `set(series.index[:22])` (string symbol labels). The intersection is *structurally*
   always empty. Printed a clean-looking "0.0% overlap with ungated momentum" and would
   have supported a dramatic conclusion. Fixed by mapping labels to positions.
2. **A ratio above 100%.** `mean fraction of eligible names held = 141%` is impossible
   and was a modelling error on my part: the held book carries a turnover-blend residual
   tail, so `len(held)` can exceed `len(eligible)`. Replaced with a proper attribution
   (what fraction of the eligible set the book took; what fraction of the held book sits
   below the DEMA).

Both were caught because the numbers were impossible, not because a test failed.
Neither affected the reported backtest numbers — these were in diagnostic code only.

### 9.2 Random-signal control — **the control FAILS**

200 seeds, coin flipped per (day, name), gated to the strategy's own 48.7% long
fraction, ranked by a second random draw so the engine's top-22 pick isn't biased by
column order.

| | value |
|---|---|
| random Sharpe | mean **−0.056**, sd 0.128, min −0.387, **max +0.344** |
| random CAGR | mean +5.28%, min +1.61%, max +9.90% |
| random MaxDD | mean −13.47%, worst −18.89% |
| **DEMA V1 Sharpe** | **+0.087** |
| seeds beaten | 172/200 (86.0%) |
| one-sided empirical p | **0.861 — not significant** |
| z-score | +1.12 |
| best single random seed | **+0.344 — beats the strategy outright** |

**This is the most damaging result in the report.** The brief's §6.5 says "beating a
coin flip is the minimum bar." A single lucky random seed beat the strategy by 4× its
Sharpe. The strategy is not distinguishable from random name selection.

The prior run used 20 seeds and reported "beats 13/20 (65%), z = +0.60" — which reads
as weak-but-present. With 200 seeds the picture is unambiguous. (The prior run's number
was not wrong; 20 seeds was simply too few to resolve the question.)

### 9.3 nsealgo composite

DEMA V1 beat it marginally: CAGR +0.31 pp, Sharpe +0.017, MaxDD +1.96 pp. Both are well
below buy-and-hold, so "beat the composite" here means beating a weaker comparator, not
having an edge. The project's own reversal-based **negative control** (CAGR 7.04%,
Sharpe 0.10) also edged out DEMA V1 — a control intended to *underperform* out-earning
the strategy is a strong hint that the TEST window's ranking is noise.

### 9.4 Cost stress (GOAL.md Gate 4)

| Scenario | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| zero cost (gross) | 7.30% | 0.117 | −12.72% |
| base (21.92 bps) | 6.86% | 0.087 | −12.88% |
| double slippage | 6.42% | 0.052 | −13.03% |
| triple slippage | 5.99% | 0.017 | −13.18% |

Costs cost ~0.44 pp of CAGR over the window. Costs are **not** the reason this fails —
even at zero cost the strategy still trails buy-and-hold. It stays net-positive under
all four, so it is "viable" in the narrow sense of not being cost-viable — but it is
not *competitive*.

## 10. Why it failed — the real reason

Three findings, in descending order of importance.

### 10.1 On TRAIN, buy-and-hold already beat every single variant

| | TRAIN Sharpe | TRAIN CAGR | TRAIN MaxDD |
|---|---|---|---|
| **buy & hold** | **0.907** | **22.19%** | −37.97% |
| best variant (V1) | 0.903 | 17.49% | **−14.01%** |
| worst variant (V4) | 0.588 | 14.44% | −30.79% |

The prior run's selection rule was "best TRAIN Sharpe among the variants" — and it
picked V1 at 0.903. Buy-and-hold scored 0.907 on the same window. **The selection was a
coin flip between V1 and doing nothing**, and the rule never compared the variants to
the benchmark at all. The benchmark was printed at the top of the log and ignored.

The variants *did* do something real: V1 cut TRAIN drawdown from −37.97% to −14.01%,
a 24 pp improvement. So the strategy is not a no-op — it is a **drawdown-reducing,
return-lagging** construction. On TRAIN the return lag was large (17.49% vs 22.19%) and
it was paid for with much better risk control. On TEST the market rose, so the return
lag was all that remained while the drawdown benefit shrank to +3.03 pp (TEST was a
mild, shallow drawdown for buy-and-hold anyway).

That is the actual failure mode: **a defensive construction run in a rising tape.**

### 10.2 The DEMA period is not a real signal

TRAIN Sharpe decayed monotonically with period — 20:0.90 → 50:0.74 → 100:0.63 →
200:0.59 — which looks like a clean, believable finding. On TEST the ordering *reverses
in magnitude and crosses zero*: V1 +0.087, V2 −0.161, V3 −0.311, V4 −0.392.

Monotone in-sample, scrambled out-of-sample. The period ranking is noise wearing the
costume of a parameter. **Longer periods are strictly worse on both windows** — that
direction is consistent — but the 20-vs-50 gap that looked meaningful on TRAIN is not.

### 10.3 The DEMA itself carries no information the momentum overlay didn't

V5 (pure DEMA, no momentum overlay) vs V1 (DEMA gate + momentum) on TEST:
Sharpe −0.008 vs +0.087; CAGR +5.74% vs +6.86%. Indistinguishable. The ablation
(diagnostics, not selectable) isolates the gate cleanly:

| Window | Gated V1 | Ungated momentum-6m | Gate contributes |
|--------|----------|---------------------|------------------|
| TRAIN | Sharpe 0.903, CAGR 17.49% | Sharpe 0.778, CAGR 18.38% | +0.13 Sharpe, **+20.9 pp MaxDD** |
| TEST | Sharpe 0.087, CAGR 6.86% | Sharpe −0.223, CAGR 2.60% | **+0.31 Sharpe, +4.25 pp CAGR, +4.0 pp MaxDD** |

The gate *does* real work — it is not a no-op. Holdings overlap ungated-momentum top-22
only **55–58%**, it is the binding constraint on ~40% of monthly rebalances, and it
adds +0.31 Sharpe on TEST. So "the DEMA is decorative" would be wrong.

But notice what it actually buys: **drawdown insurance**, again. The entire DEMA
contribution in both windows is risk reduction. And it is the *gate*, not the *period*,
that supplies it — V5 (pure DEMA distance, no gate) is flat against V1.

Also worth recording: **34.8% of the held book's names were below their own DEMA on a
typical TEST rebalance**, carried by the 0.35 turnover budget's blend tail. The engine
cannot exit a name the gate has invalidated inside one rebalance. So the realised gate
is meaningfully weaker than the score panel suggests — a harness characteristic that
would apply to any gated strategy, not specific to DEMA.

### 10.4 The one thing I got wrong as the agent

I should have made "beat the TRAIN benchmark" an explicit gate in the selection rule,
not just "maximise TRAIN Sharpe among variants." The prior run printed the benchmark and
did not use it. If a variant cannot beat buy-and-hold on TRAIN, no amount of TEST
evaluation can rescue it, and the run should have been declared negative at the TRAIN
stage — saving the entire TEST evaluation.

## 11. Verdict

**Does `DemaStrategy` make money on NSE NIFTY-50 out-of-sample? No.**

It made **+6.86% CAGR / Sharpe 0.087** net of full costs on TEST — positive, but
*worse than simply holding the index* (+8.21% / 0.185) on return, better only on
drawdown (−12.88% vs −15.91%). It does not beat a coin flip (p = 0.861 against 200
random seeds; the luckiest single seed beat it 4×). It loses to buy-and-hold on TRAIN
too, once you look. It survives costs at every stress level, so costs are not the
explanation.

This is a publishable negative result and it generalises: **a gated trend filter over a
momentum overlay is a risk-management overlay, not an alpha source.** It reliably
truncates drawdowns and reliably gives up return. In a rising, low-drawdown window —
which is exactly 2024–2026 — it is the wrong tool.

### The one thing I would try next

Not more period tuning — §10.2 shows that axis is noise. The evidence says the useful
half of this strategy is the **drawdown overlay**, so the next test is whether that
overlay has standalone value: keep the DEMA gate, drop the momentum ranking entirely
(V5's construction, but explicitly re-run under the *ranking-by-momentum* vs
*equal-weight-among-eligible* contrast), and re-test on a **fresh, never-touched holdout
that does not exist in this dataset** — the data ends 2026-10-01, so this needs new
Kite history. Until a genuinely unseen window exists, the honest status of every number
in §8 is "suggestive at best".

Second, cheaper, and available now: **the harness should gate variant selection on
beating buy-and-hold on TRAIN**, not on beating the other variants. Five of the fifty
agents running this brief will hit this exact trap, and it is the single highest-value
fix to the shared methodology.

## 12. Artifacts

| File | Contents |
|------|----------|
| `REPORT.md` | this document |
| `PLAN.md` | parameter budget declared before the prior run executed |
| `dema_lib.py` | DEMA panel + score forms + benchmarks (prior run) |
| `verify_dema.py` | exactness / no-lookahead / liveness proof — **all pass** |
| `sweep_train.py` | TRAIN sweep over the 5 declared variants |
| `evaluate_test.py` | single TEST evaluation of the frozen selection |
| `audit.py` | **this session** — independent audit, ablation, beta, 200-seed control |
| `variant_diagnostic.py` | **this session** — all 5 variants on both windows (diagnostic) |
| `train_results.json` / `.PRIOR.json` | current vs prior run — bit-identical |
| `test_results.json` / `.PRIOR.json` | current vs prior run — bit-identical |
| `audit.log`, `variant_diagnostic.log`, `test_run.VERIFY.log` | full stdout |
| `audit.json`, `all_variants.json` | machine-readable results |

**Not committed, per brief §9.** No file under `src/nsealgo/**`, `src/cryptobot/**`, or
any test file was modified. `ruff check research/agent_dema/*.py` → clean.
