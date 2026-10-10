# `regime_switch` on NSE NIFTY-50 — validation report

**Strategy:** `src/cryptobot/strategies/catalog/regime_switch_strategy.py`
**Date of run:** 2026-10-10 · **Data:** `data/nse` via `load_universe` (48 symbols, 4,625 daily bars, 2008-01-01 → 2026-10-01)
**Costs:** full Indian delivery stack, `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps all-in round trip** charged by `run_backtest` (11.92 statutory + 10 slippage). Every result below is net of that unless labelled gross.

---

## Verdict

**No. `regime_switch` does not make money on NSE, and it does not clear the coin-flip
bar.** Out of sample it returns **+3.76% CAGR against buy-and-hold's +8.18%** — worse
return, worse Sharpe (−0.22 vs +0.18), worse Calmar, and a *negative* Sharpe, meaning
it under-performed a 6.5% risk-free T-bill. The catalog's own default parameter is
worse still: **`period=20` returns −1.23% CAGR out of sample.** A static book holding
60–70% of the market, paying the identical costs, **beats it on return, Sharpe *and*
drawdown simultaneously**.

The assignment's hypothesis — that this may be the one strategy whose thesis survives
long-only because "the short leg becomes cash" — is **half right and it is worth being
precise about which half.** The thesis *is* expressible: mapping `−1 → cash` works, and
the strategy's one genuine out-of-sample effect is exactly the expected one, a smaller
drawdown (−11.70% vs −15.90%). But it buys that 4.2pp of drawdown reduction with 4.4pp
of annual return, and a boring constant-beta book achieves a *better* version of the
same trade. The cash leg is real; the edge in choosing *when* to use it is not.

This is a clean, publishable negative result.

---

## 1. What the strategy actually does

```python
def signal(self, closes, highs, lows, volumes):
    t = sma(closes, self.config.period)                       # period = 20
    b = atr(highs, lows, closes, self.config.adx_p)           # adx_p   = 14
    if t != t or b != b:
        return 0
    up = closes[-1] > t
    if up     and closes[-1] >  closes[-2]: return  1
    if not up and closes[-1] <  closes[-2]: return -1
    return 0
