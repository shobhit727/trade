# AGENT REPORT — `gaussian_strategy` on NSE NIFTY-50

**Agent:** `gaussian` · **Status:** COMPLETE — negative finding, fully evidenced
**Brief:** `research/AGENT_BRIEF.md`
**Source file:** `src/cryptobot/strategies/catalog/gaussian_strategy.py`

> **Verdict (one line): NO — `gaussian_strategy` does not make money on NSE.**
> TEST 2024-01-01 → 2026-10-01, net of 21.92 bps: **5.56% CAGR, Sharpe −0.04,
> MaxDD −12.43%**, versus buy-and-hold 8.16% / 0.18 / −15.91% and the nsealgo
> composite 6.55% / 0.07 / −14.84%. It loses to both, and its ~0.26%/yr of alpha is
> indistinguishable from zero. See §6–§9. Budget respected: **5 variants, declared
> up front** (§2).

---

## 1. What the strategy actually is

`GaussianStrategy` is a per-symbol, symmetric **z-score mean-reversion** time-series
strategy. For each symbol it takes a buffer of closes and computes

```python
z = (closes[-1] - mean(closes)) / std(closes)      # population std (np.std, ddof=0)
if z >=  entry:  return -1      # stretched HIGH  -> SHORT
if z <= -entry:  return +1      # stretched LOW   -> LONG
else:            return  0      # flat
```

Config: `period=30`, `entry=0.8`. It ignores `highs`, `lows`, `volumes` entirely.

Two facts that shape everything below:

1. **It is two-sided.** Half its signal is *short*. An Indian delivery account cannot
   short, so the NSE port keeps only the `z <= -entry` leg ("buy the dip") and treats
   `z >= entry` as *no position*. This is a structural, one-sided mutilation of the
   original — recorded honestly, not papered over.
2. **It z-scores price *levels*, not returns.** The mean and stdev are of the raw close
   series, so `z` is "how far is today's close from its own `period`-bar mean, in units of
   its own `period`-bar stdev". Price levels are not Gaussian, so the "gaussian" in the
   name is aspirational. This is a faithful port, not a bug I introduced.

## 2. Declared parameter budget — 5 variants, fixed in advance

Chosen on TRAIN (2016-01-01 → 2023-12-31) only. **Selection rule, declared before
running: highest TRAIN Sharpe; ties within 0.02 Sharpe broken by lower TRAIN MaxDD.**
The single winner is then run **unchanged** on TEST.

| ID | `period` (z window) | `entry` (z threshold) | Construction inside the signalled set |
|----|--------------------|----------------------|-----------------------------------------|
| V1 | 30 (as configured) | 0.8 (as configured) | rank by trailing 126d momentum |
| V2 | 30 | 1.2 | rank by trailing 126d momentum |
| V3 | 126 | 0.8 | rank by trailing 126d momentum |
| V4 | 10 | 0.8 | rank by trailing 126d momentum |
| V5 | 30 | 0.8 | inverse-vol equal weight (construction ablation) |

`period` and `entry` are the strategy's own two parameters; V5 is the one non-parameter
variant, spent deliberately on isolating the effect of the ranking rule rather than on a
sixth threshold. Not tested (would have been a 6th variant): `period=252`, which is the
window the original *actually* uses — see the bug in §9.

**Protocol:** TRAIN = 2016-01-01 → 2023-12-31. TEST = 2024-01-01 → 2026-10-01, touched
once at the end. Buy-and-hold control and a random-signal control are reported on the
same TEST window.

## 3. Data used

- `data/nse/*_1d.csv` via `nsealgo.data.loader.load_universe("data/nse")` (C1–C7 cleaned).
- Daily bars only. No intraday work — 1m/5m/15m is unusable for validation.
- **Survivorship bias is present and disclosed**: the panel is today's NIFTY-50
  backfilled to 2008. Results are optimistic to an unquantified degree.
- Costs: `CostModel(segment="delivery", slippage_bps=5)`; all backtest results are
  **net of `all_in_round_trip_bps` = 21.92 bps** because they come from `run_backtest`.

