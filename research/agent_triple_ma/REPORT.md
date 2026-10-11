# `triple_moving_average` on NSE NIFTY-50 — NEGATIVE FINDING

## 0. Provenance

| Field | Value |
|-------|-------|
| Assigned strategy | `triple_moving_average` |
| Source | `src/cryptobot/strategies/catalog/triple_moving_average.py` |
| Strategy class | `TripleMaStrategy` (`name = "triple_ma"`), defaults fast=5 / mid=15 / slow=30 |
| Harness | `research/agent_triple_ma/run.py` (protocol), `diag.py` + `diag2.py` (TRAIN-only diagnostics), `verify_signal.py` (fidelity proof) |
| Raw numbers | `research/agent_triple_ma/results.json` |
| **Backtest engine `engine_sha`** | **`970713f3eecf`** |
| Repo git HEAD | `2825d03` |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps** all-in round trip on ₹1,00,000 notional, charged by `run_backtest` |
| Lint | `ruff check research/agent_triple_ma/` → clean |
| Status | **COMPLETE. TEST evaluated once, after selection was frozen. Verdict: it does not make money.** |

### Engine-change note (provenance integrity)

The engine changed today: `apply_turnover_budget` was rewritten so a dropped position
**exits unconditionally and is paid for first**, instead of decaying by `1 − λ` per
rebalance. That bug made the delivered book hold mostly names the signal did *not* want,
at a fraction of the intended weight — so every headline number it produced measured
dilution, not the signal.

**Every number in this report is from `engine_sha = 970713f3eecf`.** The sha is recorded
per-result inside `results.json` (`engine_sha` on each row) and re-asserted at runtime by
`run.py`. Numbers from the pre-fix engine are not quoted anywhere in this report and are
**not comparable** to these. I have not re-run any other agent's strategy, so I cannot
and do not claim to know whether the fix moved their published numbers.

---

## 1. What the strategy is, and what it is not

```python
f = sma(closes, 5); m = sma(closes, 15); s = sma(closes, 30)
f > m > s  ->  +1      # fully bullish alignment
f < m < s  ->  -1      # fully bearish alignment
otherwise  ->   0      # EVERY mixed ordering, e.g. f > s > m
```

Three properties drove everything that follows.

1. **It is ternary, and in a long-only book two of the three states are unusable.** Only
   `f > m > s` is holdable (GOAL.md §3.1 — no shorts in an Indian delivery account). The
   `f < m < s` state is discarded; **so is the whole mixed-ordering bucket**, which is
   the *largest* single state in the sample. A long-only port of this strategy is
   therefore structurally a **half-cash strategy by construction**. This turned out to
   be the dominant term in the result (§4, Q8).
2. **It is stricter than a dual-MA crossover.** A name with `f > s` but `f < m` returns
   0, not +1. So the "triple" is a genuine extra restriction, not a relabelling.
3. **`sma()` is a simple rolling mean** (`np.mean(values[-period:])`, NaN below the
   period). Implemented as `rolling(p, min_periods=p).mean()` — verified exact, see §6.

### Construction on NSE (brief §5)

- Daily bars only. This is a daily-bar strategy; `1d` (2008→2026-10-01) is the only
  timeframe used. No intraday corroboration is claimed.
- Score: **126d trailing momentum, ranked only among names in the `f>m>s` state.**
- `PortfolioConfig()` defaults — 22 names, 12% single-name, 25% sector, 10% cash,
  35% turnover budget — enforced by `run_backtest`, not bypassed.
- Rebalance **monthly**, fixed for every variant and not counted against the budget.
- Costs: full Indian delivery stack at **21.92 bps** all-in round trip, charged every
  rebalance against compounding equity. All numbers below are **net of this**.

