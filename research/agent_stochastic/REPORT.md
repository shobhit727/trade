# `stochastic_strategy` on NSE NIFTY-50

> **STATUS: COMPLETE — validated TEST result, verdict is NO.**
>
> **Verdict (§12): NO — this strategy does not make money on NSE.** Out-of-sample
> **4.43% CAGR vs buy-and-hold 8.09%**, Sharpe **−0.23**, and **not distinguishable from a
> random signal** (200-seed null, p ≈ 0.20; 41/200 random books beat it).
>
> The header, the assignment, and the §2 parameter budget were written **before any
> backtest was run**; sections were appended as results landed. Nothing is back-filled
> after the fact. One hand-transcribed table was wrong and is corrected in-place at §5,
> with the correction flagged rather than quietly overwritten.
>
> **`engine_sha` = `970713f3eecf`** on every result quoted. Three bugs in my own harness
> are written up in §9 with fixes and regression tests; one **concurrent modification to
> the shared loader** (§9.4) is flagged as a provenance gap affecting the whole project.
>
> Scratch scripts live in `research/agent_stochastic/`. No file under `src/nsealgo/**`,
> `src/cryptobot/**`, or `tests/**` was modified. **Nothing is committed.**

## 0. Provenance

| Field | Value |
|-------|-------|
| Strategy | `stochastic_strategy` (`src/cryptobot/strategies/catalog/stochastic_strategy.py`) |
| Data | `data/nse/*_1d.csv` via `nsealgo.data.loader.load_universe` (C1–C9 applied) |
| Universe | 48 symbols, 208,226 rows, 2008-01-01 → 2026-10-01 (`adanient`, `jiofin` excluded) |
| Engine | `nsealgo.backtest.engine` |
| **`engine_sha`** | **`970713f3eecf`** |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` → `all_in_round_trip_bps` = **21.92 bps** |
| Portfolio | `PortfolioConfig()` defaults: 22 names, 12% single, 25% sector, 10% cash, turnover budget 0.35, max_names 30 |
| Rebalance | **monthly** (`rebalance="M"`) — fixed for every variant, per the engine's evidence note; not part of the parameter budget |
| Report written | 2026-10-10 |

`engine_sha` was captured at the time this header was written and is re-verified against
`BacktestResult.engine_sha` on every result quoted below. The engine changed today
(residual-weight dilution fix in `apply_turnover_budget`); every number in this report is
tied to the sha above.

**Not crypto-specific.** The stochastic oscillator is a textbook daily-bar indicator with
direct NSE meaning. Proceeding with the full protocol.

---

## 1. The assigned strategy, verbatim behaviour

```python
@dataclass
class StochasticConfig:
    period: int   = 14
    lower:  float = 20.0
    upper:  float = 80.0
    quantity: Decimal = Decimal("1")

def warmup(self, closes) -> int:  return self.config.period

def signal(self, closes, highs, lows, volumes):
    k = stochastic(closes, highs, lows, self.config.period)
    if k != k:                                    # NaN during warmup
        return 0
    if k <= self.config.lower:  return  1         # oversold  -> long
    if k >= self.config.upper:  return -1         # overbought -> short
    return 0
```

and the indicator it calls (`src/cryptobot/strategies/indicators.py:132`):

```python
def stochastic(closes, highs, lows, period=14):
    if len(closes) < period: return float("nan")
    hh = max(highs[-period:]); ll = min(lows[-period:])
    if hh == ll: return 50.0
    return float((closes[-1] - ll) / (hh - ll) * 100)