## 4. Data audit (TRAIN/TEST split) — step 0

`load_universe("data/nse")` → **48 symbols**, **4,629 daily bars**,
**2008-01-01 → 2026-10-01**. Excluded: `adanient` (corrupt, loader rule C3),
`jiofin` (<1000 bars — post-2023 re-listing, a *survivorship artefact* of the
"today's NIFTY-50" universe). 66,312 pre-2008 rows dropped, 3 extreme moves dropped.

| Set | Rows | Window |
|-----|------|--------|
| TRAIN | 1,975 | 2016-01-01 → 2023-12-29 |
| TEST | 685 | 2024-01-01 → 2026-10-01 |

### 4.1 Signal liveness (fraction of symbol-bars signalled LONG)

| ID | period | entry | TRAIN long% | TEST long% |
|----|--------|-------|-------------|------------|
| V1 | 30 | 0.8 | **24.32%** | 29.00% |
| V2 | 30 | 1.2 | 16.23% | 20.06% |
| V3 | 126 | 0.8 | 18.71% | 22.57% |
| V4 | 10 | 0.8 | 26.53% | 30.43% |

24–27% on TRAIN is well above the brief's 5% "effectively always-flat" floor, so this
strategy is *live*, not dormant. With 48 names, ~24% signalled ⇒ **≈11–12 names live on
a typical day** — comfortably inside the 22-name limit, so the constraint will not bind.

### 4.2 The univariate signal has no edge — and the sign looks inverted

Mean unconditional **5-day forward return** by `z(30)` bucket, TRAIN only
(91,275 symbol-bars):

| bucket | n | mean 5d fwd | win% |
|--------|--|-------------|------|
| z ≤ −1.5 | 10,424 | **0.126%** | 54.6% |
| −1.5 < z ≤ −1.0 | 8,747 | 0.428% | 53.5% |
| −1.0 < z ≤ −0.8 | 3,886 | 0.503% | 54.3% |
| −0.8 < z ≤ −0.5 | 5,545 | 0.443% | 54.5% |
| −0.5 < z < +0.8 | 25,619 | 0.549% | 54.7% |
| **+0.8 < z < +1.0** | 4,964 | **0.629%** | 56.3% |
| +1.0 < z ≤ +1.5 | 13,432 | 0.486% | 55.0% |
| z > +1.5 | 18,658 | 0.398% | 52.8% |
| *universe mean* | — | *0.445%* | — |

Two things stand out:

1. **Flat to monotonically decreasing in "reversion-ness".** The strategy's buy bucket
   (`z ≤ −0.8`) has a *worse* mean forward return than the unconditional universe mean
   (0.445%). Deep dips (`z ≤ −1.5`) are the worst bucket of all at 0.126%.
2. **The best bucket is the one the strategy SHORTS** (`+0.8 < z < +1.0`, 0.629%).
   So the raw relation is not mean-reversion — it is mild **momentum**. The strategy is
   pointed the wrong way, and the half we cannot use (the short leg) is the profitable half.

This is *not* a surprise and it is consistent with the existing house evidence:
`src/nsealgo/factors/core.py` already documents that reversal failed in India (Sehgal &
Jain 2011; IIMC 2020 find continuation, not reversal; the only Romano-Wolf
multiple-testing-corrected Indian study had RSI/Bollinger mean-reversion fail at adj.
p 0.071–0.473). `gaussian_strategy` is precisely a Bollinger-style mean-reversion rule
wearing a different hat — the z-score of price levels *is* a Bollinger band, and the
`entry=0.8` threshold is a narrower-than-usual band.

### 4.3 z distribution is not Gaussian

Pooled TRAIN `z(30)`: mean 0.272, **std 1.360**, skew −0.194, kurtosis −0.687. A
standard normal has std 1 and kurtosis 0. The name is a misnomer; price levels are
non-stationary, so a trailing-mean/trailing-sd z-score of *levels* is not the quantity
any distributional argument applies to.

## 5. TRAIN sweep (2016-01-01 → 2023-12-31) — where the winner was chosen

All 5 declared variants, monthly rebalance, net of 21.92 bps.