```

A per-name **time-series trend-state machine with a one-bar confirmation**: long when
price is above its own SMA *and* the last bar was up; short when below *and* the last
bar was down; **cash on the two mixed bars**. Its entire information content is a
per-name binary state, which is precisely why it can be translated honestly into a
long-only book — un-flagged names are simply not held, and that *is* the short leg.

### 1.1 Two facts about the host engine that fix the translation

Verified in `cryptobot/strategies/signal_base.py` before translating:

1. **`signal == 0` means go flat**, not "hold" — `feed()` emits a reduce-only close on
   `target == 0`. So the state is instantaneous, and the faithful reading is to sample
   it on the rebalance date. There is no "hold until the state changes" reading.
2. **`atr` never enters the decision, but its NaN guard is load-bearing.** ATR is dead
   weight as a *signal* — no ADX is computed and no volatility regime is ever tested,
   despite the config field being named `adx_p`. The strategy named "regime switch" is
   a *price-vs-SMA* switch, not a volatility-regime switch. But `atr()` returns NaN
   while `len(closes) < adx_p + 1`, so `adx_p` is a **warmup gate**: the effective
   warmup is `max(period, adx_p + 1)`, not `period`.

### 1.2 The translation was verified bar-for-bar, and it found two bugs

`verify_translation.py` runs the **actual** `RegimeSwitchStrategy` over every bar of
every symbol and compares against the vectorised panel:

> **1,040,435 bar-level comparisons. 2 residual mismatches**, both INDIGO, both
> traceable to the one interior data hole (below).

Two bugs were caught *by that check, before any backtest ran*. Both were in my first
translation and both would have silently corrupted every number in this report:

1. **`~(NaN > NaN) & (price < prev)` evaluates True.** Inside the SMA warmup region
   the vector labelled **every bar SHORT**. The catalog's `t != t` guard exists exactly
   to prevent this. Caught: 417 / 560 / 1,399 / 2,540 / 5,168 mismatches at period
   10 / 20 / 50 / 100 / 200.
2. **`adx_p` is a live warmup parameter** (§1.1.2). Without it, `period=10` began
   trading 5 bars early. Caught: 169 mismatches at period=10.

Cost of the check: it must be fed numpy views, not lists — `signal` slices with
`values[-period:]`, and `list[:i+1]` makes the loop quadratic. The naive version did
not finish in 2 minutes.

### 1.3 Data holes, audited before use

Panel NaNs: **3,406 in TRAIN, 1 in TEST** — and of those, 3,406/0 are **leading**
(names that listed after a window start), against exactly **one interior hole** in the
whole dataset (INDIGO, 2026-05-01). The panel is therefore forward-filled **from the
past only** (brief §4). The single interior hole becomes a stale-price bar where both
`rising` and `falling` are false → state 0 → not held, so the book never trades a stale
print. This is a "name hasn't started yet" fix, not a way to invent prices.

---

## 2. Declared parameter budget — 5 variants, fixed before any run

`period` is the only tunable worth spending on (`adx_p` is a warmup gate; `quantity` is
a crypto sizing field with no NSE meaning). The whole budget goes to the SMA lookback,
spanning well below and above the catalog default.

| # | name | `period` | thesis |
|---|------|----------|--------|
| V1 | `V1_p20_catalog` | 20 | the catalog default, unchanged |
| V2 | `V2_p10_fast` | 10 | fast regime switch — max responsiveness, max churn |
| V3 | `V3_p50_mid` | 50 | ~1 quarter |
| V4 | `V4_p100_slow` | 100 | ~5 months, aligned to the `GOAL.md` 5–60 day holding period |
| V5 | `V5_p200_verySlow` | 200 | ~10 months, near-institutional slow trend filter |

**Budget respected: exactly 5 variants, each run once on TRAIN, one selected on TRAIN
Sharpe (tie-break Calmar), carried unchanged into TEST.** No threshold or period was
revisited after seeing any equity curve. The §5 lookback sweep is an *ablation of the
selected variant*, not a selection candidate — the selected variant does not change.

### 2.1 Construction decisions, fixed in advance

- **Score = the strategy's own quantity, cross-sectionally ranked.** Among flagged
  names, rank by `close/SMA − 1` — *how far above its own moving average the name is*.
  Deliberately **not** a 126-day momentum rank: importing one would smuggle in the
  nsealgo composite's edge and make attribution meaningless.
- Monthly rebalance; `PortfolioConfig()` defaults (22 names, 12% single, 25% sector,
  10% cash). Not tuned — `run_backtest` enforces them.
- Un-flagged names are not held. No market-level overlay, no exposure scaling — I
  wanted to measure the per-name gate, not a different strategy.
- Costs: 21.92 bps all-in, never reduced. Zero-cost figures appear only as labelled
  gross isolations of drag.

---

## 3. TRAIN selection (2016-01-01 → 2023-12-29, 1,973 bars)

| variant | period | CAGR | Sharpe | MaxDD | Calmar | Turn | Cost drag | Avg names | Long % cells | Names/day |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 `catalog` | 20 | 7.48% | 0.15 | −17.07% | 0.44 | 4.05x/y | 2.31%/y | 15.6 | 33.3% | 16.0 |
| V2 `fast` | 10 | 10.62% | 0.48 | −11.73% | 0.91 | 4.07x/y | 2.57%/y | 16.5 | 35.0% | 16.8 |
| V3 `mid` | 50 | 8.24% | 0.22 | −20.19% | 0.41 | 4.04x/y | 2.40%/y | 15.5 | 32.8% | 15.8 |
| V4 `slow` | 100 | 10.36% | 0.42 | −17.09% | 0.61 | 3.99x/y | 2.57%/y | 15.3 | 33.5% | 16.1 |
| **V5 `verySlow`** | **200** | **11.72%** | **0.53** | −14.56% | 0.80 | 3.94x/y | 2.68%/y | 15.5 | 34.6% | 16.6 |
| *buy-and-hold (EW)* | | *21.49%* | *0.90* | *−36.66%* | | | | | | |
| *nsealgo composite* | | *20.44%* | *0.91* | *−32.94%* | | | | | | |

**Selected on TRAIN: `V5_p200_verySlow` (Sharpe 0.53).**

Three warnings were already visible before TEST, and all three held up:

1. **Every variant loses to buy-and-hold by roughly half.** Best 11.72% vs 21.49%.
2. **Turnover ~4x/yr, cost drag 2.3–2.7%/y** — 1.35× the composite's on TRAIN and
   1.81× on TEST. Not a cost catastrophe in absolute terms, but it is a lot of trading
   to pay for a filter. The one-bar confirmation makes the flag flicker, and every
   flicker is a full round trip.
3. **Under-invested by construction.** ~16 names flagged/day against a 22-name target.

The monotone ordering (Sharpe 0.15 → 0.22 → 0.42 → 0.53 as `period` goes 20 → 50 → 100
→ 200, with 10 an outlier at 0.48) was itself a warning: **the strategy only works as
the filter gets so slow it barely trades.** That is "the edge, if any, is in not
trading" — and a book that doesn't trade can't outrun the market.

---

## 4. TEST result (2024-01-01 → 2026-10-01, 684 bars) — selected variant, unchanged

| metric | **regime_switch** | **buy-and-hold** | **nsealgo composite** |
|---|---|---|---|
| Total return | **+10.91%** | **+24.64%** | +2.00% |
| CAGR | **3.76%** | 8.18% | 0.71% |
| Sharpe (rf 6.5%) | **−0.22** | +0.18 | −0.43 |
| Max drawdown | **−11.70%** | −15.90% | −15.28% |
| Calmar | 0.32 | 0.51 | 0.05 |
| Turnover | 4.03x/yr | 0.36x/yr | 2.45x/yr |
| Cost drag | 2.06%/y | 0.09%/y | 1.13%/y |
| Avg names held | 15.1 | 48 | 21.3 |
| Beta vs EW market | 0.60 | 1.00 | — |
| Annual alpha | **−1.11%** | −0.12% | — |
| Correlation to market | 0.82 | 1.00 | — |
| Max single weight | 10.80% (cap 12%) | — | — |

Yearly: 2024 **+18.0%**, 2025 **+3.8%**, 2026 (to Oct 1) **−9.5%** — 67% of years
positive. 33 rebalances.

### Head to head vs buy-and-hold
- **Return: 4.41 pp/yr WORSE** (+10.91% vs +24.64% total). On a ₹21,00,000 book that
  is **₹2,88,323 of foregone return over 2.75 years.**
- **Sharpe: 0.40 WORSE** and *negative* — the book under-performed the risk-free rate.
- **Calmar: 0.19 WORSE.**
- **Drawdown: 4.20 pp BETTER** (−11.70% vs −15.90%). This is the one thing it does.
- The trade is 4.4pp of annual return for 4.2pp of drawdown. At these levels that is a
  roughly 1:1 swap of return for pain — and §5 shows a constant-beta book gets a
  strictly better version of the same swap.

### Cost drag
| | CAGR | Sharpe | Total return |
|---|---|---|---|
| gross (zero cost) | 4.61% | −0.13 | +13.45% |
| net (base cost) | 3.76% | −0.22 | +10.91% |

Drag 0.85 pp/yr — **₹1,21,104** of the ₹21,00,000 book over the window. **Not
cost-killed** — the strategy is unviable because it has almost nothing to pay costs on,
not because costs ate it.

### Did it beat the nsealgo composite?
**Yes, on all three metrics** — 3.76% / −0.22 / −11.70% vs 0.71% / −0.43 / −15.28%.
This is worth stating plainly and then immediately discounting: it beats a benchmark
that is itself failing (the composite also has a negative out-of-sample Sharpe), and
it still loses to simply holding the index.

---

## 5. Attribution — the decisive result

Two orthogonal decompositions, 10 seeds each, on **both** TRAIN and TEST:

```
gate worth    = (GATE + RANK) − (RANDOM GATE + RANDOM RANK)
ranking worth = (GATE + RANK) − (GATE + RANDOM RANK)
```

| window | GATE+RANK | **gate worth** | ranking worth |
|---|---|---|---|
| 2009–2013 | 12.58% | −0.85pp | +0.80pp |
| 2014–2018 | 7.49% | −1.27pp | −0.99pp |
| 2019–2021 | 19.84% | **+7.79pp** | +4.51pp |
| 2022–2023 | 5.52% | −1.61pp | −0.39pp |
| TRAIN all | 11.72% | +2.38pp | +0.80pp |
| **TEST 2024–26** | **3.76%** | **+0.62pp** | **+1.13pp** |
| full 2008–26 | 9.23% | +0.39pp | +0.75pp |

**Gate: positive in 4 of 7 windows. Mean +1.06pp, median +0.39pp, range −1.61 to
+7.79.** The mean is entirely one window. **Strip 2019–2021 (the COVID crash and
rebound) and the gate's mean value is −0.06pp — indistinguishable from nothing.**
That is the honest reading of the strategy's entire thesis: a trend filter earns its
keep in a genuine crash and is a small drag otherwise.

Note on seed sensitivity: a single-seed run showed the gate worth **−0.38pp** on TEST;
10 seeds put it at **+0.62pp**. The effect is smaller than the seed noise, so any
single-seed attribution of this strategy is meaningless. Reported because it's the kind
of thing that gets quietly reported the other way.

### 5.1 It is "hold less market", and nothing more

TEST, every book net of the identical cost stack:

| book | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|
| **regime_switch (selected)** | **3.76%** | **−0.22** | **−11.70%** | 0.32 |
| static 40% beta, same costs | 3.42% | −0.52 | −6.60% | 0.52 |
| static 50% beta, same costs | 4.24% | −0.28 | −8.20% | 0.52 |
| **static 60% beta, same costs** | **5.06%** | **−0.13** | **−9.78%** | 0.52 |
| **static 70% beta, same costs** | **5.86%** | **−0.02** | **−11.34%** | 0.52 |
| buy-and-hold | 8.18% | 0.18 | −15.90% | 0.51 |

**A static 60–70% beta book beats the strategy on CAGR, Sharpe AND drawdown at the same
time.** The strategy's measured beta is 0.60; the return it delivers is what a static
0.60-beta book delivers, less 1.3pp of annual turnover cost. The entire strategy
contribution reduces to *being under-invested*, which was never the thesis.

### 5.2 Cash timing — the mechanism

| year | % of (name,bar) cells held | equal-weight market that year |
|---|---|---|
| 2024 | 43.6% | **+19.2%** |
| 2025 | 31.0% | +12.8% |
| 2026 | 24.3% | **−9.5%** |

The gate does the *directionally* right thing — most exposure in the good year, least
in the bad one — and it is still not enough, because the magnitude is wrong in both
directions. It is under-invested in 2024 (−19% market move missed) and still ~25–30%
invested into the 2026 decline. A filter that only ever removes a third of the book
cannot earn its keep.

---

## 6. Sanity checks (brief §6)

| check | result |
|---|---|
| [1] Plausibility | 3.76% CAGR — far under the 40–50% long-only ceiling. **OK** |
| [2] Weight count | avg **15.1** names (target 22, cap 30); max single weight 10.80% (cap 12%). **OK**, no residual accumulation |
| [3] Signal liveness | **33.7%** of (name,bar) cells long; 16.2 names/day; 72% of days have <22 eligible. **Genuinely live** — not an always-flat strategy — but structurally under-invested |
| [4] Cost drag | 0.85 pp/yr; gross +4.61% → net +3.76%. Not cost-killed, just low-return |
| [5] Random control | beats 51/60 (85%) of random on Sharpe, 47/60 (78%) on CAGR. **FAIL against the brief's 90% bar** |

### 6.1 On the random control — both facts, not one

- The strategy's Sharpe (−0.22) sits above the random null's median: **51/60 beats,
  one-sided binomial p < 0.001.** So it is formally distinguishable from the *median*
  coin flip.
- But it does **not** clear the brief's stated bar (≥90%), and the null is tight
  (Sharpe −0.47 ± 0.25). Against the brief's own threshold: **FAIL.**

Both statements are true. The second is the one that governs, because the brief set
90% precisely to stop a coin flip being reported as a win.

---

## 7. Negative control (detail)

60 seeds, random names with the same per-day eligible count as the real signal:

| | mean | sd | p05 | p95 |
|---|---|---|---|---|
| random CAGR | 2.60% | 1.89% | −0.21% | 5.85% |
| random Sharpe | −0.47 | 0.25 | — | — |

Strategy: CAGR 3.76%, Sharpe −0.22.

---

## 8. GOAL.md §5 gates on TEST

| gate | value | result |
|---|---|---|
| 1 — CAGR ≥ 3%/month net (~43%/yr) | 3.76%/yr | **FAIL** (needs 11× more) |
| 2 — Sharpe ≥ 1.0 | −0.22 | **FAIL** |
| 3 — positive ≥60% of years | 67% | PASS |
| 4 — MaxDD ≤ 20% | −11.70% | PASS |
| 5–7 — cost stress, capacity, robustness | not pursued; gates 1–2 fail by a wide margin | — |

**Two of the seven non-waivable gates fail, one of them catastrophically. This does not
ship.**

---

## 9. Why it failed, and the one thing I'd try next

**Most likely reason — the one-bar confirmation destroys the regime switch.**

The strategy is a *trend regime* filter with a *single-bar momentum* confirmation. On a
daily NSE name, price crosses its own 200-day SMA constantly, so the conjunction
"above the SMA **and** up today" is a low-probability event that is *systematically
least likely at exactly the moment the trend turns up*. The filter therefore exits on
noise inside a trend and only re-enters after the move has already started — it is, in
NSE, a filter that is contrarian to its own stated intent. The evidence is direct:

- Every lookback produces **negative TEST Sharpe** (10: −0.70, 20: −0.82, 50: −0.42,
  100: −0.33, 200: −0.22). There is no setting at which this works out of sample.
- **The catalog default `period=20` returns −1.23% CAGR out of sample** — the strategy
  exactly as shipped loses money on NSE.
- The gate's value is +7.79pp in one crash window and negative in three of the other
  six. It is a crash-only filter being paid a full-time cost.

The second-order problem is turnover: 4.03x/yr and 2.06%/y of cost drag — 1.81× the
composite's, or ₹1.21 lakh of the ₹21,00,000 book over the TEST window. Even a correct
signal would have to be worth more than that to clear costs, and on TRAIN the entire
book was worth 11.72% against a 21.49% market — so the signal would first have to be
worth **more than the market it is filtering**.

**The one thing I would try next.** Drop the one-bar confirmation and keep the regime
switch — a *persistent* state (`close > SMA(p)` → hold; `close < SMA(p)` → cash) with
re-entry cost amortised over a rebalance rather than paid per bar. That is the only
untested variant with a real mechanism, because the confirmation is the identified
defect and everything in §5 says the gate itself is worth ~+0.4pp median while the
churn eats it. It is a **new hypothesis**, not a re-run of this one: it needs its own
declared budget and a fresh TRAIN/TEST protocol. I have not run it here, and the
§6.1 random control means I would want the crash-window dependence (§5) resolved
before believing it.

---

## Protocol compliance

- TRAIN 2016-01-01 → 2023-12-31 used for **all** parameter selection (step 1).
- TEST 2024-01-01 → 2026-10-01 touched **once**, in step 2, with the variant read from
  `selected_variant.txt` and unchanged.
- **No TEST data influenced any parameter choice.** Steps 3–5 use TEST only for
  attribution of the already-frozen selected variant, and every one of those
  decompositions is reported with its TRAIN counterpart alongside.
- Parameter budget: 5 declared, 5 run. **Not exceeded.**
- Costs are the full delivery stack on every fill, never reduced. Zero-cost figures
  appear only as labelled gross isolations of drag (§4, §5.1).
- No lookahead: the SMA on day *t* uses closes through *t*; `run_backtest` applies
  weights decided at *t* from *t+1*; forward-fill is from the past only.
- Translation verified against the actual catalog class on 1,040,435 bar-level
  comparisons before any backtest was run (§1.2).
- `src/nsealgo/**`, `src/cryptobot/**` and all test files unmodified. Scratch only,
  under `research/agent_regime_switch/`. Nothing committed or pushed.

## Files

| file | purpose |
|---|---|
| `harness.py` | signal, score construction, B&H, random controls, windowing |
| `verify_translation.py` | bar-for-bar proof the vector matches the catalog strategy |
| `step1_train_sweep.py` | TRAIN-only selection → `train_sweep.csv`, `selected_variant.txt` |
| `step2_test_eval.py` | the single TEST run + all mandated comparisons → `test_summary.csv`, `test_random_control.csv` |
| `step3_ablation.py` | gate-vs-rank-vs-beta attribution, cash-timing |
| `step4_robustness.py` | decomposition across 7 windows, lookback sweep, liveness |
| `step5_final.py` | constant-beta comparison, control significance, GOAL gates |
| `step6_reconcile.py` | recomputes every headline number in this report from scratch |
| `robustness_windows.csv` | the 7-window decomposition |

## Bugs found (brief §8.3)

1. **In my own first translation** — `~(NaN > NaN) & (price < prev)` labels every SMA
   warmup bar SHORT; and `adx_p` is a live warmup gate (`max(period, adx_p+1)`), not a
   dead field. Both caught by `verify_translation.py` before any result was produced.
   Lesson worth propagating: a vectorised port of a guarded streaming strategy must
   reproduce the *guard*, not just the predicate. Two other agents' runs that
   translated a `if t != t` strategy without the guard would have inverted their sign.
2. **In the catalog file** (not mine to fix, reported only) — `regime_switch_strategy`
   computes `b = atr(...)` and names the parameter `adx_p`, but never computes ADX and
   never tests a volatility regime. The "regime switch" is a price-vs-SMA switch. The
   name overstates what the code does, which is how it ended up as this agent's
   "interesting long-only candidate" in the first place.