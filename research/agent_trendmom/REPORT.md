# `trend_momentum_strategy` on NSE NIFTY-50 — **NEGATIVE FINDING**

Source: `src/cryptobot/strategies/catalog/trend_momentum_strategy.py`
Scratch: `run.py` (protocol), `diag.py` (TRAIN-only diagnostic), `BUG_engine_changed_midrun.md`
Reproduce: `.venv/bin/python research/agent_trendmom/run.py` · `.venv/bin/python research/agent_trendmom/diag.py`

> **Bad news first (GOAL.md §6.7).** The strategy **loses money out-of-sample**: −0.27% CAGR
> net of the full Indian delivery stack, against **+8.18%** for buy-and-hold over the identical
> window. It fails the negative control **0/20**. It also failed on TRAIN (every variant lost
> to both buy-and-hold and the nsealgo composite). There is nothing here worth deploying.

**Engine fingerprint:** `src/nsealgo/backtest/engine.py`
sha256 `6dbee619a0d52b5861b11f41e35cd249e5e90164dce21b2242c0a65306c5b1f4`.

⚠️ **That file was rewritten by another process TWICE while this session was running** — at
14:05:28 and again at 14:11:08 on 2026-10-09 — both times uncommitted, both times changing
`apply_turnover_budget`. I did not touch it. Every number in this report is from the
14:11:08 version; five consecutive executions reproduced it byte-for-byte. The selected
variant's TEST result is **identical under both post-14:05 versions**, but three of the five
unselected variants moved by up to 0.12 pp of CAGR, so the full tables below are pinned to
the hash above and must not be compared against reports produced before 14:05 or between
14:05 and 14:11. Full incident write-up: **`BUG_engine_changed_midrun.md`** — please read it,
it affects ~30 other agent reports.

---

## 0. Is this strategy meaningful on NSE? (brief §9 pre-check)

**Yes — not crypto-specific.** The catalog file reads closes only (`sma`, `roc`) and emits a
±1/0 time-series signal. No funding rate, no liquidations, no stablecoin peg, no options IV,
no spot-futures basis. It is a portable dual-condition trend/momentum filter and has a direct
NSE reading, so I ran the full protocol.

---

## 1. The strategy, and how it maps onto the book

```python
f = sma(closes, fastperiod);  s = sma(closes, slow);  m = roc(closes, momperiod)
+1 if f > s and m >  threshold
-1 if f < s and m < -threshold
 0 otherwise
```