| id | period | entry | construction | CAGR | Sharpe | MaxDD | Calmar | Vol | Turnover | Cost | Names |
|----|--------|-------|--------------|------|--------|-------|--------|-----|----------|------|-------|
| V1 | 30 | 0.8 | momentum | 12.77% | 0.51 | −32.35% | 0.39 | 12.79% | 4.05x | 1.48% | 26.5 |
| V2 | 30 | 1.2 | momentum | 8.34% | 0.20 | −33.80% | 0.25 | 12.46% | 3.73x | 1.14% | 16.1 |
| V3 | 126 | 0.8 | momentum | 13.16% | 0.54 | −31.56% | 0.42 | 12.74% | 3.27x | 1.12% | 13.6 |
| V4 | 10 | 0.8 | momentum | 10.91% | 0.38 | −32.98% | 0.33 | 13.02% | 4.04x | 1.36% | 25.6 |
| **V5** | **30** | **0.8** | **equalw** | **13.87%** | **0.57** | **−32.46%** | **0.43** | **13.24%** | **4.05x** | **1.54%** | **26.4** |

**Declared selection rule applied: max TRAIN Sharpe → V5 (0.57), single winner, no tie.
V5 is therefore the only variant carried to TEST.** TEST was not consulted before this
choice was made and was run exactly once.

Two observations from TRAIN worth recording even though they are not the verdict:

- **The momentum rank (V1) did *not* help.** V1 (rank by 126d momentum) scored Sharpe
  0.51 against V5's 0.57 for the same `period`/`entry`. The momentum-tilting the brief
  suggests was worth *less* than just letting the engine's inverse-vol scaling handle a
  flat signal. That is convenient here — V5 is the honest "pure gaussian" measurement,
  so the TEST result is not contaminated by a borrowed momentum edge.
- **Everything already looked weak on TRAIN.** Sharpe 0.20–0.57 with a −32% drawdown is
  not a viable book by `GOAL.md` standards. TRAIN was already warning.

## 6. TEST result (2024-01-01 → 2026-10-01) — the verdict

**V5: `period=30`, `entry=0.8`, long-only, inverse-vol equal weight within the
signalled set.** Unchanged from TRAIN. **Net of 21.92 bps** (`all_in_round_trip_bps`,
because it comes from `run_backtest`).

| metric | **V5 (gaussian)** | nsealgo composite | buy-and-hold | random signal (median of 20) |
|--------|-----------------:|------------------:|-------------:|----------------------------:|
| **CAGR** | **5.56%** | 6.55% | **8.16%** | 3.79% |
| **Sharpe** | **−0.04** | 0.07 | **0.18** | −0.21 |
| Sortino | −0.06 | 0.09 | 0.25 | −0.27 |
| **MaxDD** | **−12.43%** (104d) | −14.84% (107d) | −15.91% (107d) | −11.00% |
| Calmar | 0.45 | 0.44 | 0.51 | 0.34 |
| Vol (ann) | 9.80% | 13.20% | 13.44% | 10.05% |
| Turnover | 4.08x/y | 2.07x/y | 1.00x/y | 4.03x/y |
| Cost drag | 1.00%/y | 0.55%/y | 0.08%/y | 0.99%/y |
| Avg names held | 25.2 | 21.3 | 48 | 25.1 |

Cost sanity: `round_trip_bps(100k) = 11.92`, `all_in_round_trip_bps(100k) = 21.92` — the
engine charged **21.92**, as it must. Buy-and-hold is the brief's
`panel.pct_change().mean(axis=1)` series with **one** round trip charged (half on entry,
half on exit); a true held basket that never rebalances gives 7.94% CAGR gross, so the
two benchmark readings agree.

### 6.1 Cost-drag decomposition (identical signals, cost model zeroed)

| | CAGR | Sharpe | MaxDD |
|---|-----:|-------:|------:|
| gross of cost | 6.51% | 0.05 | −12.09% |
| net of cost | 5.56% | −0.04 | −12.43% |
| **drag** | **0.95 pp/yr** | | |

