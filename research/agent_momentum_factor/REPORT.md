# `momentum_factor_strategy` on NSE NIFTY-50 — agent report

**Status:** COMPLETE — validated negative finding. All 5 declared variants tested; TEST touched once.
**Assigned strategy:** `src/cryptobot/strategies/catalog/momentum_factor_strategy.py`
(`MomentumFactorStrategy`, name = `momentum_factor`)
**Agent:** `momentum_factor`
**Scratch dir:** `research/agent_momentum_factor/`

---

## 1. What the strategy actually is (read before anything else)

```python
def signal(self, closes, highs, lows, volumes):
    m = roc(closes, self.config.period)          # close[t] / close[t-period] - 1
    if m != m:
        return 0
    return 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)
```

`roc()` is a pure **trailing** return. The whole strategy is:

> **the sign of the `period`-bar return, gated by a symmetric `threshold` deadband.**

It is a **per-symbol time-series** signal. It contains **no cross-sectional information**
despite the "factor" name: nothing in the file compares one symbol to another. Per brief §5,
the NSE book is long-only and cross-sectional, so the signal has to be translated — the
signalled names get ranked cross-sectionally and the score panel goes to `run_backtest`,
which enforces `PortfolioConfig`.

**Long-only translation** (the NSE delivery book cannot short):
> hold a name on the days its `period`-bar return sits outside the `±threshold` deadband,
> weighted by rank among the names that qualify.

### 1.1 Relationship to a sibling strategy — stated up front, because it matters

`momentum_factor_strategy` and `cross_sectional_strategy` are **the same code with different
default constants**. Both files are 32 lines, both call `roc(closes, period)` and both apply
the identical symmetric deadband. The only difference in the whole strategy is the catalog
default `threshold`:

| file | `period` | `threshold` |
|---|---|---|
| `momentum_factor_strategy.py` (mine) | 20 | **0.005** |
| `cross_sectional_strategy.py` | 20 | 0.015 |

I am assigned `momentum_factor_strategy`. I will run it as assigned, on its own parameters,
under my own declared budget. I flag the overlap because a sibling report
(`research/agent_cross_sectional/REPORT.md`) has already published TEST-window numbers for
the *same signal family* at threshold 0.015. That report is **not** my result and I do not
reuse its numbers; but it means (a) the family has been characterised before, and (b) any
*independent* confirmation of a negative finding here is genuinely valuable — and equally,
any positive finding I produced would need heavy scepticism. **This is disclosed so it can
be weighed, not hidden.**

---

## 2. DECLARED PARAMETER BUDGET — exactly 5 variants, no more

Declared here and in `research/agent_momentum_factor/common.py::VARIANTS`, **before any
backtest is run**.

| tag | period | threshold | rank_days | rebalance | note |
|-----|--------|-----------|-----------|-----------|------|
| **M1** | 20 | 0.005 | 20 | M | **the catalog defaults, verbatim** (20 / 0.005), ranked by its own ROC |
| M2 | 20 | 0.005 | 126 | M | catalog flag, ranked by 6-month momentum (brief §5 construction) |
| M3 | 60 | 0.05 | 60 | M | slower signal, deadband scaled to the period |
| M4 | 126 | 0.08 | 126 | M | 6-month signal — the horizon the engine's own evidence doc favours |
| M5 | 20 | 0.005 | 20 | W | catalog defaults, weekly rebalance instead of monthly |

* `period` / `threshold` = the strategy's **own** parameters. M1 is the catalog file exactly
  as shipped, with no tuning whatsoever — if the catalog defaults fail, that is the most
  honest result available.
* `rank_days` = the horizon used to *rank* the names the strategy flags. `rank_days == period`
  is the pure reading ("buy the strongest of my own signalled names"); `rank_days > period`
  is the brief §5 construction ("rank the signalled names by longer trailing momentum").
  Note the M1 deadband is **half** the sibling's, so M1 flags many more names.

