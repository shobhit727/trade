# AGENT REPORT — `zscore_strategy` on NSE NIFTY-50

**STATUS: COMPLETE. Verdict: NO — it does not make money on NSE.**

> ### TL;DR
> | | TEST 2024-01-01 → 2026-10-01, net of 21.92 bps |
> |---|---|
> | **Strategy (V5)** | **CAGR 5.17% · Sharpe −0.09 · MaxDD −12.52% · 61% invested** |
> | buy-and-hold | CAGR 8.45% · Sharpe 0.20 · MaxDD −15.90% |
> | nsealgo composite | CAGR 6.04% · Sharpe 0.03 · MaxDD −15.22% |
>
> It returned **less than the 6.5% Indian T-bill** — hence the negative Sharpe. It lost to
> buy-and-hold by 3.28 pts/yr and to the production composite by 0.86 pts/yr. Its apparent
> drawdown win **reverses sign at matched exposure** (it was 39% cash, not skill). A
> 20-seed random control lands it dead centre of the distribution.
>
> **But the signal is not empty** — TRAIN rank IC +0.043 (t=8.95). It is too small to pay
> for a selective, cash-heavy, 3.87x-turnover book. See §10.

Append-only. Sections 1–4 and the provenance header were written **before any backtest ran**;
5–12 were appended as results landed.

---

## 0. Provenance

| Field | Value |
|---|---|
| Agent | `agent_zscore` |
| Assigned strategy | `zscore_strategy` |
| Source | `src/cryptobot/strategies/catalog/zscore_strategy.py` |
| Strategy class | `ZscoreStrategy` (`name = "zscore"`) |
| Repo HEAD | `2825d03` |
| **`BacktestResult.engine_sha`** | **`970713f3eecf`** |
| Engine | `src/nsealgo/backtest/engine.py` (`run_backtest`) |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| Round trip charged by engine | `all_in_round_trip_bps(100_000)` = **21.92 bps** (11.92 statutory + 2x5 slippage) |
| Python | `.venv/bin/python` (host venv, tests/research policy) |

> **Engine note.** The engine changed today: a real bug was fixed where dead positions
> decayed slowly instead of exiting (`apply_turnover_budget` now gives unconditional
> priority to exits, `_exit_allocation` sells smallest-first and in whole). `engine_sha`
> is recorded above and echoed into every result table below so these numbers are
> reproducible and cannot be silently compared against a pre-fix run.

**All results in this report are net of 21.92 bps round-trip** (the engine's
`all_in_round_trip_bps`), because every backtest here goes through `run_backtest`.

---

## 1. What the strategy actually is

Source (`src/cryptobot/strategies/catalog/zscore_strategy.py`, 36 lines):

```python
@dataclass
class ZscoreConfig:
    period: int = 20
    entry: float = 0.8
    quantity: Decimal = Decimal("1")

class ZscoreStrategy(SignalStrategy):
    name = "zscore"
    def signal(self, closes, highs, lows, volumes):
        z = zscore(closes)
        if z != z or len(closes) < self.config.period:
            return 0
        if z >= self.config.entry:
            return -1          # SHORT
        if z <= -self.config.entry:
            return 1           # LONG
        return 0
```

* **Signal type**: per-symbol *time-series* mean reversion.
  `z = (last_close - mean(window)) / stdev(window)`.
* `+1` (long) when `z <= -entry` — the close is `entry` sigmas **below** its own trailing mean.
* `-1` (short) when `z >= +entry` — the mirror image.
* `0` otherwise.

**It is NOT crypto-specific.** No funding, no liquidations, no stablecoin pegs, no options
IV, no spot-futures basis. It is a textbook mean-reversion rule and it has a perfectly
ordinary NSE meaning: *buy names that have fallen far enough below their own trailing
mean to expect a bounce.* So the brief's "stop immediately" clause does not apply and
full work proceeds.

### 1.1 Two facts about the source that matter for translation

**(a) The advertised lookback is not the executed lookback.**
`ZscoreConfig.period` (default 20) is used *only* by `warmup()` and the `len(closes)` guard.
`zscore(closes)` (`src/cryptobot/strategies/indicators.py:217`) computes mean and stdev over
**every element of the array it is handed**. The array handed over is the streaming buffer in
`SignalStrategy.__init__`, which is `deque(maxlen=self._maxlen)` with `maxlen=300`, and
`ZscoreStrategy.__init__` does **not** override it:

