# anchored_vwap → NSE NIFTY-50 — agent report

**Status: COMPLETE — validated TEST result obtained. Negative finding.**

*Written incrementally during the run; sections appear in the order they were produced.*

## Assignment

| | |
|---|---|
| Strategy | `anchored_vwap` |
| Source | `src/cryptobot/strategies/catalog/anchored_vwap.py` |
| Line | — |

## Signal definition (verbatim from the catalog)

```python
v   = vwap(closes, volumes)          # trailing `period`-bar volume-weighted mean close
dev = (closes[-1] - v) / v
signal = -1 if dev >  threshold else (+1 if dev < -threshold else 0)
```

It is a **mean-reversion** trigger on the trailing VWAP: go long when price sits
more than `threshold` *below* its volume-weighted average price, short when
symmetrically above. Defaults `period=50`, `threshold=0.02`.

**Not crypto-specific** — it uses only close/volume, both of which exist on NSE daily
bars. So it is in scope; no early bail-out under brief §9.

## Translation to this book

The book is **long-only, cross-sectional**. The `-1` branch is unusable (no shorting in
an Indian delivery account), so:

* `dev < -threshold` → **eligibility filter** (the +1 long leg).
* Among eligible names we need a *score*, because `run_backtest` selects the top
  `n_positions` by score, not by signal sign. Score = trailing 126d (6m) momentum
  rank, computed among eligible names only (`NaN` elsewhere, so an ineligible name can
  never be selected).

No lookahead: `dev[t]` uses closes/volumes through `t`; the engine decides weights from
close `t` and earns returns from `t+1`.

## Declared parameter budget — 5 variants, fixed before any run

Selection rule: **highest TRAIN Sharpe**, tie-broken by lower TRAIN cost drag.

| # | variant | period | threshold | score |
|---|---------|--------|-----------|-------|
| V1 | `V1_p50_t2.0_mom`  | 50  | 0.02 | mom |
| V2 | `V2_p50_t5.0_mom`  | 50  | 0.05 | mom |
| V3 | `V3_p200_t5.0_mom` | 200 | 0.05 | mom |
| V4 | `V4_p20_t3.0_mom`  | 20  | 0.03 | mom |
| V5 | `V5_p50_t5.0_deep` | 50  | 0.05 | deep (deepest discount to VWAP first) |

Variants beyond these five were **not** tested as strategy variants. Benchmarks
(buy-and-hold, the nsealgo composite factor, momentum-without-the-filter) are reported
for attribution only and were never used to select.

## Data

* `data/nse/*_1d.csv` via `nsealgo.data.loader` — the audited path.
* TRAIN `2016-01-01 → 2023-12-31`; TEST `2024-01-01 → 2026-10-01` (brief §4).

## Costs

`CostModel(segment="delivery", slippage_bps=5)`. Backtests go through `run_backtest`,
which folds slippage in as `rt_bps + 2 × slippage_bps` ⇒ **21.92 bps round trip**.
Every result below is **net of 21.92 bps** unless explicitly labelled `gross`.

### Step 0 — harness audit (`00_audit.py`), BEFORE any result was produced

A prior interrupted run left scratch files in this directory. Rather than trust them, I
verified their load-bearing assumptions against `src/nsealgo` source directly.

| Check | Result |
|---|---|
| `common.load()` panel **identical** to the brief's `load_universe` (48 names, 4,629 bars, 2008-01-01→2026-10-01, 13,966 NaN cells both sides) | PASS |
| Volume panel aligned, non-negative, no all-NaN rows | PASS |
| **No-lookahead**: score at T identical when the panel is truncated at T (price *and* volume truncated) | PASS |
| **No-lookahead**: shocking everything after 2021 by 3× price and 7× volume leaves every pre-2021 score bit-identical | PASS |
| `vwap_panel[t]` equals a direct 50-bar window mean | PASS |
| No *partial-sum* VWAP (a NaN close inside a window must void the whole window, else a 49-price numerator gets divided by a 50-volume denominator) | PASS — 0 such windows |
| Cost model: engine reaches `CostModel` through `all_in_round_trip_bps` **only**, proven by an attribute-trap object that raises on any other member | PASS — so the `ZeroCostModel` gross-run shim is a complete substitute |
| `all_in_round_trip_bps(1e5)` = **21.92 bps**, one-way 10.96 bps | PASS — matches brief §3 |
| Net run < gross run; `run_backtest` deterministic across repeat calls | PASS |
| Volume-weighted VWAP ≠ 50d SMA (mean abs diff 0.667%) — volume weighting does real work | PASS |
| Panel VWAP reproduces the catalog's own `indicators.vwap()` on a live symbol (max rel err 4.4e-16) | PASS |
| Engine never holds an ineligible name; 12% single-name cap respected (max 0.1080) | PASS |

