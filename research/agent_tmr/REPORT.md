# AGENT REPORT — `trend_mean_reversion` on NSE NIFTY-50

**STATUS: COMPLETE. Verdict: NO — it does not make money on NSE.**

> ### TL;DR
> | | TEST 2024-01-01 → 2026-10-01, net of 21.92 bps |
> |---|---|
> | **Strategy (V4, TRAIN-selected)** | **CAGR 1.26% · Sharpe −0.35 · MaxDD −19.73% · 73% invested** |
> | buy-and-hold | CAGR 8.37% · Sharpe +0.20 · MaxDD −15.90% |
> | nsealgo composite | CAGR 0.71% · Sharpe −0.43 · MaxDD −15.28% |
>
> It loses to buy-and-hold by **7.11 pts/yr *and* 3.84 pts of drawdown**. It **fails the
> random-signal control on return** (45th percentile — a coin flip with the same name
> count does slightly better) and beats the signal-scrambled control only marginally
> (85th pctile, +0.78 pts/yr, inside the control's own spread). Costs are *not* the
> cause: at zero slippage it still only reaches 2.04%.
>
> **Two things the reviewer should not mis-cite:**
> 1. ⚠️ **This strategy does not implement mean reversion.** `z > entry AND close > SMA`
>    buys *strength* — it is trend **continuation**. So this negative result is **not**
>    evidence against mean reversion on NSE (relevant to the Gate 4 context). See §1 F3.
> 2. The TRAIN Sharpe of **+0.69 collapsed to −0.35** out-of-sample on the frozen
>    variant — a 1.04 Sharpe swing from regime change alone.
>
> Sections 1–3 + provenance were written **before any backtest ran**; 4–11 appended as
> results landed.

---


---

## 0. Provenance

| Field | Value |
|---|---|
| Agent | `agent_tmr` |
| Assigned strategy | `trend_mean_reversion` |
| Source | `src/cryptobot/strategies/catalog/trend_mean_reversion.py` |
| Strategy class | `TrendMrStrategy` (`name = "trend_mr"`) |
| Repo HEAD | `92d2581` |
| **`provenance()["engine"]`** | **`d93815344bd3`** |
| **`provenance()["loader"]`** | **`c1badf5f7df8`** |
| **`provenance()["costs"]`** | **`ba350aef75b3`** |
| **`provenance()["panel"]`** | **`389b082b832f`** |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| Round trip charged by engine | `all_in_round_trip_bps(100_000)` = **21.92 bps** (11.92 statutory + 2×5 slippage) |
| Zero-cost control | `CostModel(segment="delivery", slippage_bps=0.0)` → **11.92 bps** |
| Python | `.venv/bin/python` (host venv) |
| Panel | 48 symbols, 4625 bars, 2008-01-01 → 2026-10-01 |

> **All headline results are net of 21.92 bps** because every backtest goes through
> `run_backtest`. The zero-cost control (11.92 bps) is reported separately and labelled.

**Data note (mandatory loader step, run before any experiment):**
```
rows in            :   274,541     rows out :   207,687
dropped pre-2008   :    66,312     dropped frozen :      539
dropped non-positive:        0     dropped extreme :        3
excluded symbols   : ['adanient', 'jiofin']
```

---

## 1. What the strategy actually is — three code-fidelity findings

Source (`trend_mean_reversion.py`, 38 lines):

```python
@dataclass
class TrendMrConfig:
    slow: int = 40
    period: int = 20          # <-- DEAD, see F1
    entry: float = 1.5
    quantity: Decimal = Decimal("1")

class TrendMrStrategy(SignalStrategy):
    name = "trend_mr"
    def warmup(self, closes) -> int:
        return self.config.slow
    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.slow)
        z = zscore(closes)
        if t != t or z != z: return 0
        if z > self.config.entry and closes[-1] > t:  return 1     # LONG
        if z < -self.config.entry and closes[-1] < t: return -1    # SHORT
        return 0
```

### F1 — `TrendMrConfig.period` is dead code
`signal()` calls `zscore(closes)` with **no period argument**, and `period` is
referenced nowhere in the file (only `slow` and `entry` are). Anyone tuning `period`
on this strategy would observe **zero** effect. I reproduce the real behaviour, not the
declared intent.

### F2 — the z-score window is 300 days, not 20
`cryptobot.strategies.indicators.zscore(values)` takes the **whole array** it is given
(`(a[-1] - a.mean()) / a.std()`, `ddof=0`). `SignalStrategy` feeds it a
`deque(maxlen=300)`, so the array is the trailing **300** closes once warm. My harness
therefore uses a **300-day trailing z**, and a growing window for the first 300 bars
(`warmup` only requires 40). Population stdev (`ddof=0`), matching `np.std()`.

### F3 — **this strategy does not implement mean reversion** ⚠️
This is the headline finding and it changes what the whole study means.

The long branch fires when `z > +1.5` **and** `close > SMA(40)` — i.e. the price is
1.5 sd **above** its 300-day mean *and* above its short trend. That is buying
**strength**, not fading it. Mean reversion would require the opposite polarity
(`z > entry and close < t`, or shorting the extension). The short branch is the mirror
image: short when 1.5 sd **below** the mean and below the trend — again continuation.

So `trend_mean_reversion` is, in substance, a **trend-continuation strategy with a
z-score stretch filter**. `nsealgo/factors/core.py` is right to rule reversal out on
Indian evidence, and right that this catalog strategy is not a reversal strategy.

**Consequence for this study:** given the brief's context that a reversal composite beat
the trend composite out-of-sample, I am explicitly **not** testing the reversal thesis
here — the code does not implement it. I test what the code actually does. A negative
result below is a negative result for *this momentum implementation*, and is **not**
evidence against mean reversion on NSE. I flag this so the finding is not mis-cited
later as "reversal was tested and failed."

### F4 — the short branch is unreachable
`run_backtest` builds a **long-only** book (Indian delivery account cannot short). Only
the `+1` branch of this dual-mode strategy is tradeable. The `-1` branch is discarded —
correctly, but it means half the strategy's logic is untested by construction.

---

## 2. Declared parameter budget — fixed BEFORE any backtest (brief §4)

**At most 5 variants.** Written down first, per the protocol. The live knobs are
`slow` (SMA window) and `entry` (z threshold); `period` is dead (F1) and the z-window is
pinned at 300 by `maxlen` (F2). The five variants sweep one axis around the catalog
defaults at a time:

| Variant | `slow` | `entry` | z-window | Purpose |
|---------|--------|---------|----------|---------|
| **V1** | 40 | 1.5 | 300 | catalog defaults — baseline |
| **V2** | 20 | 1.5 | 300 | faster trend filter |
| **V3** | 60 | 1.5 | 300 | slower trend filter |
| **V4** | 40 | 1.0 | 300 | looser trigger → more names held |
| **V5** | 40 | 2.0 | 300 | tighter trigger → fewer, more extreme names |

**Selection rule (declared now, before seeing any result):** highest **TRAIN** Sharpe;
ties broken by lower TRAIN MaxDD. TRAIN only. The winner is frozen to
`selected_variant.json` with its `engine_sha`, then run **once** on TEST unchanged.

*No sixth variant will be run. If it looks like the parameter budget should be widened,
that is a finding to report, not permission to spend it.*

---

## 3. Construction (long-only, cross-sectional, per brief §5)

```python
long_flag = (z300 > entry) & (close > SMA(slow))          # the strategy's +1 branch
score = trailing_momentum_126d.where(long_flag).rank(axis=1, pct=True)
```
Rank among signalled names by trailing 126-day momentum — brief §5's prescribed
cross-sectional construction. Only flagged names may be bought. `PortfolioConfig`
defaults (22 names, 12% single, 25% sector, 10% cash) are enforced by the engine and
are not bypassed.

---

*Sections 1–3 written before any backtest was run. Results appended below.*

---

## 4. Signal fidelity — verified against the real catalog class (100%)

`01_fidelity.py` drives the actual `TrendMrStrategy` through `SignalStrategy.feed()`
bar-by-bar over all 4625 bars and compares its `signal()` output to the vectorised
panel computation.

| Check | Result |
|---|---|
| Bars compared (symbol `adaniports`) | 4625 |
| **Agreement, all bars** | **4625/4625 = 100.0000%** |
| **Agreement, saturated buffer (bar ≥300)** | **4325/4325 = 100.0000%** |
| z-window probe (bar 2500) | catalog z(300) = **+1.0656**, ours **+1.0656**, 20-bar would have been +0.3903 |

F1/F2 confirmed empirically: `period=20` is never read, and the real z-window is 300.

**Signal liveness (brief sanity check 3)** — none of the variants is near the
always-flat regime:

| Variant | TRAIN live | TRAIN names | TEST live | TEST names |
|---|---|---|---|---|
| V1 (40, 1.5) | 28.91% | 13.4 | 20.17% | 9.7 |
| V2 (20, 1.5) | 25.64% | 11.9 | 19.01% | 9.1 |
| V3 (60, 1.5) | 30.39% | 14.1 | 20.66% | 9.9 |
| **V4 (40, 1.0)** | **39.13%** | **18.1** | **29.84%** | **14.3** |
| V5 (40, 2.0) | 14.93% | 6.9 | 9.88% | 4.7 |

All well above the ~5% floor. V5 (4.7 names on TEST) is the only one thin enough to be
worth flagging, and it also has the worst TRAIN Sharpe anyway.

---

## 5. TRAIN selection — all 5 declared variants, net of 21.92 bps

Rule was fixed in §2 before any run: **max TRAIN Sharpe, tie-break lower TRAIN MaxDD.**

| run | CAGR | Sharpe | Calmar | MaxDD | Vol | Total | Turnover | CostDrag | notes |
|---|---|---|---|---|---|---|---|---|---|
| TRAIN V1 (s40,e1.5) | 8.11% | 0.19 | 0.25 | -32.23% | 11.59% | 87.9% | 3.57x/y | 2.19%/y | live 28.9%, names 12.5 |
| TRAIN V2 (s20,e1.5) | 6.96% | 0.09 | 0.31 | -22.66% | 9.59% | 72.3% | 3.69x/y | 2.14%/y | live 25.6%, names 11.1 |
| TRAIN V3 (s60,e1.5) | 9.84% | 0.32 | 0.29 | -33.50% | 12.07% | 113.5% | 3.40x/y | 2.19%/y | live 30.4%, names 13.2 |
| **TRAIN V4 (s40,e1.0)** | **14.30%** | **0.69** | **0.78** | **-18.26%** | 11.16% | 194.6% | 3.67x/y | 2.96%/y | live 39.1%, names 15.8 |
| TRAIN V5 (s40,e2.0) | 3.99% | -0.19 | 0.13 | -29.97% | 10.04% | 37.2% | 3.18x/y | 1.60%/y | live 14.9%, names 7.1 |
| TRAIN buy-and-hold | 22.52% | 0.92 | 0.59 | -37.97% | 16.73% | 416.2% | — | — | whole universe |
| TRAIN nsealgo composite | 20.44% | 0.91 | 0.62 | -32.94% | 14.64% | 350.0% | 2.08x/y | 1.99%/y | names 21.8 |

**Selected: V4 (slow=40, entry=1.0)**, TRAIN Sharpe 0.689. Frozen to
`selected_variant.json` with `engine_sha`.

> **Already visible on TRAIN:** V4 is beaten by buy-and-hold (14.30% vs 22.52%) *and* by
> the production composite (14.30% vs 20.44%), in-sample, before any out-of-sample read.
> That is the first sign the win is selection, not edge.

---

## 6. TRAIN controls — the signal vs. two negatives (20 seeds each)

| run | CAGR | Sharpe | MaxDD | Turnover | CostDrag |
|---|---|---|---|---|---|
| **TRAIN real strategy** | **14.30%** | **0.69** | -18.26% | 3.67x/y | 2.96%/y |
| TRAIN real @ **0 slippage** (11.92 bps) | 15.14% | 0.75 | -18.21% | 3.67x/y | 1.67%/y |
| TRAIN random-signal control (20 seeds) | 9.72% mean | 0.39 mean | — | ~4.1x/y | — |
| TRAIN **signal-scrambled** control (20 seeds) | 12.44% mean | 0.56 mean | — | — | — |

| Control | distribution (CAGR p10–p90) | real sits at |
|---|---|---|
| Random-signal | 8.46% – 11.52% | **100th percentile** |
| Signal-scrambled | 11.88% – 13.06% | **100th percentile** |

The scrambled control permutes the cross-sectional score **across symbols within each
rebalance date**, so it holds the same number of names out of the same flagged set with
the same score distribution and the same turnover — only the score→symbol mapping is
destroyed. It lands 1.86 pts/yr below the real strategy.

**Reading:** in-sample the ranking *does* carry information (~1.9 pts/yr over scramble,
~4.6 pts/yr over random). Note the scrambled control also beats pure random — that is
the filter itself (hold only names in an uptrend-extension state) doing work, with the
ranking adding the increment. **But both are beaten by buy-and-hold and by the
composite**, so a TRAIN edge here is not yet an investable one.

**Cost decomposition:** removing all slippage lifts CAGR only 14.30% → 15.14%
(+0.84 pts/yr), and cost drag falls 2.96%/y → 1.67%/y. So roughly **one quarter** of the
TRAIN edge is real and the cost load is moderate — costs are not the reason TRAIN looks
good, and equally they are not what will kill it. This is useful: whatever happens on
TEST will be about signal decay, not cost arithmetic.

---

## 7. THE TEST RESULT — the single untouched read

V4 (`slow=40`, `entry=1.0`) was frozen in `selected_variant.json` under
`engine_sha=d93815344bd3`; `04_test_eval.py` asserts the engine still matches before it
computes anything (**printed `engine MATCH`**). Exactly 5 variants were run; the budget
in §2 was **not** exceeded. TEST was read **once**. Nothing was re-tuned after seeing
it.

**TEST 2024-01-01 → 2026-10-01, net of 21.92 bps round trip:**

| run | CAGR | Sharpe | Calmar | MaxDD | Vol | Total | Turnover | CostDrag | notes |
|---|---|---|---|---|---|---|---|---|---|
| **TEST strategy (V4)** | **1.26%** | **−0.35** | **0.06** | **−19.73%** | 12.19% | 3.6% | 3.80x/y | 1.93%/y | names 14.8, invested 73% |
| TEST buy-and-hold | 8.37% | +0.20 | 0.53 | −15.90% | 13.46% | 25.2% | — | — | whole universe |
| TEST nsealgo composite | 0.71% | −0.43 | 0.05 | −15.28% | 11.57% | 2.0% | 2.45x/y | 1.13%/y | names 21.3 |
| TEST strategy @ **0 slippage** | 2.04% | −0.29 | 0.11 | −18.39% | 12.19% | 5.8% | 3.80x/y | 1.06%/y | 11.92 bps |

**Yearly (strategy vs buy-and-hold):**

| | 2024 | 2025 | 2026 (to 10-01) |
|---|---|---|---|
| strategy | +17.6% | +3.1% | **−14.6%** |
| buy-and-hold | +20.4% | +13.4% | −8.3% |

### Head-to-head (brief §7.4)
- vs **buy-and-hold**: **−7.11 pts/yr** on return, and **−3.84 pts worse** on drawdown.
  It loses on *both* axes — no trade-off to argue about.
- vs **composite**: +0.55 pts/yr on return but **−4.45 pts worse** drawdown. It edges the
  production composite on return and loses to it on every risk measure. Given the
  composite's own TEST Sharpe is −0.43, "beating the composite" here is beating a
  negative — it is not a win worth claiming.

### Sanity checks (brief §6)
1. **Plausibility** — 1.26% CAGR, far below the 40–50% unlevered ceiling. No compounding
   or lookahead bug. ✅
2. **Weight count** — 14.8 names average held, not 48. No residual-weight accumulation. ✅
3. **Signal liveness** — 36.32% of (symbol, bar) cells long. Nowhere near the <5%
   always-flat trap. ✅ The strategy was genuinely invested and still lost.
4. **Cost drag** — 1.93%/y against 3.80x/y turnover. Removing slippage entirely moves CAGR
   1.26% → 2.04%. **Costs are not the reason it fails** — the signal is dead before costs,
   and costs only finish it off. That is the more damning finding.
5. **Negative controls** — see §8. **It does not beat the random control on return.**

---

## 8. Against BOTH controls — where it sits

Both controls were run on TEST with 20 seeds each, using the **same live fraction
(36.32%)**, the same engine, the same 21.92 bps, the same window.

| Control | TEST CAGR (mean) | p10 – p90 | TEST Sharpe (mean) | real CAGR pctile | real Sharpe pctile |
|---|---|---|---|---|---|
| **Real strategy** | **1.26%** | — | **−0.35** | — | — |
| Random-signal | 1.69% | −0.51% – 4.28% | −0.59 | **45th** | 70th |
| **Signal-scrambled** | 0.49% | −0.67% – 1.42% | −0.45 | **85th** | 90th |

**Random-signal control.** The strategy's CAGR sits at the **45th percentile** — i.e. a
coin flip with the same number of names does **slightly better** than the strategy on
return. It clears the coin only on Sharpe (70th), because the strategy is lower-vol than
random by construction (it only holds names in an uptrend extension). **This is a failed
negative control.** A strategy that cannot beat a random selector on return has no
demonstrable edge.

**Signal-scrambled control.** Permuting the cross-sectional score across symbols within
each rebalance date — preserving turnover, exposure, name count and score distribution,
destroying only the score→symbol mapping — gives 0.49% mean, putting the real strategy at
the **85th percentile** (+0.78 pts/yr, Sharpe 90th). So a *little* ranking information
survives, but the increment is well inside the control's own spread (p10 −0.67%, p90
1.42% — the entire scramble distribution straddles the real result's neighbourhood) and
is dwarfed by the 7.11-pt gap to buy-and-hold.

**Where it sits against both, stated plainly:** the strategy beats the scrambled control
slightly and the random control not at all. Neither margin is large enough to be evidence
of an edge, and both are far below the passive benchmark. **Verdict: no edge.**

> Given the brief's context (a reversal composite beat the trend composite OOS), this
> strategy is a **trend-continuation** implementation (§1 F3), so its failure does not
> refute mean reversion on NSE — it confirms that this particular momentum variant adds
> nothing. See §10.

---

## 9. Why it failed — attribution (post-hoc, on the frozen result)

**Q1 — Is it just un-invested cash?** The book ran 73% invested. Re-pricing the *same*
names and *same* ranking at ~99% deployment: CAGR 5.17% vs universe 8.26% =
**−3.09 pts/yr still negative at matched exposure.** So cash drag explains part of the
gap (73%→99% recovers ~3.9 pts) but the **name selection itself is still −3.09 pts/yr**.
Not a cash artefact.

**Q2 — Is the filter bad, or is the ranking within it?**
- Flagged set (21d fwd, annualised): **+5.38%** vs whole universe **+7.88%** →
  the **filter alone costs −2.50 pts/yr**. Names 1.0 sd above their 300-day mean *and*
  above their 40-day SMA underperformed the universe in TEST.
- Concentrating on the **top-ranked** names (score ≥ 0.5): **+2.67%** vs whole flagged set
  **+5.38%** → the **126d momentum ranking adds a further −2.71 pts/yr**. Buying the
  *most* extended names was worse than the average flagged name.

So **both stages destroyed value**: first the filter (buy extended names), then the
ranking (prefer the very most extended). This is the classic momentum-crash signature —
capping into strength, then concentrating in the most crowded winners.

**Q3 — what we owned.** Mean weights ~2–4% across large winners (bel +112%, eichermot
+77%, bhartiartl +76% — all profitable names) but net contributions were tiny, while a
tail of large losers (tcs −40%, itc −36%, infy −28%) dragged. Concentrated small weights
meant the winners could not offset the losers.

**The one-off TEST read** — same frozen variant, TRAIN vs TEST:

| | TRAIN (selected) | TEST (one read) |
|---|---|---|
| CAGR | +14.30% | +1.26% |
| Sharpe | +0.69 | −0.35 |

A **1.04 Sharpe swing** on an unchanged strategy. The TRAIN edge was not real edge; it
was regime-fitting to 2016–2023 and it did not survive.

---

## 10. Findings and next steps

**Most likely reason for failure:** the strategy systematically buys the most
statistically-extended, highest-momentum stocks (`z₃₀₀ > entry` AND `close > SMA₄₀`,
ranked by 126d momentum). That is a crowded-momentum bet. In the 2024–2026 TEST regime —
a sharp, broad drawdown through 2026 — crowded momentum unwound, and this book, holding
the most extended names with 3.8x/yr turnover, amplified the unwind. The TRAIN window
(2016–2023, strong trending bull) rewarded exactly this behaviour, which is why the
in-sample Sharpe of +0.69 was an illusion of regime, not signal.

**The one thing to try next:** nothing *within* this signal family. Do not re-tune
`slow`/`entry` — that is minimising noise (5 variants already showed the whole grid is
flat-to-negative OOS). If pursuing this catalog slot further, the honest test is to
replicate the *filter* with a **regime gate** (e.g. only hold when the index is in an
uptrend, via `nsealgo.factors.regime`), since the Q2 evidence says the unconditional
"extended names" filter is what costs −2.5 pts/yr. But that is a new strategy, not a
rescue of this one.

---

## 11. Plain verdict

> **Does `trend_mean_reversion` make money on NSE NIFTY-50? NO.**
>
> Out-of-sample it returns **1.26% CAGR, Sharpe −0.35**, losing to buy-and-hold by
> **7.11 pts/yr** *and* to it on drawdown, failing to beat a **random** selector on
> return (45th pctile), and beaten on risk by the production composite. It also does not
> implement mean reversion at all — it is trend continuation (§1 F3) — so its failure
> says nothing about the reversal thesis; it says this momentum variant is dead on NSE.
> This is a **negative, publishable result**, honestly obtained under the protocol.

**Protocol compliance summary**
- ✅ 5/5 variants declared before running; **exactly 5 run**, none exceeded.
- ✅ Selection on TRAIN only (max Sharpe); winner frozen with `engine_sha`.
- ✅ TEST read exactly once; engine_sha asserted unchanged; nothing re-tuned after.
- ✅ Every result net of the full 21.92 bps delivery stack (11.92 statutory + 2×5 slip);
  zero-cost (11.92 bps) control run and labelled separately.
- ✅ Random-signal control (20 seeds) **and** signal-scrambled control (20 seeds) both
  run on TEST and compared; verdict stated against both.
- ✅ Buy-and-hold and nsealgo composite reported on the identical window.
- ✅ Sanity checks 1–5 all run; the failing one (#5 negative control) is reported, not
  hidden.
- ✅ Fidelity to the real catalog class proven at 100% over 4625 bars.
- ✅ No `src/` or `tests/` files modified; scratch confined to `research/agent_tmr/`.