```python
def __init__(self, config: ZscoreConfig | None = None):
    super().__init__(config or ZscoreConfig())   # maxlen defaults to 300
```

So on live crypto the z-score is measured against a trailing **300-bar** window that grows
into place over the first 300 bars — *not* a 20-bar window. `period=20` only decides when
the strategy is allowed to speak, not what it measures. Whether 20 or 300 is the "true"
strategy is genuinely ambiguous, so **both are carried as explicit variants** (V1, V3)
rather than silently picking one.

**(b) The short branch is dead on arrival here.**
The book is long-only (Indian delivery accounts cannot short, brief §5). The `z >= +entry`
branch therefore never fires. It carries no information for the long side either — it is the
exact mirror — so nothing is lost by discarding it. The entire strategy reduces to:
**hold names whose close is `entry` sigmas below their own trailing mean.**

---

## 2. Translation to the NSE book (the construction)

The strategy is a per-symbol time-series flag. The book is cross-sectional and long-only.
The construction below is the minimum honest mapping and introduces **no momentum term**,
unlike the generic recipe in brief §5.

> Brief §5 suggests ranking signalled names by *trailing momentum*:
> `score = (panel/panel.shift(126)-1).where(signal>0).rank(axis=1, pct=True)`.
> **I am deliberately not doing that for this strategy.** That recipe is a momentum
> construction: among flagged names it buys the strongest 126-day performers. Applied to a
> mean-reversion signal it would systematically prefer names that are *oversold because they
> are still falling* — i.e. it would buy the falling knife and discard the mean-reverting
> bounce. For a trend signal the recipe is right; for a reversal signal it inverts the
> strategy's entire meaning. This is recorded as a deliberate judgement call, not an
> oversight.

Construction actually used:

```
z_t,s   = (close_t,s - rolling_mean_L(close)_t,s) / rolling_stdev_L(close)_t,s   # faithful to catalog
flag_t,s= 1 if z_t,s <= -entry else 0                                            # the long branch only
score_t,s= rank_cross_sectional( -z_t,s )                                        # higher = more oversold
score_t  = score.where(flag > 0)                                                 # only flagged names score
```

* `z` is the **catalog's own time-series z-score**, so the signal is exactly the
  strategy's, not a substitute for it.
* The score is a **cross-sectional percentile of `-z`**, because `build_rebalance_weights`
  ranks whatever it is given and a long-only ₹21L book can only express a *relative*
  preference among today's names.
* Non-flagged names get `NaN` and are therefore **never bought**. The book is deliberately
  allowed to be under-invested (cash) rather than being padded with names the strategy does
  not want. `avg_names` is reported so the cash drag is visible.
* No lookahead: every input at date `t` uses closes up to and including `t`; `run_backtest`
  shifts held weights by one bar so weights decided on the close of `t` earn from `t+1`.

---

## 3. Declared parameter budget — 5 variants, declared BEFORE any run

Per brief §4, written down first and not exceeded. `period` = z-score lookback `L`,
`entry` = the sigma threshold `entry`.

| ID | `L` (z lookback) | `entry` | rationale |
|----|------------------|---------|-----------|
| **V1** | 20 | 0.8 | config defaults **as advertised** by `ZscoreConfig` |
| **V2** | 60 | 0.8 | one trading quarter — the natural swing lookback for a daily-bar NSE system |
| **V3** | 300 | 0.8 | lookback **as actually executed** on crypto (§1.1a) |
| **V4** | 60 | 1.2 | deeper threshold: fewer, more extreme names |
| **V5** | 60 | 0.5 | shallower threshold: more names, more live |

Selection rule, fixed in advance: **pick the highest TRAIN Sharpe among variants whose
signal is at least 5% live** (brief §6.3 — a strategy below ~5% live is effectively
always-flat and "loses only to costs"). If no variant clears 5% liveness, the variant with
the highest liveness is selected and that fact is reported as the headline finding.