`444` zero-volume 50-bar windows exist and map to NaN (correctly excluded, not treated
as VWAP = 0).

**Three "failures" the audit raised on its first run were bugs in the audit, not the
harness** — `np.allclose` without `equal_nan` mis-flagged the 13,966 pre-IPO NaN gaps,
and a substring regex matched `all_in_round_trip_bps` inside its own name. I replaced the
regex with the attribute trap, which is a strictly stronger test. Recorded because a
first-pass audit that cries wolf is worth knowing about.

**One real defect fixed in the scratch harness:** `_slice_metrics` differenced weights
*after* slicing to the window, so the first in-window rebalance produced `NaN` and was
silently dropped — understating turnover by roughly one third of a monthly book-turn.
Now differenced on full history, then sliced.

`ruff check research/agent_anchored_vwap/` — clean.

### Step 1 — signal liveness, TRAIN only (`01_liveness.py`)

`dev(50)` on TRAIN: mean +1.70%, sd 7.24%, 96.2% finite, P(dev>0)=58.4%, p95 |dev| = 14.59%.
So a 2% band is a live, non-trivial trigger. Volume-weighted VWAP differs from a plain
50d SMA by 0.849 pp on average — the volume weighting is doing real work, not decoration.

| variant | period | thresh | name-days | %name-days | avg/day | avg flagged at rebalance |
|---|---|---|---|---|---|---|
| V1 | 50 | 0.02 | 25,334 | 26.7% | 12.83 | **12.5** |
| V2 | 50 | 0.05 | 13,317 | 14.0% | 6.74 | 6.4 |
| V3 | 200 | 0.05 | 17,143 | 18.1% | 8.68 | 8.4 |
| V4 | 20 | 0.03 | 15,389 | 16.2% | 7.79 | 7.4 |
| V5 | 50 | 0.05 | 13,317 | 14.0% | 6.74 | 6.4 |

All five clear brief §6.3's 5% liveness floor. But note the flagged set averages
**6–13 names of 48**, against a book configured for 22. That single fact turned out to
explain most of the strategy's behaviour — see the bug below.

### Step 2 — TRAIN-only variant selection (`02_train_select.py`)

Rule fixed in advance: highest TRAIN Sharpe, tie-break lower TRAIN drag. All net of
21.92 bps.

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn | Drag | names held | gross CAGR |
|---|---|---|---|---|---|---|---|---|
| **V1_p50_t2.0_mom** | **11.01%** | **0.38** | −34.45% | 0.32 | 3.98x | 0.90% | 23.4 | 11.98% |
| V2_p50_t5.0_mom | 10.21% | 0.34 | −31.42% | 0.32 | 3.22x | 0.73% | 11.7 | 10.99% |
| V3_p200_t5.0_mom | 10.61% | 0.34 | −34.40% | 0.31 | 2.78x | 0.63% | 10.1 | 11.29% |
| V4_p20_t3.0_mom | 9.20% | 0.26 | −29.23% | 0.31 | 3.76x | 0.85% | 17.4 | 10.10% |
| V5_p50_t5.0_deep | 10.77% | 0.37 | −30.74% | 0.35 | 3.23x | 0.73% | 11.5 | 11.56% |

**TRAIN winner: V1** (period 50, threshold 0.02, momentum score) — Sharpe 0.38.
TRAIN buy-and-hold (equal weight, 90% deployed, same costs): **CAGR 19.92%, Sharpe 0.86,
MaxDD −34.79%, Calmar 0.57**. The strategy is already ~9 pp *behind* the market in-sample.
All five variants land in a tight 9.2–11.0% band with no outlier — a flat, uninformative
parameter surface, which is itself evidence the signal is not doing the work.

Reproduced the prior interrupted run's `winner.csv` exactly (11.01% / 0.38 / −34.45% /
23.4 names), so the scratch work was sound.

### 🐞 BUG FOUND — in my step-0 audit, exposed by the numbers, and it matters