So this is **not** a cost-viability failure: the strategy is positive gross *and* net.
It is simply a low-return book. Costs are a 15% haircut on the return, not the reason it
underperforms.

### 6.2 Calendar-year returns on TEST

| year | V5 | buy-and-hold | composite | random (median) |
|------|-----:|-------------:|----------:|----------------:|
| 2024 | 6.40% | 20.13% | 22.57% | 8.95% |
| 2025 | 14.36% | 13.34% | 7.16% | 11.04% |
| 2026* | −4.35% | −8.37% | −9.01% | −6.66% |

\* partial year to 2026-10-01.

V5's worst year is better than every benchmark's worst year. Its *good* years are worse.
That is the signature of a **low-beta, low-alpha** book, not an edge.

### 6.3 Signal attribution

| | |
|---|---|
| universe mean daily return | +8.83%/yr |
| V5 CAGR (net) | +5.56%/yr |
| V5 vol | 9.80% |
| corr(daily, universe) | 0.874 |
| **beta to universe** | **0.637** |
| **alpha vs universe** | **+0.263%/yr** |
| bars signalled (TEST) | 29.00% |

Beta 0.64 × 8.83% ≈ 5.6% of the return is explained by simply being in the market at
reduced size. **The signal contributes ~0.26%/yr of alpha — statistically nothing.**

### 6.4 Sanity checks (brief §6)

| check | result | verdict |
|-------|--------|---------|
| 1. Plausibility | 5.56% CAGR — no 200%+ bug | ✅ pass |
| 2. Weight count | avg **25.2** names, max 30, never >30 | ⚠️ see §7 |
| 3. Signal liveness | 29.0% of symbol-bars long, ~13.9 names/day | ✅ pass (≫5%) |
| 4. Cost drag | 0.95 pp/yr; positive gross *and* net | ✅ not cost-killed |
| 5. Negative control | beats **16/20** random signals on CAGR (5.56% vs median 3.79%) | ⚠️ marginal |

## 7. Portfolio-construction finding — the signal is ~90% diluted before it reaches the P&L

This is the most important non-verdict result of the run, and it applies to any fast,
high-liveness signal run through this engine.

| | TRAIN | TEST |
|---|---:|---:|
| days | 1,975 | 685 |
| avg names held | 26.40 | 25.22 |
| max names held / days > 30 | 30 / 0 | 30 / 0 |
| avg names signalled that day | 11.67 | 13.92 |
| **invested (Σ weights)** | **64.56%** | **69.34%** |
| **weight in currently-signalled names** | **27.62%** | **30.04%** |
| **carried-over weight, not signalled** | **62.38%** | **59.96%** |
| avg single-name weight | 2.87% | 2.94% |
| max single-name weight | 10.80% (cap 12%) | 10.80% (cap 12%) |

Three separate effects, all of them *intended* engine behaviour that I am not permitted
to bypass (brief §5), but all of which materially blunt this strategy:

1. **The book is only ~65–69% invested, not the 90% the `cash_buffer=0.10` intends.**
   `apply_turnover_budget` blends toward the target (`cur + λ·(tgt−cur)`) and never
   renormalises, so weight bleeds out of the book on every rebalance and only rebuilds
   as the target drifts back.
2. **~25–30 names are held against a 22-name intent.** When the target set is largely
   disjoint from the previous one, the 35% turnover budget cannot close the old book, so
   old names decay instead of closing. `_thin` then caps the book at `max_names=30`.
3. **The consequence: only ~30% of the book is in names the strategy is signalling today.**
   ~60% is a decaying legacy of previous picks.

A signal that fires on 29% of symbol-days is fast-moving; a book that may only turn over
35% of itself per month cannot express it. The reported −0.04 Sharpe is therefore the
result of a strategy that is *mostly* a low-volatility drift book with a small active
overlay — which is also why V5's vol (9.80%) sits so far below the universe's (13.44%).

This is not a correctness bug and I have not changed `src/nsealgo`. But it means the
headline number is not a clean read on the gaussian signal either: a construction that
traded the signal properly would give a *different* answer, in an unknown direction.