Ties broken by TRAIN Calmar, then by variant ID order (V1 < V2 < ...).

---

## 4. Split (non-negotiable)

| Set | Window | Use |
|---|---|---|
| **TRAIN** | 2016-01-01 → 2023-12-31 | variant selection, diagnostics, everything tuned |
| **TEST** | **2024-01-01 → 2026-10-01** | touched exactly once, at the end, with the chosen variant unchanged |

**Rule 4 self-report: TEST has not been inspected at any point in this report's construction
so far.** Every diagnostic in §5 and every number in §6 is TRAIN-only. The single TEST read
happens in §9 and is the last thing written.

---

## 5. Diagnostics (TRAIN only)

`nsealgo.data.loader.load_universe` — 48 symbols retained (`adanient` excluded as
structurally corrupt per rule C3; `jiofin` dropped for <1000 bars — it is a 2025 spin-off
with almost no history). Panel 4,625 daily bars, 2008-01-01 → 2026-10-01.
NaN fraction 6.27% overall, **3.60% inside TRAIN** — the holes are names that listed late
(`eternal` 3,337 NaN, `maxhealth` 3,109, `hdfclife` 2,432, `sbilife` 2,400). Every rolling
stat uses `min_periods=lookback`, so a partially-listed name simply has no score until it
has enough history. It is never forward-filled.

Cleaning: 274,541 rows in → 208,226 out (66,312 dropped pre-2008, 3 extreme).

**Signal liveness (brief §6.3), TRAIN:**

| L | entry=0.5 | entry=0.8 | entry=1.2 |
|---|---|---|---|
| 20 | 32.4% | 25.9% | 17.3% |
| 60 | 27.9% | 22.1% | 14.5% |
| 300 | 19.8% | 15.7% | 10.1% |

Every declared variant is **16–28% live** — comfortably above the 5% floor. This is *not*
an always-flat strategy, so it will not be dismissed on liveness grounds. That makes the
result that follows a genuine negative result rather than a vacuous one.

Flagged names per day at L=60/entry=0.8: median 7, mean 9.9, p90 23, max 46.
**Only 13.2% of days have ≥22 flagged**, and 9.0% of days have none. The strategy is
structurally selective: it cannot fill a 22-name book from its own signal most of the time.

---

## 6. TRAIN selection (all 5 declared variants)

TRAIN 2016-01-01 → 2023-12-29, 1,973 bars. **Net of 21.92 bps.**

| run | CAGR | Sharpe | Calmar | MaxDD | Vol | Total | Turnover | CostDrag | avg names | live |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 L=20 e=0.8 | 6.60% | 0.06 | 0.25 | −26.10% | 10.39% | 67.6% | 3.90x/y | 2.17%/y | 10.6 | 25.9% |
| V2 L=60 e=0.8 | 6.56% | 0.07 | 0.19 | −35.38% | 12.40% | 67.1% | 3.65x/y | 1.98%/y | 9.5 | 22.1% |
| V3 L=300 e=0.8 | 9.42% | 0.27 | 0.29 | −32.09% | 13.33% | 107.1% | 2.31x/y | 1.36%/y | 6.9 | 15.7% |
| V4 L=60 e=1.2 | 3.77% | **−0.19** | 0.13 | −29.11% | 10.75% | 34.9% | 3.16x/y | 1.59%/y | 6.2 | 14.5% |
| V5 L=60 e=0.5 | **10.41%** | **0.35** | **0.32** | −32.73% | 12.34% | 122.7% | 3.82x/y | 2.44%/y | 11.7 | 27.9% |
| **buy-and-hold** | **22.55%** | **0.92** | **0.59** | −37.97% | 16.73% | 417.3% | 0.00x/y | 0.00%/y | 48 | — |

**SELECTED: V5** (L=60, entry=0.5), by the rule fixed in §3 before this was run: highest
TRAIN Sharpe among variants ≥5% live. TRAIN Sharpe 0.35, Calmar 0.32, CAGR 10.41%.

V5 is frozen from here. No further parameter is touched, and TEST is read once.

Two things are already visible in TRAIN and are worth stating before the OOS number:

1. **The ordering of the variants tracks `avg names`, not any property of the signal.**
   The shallowest, most permissive variant (e=0.5) holds the most names and returns the
   most; the strictest (e=1.2) holds fewest and is the only negative-Sharpe variant. That
   is the signature of *market exposure*, not of a z-score edge — a real mean-reversion
   edge would peak at a *moderate* threshold, not monotonically at the loosest one.
2. **The strictest variant is barely alive as a trade and loses to costs anyway** (V4,
   3.77% CAGR at 1.59%/y cost drag). The one variant with a plausible story (deep
   oversold, e=1.2) is the one that does not work.

---

## 7. Sanity checks (brief §6) — TRAIN

| Check | Result | Verdict |
|---|---|---|
| **§6.1 Plausibility** | 10.41% CAGR, unlevered long-only | ✅ plausible, no bug |
| **§6.2 Weight count** | avg 11.7 names, max 22, **0 dead residues** | ✅ no residue accumulation; the post-fix engine is clean |
| **§6.3 Signal liveness** | 27.9% live | ✅ far above the 5% floor — genuinely trading |
| **§6.4 Cost drag** | 2.44%/y; zero-cost diagnostic gives 11.26% vs 10.41% net | ⚠️ costs cost 0.85 pts/yr, but **gross is also weak** — this is not a "viable gross, dead net" case |
| **§6.5 Negative control** | **real Sharpe 0.35 beats only 6/20 random controls (30th pct); random median Sharpe 0.39 > real 0.35** | ❌ **fails** |

**Negative control detail (20 seeds, same number of flagged names per day, same score
shape, only the identities random):**

```
random Sharpe : min 0.30  p25 0.35  median 0.39  p75 0.41  max 0.47
random CAGR   : min 9.46%  median 10.54%  max 11.48%
real   Sharpe :  0.35   real CAGR 10.41%
```

The strategy does not beat a coin flip on TRAIN. The median random book is *better* than
the real one on both Sharpe and CAGR.

**Beta / alpha vs the equal-weight universe (TRAIN):**

| beta | alpha (ann.) | correlation | residual vol (ann.) |
|---|---|---|---|
| 0.636 | **−3.11%/y** | 0.862 | 6.25% |

At beta 0.64, buying the market would have returned ≈0.64 × 22.55% ≈ 14.4%/y. The
strategy returned 10.41%. **It destroys ~3.1 pts of return per year relative to its own
market exposure.** The signal is not adding value; it is selecting a diluted, worse-
performing subset of the board.

**Why the book only runs at 54% invested** (structural, not a bug):

```
invested wt   min 0.0%  p25 33.3%  median 60.1%  p75 75.0%  max 90.0%
by year       2016:54% 2017:57% 2018:63% 2019:55% 2020:51% 2021:47% 2022:54% 2023:54%
```

Flat ~50–60% for eight straight years, so this is not a warm-up ramp. It is the
interaction of two things: the signal only offers ~10 names on a typical day, and
`apply_turnover_budget` gives **unconditional priority to exits** — when a month's flag
set shares few names with last month's, the forced sales consume the entire 35% one-way
allowance and nothing new can be bought that rebalance. In at least one month the book was
**100% cash** (`min 0.0%`). This is the corrected engine behaving as designed; it is a
real property of a selective signal under a turnover budget, and it is why measured beta
is 0.64 rather than ~1.

---

## 8. Bugs / issues found

**No bugs in `src/nsealgo`.** The engine behaved correctly on every check: constraints
held (max single weight 10.80% vs 12% cap), zero dead residues, `engine_sha` stable at
`970713f3eecf` across all runs, and my harness asserts on `engine_sha` after every single
`run_backtest` so a concurrent edit could not silently change a number between scripts.

One **source-level discrepancy in the strategy itself** (not a crash, but a real trap for
anyone reusing this strategy):