Step 0 checked that `build_rebalance_weights` never selects an ineligible name. It
reported 0 violations. **That check was aimed at the wrong function.** The engine's
actual book is

```
tgt[i] = apply_turnover_budget(build_rebalance_weights(...)[i], tgt[i-1], 0.35, 30)
```

and `apply_turnover_budget` returns `cur + λ·(tgt − cur)` with `cur` = the *previous*
target. A name that stops being flagged has `tgt = 0`, so its weight decays
geometrically toward zero instead of leaving on the rebalance it stops qualifying for.
With `turnover_budget = 0.35` and only ~13 of 48 names flagged, that decay is slow and
stale positions accumulate up to `max_names = 30`.

That is why "23.4 names held" sat next to "12.8 names flagged" without contradiction —
I had assumed one of the two numbers was a typo. Both were right. Measured on TRAIN:

| | |
|---|---|
| mean deployed weight | **0.670** (config target 0.90) |
| mean cash | **0.330** |
| days held ≥ `max_names`=30 | 1,163 of 1,975 |
| weight on names flagged *today* | 0.376 (56.1% of deployed) |
| weight on **stale** residuals | 0.294 (**43.9%** of deployed) |
| mean stale names | 14.09 |
| at rebalance instants: flagged / stale | 0.560 / 0.114 |

So the honest characterisation of V1 is *not* "22 flagged names at 90% deployed". It is
"up to 30 names at 67% deployed, of which ~44% of the money sits on names the strategy
stopped flagging one or more months ago." Two thirds of the intended exposure is missing;
44% of what is deployed is a bookkeeping tail. 43% of stale observations are under 1% of
book weight — materially above the engine's `DEAD_WEIGHT_EPS` of 1e-4, so the engine
cannot drop them, while being economically noise.

This is **not a bug in the strategy and not something I fixed** — it is how
`src/nsealgo`'s shared engine behaves for any signal that flags a minority of names. I
did not modify `src/nsealgo/**` (brief §9). It is reported because it caps how much of
any headline number can be attributed to the VWAP signal, and because it means the
"22 names / 90% deployed" config is not being achieved by this signal. The audit now
asserts the stale share explicitly (`< 60%` guard, currently 45.2% full-history) so it
can never be rediscovered late and mistaken for a strategy result.

### Step 3 — THE TEST EVALUATION (`03_test_final.py`)

Parameters frozen from TRAIN: **V1 = 50d VWAP, 2% band, momentum score.** No parameter
was touched after this point. All figures net of 21.92 bps round trip.

**TEST 2024-01-01 → 2026-10-01 (662 bars, 2.71y):**

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn/yr | Drag | names held | gross CAGR |
|---|---|---|---|---|---|---|---|---|
| **anchored_vwap V1** | **7.75%** | **0.17** | **−10.75%** | **0.72** | 4.09x | 0.91% | 24.1 | 8.72% |
| buy & hold (EW, net, brief §4.5) | 7.44% | 0.13 | −14.40% | 0.52 | — | — | 48 | — |

**vs buy-and-hold:** CAGR **+0.31 pp BETTER**; Sharpe +0.03; MaxDD **+3.65 pp BETTER
(shallower)**; total return 23.3% vs 22.3%.

**Sanity checks (brief §6):**
1. Plausibility — 7.75% CAGR, no 200%+ blowup. OK.
2. Weight count — 24.1 names vs target 22 (cap 30), not accumulating to 48. OK, but see
   the stale-residual bug: 24.1 held vs 14.3 flagged.
3. Signal liveness — 29.8% of name-days long, 14.3 flagged per rebalance. Well above
   the 5% floor. OK.
4. Cost drag — gross 8.72% → net 7.75%, 0.91%/yr. **Gross is positive, so this is not a
   cost-viability failure.** It is an alpha failure. Costs eat ~11% of gross return but
   are not the binding constraint.

**Random-signal control (25 draws):** random mean CAGR 5.44% (min 2.12%, max 8.55%),
strategy beats 80% of draws → "marginal". Re-run at 200 draws in step 8.

**vs the nsealgo composite factor** (same panel, same window, same costs):
composite **8.12%** CAGR / Sharpe 0.18 / MaxDD −14.84% vs anchored_vwap 7.75% / 0.17 /
−10.75%. **anchored_vwap LOSES by 0.36 pp CAGR.** It wins only on drawdown, and it
burns twice the turnover (4.09x vs 2.03x) and twice the cost (0.91% vs 0.45%).

