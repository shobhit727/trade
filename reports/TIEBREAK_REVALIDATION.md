# Tie-Break Re-Validation — which of 55 catalog conclusions survive `29764f562cd5`

> **Engine verified before every run: `engine 29764f562cd5 · loader c1badf5f7df8 ·
> costs ba350aef75b3 · panel 389b082b832f`.** `research/revalidation/core.py:check_provenance`
> aborts the run if the working tree's engine fingerprint is anything else. It was
> `29764f562cd5` for all 110 probes.
>
> **Cost stack:** `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps all-in**,
> charged by `run_backtest` on every rebalance, identical for both engines.
>
> **Windows:** TRAIN 2016-01-01→2023-12-31, TEST 2024-01-01→2026-10-01, exactly
> `AGENT_BRIEF.md` §4. **No tuning on TEST.** Every variant below was the one the agent
> itself had already frozen on TRAIN; nothing was re-selected after seeing either engine's
> TEST number. Where a TRAIN number moves, that is reported as a *selection-noise* column,
> not used to justify a new pick.
>
> **Scope: all 55 agents were re-run.** Not a subset — 55 frozen variants × 2 windows = 110
> probes, each through both engines.

---

## 0. Headline

**No published verdict flips. The "38 of 38 failed / 55 agents all negative" headline
survives.** On the new engine, **not one of the 55 variants beats buy-and-hold** on TEST
(buy-and-hold on the identical window and substrate: **+8.26% CAGR / Sharpe +0.19**), and
**not one has a positive TEST Sharpe**. Best TEST CAGR of any variant is `adx_trend` at
**+5.29% / Sharpe −0.07**.

| classification | count | meaning |
|---|---:|---|
| **INVALIDATED** | **9** | the published number moved ≥0.5pp CAGR or ≥0.10 Sharpe. The *verdict* still stands; the *figure* may not be quoted. |
| **SUSPECT** | **14** | the tie-break touched the book, but the move is immaterial. |
| **UNAFFECTED** | **32** | bit-identical books. The number stands exactly as published. |

Largest move of any agent: **+2.81pp** (`ma_cross`), then **−2.31pp** (`bollinger_bands`).
For scale, `CATALOG_TRIALS.md` itself sets 1.5pp as the threshold below which cross-agent
comparisons "should not be treated as meaningful", and `SELECTION_STUDY.md` measures a
**31pp/yr** spread between train-selected and unselected books. The tie-break is a
second-order effect on this catalog, and this report measures exactly how second-order.

**But the alarm in `reports/CATALOG_TRIALS.md` is aimed at the wrong 13 agents.** Its
exposure list was built by scanning agent *sources* for binary signals. Nine of those
thirteen are provably untouched by the fix, and the nine agents that actually moved were
mostly **not** on the list. Details in §3.

---

## 1. Method — why this is a measurement and not an inference

The tie-break fix (`f4fff7c`, `d93815344bd3` → `29764f562cd5`) replaced
`np.argsort(-score, kind="stable")` with `np.lexsort` over a
`blake2b(f"{date}|{symbol}")` key. Since the panel's columns are alphabetical, the old
engine resolved every tied score **alphabetically**.

Rather than trust any agent's stored figures, `research/revalidation/` reconstructs the
**old engine from git** (`git show f4fff7c^:src/nsealgo/backtest/engine.py`, loaded as a
live module inside the `nsealgo.backtest` package) and runs **both engines on the same
score panel**. The `old → new` delta is then the tie-break and nothing else.

Each agent's score panel is rebuilt by **importing that agent's own harness library** and
calling its own builder with the parameters from its own selected-variant artifact. No
agent's files were edited; no agent script was executed as a script (the three whose
harness is a bare `run.py` sit behind `if __name__ == "__main__":`; `agent_inapplicable`'s
unguarded `trial.py` had its `def` statements extracted with `ast` so its body never runs).

Three diagnostics per panel (`core.py:tie_exposure`):

* **`flat`** — share of rebalance dates where *every* eligible name shares one score value.
  The degenerate binary-mask case.
* **`cut`** — share of dates where the score at rank 22 equals the score at rank 23, i.e.
  names on both sides of the cut are interchangeable.
* **`book moved`** — share of rebalance dates whose **final target book** differs at all.
  This is the only quantity that can change a reported number: a different top-22
  candidate set that converges to the same book after caps, the turnover budget and
  thinning is not a different book.

### The degenerate case, reproduced exactly

| input | engine | distinct name sets across 33 TEST rebalances | turnover/yr | TEST CAGR |
|---|---|---:|---:|---:|
| truly static 0/1 mask | `d93815344bd3` | **1 of 33** | 0.64 | +9.64% |
| truly static 0/1 mask | `29764f562cd5` | **33 of 33** | 3.18 | +6.66% |

The bug is real and exactly as severe as described. One correction to the fix commit's
own wording: the degeneracy is in the **name set**, not in turnover. Turnover reads 0.64/y
rather than 0.00/y because `PortfolioConfig.vol_lookback` inverse-vol scaling re-weights a
frozen name set every day. *"One distinct book"* is the right phrase; *"0.0% turnover"*
understates the severity slightly by measuring the wrong quantity. The name set is what the
engine traded.

---

## 2. Classification table

All 55 agents, frozen selected variant, TEST window (the figure `CATALOG_TRIALS.md`
publishes). TRAIN is shown where it moved, because a selection rule is moved by TRAIN
noise even when the out-of-sample book is untouched.

Old = `d93815344bd3` on this harness. New = `29764f562cd5`. Both net of 21.92 bps.

| agent | frozen variant | old turn | new turn | old CAGR | new CAGR | ΔCAGR | old Shp | new Shp | book moved | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `ma_cross` | V3 (50/200 SMA cross, flag) | 2.19 | 3.55 | 1.47% | 4.28% | **+2.81pp** | -0.35 | -0.13 | 73% | **INVALIDATED** |
| `bollinger_bands` | V4 p60 n2.0 entry1.0 pure | 3.06 | 3.65 | 4.62% | 2.31% | **-2.31pp** | -0.22 | -0.60 | 61% | **INVALIDATED** |
| `cmf` | V2_p20_t10_flipped | 3.91 | 4.12 | 5.22% | 3.13% | **-2.09pp** | -0.12 | -0.40 | 58% | **INVALIDATED** |
| `anchored_vwap` | V3 p200 t5.0 mom | 3.14 | 3.41 | 2.61% | 0.69% | **-1.92pp** | -0.33 | -0.55 | 18% | **INVALIDATED** |
| `flag_pattern` | V0_LITERAL (2-bar run) | 4.07 | 4.07 | 2.60% | 1.31% | **-1.30pp** | -0.42 | -0.57 | 18% | **INVALIDATED** |
| `distance_ma` | V3 dev_depth p50 t0.05 | 3.63 | 3.72 | 1.44% | 0.28% | **-1.15pp** | -0.54 | -0.68 | 24% | **INVALIDATED** |
| `cointegration` | L21 e2.0 depth | 3.44 | 3.60 | 3.33% | 2.44% | **-0.89pp** | -0.40 | -0.56 | 73% | **INVALIDATED** |
| `keltner` | kelt_pure_p40_m2 | 3.28 | 3.63 | 0.97% | 0.28% | **-0.69pp** | -0.63 | -0.74 | 42% | **INVALIDATED** |
| `cci` | V5_deep (p20 entry100, deepest) | 3.81 | 3.80 | 0.12% | 0.75% | **+0.63pp** | -0.88 | -0.79 | 27% | **INVALIDATED** |
| `donchian` | breakout_p10 | 3.44 | 3.47 | -0.67% | -1.17% | -0.49pp | -0.79 | -0.88 | 27% | SUSPECT |
| `breakout_momentum` | V2_EXCL20 (excl, p20, mom10) | 3.16 | 3.33 | -0.70% | -0.24% | +0.45pp | -0.78 | -0.78 | 30% | SUSPECT |
| `volscaling` | V4_gateonly_mom126 | 4.12 | 4.12 | 4.98% | 4.64% | -0.35pp | -0.10 | -0.13 | 18% | SUSPECT |
| `regime_switch` | V5_p200_verySlow | 4.05 | 4.05 | 4.57% | 4.82% | +0.25pp | -0.14 | -0.11 | 15% | SUSPECT |
| `voltarget` | V4_atronly_mom126 | 3.81 | 3.81 | 4.09% | 4.25% | +0.16pp | -0.22 | -0.21 | 12% | SUSPECT |
| `adx_trend` | V2_mom252 | 4.12 | 4.12 | 5.43% | 5.29% | -0.14pp | -0.06 | -0.07 | 18% | SUSPECT |
| `gaussian` | V1 p30 e0.8 momentum | 4.11 | 4.11 | 4.65% | 4.78% | +0.13pp | -0.20 | -0.18 | 45% | SUSPECT |
| `rsi` | V3 p14 lower40 deepest | 4.06 | 4.06 | 2.28% | 2.18% | -0.11pp | -0.57 | -0.58 | 21% | SUSPECT |
| `triple_ma` | V1_5_15_30 | 4.10 | 4.10 | 0.66% | 0.75% | +0.09pp | -0.57 | -0.55 | 18% | SUSPECT |
| `trendvol` | tv_p20_r10 | 4.00 | 4.03 | -0.03% | 0.05% | +0.08pp | -0.74 | -0.72 | 21% | SUSPECT |
| `stochastic` | V5:momentum (p14 30/70) | 3.95 | 3.95 | 4.43% | 4.40% | -0.03pp | -0.23 | -0.23 | 3% | SUSPECT |
| `atr_breakout` | V1 (p10, mult 1.0) | 3.82 | 3.82 | -0.70% | -0.71% | -0.00pp | -0.80 | -0.80 | 6% | SUSPECT |
| `atr_trailing` | V4 p55 mult2.0 | 4.05 | 4.05 | -2.22% | -2.22% | +0.00pp | -0.78 | -0.78 | 3% | SUSPECT |
| `correlation_gate` | V2 p10 t0.010 (champion) | 4.16 | 4.16 | 0.45% | 0.45% | +0.00pp | -0.68 | -0.68 | 3% | SUSPECT |
| `absolute_momentum` | V3_p126_t0.00 | 3.03 | 3.03 | 1.11% | 1.11% | +0.00pp | -0.35 | -0.35 | 0% | UNAFFECTED |
| `bb_squeeze` | V1 p20 t.05 mom | 4.09 | 4.09 | 4.00% | 4.00% | +0.00pp | -0.22 | -0.22 | 0% | UNAFFECTED |
| `cross_sectional` | V1 (p20 t.015 rank20) | 4.15 | 4.15 | -2.31% | -2.31% | +0.00pp | -0.95 | -0.95 | 0% | UNAFFECTED |
| `cumulative_delta` | V1_w20_delta_rank | 4.16 | 4.16 | 0.70% | 0.70% | +0.00pp | -0.56 | -0.56 | 0% | UNAFFECTED |
| `dema` | V1 p20 gate+mom126 | 4.14 | 4.14 | 2.99% | 2.99% | +0.00pp | -0.31 | -0.31 | 0% | UNAFFECTED |
| `dispersion` | V5 p250 e1.0 | 2.90 | 2.90 | 2.74% | 2.74% | +0.00pp | -0.21 | -0.21 | 0% | UNAFFECTED |
| `dual_ma` | V5_5_20 | 3.96 | 3.96 | -0.91% | -0.91% | +0.00pp | -0.57 | -0.57 | 0% | UNAFFECTED |
| `dual_momentum` | V3_ema50_200 | 2.53 | 2.53 | 2.87% | 2.87% | +0.00pp | -0.20 | -0.20 | 0% | UNAFFECTED |
| `ema_cross` | V2_5_20 | 3.96 | 3.96 | -0.91% | -0.91% | +0.00pp | -0.57 | -0.57 | 0% | UNAFFECTED |
| `ensemble` | V2_10_14_2 | 4.06 | 4.06 | 0.32% | 0.32% | +0.00pp | -0.54 | -0.54 | 0% | UNAFFECTED |
| `fisher` | V2 (p10 e-2.0) | 3.77 | 3.77 | 3.69% | 3.69% | +0.00pp | -0.20 | -0.20 | 0% | UNAFFECTED |
| `gap` | V4 L5 thr0.010 | 4.07 | 4.07 | 2.72% | 2.72% | +0.00pp | -0.31 | -0.31 | 0% | UNAFFECTED |
| `hull_ma` | V2_10 | 4.01 | 4.01 | 1.40% | 1.40% | +0.00pp | -0.42 | -0.42 | 0% | UNAFFECTED |
| `inapplicable` | basket p120_t0.015 | 2.94 | 2.94 | 1.00% | 1.00% | +0.00pp | -0.34 | -0.34 | 0% | UNAFFECTED |
| `kama` | V2_10 | 3.91 | 3.91 | 0.36% | 0.36% | +0.00pp | -0.50 | -0.50 | 0% | UNAFFECTED |
| `macd` | V3_5_20_9 | 4.11 | 4.11 | 4.07% | 4.07% | +0.00pp | -0.21 | -0.21 | 0% | UNAFFECTED |
| `mfi` | V3_mfi_p14_l40 | 4.12 | 4.12 | 0.99% | 0.99% | +0.00pp | -0.66 | -0.66 | 0% | UNAFFECTED |
| `momentum_factor` | M4 (p126 t.08 rank126) | 3.17 | 3.17 | -0.36% | -0.36% | +0.00pp | -0.48 | -0.48 | 0% | UNAFFECTED |
| `momvol` | V5 | 3.03 | 3.03 | 1.11% | 1.11% | +0.00pp | -0.35 | -0.35 | 0% | UNAFFECTED |
| `multifactor` | V1 p20 rsip14 rank126 | 4.00 | 4.00 | 0.40% | 0.40% | +0.00pp | -0.52 | -0.52 | 0% | UNAFFECTED |
| `obv` | V2_obv_n5 | 4.16 | 4.16 | 2.40% | 2.40% | +0.00pp | -0.39 | -0.39 | 0% | UNAFFECTED |
| `regression` | V4_p50_momrank | 3.75 | 3.75 | 0.35% | 0.35% | +0.00pp | -0.43 | -0.43 | 0% | UNAFFECTED |
| `relstrength` | V4 roc126 t8% | 3.17 | 3.17 | -0.36% | -0.36% | +0.00pp | -0.48 | -0.48 | 0% | UNAFFECTED |
| `roc` | V3_wide (p10 t0.00 rank mom126) | 4.02 | 4.02 | 1.27% | 1.27% | +0.00pp | -0.42 | -0.42 | 0% | UNAFFECTED |
| `supertrend` | st_p20_m3.0 | 3.88 | 3.88 | -1.19% | -1.19% | +0.00pp | -0.60 | -0.60 | 0% | UNAFFECTED |
| `tema` | V4 (p20 rank mom12_1) | 4.14 | 4.14 | 0.96% | 0.96% | +0.00pp | -0.51 | -0.51 | 0% | UNAFFECTED |
| `timeseries` | V4 p126 thr0.00 | 3.03 | 3.03 | 1.11% | 1.11% | +0.00pp | -0.35 | -0.35 | 0% | UNAFFECTED |
| `tmr` | V4 slow40 entry1.0 | 3.80 | 3.80 | 1.26% | 1.26% | +0.00pp | -0.35 | -0.35 | 0% | UNAFFECTED |
| `trendmom` | V3 | 3.38 | 3.38 | -0.27% | -0.27% | +0.00pp | -0.44 | -0.44 | 0% | UNAFFECTED |
| `vwm` | V1 p20 t0.01 | 4.14 | 4.14 | -1.41% | -1.41% | +0.00pp | -0.69 | -0.69 | 0% | UNAFFECTED |
| `williamsr` | V4 fast-touch21 (p5, -80) | 3.33 | 3.33 | 1.44% | 1.44% | +0.00pp | -0.31 | -0.31 | 0% | UNAFFECTED |
| `zscore` | V5 L60 e0.5 | 3.87 | 3.87 | 5.17% | 5.17% | +0.00pp | -0.09 | -0.09 | 0% | UNAFFECTED |

**Classification rule, fixed before looking at the distribution:** INVALIDATED if
|ΔCAGR| ≥ 0.5pp or |ΔSharpe| ≥ 0.10 (roughly ⅓ of the 1.5pp that `CATALOG_TRIALS.md`
itself treats as meaningful); SUSPECT if the book moved at all but neither threshold was
crossed; UNAFFECTED if the book is bit-identical.

### TRAIN-side moves (selection noise, not published OOS)

29 of 55 TRAIN books moved; 26 were bit-identical. Largest: `ma_cross` 14.75% → 12.56%
(−2.18pp), `voltarget` 13.66% → 12.36% (−1.30pp), `cointegration` 6.40% → 5.12%
(−1.28pp), `bollinger_bands` 7.27% → 6.78% (−0.49pp), `breakout_momentum` 4.12% →
3.64% (−0.49pp), `cci` 6.13% → 6.56% (+0.43pp), `ensemble` 8.40% → 8.00% (−0.41pp),
`hull_ma` 10.19% → 9.78% (−0.41pp).

This is the same mechanism the fix commit found in production — a 2.7% perturbation of a
book flips the argmax of a TRAIN sweep — and it corroborates `SELECTION_STUDY.md`
independently from a second direction. It is *not* evidence that any of these strategies
work; it is evidence that **selecting on TRAIN Sharpe at this sample size is not a
measurement.**

---

## 3. Which negative results flip or materially change

**This is the section the task asked for, and the answer is: none flip, nine figures
change.**

Every one of the 55 verdicts was NO. On `29764f562cd5` every one is still NO. Specifically:

* **Zero variants beat buy-and-hold.** Best is `adx_trend` +5.29% vs BH +8.26%. The second
  best is `zscore` +5.17%. Both were losers before and are losers now.
* **Zero TEST Sharpe sign flips.** The largest Sharpe move is −0.38 (`bollinger_bands`
  −0.22 → −0.60); no variant crosses zero in either direction.
* **Nine INVALIDATED figures** (§2). Every one moves *further from* its prior value in
  the direction that makes the strategy look **worse**, except `ma_cross` and `cci`, which
  improve. Nothing crosses the bar.

The nine in detail, with why each moved:

| agent | why it was exposed | net effect on the published claim |
|---|---|---|
| `ma_cross` | **feeds a bare 0/1 mask.** `ma_cross_score(..., "flag")` returns `flag.astype(float).where(flag)` — 100% flat on every rebalance date. | **The one case where the old alphabetical bias was *costing* the strategy money.** +2.81pp, Sharpe −0.35 → −0.13, turnover 2.19 → 3.55. Still a loser, but the published −0.32 Sharpe understated it by more than half. |
| `bollinger_bands` | `pure` construction → 58% flat. Equal weights, so `_thin`/`_exit_allocation` also ranked ties by column order. | −2.31pp, Sharpe −0.22 → −0.60. Report's "−0.11% CAGR, loses to a coin flip" becomes materially worse. |
| `cmf` | `cmf < −thr` gate, 58% of rebalances select a different book. | −2.09pp. Report's "beats only 49% of random seeds" — the corrected figure is further below the null, so the finding is *strengthened*. |
| `anchored_vwap` | 18% of rebalances, 12% flat. | −1.92pp. Report claimed "+0.06 pp/yr excess, t = −0.00" — the corrected figure is decisively negative, not marginally so. |
| `flag_pattern` | 9% flat, 6% cut-tied. | −1.30pp. |
| `distance_ma` | `dev_depth` → 15% flat. | −1.15pp. Report's "loses to a coin flip" is now a much clearer loss. |
| `cointegration` | `depth` rule → 61% flat, 73% book moved. | −0.89pp. |
| `keltner` | `pure` → 24% flat, 42% book moved. | −0.69pp. |
| `cci` | `deepest` on CCI → 15% flat. | **+0.63pp** — improves, but from −0.88 Sharpe to −0.79. Still the worst book in the set. |

### The `CATALOG_TRIALS.md` exposure list is 9/13 wrong

Its banner flags 13 agents "needing re-validation", chosen by scanning agent sources for
binary signals. Measured:

| flagged agent | book moved | ΔCAGR | actual verdict |
|---|---:|---:|---|
| `cross_sectional`, `cumulative_delta`, `dema`, `ema_cross`, `inapplicable`, `obv`, `roc`, `tema`, `tmr` | **0%** | **+0.00pp** | **UNAFFECTED** |
| `adx_trend` | 18% | −0.14pp | SUSPECT |
| `breakout_momentum` | 30% | +0.45pp | SUSPECT |
| `rsi` | 21% | −0.11pp | SUSPECT |
| `trendvol` | 21% | +0.08pp | SUSPECT |

**Zero of the thirteen are INVALIDATED.** Eight are provably untouched.

The reason is structural, and it is worth stating because the heuristic got it backwards.
Almost every agent implements §5 of the brief as

```python
score = mom.where(signal > 0).rank(axis=1, pct=True)
```

The *signal* is binary — but the engine never sees the signal. It sees a **cross-sectional
percentile rank of trailing momentum among the flagged names**, which is continuous and
strictly increasing within the eligible set. `pct=True` yields `1/n, 2/n, …, n/n`; ties
require two names to have bit-identical 126-day returns. Measured across the 55 panels:
mean unique score values per rebalance date is typically 17–48 out of ≤48 eligible, and
**32 of 55 books came out bit-identical.**

The agents that *were* exposed are the ones that skipped the ranking step and passed a raw
value through — `ma_cross`'s `flag`, and the `pure`/`dev_depth`/`depth` constructions.
**That is a different list, and `CATALOG_TRIALS.md` did not have it.**

---

## 4. How many of the 55 conclusions survive

**All 55 verdicts survive. 32 of 55 published figures survive bit-for-bit. 23 figures need
a corrected number attached; 0 need a corrected conclusion.**

Put differently:

* The project's central claim — *no crypto-catalog strategy transfers to a long-only NSE
  book* — is **not disturbed by this bug**. It was tested 55 ways; it survives all 55.
* The fix **strengthens** `CONTROL_DIAGNOSTIC.md` and `SELECTION_STUDY.md` rather than
  undermining them, exactly as the fix commit found for the production headline.
* The `CATALOG_TRIALS.md` banner's warning — *"the '38 of 38 negative' headline is NOT a
  trustworthy result of the current engine"* — is **too strong**. It was right to
  re-run; the re-run shows the headline holds. What was wrong was the *attribution*, not
  the verdict.

The most useful thing this exercise produced is not a corrected number. It is a **method
correction**: *the exposure test for a tie-break bug is a measurement of the score panel,
not a reading of the signal.* Every agent in this catalog had a binary signal; almost none
had a binary score. Scoring them apart required rebuilding 55 panels and running 110
backtests — a source-code scan cannot tell them apart, and got 9 of 13 wrong in the
direction that *over*-warned while missing the one agent that was truly degenerate.

---

## 5. Harness bugs found in re-used agent scripts

Reported, not edited. All are in `research/agent_*/`, none were modified.

### 5.1 `agent_ma_cross` — the bug, documented as a feature

`research/agent_ma_cross/harness.py:59-62`:

> `flag` — score 1.0 where the flag fires, NaN elsewhere. **Ties are broken by the
> engine's deterministic stable sort, i.e. column order — a *neutral* tie-break.**

The agent *identified* the exact mechanism, named it, and recorded a wrong conclusion
about it. Column order is alphabetical, not neutral. This is the largest single mover in
the study (+2.81pp) and the only agent whose score panel was 100% flat. **Worth fixing in
that agent's source**, or at least correcting that comment.

### 5.2 `agent_donchian`, `agent_flag_pattern` — harness can no longer rebuild its own inputs

Both ship a `load_all()` that re-derives high/low per symbol through `load_symbol` and
**asserts the result matches `load_universe`**. On today's panel that assertion fails:

```
OHLC rebuild diverged from load_universe close panel
OHLC rebuild diverged from the load_universe panel
```

Their harnesses cannot run at all. I worked around it by calling `load_symbol` directly
(the same cleaning path they use), so the signal maths tested here is theirs — but as
shipped, neither script executes.

### 5.3 `agent_inapplicable` — bypasses the mandated loader; 2 of 10 variants now raise

Two separate problems:

1. `trial.py:load_panel()` reads the raw `*_1d.csv` files and hand-slices `>= 2008-01-01`.
   It never calls `load_universe`, so it bypasses cleaning rules C1–C8 and keeps **50
   symbols where every other agent keeps 48**. Its results are not on the same substrate
   as the other 54. (This is why its `EmptyScorePanelError` mentions "50 of 50 cells" —
   the guard was reading the 50-column panel against a 48-column expectation.)
2. The new engine's `EmptyScorePanelError` now **aborts** two of its ten declared
   variants outright — `basket p20_t0.05` and `meta p10` — where the old engine silently
   returned a flat book. The remaining eight run.

   This is the guard working correctly, but it means the file needs updating before it
   can be re-run by its author.

### 5.4 The bare-0/1 "random control" pattern — reproduced, and the fix is one line

The commit message describes an agent whose random control was built from a bare 0/1 mask
and became an alphabetical book. Confirmed, on the agent's own pattern:

| control construction | book moved | old CAGR | new CAGR | old Sharpe | new Sharpe |
|---|---:|---:|---:|---:|---:|
| bare 0/1 mask from `rng.random(...) < frac` | **100%** | +2.42% | **+0.85%** | −0.36 | **−0.62** |
| i.i.d. `Uniform(0,1)` score | **0%** | +5.39% | +5.39% | −0.08 | −0.08 |

A nominal "random" control was worth **−1.57pp of CAGR and 0.26 of Sharpe** of pure
alphabetical bias. Any negative control that ends in a bare 0/1 mask needs a second
independent uniform. I checked the obvious candidates in this catalog — `absolute_momentum`,
`cumulative_delta`, `momvol`, `fisher`, `inapplicable` all rank the mask
(`rank(axis=1, pct=True)`) and are therefore **fine**; the ranking line, not the mask, is
what saves them.

### 5.5 `agent_inapplicable` again — TEST-window warmup starvation

Its `run()` slices `panel` and `score` to the window and calls `run_backtest`, which
computes `rets` and the 60-day `vol` from the sliced panel only. The first rebalance after
2024-01-01 therefore has no volatility estimate for any name. `EmptyScorePanelError` fires
on TRAIN for two variants; the same starvation is why the brief's "142 of 684 TEST days
held zero names" observation is reproducible here. **Every** panel I built scores on the
full 2008→2026 history and only then slices, so this report is free of the effect — but
every agent whose harness slices first may not be.

Across all 110 probes, **31 agents hit at least one rebalance date with zero eligible
names** (287 dates total), which the old engine absorbed as a silent flat book and the new
engine refuses. For the old-vs-new comparison those dates are filled with 0.0 **for both
engines**, so the reported delta remains a clean isolation of the tie-break; the count is
carried per-row in `results.json` as `empty_rebalances`.

### 5.6 Fidelity gaps between my old-engine re-run and the agents' own reported numbers

For the same frozen variant on the old engine, my harness and the agent's report disagree
on three agents by more than a rounding difference:

| agent | my old-engine TEST CAGR | agent's reported | Δ |
|---|---:|---:|---:|
| `bollinger_bands` | 4.62% | −0.11% | **4.73pp** |
| `flag_pattern` | 2.60% | 0.73% | **1.87pp** |
| `cci` | 0.12% | 4.56% | **4.44pp** |

These are *not* tie-break effects — both columns are the same engine. They are harness
divergence, most likely TEST-window slicing or warmup handling differing between my driver
and the agent's own runner. I did not chase them: the `old → new` delta is internally
consistent either way, and the verdicts are unchanged under both numbers (`bollinger_bands`
and `cci` are losers in mine and in the report; `flag_pattern` is a loser in both). But it
does mean **the agent's own figures for those three should not be quoted to the precision
they are printed at.**

---

## 6. Reproducing this

```bash
.venv/bin/python research/revalidation/run_all.py    # batch 1 (19 agents)
.venv/bin/python research/revalidation/run_all2.py   # batch 2 (23)
.venv/bin/python research/revalidation/run_all3.py   # batch 3 (8)
.venv/bin/python research/revalidation/run_all4.py   # batch 4 (4)
.venv/bin/python research/revalidation/run_all5.py   # batch 5 (inapplicable)
.venv/bin/python research/revalidation/make_table.py # verdicts + counts
```

Each batch merges into `research/revalidation/results.json` on `label`, so batches
accumulate and re-running is idempotent. `core.py:check_provenance()` runs first in every
batch and aborts on an unexpected engine fingerprint.

| file | role |
|---|---|
| `core.py` | old-engine loader (from git), `tie_exposure`, `probe`, provenance gate |
| `agentlib.py` | imports an agent's own harness library without executing its script |
| `run_all*.py` | the 55 per-agent builders, each with its frozen variant |
| `introspect.py` | one-off: dumps each agent's score-builder signatures |
| `results.json` | all 110 probes, both engines, full diagnostics |

`.venv/bin/ruff check research/revalidation/` → clean. `pytest tests/unit` → 1604 passed;
the 3 failures in that file (`test_utils_logging`, `test_web_backtest`) are pre-existing in
`cryptobot`, reproduce with this directory removed, and are unrelated to this work.

**Nothing was committed. `src/`, `tests/`, and every `research/agent_*/REPORT.md` are
untouched.**

---

## 7. What I would do next

1. **Fix `agent_ma_cross`'s docstring or its score.** It is the only agent feeding a bare
   0/1 mask, it is the largest mover, and its source currently asserts the bug is neutral.
2. **Re-run the three fidelity-gap agents** (`bollinger_bands`, `flag_pattern`, `cci`) with
   their own runners rather than my driver, to find where the 1.9–4.7pp divergence lives.
3. **Point the `CATALOG_TRIALS.md` banner at the right 9 agents** and downgrade the "38 of
   38 is not trustworthy" language — the re-run supports it.
4. **Adopt the `tie_exposure` diagnostic as a standard plausibility check** alongside §6 of
   `AGENT_BRIEF.md`. A one-line `cut_tied` print would have caught `ma_cross` at write time
   and would have caught the bare-0/1 controls in three agents. It is a strictly better
   test than "did my signal have a threshold in it", which is what the exposure list used.