* **`ZscoreConfig.period` is documented-by-name as the lookback but is not the lookback.**
  `zscore(closes)` (`src/cryptobot/strategies/indicators.py:217`) computes mean and stdev
  over **every element of the array it is handed**, and `ZscoreStrategy.__init__` does not
  pass `maxlen`, so `SignalStrategy`'s default `maxlen=300` applies. On live crypto the
  z-score is therefore measured against a trailing **300-bar** buffer, not the 20 the
  config advertises. `period` only sets *when the strategy is allowed to speak*
  (`warmup`), not *what it measures*.
  Impact on my run: this is why V1 (L=20) and V3 (L=300) are separate declared variants
  rather than one — the "correct" L is genuinely ambiguous from the source. Anyone
  refactoring this strategy to `zscore(closes[-self.config.period:])` would be **changing
  its behaviour**, not fixing a cosmetic bug, and would need to re-validate it.
* Minor: the `period` guard `len(closes) < self.config.period` can never be false on live
  crypto when `period <= 300`, because `warmup()` already gates on the same condition.
  Dead code in practice.

**One bug in my own harness, found and fixed before it could corrupt a reported number.**

* `06_forward_ic.py` first computed its cross-sectional comparison as
  `(tr - tr.mean(axis=1)) / tr.std(axis=1, ddof=0)`. **`df - series` aligns on COLUMNS,
  not rows**, so every cell became NaN and the entire cross-sectional IC block reported
  `n=0` — an empty result that printed without error and would have been easy to report as
  "no relationship". `nsealgo.factors.core.zscore_cross_sectional` gets this right with
  `factor.sub(mu, axis=0)`. Fixed to `.sub(mu, axis=0).div(sd, axis=0)` and given an
  `assert xs_z.notna().any()`. The fix produced the strongest result in the report
  (63-day IC +0.0760, t=16.70), so the empty panel had been hiding the best evidence in
  the exercise.
* **This did not touch any headline number.** `ts_zscore` derives its mean from
  `panel.rolling(...)`, which returns a *DataFrame*, so `panel - mu` aligns on both axes
  correctly. Only the side-by-side comparison was affected. Stating this explicitly
  because the bug was in a script that also computes reported statistics.
* A second, purely cosmetic bug: `05_dd_attribution.py` printed fractions as percentages
  without the ×100. Caught by checking that the 100%-exposure row reproduced the
  buy-and-hold MaxDD of −15.90% exactly; it printed −0.16%. Fixed and re-run.

---

## 9. TEST evaluation — the single untouched read

**Protocol compliance.** V5 (L=60, entry=0.5) was selected on TRAIN in §6 and run here
unchanged. `selected_variant.json` carries the `engine_sha` it was selected under
(`970713f3eecf`); the script asserts it matches the live engine before running, and prints
`MATCH`. It does. Nothing was re-tuned after seeing a TEST number.

One disclosure: the first execution of `03_test_eval.py` printed the yearly table with the
first calendar year sliced off (`yr[1:]`), which hid 2024. I fixed that reporting bug and
re-ran the identical frozen evaluation — 2024 was a **+20.7%** year for buy-and-hold and
**+21.9%** for the composite against **+6.1%** for the strategy, so the fix *worsens* the
strategy's relative showing. No parameter was touched.

**Window: 2024-01-01 → 2026-10-01, 684 bars, 48 symbols. Net of 21.92 bps.**

| run | CAGR | Sharpe | Calmar | MaxDD | Vol | Total | Turnover | CostDrag | notes |
|---|---|---|---|---|---|---|---|---|---|
| **V5 STRATEGY** | **5.17%** | **−0.09** | 0.41 | −12.52% | 9.41% | 15.2% | 3.87x/y | 1.90%/y | avg 13.8 names, 61.0% invested |
| **buy-and-hold** | **8.45%** | **0.20** | 0.53 | −15.90% | 13.46% | 25.5% | 0.00x/y | 0.00%/y | 48 names, equal weight |
| **nsealgo composite** | 6.04% | 0.03 | 0.40 | −15.22% | 13.25% | 17.9% | 2.08x/y | 1.10%/y | production factor blend |
| zero-cost *(diagnostic, not reportable)* | 5.99% | −0.00 | 0.49 | −12.21% | 9.40% | 17.7% | 3.87x/y | 1.04%/y | — |

**Yearly (TEST; first year measured from a starting equity of 1.0, so 2024 is partial):**

| | 2024 | 2025 | 2026 (to 01-Oct) |
|---|---|---|---|
| V5 STRATEGY | +6.1% | +13.6% | −4.4% |
| buy-and-hold | +20.7% | +13.4% | −8.3% |
| nsealgo composite | +21.9% | +6.6% | −9.3% |