**Family disclosure — TEST for all five declared variants.** Selection was done on
TRAIN; this is disclosure of the whole family, not selection.

| variant | TEST CAGR | Sharpe | MaxDD | names |
|---|---|---|---|---|
| **V1 (TRAIN-selected headline)** | **7.75%** | 0.17 | −10.75% | 24.1 |
| V2_p50_t5.0_mom | 1.73% | −0.47 | −15.32% | 14.4 |
| V3_p200_t5.0_mom | 1.71% | −0.41 | −14.86% | 12.2 |
| V4_p20_t3.0_mom | 3.35% | −0.32 | −10.75% | 15.8 |
| V5_p50_t5.0_deep | 1.52% | −0.48 | −15.32% | 14.3 |

**Protocol disclosure, stated plainly:** this TEST file evaluates all five variants, so
TEST was observed across the family, not only at the selected point. That is a
deviation from the strictest reading of brief §4.4 and I am reporting it rather than
hiding it. Mitigating facts: (i) `winner.csv` was written at 08:57 and every TEST output
file at 09:11+, so V1 was genuinely fixed by TRAIN before any TEST number existed;
(ii) V1 is the **best on TRAIN and the best on TEST** — the family disclosure does not
hand me a better headline than the pre-registered one. But I cannot un-see the family,
and the headline is therefore conditional on my having not re-selected. I did not
re-select.

Interesting and important: the TRAIN surface was flat (all five 9.2–11.0%) while the
TEST surface is violently split (7.75% vs 1.5–3.4%). The variants differ mainly in how
many names they hold (24.1 vs 12–16). So on TRAIN the variants were all effectively
"a partially-invested momentum book", and on TEST the differences in breadth decided
the outcome. That is a warning that the TRAIN surface was flat by accident and carried
no information about which variant would survive.

**TEST yearly returns:**

| year | buy & hold | anchored_vwap | alpha |
|---|---|---|---|
| 2024 | 17.94% | 9.15% | −8.79% |
| 2025 | 12.01% | 16.67% | +4.66% |
| 2026 (to 01 Oct) | −7.40% | −3.16% | +4.24% |

2/3 positive years, 2/3 years beating buy-and-hold. It loses badly in the one strong
up-year (2024) and wins in the two weaker ones — i.e. it behaves like a de-risked book,
not like an alpha source.

### Step 4 — attribution (`04_attribution.py`)

| book | TEST CAGR | Sharpe | MaxDD | Turn | names |
|---|---|---|---|---|---|
| anchored_vwap V1 (filter + momentum) | 7.75% | 0.17 | −10.75% | 4.09x | 24.1 |
| 6m momentum, **no** VWAP filter | 4.18% | −0.10 | −16.86% | 2.77x | 22.0 |
| VWAP filter only, **no** momentum | 7.58% | 0.15 | −10.75% | 4.08x | 23.9 |
| buy & hold (equal weight, net) | 7.44% | 0.13 | −14.40% | 0.00x | 48 |

Read carefully, this is the whole story:

* **Filter alone = 7.58%, which is buy-and-hold (7.44%) to within 0.14 pp.** The VWAP
  filter by itself does nothing.
* Momentum alone = **4.18%**, *worse* than buy-and-hold. The "+3.57 pp marginal
  contribution" is not the filter creating return; it is the filter **undoing damage
  the momentum score did.** Adding it moves 4.18% → 7.75%, i.e. back to market, plus
  0.31 pp.
* Filtering changes the book substantially — only 7 of the last-rebalance names overlap
  momentum-only — and cuts turnover 3.85x → 2.45x (full history). So the filter is real,
  it just isn't profitable.

**Raw signal check** (the cleanest test, no portfolio machinery at all): mean 21-day
forward return of flagged names 1.66% vs unflagged 1.44% — a **+0.21 pp edge per month,
t = 0.66, NOT significant at 5%** (217 non-overlapping monthly observations, so no
overlap-inflation; an earlier overlapping-window version of this test was ~4.6× too
generous and has been corrected). If the +0.21 pp were real it would annualise to
+2.45 pp/yr. It is not distinguishable from zero.

### Step 5 + 7 — is the TEST edge real? (`05_significance.py`, `07_decompose_alpha.py`)