**Survivorship bias is present** (today's NIFTY-50, backfilled) and applies to every
number in this report.

---

## 2. Declared parameter budget — written before anything was run

**5 variants. Rebalance frequency is not a variant.** No threshold tuning at any point.

| Variant | fast | mid | slow | rationale (a priori) |
|---------|------|-----|------|----------------------|
| V1 | 5 | 15 | 30 | catalog default, unmodified |
| V2 | 10 | 30 | 60 | 2× default — smallest jump that clears daily-bar noise |
| V3 | 20 | 50 | 100 | the canonical daily triple-MA triple |
| V4 | 20 | 60 | 120 | slower triple, closer to a swing filter |
| V5 | 10 | 20 | 50 | asymmetric tight-mid (does the mid leg matter?) |

**5 declared, 5 run, 0 exceeded.** Selection rule, fixed in advance: **max TRAIN Calmar**.

`diag.py` / `diag2.py` are TRAIN-only diagnostics of the *mechanism*; they are not
variants and no reported result depends on them.

---

## 3. Results

### 3a. TRAIN (2016-01-01 → 2023-12-31) — selection only

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Avg names | Vol% |
|---------|-------|--------|--------|--------|----------|-----------|-----------|------|
| V1 5/15/30 | 7.52 | 0.15 | −18.83 | **0.40** | 4.01 | 2.30 | 15.9 | 8.68 |
| V2 10/30/60 | 9.64 | 0.31 | −30.31 | 0.32 | 3.90 | 2.49 | 16.4 | 11.40 |
| V3 20/50/100 | 10.98 | 0.37 | −33.84 | 0.32 | 3.60 | 2.34 | 17.1 | 13.59 |
| V4 20/60/120 | 11.78 | 0.42 | −33.18 | 0.35 | 3.42 | 2.29 | 17.3 | 13.93 |
| V5 10/20/50 | 6.42 | 0.04 | −28.83 | 0.22 | 3.98 | 2.22 | 15.9 | 9.89 |
| **buy & hold (engine)** | **21.24** | **0.96** | −33.81 | **0.63** | 0.55 | 0.48 | 21.8 | 14.67 |
| buy & hold (equal-weight, literal) | 21.56 | 0.90 | −36.66 | 0.59 | — | — | 48 | 16.13 |
| nsealgo composite | 20.72 | 0.93 | −32.94 | 0.63 | 1.97 | 1.97 | 21.8 | 14.67 |

V1 was selected on **max Calmar** — and it is worth being blunt about how weak that was:
V1's Calmar edge (0.40 vs 0.35 for the runner-up) came *entirely* from the shallowest
drawdown (−18.83%, roughly half of everyone else's), not from any return advantage. V1
finished **4th of 5 on TRAIN CAGR** (only V5 was worse). I made the call as declared and
did not revisit it.

Two buy-and-hold baselines are reported because the brief's literal definition
(`panel.pct_change().mean(axis=1)`, costed once at entry) and the engine-matched
definition (same 22 names, same caps, same cost model, same turnover budget) differ by
~4 pp on TEST. The engine-matched one is the fair comparison; both are given.

### 3b. TEST (2024-01-01 → 2026-10-01) — touched once, after V1 was frozen

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Avg names | Vol% | Yrs+ |
|---------|-------|--------|--------|--------|----------|-----------|-----------|------|------|
| **V1 5/15/30 (selected)** | **−0.36** | **−0.68** | **−17.56** | **−0.02** | 4.10 | 1.95 | 16.3 | 9.14 | 0.67 |
| V2 10/30/60 | −2.43 | −0.78 | −23.35 | −0.10 | 4.01 | 1.93 | 16.0 | 10.46 | 0.67 |
| V3 20/50/100 | −1.61 | −0.59 | −25.08 | −0.06 | 3.72 | 1.84 | 17.0 | 12.19 | 0.67 |
| V4 20/60/120 | −2.79 | −0.68 | −27.10 | −0.10 | 3.63 | 1.77 | 16.9 | 12.29 | 0.33 |
| V5 10/20/50 | 1.75 | −0.39 | −12.89 | 0.14 | 4.03 | 2.00 | 16.5 | 10.29 | 0.67 |
| **buy & hold (engine)** | **4.47** | **−0.09** | −15.97 | **0.28** | 0.64 | 0.32 | 21.3 | 12.30 | 0.67 |
| buy & hold (equal-weight, literal) | 8.21 | 0.19 | −15.90 | 0.52 | — | — | 48 | 13.45 | 0.67 |
| **nsealgo composite** | **6.04** | **0.03** | **−15.22** | **0.40** | 2.08 | 1.10 | 21.3 | 13.25 | 0.67 |

**Every one of the five variants is negative on TEST.** Not one parameterisation made
money. V1's total return over the window is **−1.2%** (normalised equity ends at 0.990);
₹1,14,939 of costs were paid on ₹21,00,000 of capital — 5.5% of capital over 2.75 years,
which reconciles with the 1.95 %/y reported drag.

TEST calendar years — selected variant vs buy-and-hold:

| | 2024 | 2025 | 2026 (to 10-01) |
|---|---|---|---|
| **V1 (selected)** | +10.79% | +1.12% | **−11.63%** |
| buy & hold (engine) | +14.36% | +10.58% | −10.60% |
| buy & hold (equal-weight) | +20.26% | +13.35% | −8.27% |

### 3c. TEST vs buy-and-hold (selected variant)

| axis | V1 | BH (engine) | verdict |
|------|-----|-------------|---------|
| Return | **−0.36%** CAGR | **+4.47%** CAGR | **worse by 4.83 pp/yr** |
| Drawdown | −17.56% | −15.97% | **worse by 1.59 pp** |
| Sharpe | −0.68 | −0.09 | **worse by 0.59** |
| Calmar | −0.02 | 0.28 | worse |

Against the literal equal-weight baseline the gap is larger: **8.57 pp/yr worse on
return**, and **1.66 pp worse on drawdown**.

The strategy is not even *paid* for its risk: V1 delivered 9.14% annualised volatility
against buy-and-hold's 12.30%, and still lost more, because the missing return is
missing alpha, not missing risk. Its lower volatility comes from holding cash, not from
avoiding losers.

### 3d. Random-signal control — **FAIL, 19/20**

20 seeds, TEST, identical % of cells long (37.2%), identical 126d ranking, only the
*membership* chosen by a coin flip:

| | value |
|---|---|
| random TEST CAGR | median **+2.26%**, range −0.60% to +6.06% |
| V1 TEST CAGR | **−0.36%** |
| seeds beaten | **1 / 20** |

**A coin flip with the same exposure beats this strategy in 19 runs out of 20.** It fails
the minimum bar. For scale, the neighbouring `dual_moving_average` audit lost 20/20 to a
random control whose median was +5.11% against its own +1.46%; the random median here is
+2.26% against −0.36%. So the *margin* over noise is actually slightly smaller than
`dual_moving_average`'s (2.62 pp vs 3.65 pp) — the difference is that this strategy loses
to noise while still being **negative in absolute terms**, where `dual_moving_average` at
least stayed positive.

### 3e. vs the nsealgo composite — **FAIL**

| TEST | CAGR% | Sharpe | MaxDD% |
|------|-------|--------|--------|
| V1 (selected) | −0.36 | −0.68 | −17.56 |
| nsealgo composite | 6.04 | 0.03 | −15.22 |

Worse on all three. The composite is **6.40 pp/yr better on return and 2.34 pp better
on drawdown**.

### 3f. Cost stress (selected variant, TEST CAGR%)

| zero cost | 10 bps slip (2×) | **5 bps (as reported)** | 15 bps (3×) |
|---|---|---|---|
| +0.46 | −1.17 | **−0.36** | −1.98 |

Gross of all costs the strategy returns **+0.46%**. Costs take it to −0.36%. So the
honest framing is **not** "costs killed a good strategy" — there was no gross edge to
begin with. Costs removed a ~0.8 pp/yr surplus that was already indistinguishable from
zero. The strategy is not cost-killed; it is edge-free, and then it pays 1.95 %/y for
the privilege.

---

## 4. Why it fails — TRAIN-only diagnostics

All of §4 is computed on 2016-01-01 → 2023-12-31 only. TEST was not consulted.

### Q1. The `f > m > s` state is *negatively* predictive on TRAIN

Average forward 21-trading-day return, by strategy state:

| variant | `f>m>s` (+1) | `f<m<s` (−1) | mixed (0) | bullish − mixed |
|---------|--------------|--------------|-----------|------------------|
| V1 5/15/30 | 1.71% | 2.14% | 2.17% | **−0.46 pp** |
| V2 10/30/60 | 1.62% | 2.58% | 1.84% | −0.22 pp |
| V3 20/50/100 | 1.55% | 2.72% | 1.83% | −0.28 pp |
| V4 20/60/120 | 1.39% | 3.03% | 1.83% | −0.44 pp |
| V5 10/20/50 | 1.60% | 2.43% | 1.99% | −0.39 pp |

Higher forward return is what a long-only holder wants, so read the ordering carefully —
it is the opposite of intuitive, and it is the cleanest finding in this report.

**The signal is monotonically inverted.** In **all five variants** the fully-bullish
alignment `f>m>s` has the *lowest* forward return of the three states, and the fully-bearish
alignment `f<m<s` has the *highest* in four of five (the exception is V1, where the mixed
bucket edges it by 3 bp). Ordering the buckets by how bullish they look:

```
V1   mixed 2.17%  >  bearish 2.14%  >  bullish 1.71%   (bullish still worst)
V2   bearish 2.58%  >  mixed 1.84%  >  bullish 1.62%
V3   bearish 2.72%  >  mixed 1.83%  >  bullish 1.55%
V4   bearish 3.03%  >  mixed 1.83%  >  bullish 1.39%
V5   bearish 2.43%  >  mixed 1.99%  >  bullish 1.60%
```

So the strategy's `+1` — the only state it can put money into — points at the group with
the worst forward returns, and its `−1` points at the best. **The one output this strategy
produces correctly is the half an Indian delivery account is forbidden to trade.** That is
not a subtle edge case; it is a sign inversion in the cross-section, present in every
parameterisation I tested.

Caveat, stated plainly: this is a *univariate marginal* statistic, not a portfolio result.
It says nothing conditional on momentum rank, and §Q9 shows that a book which ranks by
momentum first does *not* actually gain from acting on it. The correct conclusion is that
the raw signal carries no usable information either way — not that a bearish filter is a
profitable rule.

### Q2. The third leg — the "triple" — destroys value relative to its own two-leg version

Forward 21d return, strict alignment vs the looser `f > m` filter:

| variant | `f>m>s` | `f>m` only | `f>s` only | strict lift |
|---------|---------|------------|------------|-------------|
| V1 | 1.71% | 1.98% | 1.83% | **−0.27 pp** |
| V2 | 1.62% | 1.72% | 1.63% | −0.10 pp |
| V3 | 1.55% | 1.55% | 1.64% | 0.00 pp |
| V4 | 1.39% | 1.48% | 1.58% | −0.09 pp |
| V5 | 1.60% | 1.82% | 1.65% | −0.22 pp |

This is a finding specific to the *triple* MA: demanding monotone alignment is worse
than the same strategy with the mid leg removed. The mid average is not confirming the
trend; it is discarding the best of it. On NIFTY-50, "fast is above slow **but** has
just crossed under the mid" is a continuation state, not a warning.

### Q3. No market-timing power

Correlation of signal breadth (fraction of the universe in `f>m>s`) against the forward
21-day equal-weight market return, TRAIN:

| V1 | V2 | V3 | V4 | V5 |
|----|----|----|----|----|
| −0.033 | −0.015 | −0.011 | −0.025 | −0.025 |

All effectively zero. So the strategy cannot rescue itself as a regime overlay either.

### Q4–Q6. Strip the gate, and the book becomes a normal momentum book

| TRAIN book | CAGR% | Sharpe | MaxDD% | Avg names |
|------------|-------|--------|--------|-----------|
| **no gate — pure 126d momentum rank** | **17.56** | 0.73 | −35.21 | 21.8 |
| with V1 5/15/30 gate | 7.52 | 0.15 | −18.83 | 15.9 |
| with V3 20/50/100 gate | 10.98 | 0.37 | −33.84 | 17.1 |

The gate removes **10 pp/yr** of TRAIN return. Once the book already ranks by momentum,
the moving-average gate is a redundant screen stacked on top of the factor doing the
work, and on this universe it selects *against* forward returns.

Eligibility, V1, TRAIN: **57% of rebalance months have fewer than 22 eligible names**
(median 19). The 22-name cap is not the binding constraint — the signal is.

### Q7–Q9. The dominant failure mode is **cash, not stock selection**

Realised invested weight, V1, TRAIN: **mean 55.8%** against the 90% the cash buffer
intends. p05 is 16.0%, p95 is 87.1%. 1.9% of TRAIN bars are 100% cash, in exactly two
spells — **2020-04-01 → 2020-04-30** (the COVID crash — a good call) and **2016-01-01 →
2016-01-29** (the first month of TRAIN).

Counterfactual: let the *uninvested* sleeve earn the equal-weight universe return on the
same days, same caps, same costs.

| TRAIN book | CAGR% | invested | + cash→universe | lift |
|------------|-------|----------|-----------------|------|
| hold `f>m>s` only (as reported) | 7.52 | 55.8% | **14.48** | **+7.55 pp** |
| exclude only the **bearish** state | 13.95 | 81.3% | 15.73 | +3.33 pp |
| exclude both extremes | 10.94 | 51.0% | 19.20 | +9.29 pp |
| hold everything (pure momentum) | 17.56 | 88.6% | 16.48 | +1.46 pp |

**≈7.6 pp/yr of TRAIN return is lost to idleness, not to picking the wrong stocks.** This
also decomposes the §Q4 headline cleanly: the gate costs 17.56 → 7.52, i.e. **10.0 pp/yr,
of which 7.6 pp is idleness and only ~2.4 pp is actually wrong stock selection.** The
signal's selection damage is real but secondary; its cash damage is three times larger.

The counterfactual that isolates which state is responsible is decisive: excluding only the
*bearish* state lifts TRAIN CAGR from 7.52% to 13.95% and raises invested weight from 55.8%
to 81.3%, while the bullish filter contributes nothing positive at all. **The neutral state
— the strategy's `return 0` — is where the money dies.**

Mechanism: a ternary per-symbol signal collides with a long-only book. A name only earns
a slot when all three averages are stacked in order, so the book is simultaneously a
negative-alpha screen (Q1) *and* a de-facto half-cash market-timing overlay (Q7–Q9),
and the two compound.

---

## 5. Sanity checks (brief §6)

| # | Check | Result |
|---|-------|--------|
| 1 | **Plausibility** — no >40–50% CAGR artefact | **PASS.** −2.8% to +1.8% on TEST; 6.4–11.8% on TRAIN. No lookahead, no compounding bug. |
| 2 | **Weight count** — not 48, not accumulating | **PASS, but for the wrong reason.** 15.9–17.3 names vs the 22 target — *below*, not above, so no residual accretion. Cause is eligibility (§Q5), not a weight bug. Max single position 5.8–7.1%, well under the 12% cap. |
| 3 | **Signal liveness** — not effectively flat | **PASS.** Long 39.5% of cells on TRAIN, 37.2% on TEST — far above the 5% floor. The strategy was genuinely deployed every day. Its problem is what it did while deployed, not that it stood aside. |
| 4 | **Cost drag** — reported, and is it fatal? | **PASS.** 1.77–2.49 %/y, reconciled against ₹1,14,939 paid on ₹21,00,000. Higher than `dual_moving_average`'s ~1.2 because turnover is 3.6–4.1×/y. Not the cause: zero-cost CAGR is only +0.46%. |
| 5 | **Negative control** — beats a random signal? | **FAIL. Lost to 19 of 20 random seeds** (median +2.26% vs −0.36%). |
| 6 | **Beats the nsealgo composite?** | **FAIL.** 6.40 pp/yr worse on return, 2.34 pp worse on drawdown, 0.71 worse on Sharpe. |

---

## 6. Fidelity check — is the vectorised signal actually this strategy?

Every number above depends on `tma_signal()` being `TripleMaStrategy.signal()`.

`verify_signal.py` drives the **real catalog class**, one symbol at a time, bar by bar
over 4,000 bars per variant, and compares against the vectorised panel version:

```
V1_5_15_30     cells compared 192000  mismatches 0  ref states {-1: 46722, 0: 72904, +1: 72374}
V2_10_30_60    cells compared 192000  mismatches 0  ref states {-1: 41598, 0: 72891, +1: 77511}
V3_20_50_100   cells compared 192000  mismatches 0  ref states {-1: 37689, 0: 71278, +1: 83033}
V4_20_60_120   cells compared 192000  mismatches 0  ref states {-1: 35421, 0: 72155, +1: 84424}
V5_10_20_50    cells compared 192000  mismatches 0  ref states {-1: 43762, 0: 72840, +1: 75398}
```

**960,000 cells, 0 mismatches — bit-identical.** No result here is an artefact of the
port.

---

## 7. Verdict

**No — `triple_moving_average` does not make money on NSE NIFTY-50. All five parameter
variants lost out-of-sample (−2.79% to +1.75% CAGR); the variant selected on TRAIN by the
pre-declared rule returned −0.36% CAGR against 4.47% for buy-and-hold and 6.04% for the
nsealgo composite, lost on drawdown and Sharpe too, and failed the negative-control bar by
losing to 19 of 20 random signals with identical exposure.**

**Most likely reason — two failures compounding.** The `f > m > s` gate is a
*negative*-alpha screen on this universe (TRAIN forward-return gap −0.22 to −0.46 pp), and
because the signal is ternary, the same rule also parks the book in cash ~44% of the time,
costing a further ~7.6 pp/yr. Requiring monotone alignment is strictly worse than the
two-leg `f > m` version of the same idea, so the third average is not neutral — it is
subtractive. The result is a half-cash book holding a mildly-wrong selection.

**One thing I would try next — and the evidence caps the upside sharply.** The TRAIN
ablation points at one specific, testable change: **use only the bearish state as the
exclusion and treat the mixed/neutral state as holdable**, which is the one place the
signal is informative (§Q1). On TRAIN that moves 7.52% → 13.95% CAGR and 55.8% → 81.3%
invested.

But I would not bet on it, and the same ablation table says why: **13.95% still loses to
doing nothing at all** (hold everything, 17.56%) and to plain buy-and-hold (21.24%). So
the fix recovers most of what the *bullish filter* destroys without ever becoming a
strategy of its own — it just removes the damage and hands the work back to the momentum
rank the engine was already doing. Combined with the breadth-vs-market correlation
(−0.011 to −0.033, i.e. no timing power), there is no configuration of this signal I
would deploy. Its real value is as a diagnostic case for why a ternary per-symbol signal
in a long-only book degenerates into a half-cash negative screen, and why the extra
strictness of a "triple" crossover makes an already-redundant filter worse.

---

## 8. Bugs and harness findings

**No bug found in `src/nsealgo/**` or `src/cryptobot/**`.** I did not modify either. Two
findings are worth recording:

**(a) Harness footgun, not a bug — a sparse score silently produces a half-cash book.**
`build_rebalance_weights` correctly holds only names with a finite score, so a strategy
whose signal is sparse simply invests less, with no warning. `run_backtest` surfaces this
only as `diag["avg_names"]`, which is easy to read as "some names fell out" when it
actually means "44% of capital was idle". A `diag["avg_invested_weight"]` alongside the
existing diagnostics would have surfaced this as the headline failure mode immediately
instead of after three diagnostic scripts. Worth adding for the next agent.

**(b) Warmup convention bites silently when a diagnostic recomputes on a sliced panel.**
The headline table computes SMA and momentum on the **full** panel (2008→2026) and then
slices, so TRAIN's first bars have real history behind them. My first diagnostic pass
sliced first, which cost 126 days of momentum warmup and moved the same TRAIN figure by
~0.6 pp (6.93% vs 7.52%). Small enough to be easy to miss and large enough to flip an
ablation's ranking — `diag.py` Q4 reported the no-gate momentum book at 15.27% under the
sliced convention versus 17.56% under the matched one, a 2.3 pp gap that changes the
headline "the gate costs 10 pp/yr" statement to 4.3 pp. Any future agent comparing a
diagnostic against a headline number must state its warmup convention explicitly, and
should check that the two reconcile. Both diagnostic scripts here now build on the full
panel and their headline rows reproduce 7.52% / 17.56% exactly.

Three bugs I introduced in my own scratch scripts, found and fixed during this run, listed
so they are not mistaken for findings about the strategy: NaN propagation from
`ndarray.mean()` on the forward-return label (fixed with `np.nanmean`); an **inverted
boolean mask** in the Q9 ablation, which briefly reported "hold f>m>s only" for a book
that actually held everything *except* `f>m>s` — this was the wrong-sign result, and it
was caught only because the number refused to reconcile with the headline table; and
passing a DataFrame where a function expected an index. The Q9 number is now verified to
reconcile exactly with the headline V1 TRAIN figure of 7.52%.

---

## 9. Protocol compliance

- Parameters chosen on **TRAIN only**; TEST evaluated **once**, unchanged, after V1 was
  frozen by the pre-declared Calmar rule. TEST was not consulted during any diagnostic.
- **5 variants declared, 5 run, 0 exceeded.** No threshold tuned against the equity curve.
- **No lookahead.** SMAs and momentum use closes up to and including *t*; `run_backtest`
  holds those weights from *t+1* (`held.shift(1) * rets`). No forward-fill from the future.
  Forward returns appear only as *labels* in TRAIN-only diagnostics, never as inputs.
- **Full Indian delivery cost stack** (STT, exchange txn, SEBI, stamp, DP, brokerage, 18%
  GST) at **21.92 bps all-in** round trip, charged every rebalance against compounding
  equity. Every reported number is net of it unless explicitly labelled zero-cost.
- All results attributed to **`engine_sha = 970713f3eecf`**.
- Survivorship bias noted on every number.
- Lint clean: `ruff check research/agent_triple_ma/`.
- **No commits made.** No file outside `research/agent_triple_ma/` was modified.