### 9.1 vs buy-and-hold (identical window, both net)

| | strategy | buy-and-hold | delta |
|---|---|---|---|
| CAGR | 5.17% | 8.45% | **−3.28 pts** ❌ |
| Sharpe | −0.09 | 0.20 | **−0.29** ❌ |
| Calmar | 0.41 | 0.53 | −0.12 ❌ |
| MaxDD | −12.52% | −15.90% | +3.38 pts — **but see 9.3** |

**Worse on return by 3.28 pts/yr, worse on risk-adjusted return. The drawdown comparison
does not survive scrutiny** (9.3).

### 9.2 The drawdown result is an artifact of holding cash

The strategy averaged **61.0% invested**; buy-and-hold is 100% invested. A book that is
39% cash will mechanically have a shallower drawdown, and that is not selection skill.
Re-running buy-and-hold at the strategy's own average exposure:

| exposure | CAGR | MaxDD | Calmar |
|---|---|---|---|
| 100% | 8.45% | −15.90% | 0.53 |
| 80% | 8.22% | −12.40% | 0.66 |
| 70% | 8.07% | −10.61% | 0.76 |
| **61% (strategy's actual)** | **7.92%** | **−8.98%** | **0.88** |
| 50% | 7.72% | −6.94% | 1.11 |

> **At matched exposure, buy-and-hold's drawdown was 3.54 pts *shallower* than the
> strategy's** (−8.98% vs −12.52%). The apparent drawdown advantage reverses sign
> entirely. The z-score signal makes the drawdown **worse**, not better; the only thing
> softening it was the cash the signal forced us to hold.

### 9.3 Random-signal control

20 seeds, same number of flagged names per day, same score shape, random identities:

| window | strategy Sharpe | random Sharpe (min / median / max) | beat rate |
|---|---|---|---|
| TRAIN | 0.35 | 0.30 / **0.39** / 0.47 | **6/20 — 30th pct (LOSES)** |
| TEST | −0.09 | −0.41 / −0.14 / +0.05 | 15/20 — 75th pct |

**The sign of this comparison flips between the two windows**, which is itself the finding:
there is no stable edge. On TRAIN the strategy lost to the median random book; on TEST it
beat 15/20 — but note that *every* random control on TEST had a negative Sharpe, so being at
the 75th percentile of an entirely losing pack is not evidence of anything.

Decisive framing: on TEST the random controls span **2.35%–6.56% CAGR and the strategy
returned 5.17% — dead centre of the distribution, against buy-and-hold's 8.45%. Not one
of the 20 random books, and not the strategy, beat simply holding the index.**

### 9.4 vs the nsealgo composite

| | strategy | composite | delta |
|---|---|---|---|
| CAGR | 5.17% | 6.04% | −0.86 pts ❌ |
| Sharpe | −0.09 | 0.03 | −0.12 ❌ |
| MaxDD | −12.52% | −15.22% | +2.70 pts (cash artifact, per 9.2) |

**It loses to the production composite on every measure that survives the cash adjustment.**

### 9.5 Beta / alpha

| beta | alpha (ann.) | correlation | residual vol (ann.) |
|---|---|---|---|
| 0.585 | **+0.22%/y** | 0.835 | — |

Alpha is indistinguishable from zero. At beta 0.585 the strategy is a diluted market bet
that adds no return per unit of risk.

---

## 10. Why it failed — and the part that is genuinely interesting

The obvious conclusion ("mean reversion doesn't work in India") is **not what the data
shows**, and reporting only that would be wrong. On TRAIN the rank information coefficient
of this signal is **statistically significant and positive in exactly the direction the
book trades** (21-day horizon, `06_forward_ic.py`):

| signal | fwd 5d | fwd 21d | fwd 63d |
|---|---|---|---|
| time-series z (the catalog's) | +0.0265 (t 5.44) | **+0.0432 (t 8.95)** | +0.0325 (t 7.46) |
| cross-sectional z (alternative) | +0.0122 (t 2.62) | +0.0367 (t 7.61) | **+0.0760 (t 16.70)** |

**The signal genuinely predicts forward returns.** Buying oversold names does outperform
buying extended ones in this data.

**So the failure is one of magnitude, not of sign.** To beat buy-and-hold, a book running
at beta 0.585 with 39% cash needs roughly +4 pts/yr of alpha just to catch up, before
paying 1.90%/y in costs. The measured out-of-sample alpha is +0.22%/y. The edge is
statistically real and economically far too small to survive (a) the cash the selectivity
forces into the book and (b) 3.87x/y turnover.

This refines — without overturning — the prior recorded in `src/nsealgo/factors/core.py`,
which cites Sehgal & Jain (2011), IIMC (2020) and the Romano-Wolf-corrected technical study
to exclude reversal from the production composite. **My IC result is consistent with that
decision while adding precision the portfolio numbers hide: reversal in Indian cash equities
is not zero, it is small and real, and small-and-real is exactly what a 22-name,
cash-buffered, monthly-rebalanced, cost-paying book cannot monetise.**

### The one thing I would try next

**Not another threshold.** The declared budget is spent and the TRAIN ordering shows
thresholds mostly buy exposure, not edge.

**Test the cross-sectional construction of the same idea, at the 63-day horizon.** It is
the strongest number in this entire exercise — IC +0.0760, t = +16.70 — and it is *not* a
re-run of the same bar:

* The catalog's z is a **time-series z on a price level**, so it is heavily contaminated
  by an ongoing trend: in a sustained downtrend a name sits permanently far below its own
  trailing mean and the signal keeps calling it "oversold" long after the bounce has gone.
* A **cross-sectional** z measures oversoldness *relative to the rest of the board today*,
  which is trend-free by construction.
* The 63-day horizon matches where the cross-sectional signal is strongest, and is
  naturally aligned to a monthly rebalance with low turnover (the time-series z at 63d
  manages only +0.0325 — the construction matters more than the lookback).

Caveat, stated plainly: **that IC is a TRAIN observation and is not validated
out-of-sample.** It is a hypothesis with a measured reason behind it, not a result. The
discipline that produced §9 has to apply to it too — it gets one frozen TRAIN selection and
one OOS read, and it must be expected to fail the same way if the problem is the market
rather than the construction.

---

## 11. Verdict

> ### No. `zscore_strategy` does not make money on NSE.
>
> On the held-out window (2024-01-01 → 2026-10-01) it returned **5.17%/y net of the full
> 21.92 bps Indian delivery stack** — **below the 6.5% Indian T-bill**, which is why its
> Sharpe is **negative (−0.09)**. It lost to buy-and-hold by **3.28 pts/yr of CAGR and
> 0.29 of Sharpe**, and lost to the nsealgo production composite by 0.86 pts/yr. Its one
> apparent advantage — a shallower drawdown — **reverses sign at matched exposure**: it was
> 39% cash, not skill. A 20-seed random control with identical position counts lands the
> strategy dead centre of the distribution (2.35%–6.56% CAGR), confirming it is
> indistinguishable from noise.
>
> The signal is not empty — its rank IC on TRAIN is +0.043 (t=8.95). It is simply **too
> small to pay for a selective, cash-heavy, 3.87x-turnover book in this market**, which is
> a more precise statement of the prior already encoded in `factors/core.py` than the
> portfolio numbers alone give.

**Parameter budget: 5 declared, 5 used.** No sixth variant was run. TEST was read once.

---

## 12. Reproduce

```bash
.venv/bin/python research/agent_zscore/00_data.py           # data + liveness (TRAIN)
.venv/bin/python research/agent_zscore/02_train_select.py   # 5 variants -> selection
.venv/bin/python research/agent_zscore/04_train_controls.py # random control, beta, cost
.venv/bin/python research/agent_zscore/03_test_eval.py      # THE single TEST read
.venv/bin/python research/agent_zscore/05_dd_attribution.py # drawdown vs exposure
.venv/bin/python research/agent_zscore/06_forward_ic.py     # rank IC (TRAIN only)
```

Artifacts: `panel.pkl`, `train_results.json`, `selected_variant.json`,
`train_controls.json`, `test_results.json`, `dd_attribution.json`, `forward_ic.json`.