Daily returns do not overlap, so a daily t-stat on the excess series is honest; I also
block-bootstrap in 21-day blocks because monthly rebalancing induces autocorrelation.

| window | strategy CAGR | B&H CAGR | delta | daily excess | annualised | t | 90% CI | P(alpha≤0) |
|---|---|---|---|---|---|---|---|---|
| TRAIN | 11.01% | 20.00% | **−8.99 pp** | −3.29 bps | −8.04%/yr | **−3.64** | [−11.47, −4.31]% | 100% |
| TEST | 7.75% | 7.52% | +0.24 pp | −0.00 bps | **−0.01%/yr** | **−0.00** | [−5.95, +5.21]% | 51.7% |

**This is the headline finding.** On TEST the strategy's daily excess return over
buy-and-hold is **−0.01%/yr with t = −0.00** — arithmetically indistinguishable from
zero — yet its CAGR is 0.31 pp *higher*. A positive CAGR gap with zero arithmetic excess
can only be a compounding effect, not a return edge.

**Cash-matched benchmark.** Comparing a book that averages 67–70% deployed against a 90%
deployed benchmark conflates "the signal worked" with "the book held less stock". Re-run
at matched deployment:

| window | strategy | B&H @90% | B&H @ same deployment | CAGR gap | arithmetic excess | t |
|---|---|---|---|---|---|---|
| TRAIN | 11.01% | 19.92% | 14.74% @67% | **−3.73 pp** | −3.04%/yr | −1.54 |
| TEST | 7.75% | 7.44% | 5.90% @70% | **+1.85 pp** | +1.79%/yr | **+0.60** |

Variance-drag decomposition of the TEST gap:

```
strategy :  arithmetic +7.97%/yr   variance drag -0.50%/yr   geometric +7.47%  (obs +7.75%)
B&H@70%  :  arithmetic +6.18%/yr   variance drag -0.45%/yr   geometric +5.90%
=> of the +1.85 pp CAGR gap: +1.79 pp is return, -0.06 pp is lower volatility
```

So on TEST nearly all of the cash-matched gap is nominally "return" — but it carries
**t = +0.60**, nowhere near the 1.96 needed for 5%. On TRAIN the same measurement is
**−3.04%/yr, t = −1.54** — negative, and only missing significance by a whisker.