**Selection rule (declared, fixed before running):** highest **TRAIN** Sharpe, tie-break
shallowest (least negative) TRAIN MaxDD. Only the winner is ever run on TEST. A 6th variant is
not permitted and will not be run; if I am tempted I will say so in the report rather than
quietly doing it.

**Why Sharpe and not CAGR:** Sharpe is the risk-adjusted criterion and is what `GOAL.md` §5
gates on. I declare now — *before seeing any result* — that a variant whose TRAIN Sharpe is
merely **beta-inflated** (i.e. buy-and-hold beat it on TRAIN) is not a winner, and I will
report the TRAIN-vs-buy-and-hold gap for every variant regardless of who "wins".

**Split (non-negotiable):**
* **TRAIN** 2016-01-01 → 2023-12-31 — everything tuned on.
* **TEST** 2024-01-01 → 2026-10-01 — touched exactly once, at the end.

---

## 3. Data

`data/nse/<symbol>_1d.csv` via `nsealgo.data.loader.load_universe("data/nse")` — the
cleaned daily close panel. **Daily bars only.** `1m` does not exist and `5m`/`15m` cover
~7 weeks, so no intraday work is attempted and no intraday claim is made.

**Survivorship bias is PRESENT** (today's NIFTY-50 backfilled to 2002). Every number in this
report is biased optimistic for that reason.

---

## 4. Cost basis

`CostModel(segment="delivery", slippage_bps=5)` — the full Indian delivery stack.

Every result below goes through `run_backtest`, which never calls `fill_price`, so the engine
charges `all_in_round_trip_bps(100_000)` = **21.92 bps** round trip
(11.92 statutory + 2 × 5 bps slippage). **Every backtest number in this report is net of
21.92 bps.** The 11.92 bps statutory figure appears only in the cost sanity check.

---

## 5. Verification log

### V1 — data audit (`00_load.py`) ✅
```
rows in 274,541 -> out 208,226 | dropped pre-2008 66,312 | extreme 3
excluded: ['adanient', 'jiofin']   symbols 48   panel (4625, 48)
index 2008-01-01 -> 2026-10-01 Asia/Kolkata   NaN cells 13,916
TRAIN  1,973 bars (2016-01-01 -> 2023-12-29)
TEST     684 bars (2024-01-01 -> 2026-10-01)
TRAIN equal-weight CAGR +22.31%   TEST equal-weight CAGR +8.30%
```
Both windows are fully covered. **Survivorship bias present** — today's NIFTY-50 backfilled
to 2008; `adanient`/`jiofin` excluded by the loader as too short to survive. Every number
below is biased optimistic on that account.

TRAIN was a strong tape (+22.31 %/yr equal-weight) and TEST a weaker one (+8.30 %/yr).
That matters for §2's caveat: TRAIN Sharpe will be inflated by beta.

### V2 — signal equivalence (`10_verify_signal.py`) ✅ **PASS**
The vectorised `strategy_signal` was compared bar-by-bar against the **actual catalog class**
`MomentumFactorStrategy.signal` over all 48 symbols, all 5 declared parameter sets:

| variant | params | bars compared | result |
|---------|--------|---------------|--------|
| M1 | period 20, thr 0.005 | 207,044 | **IDENTICAL** |
| M2 | period 20, thr 0.005 | 207,044 | **IDENTICAL** |
| M3 | period 60, thr 0.05 | 204,988 | **IDENTICAL** |
| M4 | period 126, thr 0.08 | 201,705 | **IDENTICAL** |
| M5 | period 20, thr 0.005 | 207,044 | **IDENTICAL** |

Zero mismatches. The harness measures the strategy I was assigned, not a lookalike.

**Signal liveness (brief §6 check 3) — fraction of name-bars by state:**

| variant | window | long | flat | short | avg long-eligible names/day |
|---------|--------|------|------|-------|------------------------------|
| M1/M2/M5 | TRAIN | 53.6% | 8.8% | 37.6% | 25 |
| M1/M2/M5 | TEST | 51.5% | 6.5% | 42.0% | 24 |
| M3 | TRAIN | 46.4% | 31.3% | 22.3% | 22 |
| M3 | TEST | 42.1% | 34.0% | 23.9% | 20 |
| M4 | TRAIN | 48.0% | 33.1% | 18.9% | 23 |
| M4 | TEST | 45.7% | 35.6% | 18.7% | 21 |

All far above the 5% floor, so "effectively always flat" is **ruled out** for every variant.

⚠️ **Structural warning from this table:** the catalog deadband (`±0.5 %` on a 20-day ROC)
leaves only **6.5 % of TEST name-bars flat** and flags **24 of 48 names long on an average
day** — against a book that can only hold 22. The gate is therefore **near-non-binding**:
M1/M2/M5 will behave almost identically to "rank all 48 names by 20-day ROC". M1 has
essentially no strategy-specific content. This is recorded now, before any return is seen.

### V3 — two bugs in **my own harness**, found and fixed before trusting any number
The first TRAIN sweep produced an impossible table (Sharpe 44, turnover 408×/yr,
`avg_names` 1956 for a 48-name universe, buy-and-hold "best day +99.78 %"). Both causes were
mine, in `research/agent_momentum_factor/common.py`; neither touched `src/`:

1. **`benchmark_buy_hold` mangled the first bar.** It subtracted the deployment cost from a
   *return* instead of from *equity*, then set `daily[0]` to that number — inventing a
   +99.78 % first-day gain and inflating buy-and-hold's Sharpe to 20.8. Rewritten to charge
   the cost against equity and earn returns from the second bar. Fixed BH now prints
   TRAIN 21.49 % CAGR / Sharpe 0.90 / MaxDD −36.66 %, which reconciles with the raw gross
   equal-weight CAGR of 22.31 % less the one-off cost.
2. **`fmt_table` guessed units by magnitude** (`abs(v) < 20` → treat as a fraction). That
   printed `avg_names` 19.57 as `1956.51` and Sharpe 0.649 as `64.90`. Replaced with an
   explicit percent-column set. The underlying `avg_names` was always correct (max 30 =
   `max_names`, verified against the engine directly).

**Re-run after the fix — every number below this line is post-fix.**

### V4 — TRAIN sweep of the 5 declared variants (`20_train_select.py`) ✅
Selection rule as declared: max TRAIN Sharpe, tie-break shallowest TRAIN MaxDD.
**TRAIN only — TEST untouched.**

| tag | period | thr | rank_d | reb | CAGR % | Sharpe | MaxDD % | Calmar | Turn x/y | Cost %/y | avg names | **edge vs BH pp/yr** |
|-----|--------|-----|--------|-----|--------|--------|--------|--------|----------|----------|-----------|---------------------|
| M1 | 20 | 0.005 | 20 | M | 6.89 | 0.087 | −26.63 | 0.26 | 4.11 | 2.30 | 19.3 | **−14.60** |
| M2 | 20 | 0.005 | 126 | M | 10.94 | 0.444 | −24.19 | 0.45 | 4.02 | 2.63 | 19.2 | **−10.56** |
| M3 | 60 | 0.05 | 60 | M | 12.59 | 0.482 | −33.35 | 0.38 | 3.70 | 2.64 | 17.5 | **−8.91** |
| **M4** | 126 | 0.08 | 126 | M | 15.11 | **0.608** | −35.59 | 0.42 | 3.09 | 2.44 | 17.8 | **−6.38** |
| M5 | 20 | 0.005 | 20 | W | 9.45 | 0.286 | −23.14 | 0.41 | 14.01 | 8.26 | 19.1 | **−12.05** |
| **BH** | — | — | — | — | **21.49** | **0.90** | −36.66 | 0.59 | 0.00 | 0.03 | 48 | — |

**SELECTED ON TRAIN: M4** (Sharpe 0.608, unique maximum — no tie, so the tie-break was not
exercised). Frozen from here; only M4 goes to TEST.

🔴 **The decisive TRAIN finding, stated before TEST is opened: variants beating
buy-and-hold on TRAIN = 0 of 5.** Every one is behind, by 6.38 to 14.60 pp/yr. Buy-and-hold
itself scores a TRAIN Sharpe of **0.90** — higher than every variant, including the selected
one. M4 "wins" the declared rule only because all five candidates are worse than doing
nothing. **The declared selection rule picked the least-bad loser, not a winner.**

Note also that **M1 — the catalog's own shipped defaults, run verbatim with no tuning at
all — is the worst variant on TRAIN** (Sharpe 0.087, 14.60 pp/yr behind). If this strategy
has any chance anywhere, it is not at its defaults.

The TRAIN beta-inflation caveat flagged in §2 is realised: TRAIN was a +22.3 %/yr tape, so
every long-only book printed a respectable Sharpe. Sharpe alone could not have told me the
market beat all of them — the CAGR column does, and it is reported for every variant.


---

## 6. Results

### 6.1 TEST — the single out-of-sample evaluation (`30_test_eval.py`)

**M4, frozen on TRAIN, evaluated unchanged** on TEST 2024-01-01 → 2026-10-01
(684 bars, 2.80 y). Costed at the engine's `all_in_round_trip_bps` = **21.92 bps**
round trip (11.92 statutory + 2 × 5 bps slippage).

| metric | **STRATEGY M4** | buy-and-hold | nsealgo composite | random control (5 seeds) |
|---|---|---|---|---|
| **CAGR %** | **−0.36** | **+8.18** | +6.04 | +5.45 |
| **Sharpe** | **−0.48** | +0.18 | +0.03 | −0.05 |
| Sortino | −0.57 | +0.25 | +0.04 | — |
| **MaxDD %** | **−23.10** | **−15.90** | −15.22 | −12.04 |
| **Calmar** | **−0.02** | +0.51 | +0.40 | — |
| Vol % | 12.37 | 13.45 | 13.25 | — |
| Total % | −1.02 | +24.64 | +17.86 | — |
| Turnover x/yr | 3.17 | 0.00 | 2.08 | ~3.2 |
| **Cost drag %/yr** | **1.57** | 0.08 | 1.10 | ~1.6 |
| Trades /yr | 11.77 | 0.36 | 11.77 | 11.77 |
| Win rate % | 51.02 | 53.80 | 51.75 | — |
| **avg names held** | **16.8** | 48 | 21.3 | 21.3 |

Cost actually charged: **Rs 92,290** on the Rs 21,00,000 book over 2.80 y (≈ 1.57 %/yr).
Max single weight 10.80 % (cap 12 %), mean invested 80.1 % (target 90 %) — the shortfall is
the 25 % sector cap, which is binding by design.

Yearly:

| year | strategy | buy-and-hold |
|---|---|---|
| 2024 | +18.16% | +19.87% |
| 2025 | −0.13% | +13.35% |
| 2026 (to 01 Oct) | −16.12% | −8.27% |

### 6.2 Head-to-head vs buy-and-hold (identical window, identical costs)

* **Return: WORSE by 8.54 pp/yr** (−0.36 % vs +8.18 % CAGR).
* **Drawdown: WORSE (deeper) by 7.20 pp** (−23.10 % vs −15.90 %).

It lost on **both** axes. There is no risk-adjusted argument for holding it: the strategy is
also *less* volatile (12.37 % vs 13.45 %), so the underperformance is not a risk-taking
difference — it is simply a worse return stream.

### 6.3 Random-signal control — **FAILED**

Matched on cross-sectional selectivity (same number of eligible names per rebalance, so
turnover and cost drag are comparable), zero signal. Five seeds:

| seed | 1 | 2 | 3 | 4 | 5 | mean |
|---|---|---|---|---|---|---|
| CAGR % | 5.94 | 6.77 | 5.21 | 1.67 | 7.67 | **+5.45** |
| Sharpe | −0.00 | +0.08 | −0.08 | −0.40 | +0.16 | **−0.05** |
| MaxDD % | −11.44 | −11.21 | −11.64 | −14.66 | −11.25 | **−12.04** |

**A coin flip beat the strategy by 5.81 pp/yr of CAGR and 0.44 of Sharpe, and drew down
11.06 pp less.** Four of five seeds beat it on return; four of five beat it on drawdown.
Beating a coin flip is the minimum bar (§6.5) and this is well below it.

### 6.4 vs the nsealgo composite — **LOST**

Composite +6.04 % CAGR / Sharpe +0.03 / MaxDD −15.22 % vs the strategy's −0.36 % /
−0.48 / −23.10 %. Worse by **6.40 pp of CAGR** and **7.88 pp deeper in drawdown**. The
house default dominates it on every axis. It does not deserve to replace the composite.

### 6.5 All 5 declared variants on TEST (reporting only — M4 stays the frozen pick)

| tag | CAGR % | Sharpe | MaxDD % | Turn x/y | Cost %/y | avg names |
|---|---|---|---|---|---|---|
| M1 | −1.54 | −0.87 | −19.25 | 4.16 | 1.95 | 18.3 |
| M2 | −0.66 | −0.59 | −22.41 | 4.09 | 2.00 | 18.1 |
| M3 | −1.62 | −0.61 | −23.20 | 3.90 | 1.89 | 16.6 |
| **M4** (TRAIN pick) | **−0.36** | **−0.48** | −23.10 | 3.17 | 1.57 | 16.8 |
| M5 | −0.62 | −0.54 | −20.13 | 13.35 | 6.29 | 18.6 |

**All five are negative out-of-sample. Zero of five make money.** This is not a
selection failure — the whole declared family fails on TEST. (M4 does happen to rank best
on TEST too, but on a −0.36 % base; that is noise, not skill.)

---

## 7. Sanity checks (brief §6) — `50_sanity.py`. All PASS; the failure is real.

| # | check | result |
|---|---|---|
| **1** | Plausibility | TRAIN CAGR 15.11 %, TEST −0.36 %. Nowhere near the 40–50 % unlevered ceiling → no lookahead, no mis-indexed score panel, no compounding bug. **PASS** |
| **2** | Weight count | avg **16.8** names held on TEST, **max 22** (= `n_positions`), **0** rows above 30. Max single weight 10.80 % (cap 12 %), mean invested 80.1 % (target 90 %, shortfall is the binding 25 % sector cap). No residual accumulation. **PASS** |
| **3** | Signal liveness | long on **45.7 %** of TEST name-bars (flat 35.6 %, short 18.7 %). Far above the 5 % floor — the "effectively always flat" failure mode is ruled out. **PASS** |
| **4** | Cost drag | 1.57 %/yr. **NOT the cause of the failure**: at **zero cost** the strategy still makes only **+0.27 % CAGR**; at double slippage −1.00 %. There is no gross edge for cheaper execution to rescue, and `GOAL.md` §6.4 forbids trying anyway. |
| **5** | Random control | **FAIL** — see §6.3, lost by 5.81 pp CAGR. |
| **6** | No-lookahead, empirical | Truncating the panel at 2020-06-30 / 2023-06-30 / 2025-03-31 / 2026-04-30 and re-running reproduces the full-history equity curve **exactly** (max diff `0.000e+00`, 3,072–4,515 overlapping bars). No future bar reached a past decision. **PASS** |
| **7** | Cost model sanity | Statutory round trip at Rs 1,00,000 = **11.92 bps** (published 11.65–11.66); engine charges **21.92 bps** all-in. Every number above is net of 21.92. **PASS** |

---

## 8. Why it failed (`40_diagnose.py`, on the frozen M4)

### 8.1 The signal is a **reversal** signal, not a momentum signal

Each leg of the strategy, scored against the forward 21-bar return (arithmetic mean scaled
by 244/21; overlapping windows are **not** compounded — see BUG-5):

| window | leg | n | mean fwd 21d | annualised | win % | t |
|---|---|---|---|---|---|---|
| TRAIN | long (ROC126 > +8%) | 45,450 | +1.72% | **+20.0 %** | 58 | +41.5 |
| TRAIN | flat | 27,940 | +1.24% | +16.4 % | 58 | +27.3 |
| TRAIN | short (ROC126 < −8%) | 17,908 | +3.15% | **+38.0 %** | 64 | +43.0 |
| **TRAIN** | **long − short spread** | | | **−17.05 pp/yr** | | |
| TEST | long | 14,659 | +0.92% | **+10.0 %** | 54 | +14.7 |
| TEST | flat | 11,262 | +0.73% | +8.0 % | 54 | +10.0 |
| TEST | short | 5,901 | +1.33% | **+13.0 %** | 55 | +11.5 |
| **TEST** | **long − short spread** | | | **−3.10 pp/yr** | | |

**The names the strategy tells you to SHORT earned ~2× the annualised forward return of the
names it tells you to LONG — on both windows.** The long-only restriction is not what killed
it; the long leg is itself the wrong leg.

The cross-sectional rank IC of ROC vs forward 21d is **negative on both windows**
(TRAIN −0.0066, t = −1.17; TEST −0.0065, t = −0.80) — the right sign, but **statistically
insignificant**. So the reversal tilt is a consistent sign, not a measured edge. Honest
reading: this signal has no demonstrable predictive power at all, in either direction.

### 8.2 It was already behind buy-and-hold on TRAIN — the Sharpe was beta

| variant | TRAIN CAGR % | TRAIN Sharpe | TRAIN MaxDD % | edge vs BH (pp/yr) |
|---|---|---|---|---|
| **buy-and-hold (TRAIN)** | **+21.49** | **0.90** | −36.66 | — |
| M1 (catalog defaults, verbatim) | +6.89 | 0.087 | −26.63 | **−14.60** |
| M2 | +10.94 | 0.444 | −24.19 | −10.56 |
| M3 | +12.59 | 0.482 | −33.35 | −8.91 |
| **M4 (TRAIN pick)** | +15.11 | **0.608** | −35.59 | **−6.38** |
| M5 | +9.45 | 0.286 | −23.14 | −12.05 |

**Variants beating buy-and-hold on TRAIN: 0 of 5.** Buy-and-hold's own TRAIN Sharpe (0.90)
is **higher than every variant including the selected one**. The declared rule picked the
least-bad loser. This was visible in **TRAIN** — the run did not need TEST to reveal it,
and I flag that as the methodological lesson.

TRAIN was a +22.31 %/yr equal-weight tape. Any long-only book prints a respectable Sharpe
on a tape like that; Sharpe alone cannot detect that the market beat all of them.

### 8.3 The catalog threshold is **near-non-binding**, so M1 is barely a strategy

| variant | threshold | avg long-eligible names/day | days with ≥22 eligible | days with all 48 |
|---|---|---|---|---|
| M1 (catalog default) | 0.005 | **25.7 / 48** | **65.4 %** | 0.0 % |
| M4 | 0.080 | 23.0 / 48 | 50.8 % | 0.0 % |

A book that can hold only 22 names, fed a gate that admits ≥22 names on **65 % of days**,
is not being filtered — on most days the deadband excludes nobody from contention and the
book degenerates to *"the 22 names with the highest 20-day ROC"*. That is plain 20-day
momentum ranking with **no strategy-specific content at all**. Consistent with this, **M1,
the catalog's shipped defaults run verbatim, is the worst variant on both windows**
(TRAIN Sharpe 0.087; TEST CAGR −1.54 %, Sharpe −0.87 — the worst TEST Sharpe of the five).

The strategy as shipped is a mis-specified momentum screen: its gate is too tight to
filter and its horizon is too short to survive reversal.

### 8.4 The horizon effect is real but inverted, and it is regime-dependent

Top-minus-bottom-quintile forward-21d return, by trailing lookback:

| window | 20d | 60d | 126d | 252d |
|---|---|---|---|---|
| TRAIN | **−9.4 pp** | **−3.1 pp** | **−0.9 pp** | **−1.9 pp** |
| TEST | **−2.2 pp** | **−5.7 pp** | **+6.0 pp** | **+8.1 pp** |

On TRAIN, *every* horizon is a reversal spread — which is why no variant beat the market
there. On TEST, short horizons still reverse but 126d and 252d are genuinely positive
(+6.0 / +8.1 pp). **M4 sits exactly on the 126d horizon, which is the one horizon TRAIN
showed as flat (−0.9 pp) and the one TEST showed as working.** The TRAIN-only selection
rule therefore picked the variant with the *least* TRAIN signal and — by luck — the most
TEST signal. That is not skill; the TEST gain was not predictable from TRAIN.

### 8.5 Regime

TRAIN: equal-weight +22.31 %/yr, vol 16.13 %, MaxDD −36.66 %, 57.8 % of days up.
TEST: +8.30 %/yr, vol 13.45 %, MaxDD −15.90 %, 53.8 % of days up.
TEST was a materially weaker tape, but buy-and-hold still made +8.18 %/yr there, so the
regime does **not** excuse the failure.

---

## 9. Verdict

> **No. `momentum_factor_strategy` does not make money on NSE NIFTY-50.**
> Its TRAIN-selected variant M4 returned **−0.36 % CAGR (Sharpe −0.48, MaxDD −23.10 %)**
> out-of-sample against **+8.18 % CAGR** for buy-and-hold over the identical window —
> **8.54 pp/yr worse on return and 7.20 pp deeper in drawdown**. All five declared variants
> are negative on TEST. It loses to a matched random signal by 5.81 pp/yr and to the nsealgo
> composite by 6.40 pp/yr. It was already 6.38 pp/yr behind buy-and-hold on TRAIN, before
> TEST was ever opened.

**Most likely reason.** The signal is a **short-horizon reversal** signal wearing a momentum
name, and the book is forced long-only into its losing leg. Over the forward 21-bar return,
the strategy's *short* leg earned +38.0 %/yr on TRAIN and +13.0 %/yr on TEST versus +20.0 %
and +10.0 % for its long leg — a long-minus-short spread of **−17.05 pp/yr (TRAIN)** and
**−3.10 pp/yr (TEST)**, with a negative rank IC on both windows. Compounding this, the
catalog threshold (±0.5 % on a 20-day ROC) is **non-binding**: it admits ≥22 of 48 names on
65 % of days against a 22-slot book, so the strategy contributes no selectivity over plain
20-day ROC ranking — it only adds ~1.6 %/yr of cost drag. Costs are not the problem (at
zero cost the strategy still makes only +0.27 %), so there is nothing a cheaper execution
could rescue.

**The one thing I would try next.** Do **not** tune this strategy further — the evidence
says its horizon is the problem, and no horizon on TRAIN was positive. The one lever with
support is to move the *construction*, not the parameters: the horizon sweep in §8.4 shows
126d and 252d momentum spreads turn **positive out-of-sample** (+6.0 / +8.1 pp on TEST)
while 20d and 60d stay negative, and the engine's own evidence doc (`factors/core.py`)
already ranks `momentum_6m` and `momentum_12_1` as the primary alpha engine. A book built
on **pure long-horizon momentum with the momentum_factor gate removed entirely** is a
different strategy and is already represented by the composite. I have **not** run it: it
would be a 6th variant and the declared budget is 5. Caveat for whoever does: the TEST
window is one regime, and "invert or lengthen it" is exactly the shape of finding that
gets over-fitted — it must be validated on a *fresh* window, not on this one.


---

## 10. Protocol compliance statement

* **Parameter budget: 5 variants declared, 5 variants run, 0 exceeded.** Declared in
  `common.py::VARIANTS` and in §2 of this report **before any backtest was run**. TRAIN
  swept once (`20_train_select.py`), one winner frozen (M4), one TEST evaluation
  (`30_test_eval.py`). `40_diagnose.py` and `50_sanity.py` are diagnostics **on the frozen
  M4** — they compute no new candidate and select nothing. The "one thing to try next" in
  §9 is explicitly **not run**, because it would be a 6th variant.
* **TEST discipline.** Selection used TRAIN only, by the rule declared before running
  (max TRAIN Sharpe; M4 won uniquely, no tie). M4 was then evaluated on TEST unchanged.
  I did **not** look at TEST while iterating, and no parameter was altered after TEST
  became visible. *(Disclosure: I read the sibling report
  `research/agent_cross_sectional/REPORT.md` before starting, which contains TEST numbers
  for the same signal family at a different threshold. I did not reuse its numbers, did
  not copy its variants, and my selection rule was fixed beforehand — but a reader should
  weigh this. See §1.1.)*
* **No lookahead.** Every factor is trailing; `run_backtest` lags weights one bar. Verified
  empirically by truncation at four cut dates — equity curves reproduce to `0.000e+00`.
* **Costs.** Every backtest number is net of **21.92 bps** all-in (11.92 statutory +
  2 × 5 bps slippage), the rate `run_backtest` actually charges. The 11.92 bps statutory
  figure appears only in the cost sanity check, never as a result. Buy-and-hold is charged
  a real deployment cost at the same all-in rate.
* **Constraints not bypassed.** Default `PortfolioConfig` throughout (22 picks, 12 % single
  name, 25 % sector, 10 % cash, 35 % turnover budget, 30 max names). Verified: max 22 names
  held, max single weight 10.80 %.
* **Survivorship bias is PRESENT** (today's NIFTY-50 backfilled to 2008; `adanient` and
  `jiofin` excluded by the loader). Every number above is biased optimistic on that
  account. The failure (8.54 pp/yr) is far too large for the bias to rescue.
* **Daily bars only.** No intraday claim is made. `1m` does not exist; `5m`/`15m` cover
  ~7 weeks and were not used.
* **Lint:** `.venv/bin/ruff check research/agent_momentum_factor/` → *All checks passed!*
* **Not committed.** No commit, no push. Nothing in `src/**`, `tests/**`, `GOAL.md` or
  `reports/**` was modified. Bugs in `src/` are reported in `BUGS.md`, not patched.

---

## 11. Artifacts

| file | contents |
|---|---|
| `REPORT.md` | this report |
| `BUGS.md` | 1 real bug in `src/nsealgo/costs.py`, 3 structural/catalogue findings, 4 bugs in my own harness (all fixed before use) |
| `common.py` | signal, score construction, **declared `VARIANTS`**, benchmark, random control, formatters |
| `00_load.py` | mandatory data audit |
| `10_verify_signal.py` | proves the vectorised signal == the catalog class (207k bar comparisons) + liveness |
| `20_train_select.py` / `20_train.json` | TRAIN sweep + the TRAIN-only selection |
| `30_test_eval.py` / `30_test.json` | the single TEST evaluation + all controls |
| `40_diagnose.py` | why it failed — leg analysis, rank IC, horizon sweep, gate bindingness |
| `50_sanity.py` | brief §6 sanity checks incl. the no-lookahead truncation test |
| `test_equity_M4.csv`, `test_equity_bh.csv` | TEST equity curves |

Reproduce:
```
.venv/bin/python research/agent_momentum_factor/{00_load,10_verify_signal,20_train_select,30_test_eval,40_diagnose,50_sanity}.py
```