Two legs that must **agree**: a trend leg (fast SMA above slow SMA) and a momentum leg
(short-horizon ROC has moved more than ±`threshold` in the trend's direction). Catalog
defaults: `fast=10, slow=40, mom=15, threshold=0.01`.

Two consequences of mapping a ±1/0 time-series signal onto a long-only cross-sectional book:

1. **Only `+1` is holdable** (no shorts in an Indian delivery account, GOAL.md §3.1). The `0`
   state is also not holdable, so this is *more* selective than a plain dual-MA crossover —
   both legs must fire.
2. **The signal is a filter; a rank picks the winners among survivors.** Brief §5 recipe,
   used verbatim:
   ```python
   score = (panel/panel.shift(126) - 1.0).where(signal_panel > 0).rank(axis=1, pct=True)
   ```
   126d trailing momentum, ranked cross-sectionally **only among names flagged `+1`**.
   Unflagged names are NaN and are therefore unbuyable by the engine.

Portfolio: `PortfolioConfig()` defaults (22 positions, 12% single name, 25% sector, 10% cash,
35% turnover budget, 30-name thinning), enforced by `run_backtest`. Monthly rebalance.
Costs: `CostModel(segment="delivery", slippage_bps=5)` →
**`all_in_round_trip_bps(100_000)` = 21.92 bps** (statutory 11.92 + 2×5 bps slippage),
charged every rebalance against compounding equity. **Every number is net of 21.92 bps**
unless explicitly labelled zero-cost.

### Data

`load_universe("data/nse")` → **48 symbols × 4,625 bars, 2008-01-01 → 2026-10-01**.
Cleaning: 274,541 → 208,226 rows (66,312 pre-2008 dropped, `adanient` + `jiofin` excluded,
3 extreme moves dropped). **Survivorship bias is present** (today's NIFTY-50, backfilled);
GOAL.md §11.1 measures it at ~7.3%/yr. It applies to every table below.

---

## 2. Declared parameter budget — 5 variants, declared before running

| Variant | fast | slow | mom | threshold | rationale |
|---------|------|------|-----|-----------|-----------|
| **V1** | 10 | 40 | 15 | 0.01 | **catalog default**, verbatim |
| **V2** | 20 | 100 | 60 | 0.01 | slower trend leg, longer momentum leg |
| **V3** | 50 | 200 | 60 | 0.01 | long-term trend leg |
| **V4** | 10 | 40 | 15 | 0.05 | V1 with a 5× conviction bar |
| **V5** | 5 | 20 | 10 | 0.01 | fast / short-horizon |

**Selection rule, fixed in advance: maximum TRAIN Sharpe** (tie-break TRAIN Calmar).

**Budget accounting: 5 declared, 5 run, 0 exceeded, 0 spare.**
The TRAIN-only ablations in `diag.py` are mechanism diagnostics, **not** strategy variants;
no reported result depends on them.

---

## 3. TRAIN 2016-01-01 → 2023-12-31 (selection only)

| | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Live% | YrPos |
|---|---|---|---|---|---|---|---|---|---|
| V1 10/40/15 | 6.25 | 0.02 | −25.57 | 0.24 | 4.03 | 2.14 | 15.9 | 41.1% | 0.62 |
| V2 20/100/60 | 13.98 | 0.58 | −29.81 | 0.47 | 3.30 | 2.41 | 18.7 | 52.8% | 0.75 |
| **V3 50/200/60 (SELECTED)** | **15.01** | **0.64** | **−28.11** | **0.53** | 3.37 | 2.63 | 17.6 | 46.3% | 0.88 |
| V4 10/40/15 thr5% | 4.31 | −0.25 | −15.27 | 0.28 | 3.90 | 1.92 | 10.5 | 23.9% | 0.75 |
| V5 5/20/10 | 9.04 | 0.31 | −12.32 | 0.73 | 4.10 | 2.47 | 16.3 | 41.4% | 0.75 |
| BH top-22 by 126d | 17.56 | 0.73 | −35.21 | 0.50 | 2.64 | 2.29 | 21.8 | — | 1.00 |
| **EW buy-and-hold (all 48)** | **21.49** | **0.90** | −36.66 | 0.59 | — | — | 48 | — | — |
| nsealgo composite | 20.72 | 0.93 | −32.94 | 0.63 | 1.97 | 1.97 | 21.8 | — | 1.00 |

**Every variant already lost on TRAIN** — to buy-and-hold on return and Sharpe, to the
nsealgo composite on both. The selected variant (V3) beat only the *slower* variants. Nothing
about TRAIN suggested an edge; TEST merely confirmed it.

---

## 4. TEST 2024-01-01 → 2026-10-01 — touched once, after V3 was frozen

| | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Live% | YrPos |
|---|---|---|---|---|---|---|---|---|---|
| V1 | −1.49 | −0.75 | −18.87 | −0.08 | 4.11 | 1.93 | 15.8 | 38.1% | 0.33 |
| V2 | 0.82 | −0.39 | −19.99 | 0.04 | 3.43 | 1.72 | 18.2 | 50.5% | 0.67 |
| **V3 (SELECTED)** | **−0.27** | **−0.44** | **−22.58** | **−0.01** | 3.38 | 1.68 | 17.2 | 45.2% | 0.67 |
| V4 | −1.42 | −0.87 | −16.55 | −0.09 | 3.93 | 1.80 | 9.3 | 19.3% | 0.33 |
| V5 | 0.53 | −0.62 | −18.12 | 0.03 | 4.12 | 2.00 | 16.1 | 39.0% | 0.33 |
| BH top-22 by 126d | 1.58 | −0.30 | −18.82 | 0.08 | 2.77 | 1.39 | 21.3 | — | 0.67 |
| **EW buy-and-hold (all 48)** | **8.18** | **0.18** | **−15.90** | **0.51** | — | — | 48 | — | — |
| nsealgo composite | 6.04 | 0.03 | −15.22 | 0.40 | 2.08 | 1.10 | 21.3 | — | 0.67 |

All five variants are negative or near-zero. **The ranking inverted relative to TRAIN**:
V3 was 1st of 5 on TRAIN Sharpe and 2nd of 5 on TEST; the best TEST variant (V2, +0.82%)
was 2nd of 5 on TRAIN. Nothing selected, because nothing worked.

Selected variant (V3), TEST calendar years: 2024 **+16.75%**, 2025 **+2.42%**, 2026 (to
2026-10-01) **−17.00%**.
Buy-and-hold same years: +20.13%, +13.35%, −8.27%. Top-22 momentum: +17.91%, +1.32%, −12.53%.
The whole gap is 2026, where the book gave back roughly five months of the 2024 gain.

### TEST vs buy-and-hold

Two benchmarks, because they answer different questions:

- **vs literal buy-and-hold** (brief §4 rule 5, `panel.pct_change().mean(axis=1)`, equal
  weight all 48 names, net of one round trip to build the position):
  **worse by 8.45 pp/yr** (−0.27% vs +8.18%); **worse on drawdown by 6.68 pp**
  (−22.58% vs −15.90%); **worse on Sharpe by 0.62**; **worse on Calmar by 0.52**.
- **vs the like-for-like top-22 momentum book** (same constraints, same costs, no signal
  gate): **worse by 1.85 pp/yr** (−0.27% vs +1.58%) and **worse on drawdown by 3.76 pp**.
  This is the honest measure of what the trend+momentum gate *added* over plain momentum
  exposure: **nothing.**

### Random-signal control — **FAIL**

20 seeds, identical % of bars long (45.2%), identical 126d ranking among the chosen names,
entries placed by a coin flip instead of the signal.

TEST CAGR: median **+2.46%**, range −0.00% to +4.70%.
TEST Sharpe: median −0.44, range −0.76 to −0.19.

**V3 beat 0 of 20 random seeds on CAGR** — it was the worst of 21 books compared. On Sharpe
it beat 8 of 20, i.e. it sat at the median of the coin flips. A coin flip with the same
exposure made **+2.46%** where the strategy made **−0.27%**.

### Did it beat the nsealgo composite?

**No.** Composite TEST: +6.04% CAGR, Sharpe 0.03, MaxDD −15.22%, turnover 2.08×/y. The
strategy is **6.31 pp/yr worse, 0.41 worse on Sharpe, 7.36 pp worse on drawdown**, and it
turns over 1.6× as much to earn less. It lost to the composite on TRAIN as well.

### Cost stress (V3, TEST CAGR%)

| zero cost | base (21.92 bps) | 2× slippage (31.9) | 3× slippage (41.9) |
|---|---|---|---|
| **+0.41** | **−0.27** | −0.94 | −1.61 |

Gross (zero-cost) CAGR is **+0.41%**. Costs take it negative — so cost is *part* of the story,
but the honest conclusion is stronger than "too expensive": **at literally zero cost the
strategy still made 0.41%/yr, which is inside the noise of an equal-weight index.** There was
no edge for costs to consume. Charged costs across TRAIN were ₹4,46,868 on a ₹21,00,000 book
(2.63%/yr).

### Sanity checks (brief §6)

1. **Plausibility — PASS.** Highest CAGR anywhere in this report is 21.49% (EW buy-and-hold,
   TRAIN). The strategy peaks at 15.01%. Nothing near the 40–50% unlevered ceiling; no
   lookahead, no compounding bug.
2. **Weight count — PASS.** V3 TEST: avg 17.2 names, median 21, max observed 22 (never above
   the 22 limit), min 0 (cash at the start of the window). No residual-weight accretion.
   Mean invested 79.9% against a 90% target — the shortfall is explained in §5.
3. **Signal liveness — PASS on the time-series measure, QUALIFIED on the book measure.**
   Flagged long on 45.2% of TEST bars, far clear of the 5% "effectively flat" floor. But on
   **rebalance** dates the gate offers fewer names than the book has slots (see §5), which is
   why the book averages 17.2 names rather than 22.
4. **Cost drag — REPORTED.** 1.68%/y net, gross +0.41% → net −0.27%. As above: not a
   cost-kill story, a no-edge story.
5. **Negative control — FAIL, 0/20.** This is the decisive result.

---

## 5. Why it fails (TRAIN-only diagnostic, `diag.py`)

**(a) Both legs are negatively predictive, and they compound.**

Average forward 21-day return by state, TRAIN:

| state | fwd 21d return | cells | spread vs universe |
|---|---|---|---|
| whole universe | +1.912% | — | — |
| trend leg only (SMA 50>200) | **+1.646%** | 64.5% | **−0.266 pp** |
| momentum leg only (ROC60 > 1%) | **+1.788%** | 57.9% | **−0.124 pp** |
| **both legs (= the strategy)** | **+1.700%** | 46.3% | **−0.212 pp** |

A name the strategy flags long is expected to return **21 bp less over the next month** than
a name it does not. The filter is a mildly negative-alpha screen, so applying it as a gate
deletes the better half of the candidate set.

**(b) Removing each leg strictly improves the book.** Same rank, same costs, TRAIN:

| construction | CAGR% | Sharpe | MaxDD% | Names | Turn | Cost% |
|---|---|---|---|---|---|---|
| **both legs (= the strategy)** | **15.01** | **0.64** | −28.11 | 17.6 | 3.37 | 2.63 |
| trend leg only | 17.12 | 0.71 | −35.10 | 20.6 | 2.61 | 2.21 |
| momentum leg only | 14.57 | 0.61 | −29.96 | 19.5 | 3.34 | 2.50 |
| **no gate at all (= top-22 momentum)** | **17.56** | **0.73** | −35.21 | 21.8 | 2.64 | 2.29 |
| rank by the strategy's own ROC(60) | 13.47 | 0.54 | −27.41 | 17.6 | — | — |

Every addition of the gate costs return. The one place the gate *helps* is drawdown
(−28.1% vs −35.2%), and that is bought by holding cash in a smaller, more concentrated
book — not by alpha.

**(c) More conviction makes it monotonically worse.** Raising the momentum threshold on V3,
TRAIN:

| threshold | 0.00 | 0.01 | 0.02 | 0.05 | 0.10 |
|---|---|---|---|---|---|
| CAGR% | 15.77 | 15.01 | 13.97 | 13.63 | 9.88 |
| Sharpe | 0.69 | 0.64 | 0.58 | 0.56 | 0.32 |
| live% | 48.3 | 46.3 | 44.3 | 38.1 | 27.2 |

The catalog's 1% conviction bar costs 0.76 pp of CAGR and 0.05 of Sharpe on TRAIN for no
benefit at all. A signal whose *strength* dial only ever hurts is a signal whose direction
is wrong, not merely noisy.

**(d) Breadth is wrong-signed as a market timer.** TRAIN,
corr(fraction of names with SMA50>SMA200, forward 21d equal-weight return) = **−0.114**.
Lowest-breadth quartile: forward 21d **+3.272%**. Highest-breadth quartile: **+2.438%**.
Spread **−0.834 pp** — i.e. on this universe a broad, "everything is trending up" reading was
a *reliable forward sign of worse returns*. So the trend leg cannot be salvaged as an exposure
overlay either; it points the wrong way.

**(e) Structural: the gate under-fills the book.** Flagged names on the first trading day of
each month:

| window | mean | median | min | max | rebalances with <22 flagged | with <10 |
|---|---|---|---|---|---|---|
| TRAIN | 22.0 | 22 | 3 | 44 | 45/96 | 10/96 |
| TEST | 22.3 | 22 | 3 | 43 | 17/34 | 6/34 |

On roughly **half of all rebalances the confluence filter offers fewer candidates than the
book has slots**, and on ~1-in-8 it offers fewer than ten. Combined with the 12% single-name
cap, that forces large unplanned cash positions — which is precisely why mean invested weight
is 79.9% against a 90% target. The strategy cannot even fill its mandate consistently.

**(f) Robustness checks (GOAL.md §5 Gate 4).** P&L concentration on TRAIN is *good* — top
single stock 5.6%, top 3 = 15.3%, all 48 names contributed. Turnover does not blow up
(3.4×/y). But **1 of 5 neighbouring parameter settings was profitable on TEST** (Gate 4 wants
≥4 of 6), and the 2× slippage stress takes it further negative. Gate 4 fails.

---

## 6. Verdict

**No — `trend_momentum_strategy` does not make money on NSE.** It returns **−0.27% CAGR
out-of-sample** against **+8.18%** for buy-and-hold and +2.46% for a random signal with the
same exposure, loses to buy-and-hold on return, Sharpe and drawdown alike, loses to the
nsealgo composite by 6.31 pp/yr, and fails the negative control **0 for 20**.

**Most likely reason:** the two legs are **redundant** with the cross-sectional momentum rank
the book already sorts on, and on this universe each is **mildly negatively** predictive of
forward 21-day returns. Requiring confluence then compounds two negative screens and deletes
the highest-momentum names — which are exactly the names carrying the alpha. Per-symbol
trend-following has no marginal information once the book is already long-only and ranked by
momentum, and on NIFTY-50 it selects against the return.

**One thing to try next:** drop the confluence entirely and retire the strategy as an entry
signal. The TRAIN evidence is unambiguous and consistent in direction (every threshold, every
leg ablation, and the breadth correlation all point the same way), so re-parameterising it
would be curve-fitting to a result already known to be wrong. If a trend input is wanted, the
only reading left untested here is the *unconditional* one — size the existing
momentum-composite book down when trend breadth is **low** rather than high, since (d) shows
breadth was anti-predictive. That inverts the strategy's own thesis, which is a sign it is a
different strategy, and I would want it validated as one on a fresh TRAIN/TEST split rather
than borrowed from this run.

---

### Protocol compliance

- Parameters chosen on **TRAIN only**; TEST evaluated once, unchanged, after V3 was frozen by
  the pre-declared max-TRAIN-Sharpe rule. **I did not look at TEST while iterating.**
- **5 variants declared, 5 run, 0 exceeded.** No threshold tuning against any equity curve.
  The threshold sweep in §5(c) is a TRAIN-only mechanism diagnostic.
- No lookahead: SMA/ROC at *t* use closes up to and including *t*; `run_backtest` holds those
  weights from *t+1* (`held.shift(1) * rets`). No forward-fill from the future.
- Costs are the full Indian delivery stack including 18% GST, charged every rebalance against
  compounding equity, at **21.92 bps** all-in. All numbers net unless labelled zero-cost.
- Survivorship bias disclosed throughout.
- Engine fingerprint recorded (`6dbee619…`); five consecutive executions reproduced the
  tables exactly.
- Nothing under `src/` or `tests/` was modified. No commit, no push.