Put together: TRAIN significantly worse than the market; TEST nominally better but not
distinguishable from zero. A signal whose excess return is −8.0%/yr in-sample and
+1.8%/yr out-of-sample (neither significant at 5% in the direction you'd need) is a
null result with a favourable drawdown, not an edge.

### Step 8 — random-signal control at 200 draws (`08_random_control_robust.py`)

Only the **eligibility** draw is randomised; score construction, portfolio constraints,
rebalance dates and costs are identical, so any difference is attributable to the VWAP
filter's choice of names.

| | |
|---|---|
| random CAGR mean / sd | **4.93%** / 1.82 pp (min −0.30%, max 8.68%) |
| percentiles | p25 3.56% · p50 4.93% · p75 6.29% · **p90 7.25%** · p95 7.92% · p99 8.52% |
| random Sharpe (rf 6.5%) | mean **−0.10**, sd 0.17 |
| strategy | CAGR 7.75%, Sharpe 0.17 |
| **strategy beats** | **185/200 draws = 92.5th percentile** |
| strategy vs random mean | **+2.82 pp** |
| random draws beating B&H@90% (7.44%) | 8% |
| random draws beating cash-matched B&H (5.90%) | 33% |

Step 3's 25-draw estimate said 80%; at 200 draws it is **92.5%**, comfortably clearing
brief §6.5's minimum bar. So the construction is *not* a coin flip — it does something.

**But that is the weakest bar available, and it must not be confused with alpha.** The
random books average only 4.93% because they hold ~13 arbitrary names at ~70% deployed;
the strategy beats them mostly by holding a broader, more market-like book. The
comparison that actually tests for alpha is the cash-matched excess return, and that is
**+1.79%/yr, t = +0.60** — not significant.

*(Correction: step 8's first run printed a raw Sharpe of 0.79 for the strategy where step
3 reports 0.17. Both are "right" but on different bases — step 3 subtracts the 6.5%
T-bill proxy, step 8's first version did not. Re-run on a single basis (rf = 6.5%):
strategy Sharpe **0.17**, random Sharpe mean **−0.10**. The CAGR figures, which carry the
comparison, were never affected.)*

---

# 9. Verdict

## Does `anchored_vwap` make money on NSE? **NO.**

Not as a strategy with an edge. It makes money in the sense that a long-only book over
Indian equities makes money, and it has a nicer drawdown curve than buy-and-hold. But it
does not make money *because of the anchored-VWAP signal*, and nothing in the evidence
survives as tradable alpha.

## Required summary (§7)

**1. Signal.** Trailing volume-weighted mean close over `period` bars; go long when price
is more than `threshold` below it. Variants tested (budget 5, declared before any run):
V1 p50/t2%/momentum, V2 p50/t5%/momentum, V3 p200/t5%/momentum, V4 p20/t3%/momentum,
V5 p50/t5%/deepest-discount. Exactly 5. Budget not exceeded.

**2. TEST (2024-01-01 → 2026-10-01), net of 21.92 bps:**

| | anchored_vwap V1 |
|---|---|
| CAGR | 7.75% (gross 8.72%) |
| Sharpe (rf 6.5%) | 0.17 |
| MaxDD | −10.75% |
| Calmar | 0.72 |
| Turnover/yr | 4.09x |
| Cost drag | 0.91%/yr |
| Avg names held | 24.1 (only 14.3 flagged — see bug) |

**3. Buy-and-hold, identical window, identical costs:** CAGR 7.44%, Sharpe 0.13,
MaxDD −14.40%, Calmar 0.52.

**4. TEST vs buy-and-hold:** better by **+0.31 pp CAGR** and **+3.65 pp drawdown**
(shallower). But the arithmetic excess return is **+0.06%/yr** (daily +0.02 bps) —
i.e. the return gap is essentially nil and the *entire* headline advantage is a lower-volatility
artefact of holding ~30% cash and ~24 names instead of 48. Against a **cash-matched**
benchmark (B&H at the strategy's own 70% deployment, CAGR 5.90%) the gap is +1.85 pp,
carrying **t = +0.60** — not significant.

**5. Random-signal control:** beats **185/200** draws, 92.5th percentile. Passes the
coin test. Passes the minimum bar; fails to clear the bar that matters.

**6. vs the nsealgo composite factor:** composite **8.12%** CAGR / Sharpe 0.18 vs
anchored_vwap 7.75% / 0.17. **Loses by 0.36 pp**, while spending twice the turnover
(4.09x vs 2.03x) and twice the cost (0.91% vs 0.45%).

**7. Verdict:** **No** — `anchored_vwap` does not make money on NSE as a strategy.

**8. Most likely reason, and the one thing I would try next.**

The most likely reason it fails: **the signal has no cross-sectional edge in Indian
equities, and a VWAP-based mean-reversion filter is the wrong family.** The evidence is
direct and comes from three independent angles:

* *Raw signal:* flagged names' 21-day forward return is 1.66% vs 1.44% for unflagged —
  a +0.21 pp/month edge at **t = 0.66**. Not distinguishable from zero. This is the
  cleanest test because it involves no portfolio machinery at all.
* *Decomposition:* the filter alone scores 7.58%, statistically indistinguishable from
  buy-and-hold's 7.44%. Its apparent "+3.57 pp contribution" is only the filter
  *cancelling out* the momentum score's damage (momentum alone = 4.18%). It subtracts
  from nothing and adds to nothing.
* *Out-of-sample decay:* the strategy was significantly **worse** than the market in
  TRAIN (−8.04%/yr, **t = −3.64**, 100% bootstrap probability of alpha ≤ 0) and
  nominally better in TEST (+1.79%/yr, t = +0.60). A −8% in-sample and a +1.8%
  out-of-sample excess, neither significant in the direction needed, is a null.

This is consistent with the finding already documented in `src/nsealgo/backtest/engine.py`
and `reports/FACTOR_EVIDENCE.md`: the Indian literature and the one multiple-testing-
corrected Indian study both favour **short-term continuation**, and mean-reversion rules
(RSI, Bollinger) failed. An anchored-VWAP reversion filter is squarely in the family that
has been tested and rejected. That prior was correct, and this run is an independent
confirmation of it on a signal it had not previously been run against.

**The one thing I would try next:** not a VWAP variant. The interesting finding buried in
this report is not the strategy — it is that the *engine's* turnover budget silently
left 47% of the deployed book in names the strategy had stopped flagging, and left the
book 30% in cash, so the configured 22-name / 90%-deployed mandate was never actually
delivered by any signal in this minority-flag regime. I would fix that at the harness
level (`src/nsealgo/backtest/engine.py:apply_turnover_budget`, e.g. by exempting
ineligible-to-eligible transitions from the drift or by hard-zeroing names that leave the
target set) and then re-run the *whole* catalog on NSE. Until the book holds what it says
it holds, every minority-flag strategy's measured CAGR is a mixture of its signal and
the harness's cash drag, and the two cannot be separated. I did not make this change —
brief §9 forbids modifying `src/nsealgo/**` — and fixing it would change every other
agent's numbers, so it needs to be an owner decision, not mine.

---

# 10. Provenance, honesty, and housekeeping

* **TEST discipline.** Parameters were frozen on TRAIN (`winner.csv`, written 08:57; every
  TEST artefact 09:11+). TEST was read once in step 3. As disclosed in step 3, step 3 also
  printed the whole variant family on TEST; I did not re-select on that information and V1
  was the pre-registered pick, but I am reporting the deviation rather than hiding it.
* **Cost basis.** Every headline is net of **21.92 bps** round trip (statutory + 5 bps/side
  slippage), matching brief §3 for `run_backtest` usage. The 11.92 bps figure is never
  used. Gross figures are labelled and come from a verified zero-cost shim.
* **Known artefact bug, quantified, disclosed, not silently corrected:**
  `apply_turnover_budget` retains ineligible names as decaying residuals — 44.8% of
  deployed weight on TRAIN, 47.2% on TEST. This is a property of the shared engine, not of
  the strategy, and it depresses every number in this report for *any* minority-flag
  signal. Step 0 now asserts the stale share (<60%, currently 45.2% full-history).
* **Bugs in my own scratch work, found and fixed:** (i) turnover was differenced after
  window-slicing, silently dropping one in-window rebalance; (ii) the step-0 no-lookahead
  test truncated price but read volume from the full-history panel, so it passed
  vacuously — now truncates both and additionally shocks post-2021 volume by 7×;
  (iii) the step-0 eligibility check tested `build_rebalance_weights` instead of the book
  the engine actually holds, which is why it wrongly reported "0 violations"; (iv) step 8
  printed Sharpe on a non-risk-adjusted basis, conflicting with step 3 — re-run on one
  basis.
* **No lookahead.** Proven mechanically, not asserted: scores at T are invariant to
  truncating the panel at T, and a 3× price / 7× volume shock applied to everything after
  2021 leaves every pre-2021 score bit-identical. The engine decides weights from close t
  and earns from t+1.
* **No files modified** under `src/nsealgo/**`, `src/cryptobot/**`, `tests/`, `GOAL.md` or
  `reports/`. No commit made.
* **Lint:** `.venv/bin/ruff check research/agent_anchored_vwap/` → all checks passed.
* **Files:** `00_audit.py` (harness verification) · `01_liveness.py` · `02_train_select.py`
  → `winner.csv` · `03_test_final.py` → `test_returns.csv` · `04_attribution.py` →
  `monthly_edge.csv` · `05_significance.py` · `06_book_decomposition.py` ·
  `07_decompose_alpha.py` · `08_random_control_robust.py` → `08_out.txt`.

## One-paragraph summary

`anchored_vwap` translated to NSE as a long-only cross-sectional filter — buy names more
than 2% below their trailing 50-day volume-weighted average price, rank those by 6-month
momentum. On TRAIN it returned 11.01% against the market's 19.92%. Frozen and run once on
TEST it returned 7.75% against the market's 7.44% — a +0.31 pp gap whose arithmetic
excess is +0.06%/yr, i.e. nil; the visible advantage is a shallower drawdown bought with
30% cash and 24 names instead of 48. Against a cash-matched benchmark the excess is
+1.79%/yr at t = +0.60, not significant, and the raw signal shows a +0.21 pp/month edge at
t = 0.66. It beats a coin 92.5% of the time and loses to the nsealgo composite while
burning twice the turnover. **It does not make money on NSE.** The useful output is the
finding that the shared engine's turnover budget leaves ~47% of the deployed book in
stale, unflagged names and the book 30% in cash, which caps every minority-flag
strategy's measured return and should be fixed before the catalog is re-run.