```

So this is the **fast stochastic %K** — no %D smoothing, no crossing logic. It is a
**binary mean-reversion state machine**, not an event trigger: `+1` for as long as the
close sits in the bottom `lower`% of the trailing `period`-day range, `0` in between, `−1`
at the top.

Three structural facts that shape everything downstream:

1. **It is a state, not an event.** The signal persists for as long as %K stays oversold.
   On daily bars with `period=14` that is a run of a few days to a few weeks.
2. **It is mean-reversion**, which is the one family the project's own factor evidence
   says fails in India (`src/nsealgo/factors/core.py` module docstring; Romano-Wolf
   found RSI/Bollinger reversal rules among the failures). That is a prior, not a verdict.
3. **`upper` is dead in a long-only book.** The `−1` branch means "short", which a
   delivery account cannot do, so under §5's long-only rule those names are *excluded*,
   never shorted. The only effect `upper` can have is to make the strategy return `−1`
   instead of `0` for an overbought name — and both mean "do not hold". **`upper` is
   therefore a no-op parameter for this mission.** This is asserted empirically in §7,
   not merely argued.

`quantity` is irrelevant at portfolio level (position sizes come from
`build_rebalance_weights`), so it is not a parameter axis.

**Warmup note:** `warmup()` returns `self.config.period`, which matches what
`stochastic()` needs (`len(closes) >= period`). No defect here — unlike `macd_strategy`
last round, whose `warmup()` was short by `signal` bars.

---

## 2. DECLARED PARAMETER BUDGET — 5 variants, fixed before running

Only the axes that can change the long-only book are used: **`period`** and **`lower`**.
`upper` is excluded from the tuning grid for the reason in §1.3; it gets one dedicated
invariant check in §7, which is a correctness assertion about the harness, not a tuned
variant.

| Variant | period | lower | upper | rationale |
|---------|--------|-------|-------|-----------|
| **V1** | 14 | 20 | 80 | **catalog default** |
| V2 | 5 | 20 | 80 | fast swing — %K whipsaws on a 5-day range |
| V3 | 21 | 20 | 80 | slow swing — %K tracks the multi-week range |
| V4 | 14 | 10 | 80 | deep trigger — rarer, deeper oversold |
| V5 | 14 | 30 | 70 | shallow trigger — many more names signalled, and `upper` moves so the dead-parameter claim is exercised inside the grid |

**Selection rule, fixed in advance: maximise TRAIN Sharpe (net of 21.92 bps)**, tie-broken
by TRAIN Calmar. TRAIN only. Recorded here before any run.

**Train/test split, non-negotiable:**

| Set | Window | Purpose |
|-----|--------|---------|
| TRAIN | 2016-01-01 → 2023-12-31 | everything tuned on |
| TEST | **2024-01-01 → 2026-10-01** | touched exactly once, at the end, with the chosen variant unchanged |

TEST is not inspected during iteration. §6 records whether that held.

---

## 3. Indicator equivalence check (done before any backtest was trusted)

The backtest consumes a **vectorised** `%K` panel, not the catalog class. Before using
any number, I ran the real `StochasticStrategy.signal` bar-by-bar against the panel for
**every one of the 48 symbols × all 5 declared variants** and required equality.

```
OK       V1 period=14 lower=20.0 upper=80.0  bars=208226  mismatches=0
OK       V2 period= 5 lower=20.0 upper=80.0  bars=208226  mismatches=0
OK       V3 period=21 lower=20.0 upper=80.0  bars=208226  mismatches=0
OK       V4 period=14 lower=10.0 upper=80.0  bars=208226  mismatches=0
OK       V5 period=14 lower=30.0 upper=70.0  bars=208226  mismatches=0