## 8. Answers to the brief's seven questions

1. **Strategy / signal / variants.** `gaussian_strategy`: long-only z-score mean-reversion
   on daily closes, `period`-bar trailing window, buy when `z ≤ −entry`, flat otherwise
   (the `z ≥ entry` short leg is unusable in a delivery account). Variants V1–V5 as
   declared in §2 — **5 tested, budget respected, not exceeded.**
2. **TEST table** — §6.
3. **Buy-and-hold, same window** — §6 (8.16% CAGR, Sharpe 0.18, MaxDD −15.91%).
4. **Better or worse?** **Worse on return, better on drawdown.** CAGR **−2.60 pp/yr**
   vs buy-and-hold; Sharpe **−0.22**. MaxDD **3.48 pp shallower** (−12.43% vs −15.91%).
   On Calmar it is marginally worse (0.45 vs 0.51), so the drawdown advantage does not
   buy back the return shortfall.
5. **Random-signal control.** Beats **16/20** seeds on CAGR; median random 3.79% CAGR /
   Sharpe −0.21 vs V5 5.56% / −0.04. It clears the coin-flip bar — by about 1.8 pp/yr,
   which is not much, but it is not a pure coincidence either.
6. **nsealgo composite?** **No — V5 loses to it.** CAGR 5.56% vs 6.55% (−0.99 pp),
   Sharpe −0.04 vs 0.07. V5's only edge is a shallower MaxDD (−12.43% vs −14.84%) and
   lower vol. The house composite strictly dominates it.
7. **Verdict: NO. `gaussian_strategy` does not make money on NSE out-of-sample.** It
   returned 5.56% CAGR at a Sharpe of −0.04 — statistically indistinguishable from the
   risk-free rate — while buying the index, holding the index, and the project's own
   composite all did better.

## 9. Most likely reason it failed, and the one thing to try next

**Reason: it is a mean-reversion strategy and Indian equities exhibit short-term
continuation, not reversal.** This was established on TRAIN before any backtest was run
(§4.2) and the TEST result is consistent with it. The mean forward 5-day return of the
strategy's own buy bucket (`z ≤ −0.8`) is *below* the unconditional universe mean, the
deepest-dip bucket is the worst of all, and the best-performing bucket is the one the
strategy would have **shorted**. The signal is not merely absent — its sign is wrong. This
independently reproduces the finding already recorded in
`src/nsealgo/factors/core.py` (Sehgal & Jain 2011; IIMC 2020; the Romano-Wolf
multiple-testing-corrected Indian study in which RSI and Bollinger mean-reversion all
failed at adjusted p 0.071–0.473). `gaussian_strategy` is a Bollinger-band rule with a
narrower band; it lands in the same failed family.

The long-only mutilation makes it worse: the profitable half of the signal is the half
that requires shorting, and there is no cash-account translation of "short the extension".

**One thing to try next:** nothing inside this strategy. The evidence says the fix is not
a better `period` or `entry` — it is that the only profitable region of this signal is
unreachable without a short leg. If the house wants to use the finding rather than the
strategy, the actionable version is the **inverse** rule as a *separate* strategy
(buy strength, `z ≥ +entry`), which the TRAIN bucket table suggests has the better sign
and which is testable inside the long-only constraint. Note that inverting it makes it a
momentum rule, at which point `build_composite_score` already does that job better — so
the honest expectation is that this line of work should be **closed**, not extended.

Secondary, if anyone revisits it: the `period=300` variant that reproduces the shipped
buffer behaviour (BUG-1) was outside my declared budget and remains untested.

## 10. Bugs

### BUG-1 (in the assigned strategy) — `GaussianConfig.period` is decorative

`gaussian_strategy.py:29` calls `zscore(closes)`, which consumes the **entire buffer**,
not `config.period` bars. The buffer is `deque(maxlen=self._maxlen)` with
`_maxlen = 300` (`signal_base.py:63` and `:39`), so the shipped strategy is a hard-coded
300-bar z-score. Verified:

```
period=10   buffer=[10 bars]  -> z=1.5667   buffer=[210 bars] -> z=1.7238
period=30   buffer=[30 bars]  -> z=1.6752   buffer=[230 bars] -> z=1.7245
period=126  buffer=[126 bars] -> z=1.7184   buffer=[326 bars] -> z=1.7267
```

For the same declared `period` the z-score — and therefore the signal — **changes with
how many bars happen to be in the buffer**. `period` is consumed only by `warmup()`
(line 26), so it is not tunable in any meaningful sense. Secondary effect: in the first
`period` bars after a symbol connects or reconnects, z is computed over a short buffer
and so has different variance — a silent, unlogged regime change in the signal.

**Fix:** `zscore(closes[-self.config.period:])`, or pass the period into the indicator.

**How I handled it:** the NSE port implements a strictly-trailing `period`-bar rolling
z, i.e. the *documented intent*, and deliberately does not reproduce the 300-bar
behaviour. Testing the literal behaviour needs `period=300`, which is outside the
declared budget — flagged, not silently run.

### BUG-2 (in my own harness, caught before reporting) — benchmark over-charged costs 685×

My first `buy_and_hold` helper computed `net = (1 + r) * (1 - rt)`, applying the round
trip to **every daily bar**. Over the 685-bar TEST window that is
`(1 − 0.002192)^685 = 0.2225` — a **78% equity haircut**. It reported the benchmark at
**−36.63% CAGR / −72.16% MaxDD**, wildly inconsistent with the +8.83%/yr mean daily
return of the same series — and that inconsistency is what exposed it.

**Why it matters beyond my own file:** it is the exact mirror image of the failure mode
brief §3 warns about. Overstating cost drag makes a strategy look worse than it is and
can kill a viable result; here it would have turned "gaussian loses to buy-and-hold by
2.6 pp" into the much more dramatic and much less true "gaussian loses to a benchmark
that lost 72%". Fixed to charge half the round trip on the entry bar and half on the
exit bar; all numbers in this report use the fixed version. The strategy result itself
was never affected — it came from `run_backtest`, not from this helper.

**Note on the harness, not a bug but a trap:** the brief's benchmark,
`panel.pct_change().mean(axis=1)`, is a **daily-rebalanced** equal-weight return. A true
held basket is a different series. On this TEST window they happen to agree closely
(8.16% vs 7.94% CAGR) so nothing here hinges on which is used, but they are not the same
thing and should not be conflated in future work.

## 11. Protocol compliance

- Parameter variants tested: **5** (V1–V5). Declared in §2 before any run. **Not exceeded.**
- TEST window opened **once**, after the TRAIN winner was fixed by the pre-declared rule.
- No TEST numbers were used to choose `period`, `entry`, or construction.
- Cost handling: `CostModel(segment="delivery", slippage_bps=5)`; strategy results from
  `run_backtest` are net of **21.92 bps**; the 11.92 bps statutory-only figure is never
  mixed in.
- No lookahead: z, momentum and vol are all strictly trailing; `run_backtest` holds
  weights decided at *t* from *t+1*. The score is built on the full panel (so warmup is
  real at the first TEST bar) and then *sliced* — never reverse-filled.
- Survivorship bias present and disclosed throughout (today's NIFTY-50 backfilled; `jiofin`
  dropped for insufficient history; `adanient` dropped as corrupt).
- Nothing in `src/**` or `tests/**` was modified. No commit made.

## 12. Files

| file | purpose |
|------|---------|
| `harness.py` | shared: rolling z, signal panel, score construction, cost model, buy-and-hold |
| `s0_characterise.py` | data audit, signal liveness, z distribution, forward-return buckets, BUG-1 proof |
| `s1_train_sweep.py` | TRAIN sweep over the 5 declared variants + selection rule |
| `s2_test.py` | the single TEST run: winner, buy-and-hold, composite, random control, attribution |
| `s3_anomaly.py` | diagnosis of the benchmark anomaly (led to BUG-2) |
| `s4_weights.py` | weight-count / dilution diagnostics |
| `train_results.csv`, `test_results.csv`, `test_random_control.csv` | raw outputs |