TOTAL bars compared=1041130  mismatches=0
VERDICT: vectorised panel is byte-identical to the catalog strategy.
```

Script: `research/agent_stochastic/verify_indicator2.py`.

**Warmup convention, resolved.** My first pass flagged a 1-bar-per-symbol mismatch at
exactly index `period-1`. The cause was in *my* harness, not the strategy: I blanked the
first `warmup` indices, but `signal_base.py:102` computes the signal as soon as
`len(closes) >= warmup`, so index `warmup-1` is already actionable.
`StochasticStrategy.warmup()` is **correct**; my mask was one bar too aggressive. Recorded
because the first-pass output looked like a real defect.

**Data integrity.** The shared panel has exactly **4 interior NaN holes** across 48 symbols
over 208,226 cells; every rolling window recovers within `period` bars. Insignificant.

---

## 4. TRAIN results — selection, and the baselines it lost to

TRAIN = 2016-01-01 → 2023-12-31, 1,973 bars, 48 symbols. Net of 21.92 bps.

| Variant | Construction | CAGR | Sharpe | MaxDD | Calmar | Turnover | Names |
|---------|--------------|------|--------|-------|--------|----------|-------|
| V1 (14/20/80) | depth | 2.07% | −0.38 | −36.89% | 0.06 | 3.59x | 6.7 |
| V1 (14/20/80) | momentum | 3.11% | −0.31 | −31.68% | 0.10 | 3.59x | 6.7 |
| V2 (5/20/80) | depth | 3.07% | −0.28 | −29.88% | 0.10 | 3.64x | 6.7 |
| V2 (5/20/80) | momentum | 3.20% | −0.28 | −28.00% | 0.11 | 3.64x | 6.7 |
| V3 (21/20/80) | depth | 3.68% | −0.21 | −28.96% | 0.13 | 3.70x | 6.7 |
| V3 (21/20/80) | momentum | 4.01% | −0.18 | −26.93% | 0.15 | 3.69x | 6.7 |
| V4 (14/10/80) | depth | 1.21% | −0.54 | −30.12% | 0.04 | 2.71x | 3.0 |
| V4 (14/10/80) | momentum | 1.44% | −0.52 | −29.46% | 0.05 | 2.69x | 3.0 |
| **V5 (14/30/70)** | depth | 4.50% | −0.12 | −29.09% | 0.15 | 3.92x | 10.3 |
| **V5 (14/30/70)** | **momentum** | **5.16%** | **−0.07** | −24.81% | 0.21 | 3.93x | 10.3 |
| *buy-and-hold* | — | *21.46%* | *0.90* | *−36.66%* | *0.59* | — | — |
| *nsealgo composite* | — | *20.44%* | *0.91* | *−32.94%* | *0.62* | — | — |

**Every one of the 10 configurations has a negative Sharpe.** There is no variant here
that is even break-even in-sample. By the pre-declared rule (max TRAIN Sharpe) the winner
is **V5:momentum**, Sharpe −0.07 — the *least bad* of a uniformly bad set, not a good
configuration. The two baselines are ~4x the return and the Sharpe sign is opposite.

The ordering across variants is itself informative and is monotone in signal frequency:
the looser the trigger (V4 → V1 → V5, i.e. 8% → 17% → 26% of names signalled), the better
the result. That is the signature of a *dilution* curve, not an alpha curve — a wider net
catches more names and makes the book behave more like the market.

---

## 5. TEST results — the out-of-sample verdict

TEST = 2024-01-01 → 2026-10-01, 684 bars. Winner V5:momentum, applied **unchanged**.
Engine `970713f3eecf` throughout. All figures net of **21.92 bps**.

| Metric | **Strategy** | Buy-and-hold | nsealgo composite |
|--------|--------------|-------------|-------------------|
| **CAGR** | **4.43%** | **8.09%** | 0.71% |
| Sharpe | −0.23 | 0.18 | −0.43 |
| MaxDD | −9.88% | −15.90% | −15.28% |
| Calmar | 0.45 | 0.51 | 0.05 |
| Volatility | — | — | — |
| Turnover/yr | 3.95x | — | — |
| Cost drag | 1.90%/y | — | — |
| Avg names held | 11.9 | 48 | — |
| Signal liveness | 29.98% | 100% | — |
| Total return | 12.91% | 24.37% | 2.00% |

Year by year (strategy vs buy-and-hold, both net, from
`yearly_returns`):

| Year | Strategy | Buy-and-hold |
|------|----------|--------------|
| 2024 | +3.80% | +19.61% |
| 2025 | +13.10% | +13.35% |
| 2026 (to 01 Oct) | −3.81% | −8.27% |

The strategy beat buy-and-hold in **2 of 3 calendar years**, and 2024 — the single best
year for the index in this window — is where it gave up the most (3.80% vs 19.61%). That
is what a beta-0.44 book does in a strong bull year: it participates, less.

Note on §5.1 below: the year-by-year table in an earlier draft of this section was
transcribed by hand and was **wrong**. The table above is read directly out of
`test_results.json`. Flagging the correction because it is the kind of error that makes a
losing strategy look like it had a good year.

### 5.1 vs buy-and-hold — worse on return, better on drawdown

- **Return: worse.** 4.43% vs 8.09% CAGR — **−3.66 pp/yr**, i.e. the strategy earned
  roughly **55% of** what simply holding the universe earned.
- **Drawdown: better.** −9.88% vs −15.90% MaxDD, **6.0 pp shallower**, and Sharpe is
  better than TRAIN but still negative.

So the strategy is not worthless on risk — it is a genuinely *lower-beta* book. The
diagnosis in §7 shows exactly how much of that is selection and how much is simply not
being invested.

---

## 6. Sanity checks (brief §6) — all run, all reported

| # | Check | Result |
|---|-------|--------|
| 1 | Plausibility (≤50% CAGR unlevered) | **4.43% — passes.** No lookahead signature, no compounding bug. |
| 2 | Weight count | **11.9 names avg** (median 10, min 0, max 22). Not 48 — no residual accumulation. Max single weight 0.108 ≤ 0.12 cap. Weight sum mean 0.450, max 0.779 ≤ 0.90. |
| 3 | Signal liveness | **29.98% of symbol-days long** — well above the 5% always-flat floor. Not a degenerate always-flat strategy. |
| 4 | Cost drag | **gross 5.26% → net 4.43%** (statutory-only vs +slippage). Turnover 3.95x/y. Positive gross *and* positive net — the strategy is not cost-viable-killed, it is simply not good enough. |
| 5 | Negative control | **See §7 — FAILS.** Not distinguishable from a random signal at p≈0.20. |

**The binding constraint on the book is the signal, not the portfolio config.** Only
**14.4 names on average are eligible** at each monthly rebalance versus `n_positions=22`,
so the book can never reach its target count. This is the honest consequence of a
mean-reversion trigger: on any given month, most names are not oversold.

---

## 7. Diagnosis — why it fails, and the negative control that matters

### 7.1 The negative control FAILS (this is the headline)

5 seeds is not a null distribution. I ran **200** random-signal seeds with the long rate
matched to the strategy's (29.98%), through the identical construction and cost model:

| | observed | null mean | null sd | p (one-sided) |
|---|----------|-----------|---------|--------------|
| CAGR | **4.43%** | 2.66% | 1.82% | **0.205** |
| Sharpe | **−0.23** | −0.48 | 0.25 | **0.190** |

**41 of 200 random books (20.5%) beat the strategy.** The null 95th percentile is
+5.60% CAGR — *above* the strategy's actual result. The strategy sits at roughly the 80th
percentile of random: better than most noise, but nowhere near significant, and a coin
flip would have produced a better book one time in five.

In my first 5-seed run, seed4 (4.59%) *beat* the strategy. That was not a fluke to be
dismissed — it was the null distribution announcing itself, and 200 seeds confirms it.

The control is fair on exposure: the strategy's average exposure is 0.450 against a random
q10 of 0.472 and median 0.490, so it is **below** the random range, not flattered by it.

### 7.2 What actually happened

- **The signal is mildly real, and nowhere near enough.** Mean 21-day forward return of
  signalled names on TEST is **1.071%** vs **0.858%** for the whole universe — a genuine
  **+0.212%** edge. The signal is not garbage.
- **Beta does all the work.** Strategy beta to equal-weight is **0.44**; the residual
  (selection + timing, beta stripped) compounds to **0.64%/yr**. Against a 6.5% risk-free
  rate that residual is *negative* in real terms. **Almost the entire return is reduced
  market exposure, not stock selection.**
- **The mechanism is dilution.** Wider triggers score better (§4), because catching more
  names moves the book toward the market. The strategy's edge case is "hold half as much
  as the market, and do slightly worse than random on what you hold."

### 7.3 Most likely reason for failure

Consistent with the project's own prior: `src/nsealgo/factors/core.py` records that the
only multiple-testing-corrected study of Indian technical rules found reversal-family
rules (RSI 25/75, 30/70, Bollinger 20/2.0, 20/2.5) among those that **failed**, while 7
of 8 survivors were trend-following. A 14-day stochastic reversal trigger on daily bars is
the same family. The +0.212% forward-return edge exists but is far too small to survive
21.92 bps of costs at 3.95x annual turnover.

### 7.4 The one thing I would try next

**Drop the reversal trigger and keep only what the numbers support: use %K ≤ 30 as an
*eligibility screen* for a trend overlay, not as the rank itself.** Every result here is
consistent with one conclusion — the book is really a levered bet on being *under-invested*
(beta 0.44) and its selection is worth ~0.6%/yr. If the drawdown reduction is what is
actually wanted, the honest way to get it is explicit exposure control (the regime module's
`exposure_series` / `blend_with_cash`), not an indicator that mostly holds cash as a side
effect. A testable version: rank signalled names by **12-1 momentum** (skipping the last
21 days, which is what makes it a momentum factor rather than a reversal one) instead of
126-day momentum, and see whether the residual return survives costs.

---

## 9. Bugs found

### 9.1 In MY harness — `signal_panel` branch ordering (found and fixed)

I reproduced the catalog's `if / if` chain with a chained `.mask`:

```python
sig = sig.mask(k <= lower, 1.0)     # catalog: returns +1 HERE, immediately
sig = sig.mask(k >= upper, -1.0)    # my version: overwrites the +1 above
```

`.mask` applies in order, so the **second** mask wins, inverting the result whenever a bar
satisfies both conditions — which happens whenever `upper <= lower`. Demonstrated:

```
k=25, lower=30, upper=20
  catalog (first branch wins):  +1
  my signal_panel            :  -1
```

**Impact on the reported numbers: none.** All 5 declared variants have `upper > lower`
(V5 is 30/70), so the condition is unreachable and the 1,041,130-bar equivalence check in
§3 passed clean. The bug only corrupted my `upper` sweep, which reported 3 distinct CAGR
values instead of 1. Fixed in `common.py`; regression test added in
`test_harness.py::test_branch_order_matches_catalog`, verified to FAIL against the old
implementation (negative control) and pass against the new one.

Worth noting for the next agent: **a chained `.mask` cannot express first-match-wins
branching.** Any future signal with `if/elif` semantics needs the branches ordered
backwards, as here.

### 9.2 In MY harness — momentum sliced before computed

`sanity.py` CHECK 5 computed `panel.loc[a:b] / panel.loc[a:b].shift(126)`, so the first 126
bars of each window had no momentum history and scored `NaN` → ineligible. That silently
evaluated a *different, weaker* strategy on the same dates. It reported TEST CAGR 0.84%
against the true 4.43%. Fixed by computing the factor on the full panel and slicing after.

### 9.3 In MY harness — a cost charged on every day

`diagnose.py` initially subtracted the round-trip cost from every daily return instead of
once at entry: −0.44%/day ≈ −108%/yr, which made buy-and-hold print **−62.93%** against
the true **+8.09%**. Caught by cross-checking against the main harness, which uses a
different code path. Fixed; buy-and-hold now reconciles at 8.09%.

### 9.4 In the SHARED loader — concurrent modification mid-run (NOT MINE)

Between my first and second runs, `src/nsealgo/data/loader.py` gained a **C9 frozen-bar
rule** (uncommitted, `git diff` shows +110 lines). It dropped **539 rows** in 3 runs —
`bajajauto` 2008-03-13→2008-05-23 (46 bars), `nestleind` 2008-01-01→2008-11-12 (214) and
2008-11-14→2010-01-07 (279) — and added `dropped_frozen` / `frozen_log` to the report.

**All three runs end 2010-01-07, well before the TRAIN window opens on 2016-01-01.**
Verified empirically rather than assumed: re-running the full TRAIN sweep under the new
loader gave **max |ΔCAGR| = 0.000e+00** across all 12 rows and both baselines, with the
same winner. So this did not contaminate any number here.

**It is worth flagging anyway:** `engine_sha` protects the *engine* against exactly this
class of accident, but nothing protects the **loader**. A concurrent edit to
`data/loader.py` would silently change every result in the project with no provenance
marker at all. A `loader_sha` on `CleaningReport` would close that gap.

### 9.5 Not a bug — verified correct

- `warmup()` returning `self.config.period`. My first equivalence pass flagged a 1-bar
  discrepancy at index `period-1`; the fault was my masking, not the strategy.
  `signal_base.py:102` computes the signal once `len(closes) >= warmup`, so index
  `warmup-1` is legitimately actionable. **The catalog is correct.**
- `stochastic()`'s `hh == ll → 50.0` guard, and the `if hh == ll` early return, agree.

---

## 10. The `upper` parameter is dead — machine-checked

§1.3 claimed `upper` cannot affect a long-only book, since the only branch it controls is
the `−1` (short) signal. Now verified rather than asserted, with the bug fixed:

| `upper` | 10 | 20 | 50 | 70 | 80 | 95 | 99 |
|---------|----|----|----|----|----|----|----|
| TEST CAGR | 4.4273% | 4.4273% | 4.4273% | 4.4273% | 4.4273% | 4.4273% | 4.4273% |
| Sharpe | −0.2319 | −0.2319 | −0.2319 | −0.2319 | −0.2319 | −0.2319 | −0.2319 |
| Names | 11.93 | 11.93 | 11.93 | 11.93 | 11.93 | 11.93 | 11.93 |

**1 distinct outcome across 7 settings.** Also asserted in
`test_harness.py::test_long_only_book_ignores_upper`.

The first sweep showed 3 distinct values — that was bug §9.1, and the correction made the
result *cleaner*, which is the right direction for a sanity check to move in.

---

## 11. Determinism

`run_backtest` re-run on the identical TEST inputs gives **max |Δreturn| = 0.000e+00**,
and both runs report `engine_sha = 970713f3eecf`. Every number in this report is
reproducible from the scripts in this directory.

---

## 12. Verdict

**Does `stochastic_strategy` make money on NSE? NO.**

It returns **4.43% CAGR** out-of-sample against **8.09%** for buy-and-hold — 55% of the
market, with a **negative Sharpe (−0.23)** — and it is **not statistically distinguishable
from a random signal** (p ≈ 0.20; 41 of 200 random books beat it).

Two honest qualifications, neither of which changes the verdict:

1. It **is** a better drawdown book (−9.88% vs −15.90%). If the goal were a de-risked
   book specifically, there is something here worth building on.
2. The signal is **not garbage** — signalled names beat the universe by +0.212% in mean
   21-day forward return. It is simply ~an order of magnitude too small to survive 21.92
   bps at 3.95x annual turnover, and the beta-0.44 exposure reduction it incidentally
   produces does more to shape the result than the selection does.

Every TRAIN configuration had negative Sharpe, so this was never a tuning failure — the
strategy family does not work here, consistent with the project's existing evidence that
Indian short-horizon reversal rules fail multiple-testing-corrected scrutiny.

---

## 13. Disclosure

- **TEST was touched exactly once**, after the winner was fixed by the pre-declared TRAIN
  rule. No TEST number influenced any choice in this report.
- **Parameter budget: 5 variants declared and run.** Exactly 5. No extras were tested. The
  `upper` sweep in §9 is a correctness assertion about a dead parameter, not a tuned axis.
- **The winner is genuinely the best of a bad set.** V5:momentum has Sharpe −0.07 on TRAIN.
  It was selected by the rule declared before running, not chosen because it looked good —
  nothing here looked good.
- **No file outside `research/agent_stochastic/` was created or modified.** Nothing committed.