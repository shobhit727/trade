# `ensemble_signals` on NSE NIFTY-50 — NEGATIVE FINDING

Source: `src/cryptobot/strategies/catalog/ensemble_signals_strategy.py`
Scratch: `research/agent_ensemble/` (`run.py` protocol, `diag.py` TRAIN-only diagnostic,
`results.json`); bugs in `research/agent_ensemble/BUGS.md`.

**One-line verdict: No.** TEST +2.18% CAGR / Sharpe −0.28 / MaxDD −15.48% vs 2.60% /
−0.22 / −16.86% for buy-and-hold; lost to 20/20 random signals. The three "independent"
legs agree 93.4% (SMA vs EMA) and the third one (RSI) is wrong-signed on TRAIN.
Also found: a **HIGH-severity data bug** in `load_universe` (§7 / `BUGS.md`).

---

## 0. Strategy under test

`EnsembleSignalsStrategy` votes three indicators and only signals when a quorum agrees:

| leg | condition | vote |
|-----|-----------|------|
| SMA | `close > SMA(period)` | +1 else −1 |
| EMA | `close > EMA(period)` | +1 else −1 |
| RSI | `RSI(rsip) > 55` | +1, `RSI < 45` → −1, else 0 |

`signal = +1 if votes >= min_votes else (-1 if votes <= -min_votes else 0)`.
Catalog defaults: `period=20`, `rsip=14`, `min_votes=2`.
The `if sma(...) != sma(...)` line in the source is dead (it adds 0).

Note at declaration time, before any result: **all three legs vote on the same latent
thing** — recent price strength. SMA-up, EMA-up and RSI>55 are near-collinear. This is a
redundant ensemble, not three independent opinions, and I expect it to behave like a
single momentum gate. Recording this now so the finding cannot be re-interpreted later.

Not crypto-specific (no funding, liquidations, pegs, IV or basis) — so it is admissible
on NSE and the work continues.

---

## 1. Declared parameter budget — 5 variants, declared before any run

One-at-a-time around the catalog default. Rebalance frequency held at monthly throughout
(the engine's evidence note; no Indian study supports weekly).

| Variant | `period` (SMA+EMA) | `rsip` | `min_votes` |
|---------|--------------------|--------|-------------|
| V1 | 20 | 14 | 2 (catalog default) |
| V2 | 10 | 14 | 2 |
| V3 | 50 | 14 | 2 |
| V4 | 20 | 7 | 2 |
| V5 | 20 | 14 | 3 (unanimous) |

The RSI 55/45 thresholds are hard-coded literals in the strategy source; changing them
would be editing the strategy, not varying a parameter, so they are held fixed.

**Selection rule, fixed in advance: max TRAIN Calmar.** No threshold may be tuned against
the equity curve. If I end up running more than these 5 variants I will say so in this
report rather than hide it.

---

## 2. Data

`load_universe("data/nse")` → **panel (4629, 48)**, 2008-01-01 → 2026-10-01, 13,966 NaNs.

```
rows in 274,541 | out 208,226 | dropped pre-2008 66,312 | artifact 0
non-positive 0 | extreme 3 | excluded symbols ['adanient', 'jiofin']
```

Survivorship bias is present (today's NIFTY-50, backfilled) and applies to every number
below. Costs: `CostModel(segment="delivery", slippage_bps=5)` →
`round_trip_bps = 11.92`, `all_in_round_trip_bps = 21.92`. Because `run_backtest` folds
slippage into the round trip, **every result here is net of 21.92 bps** unless explicitly
labelled zero-cost.

**Panel repair (judgement call, disclosed).** `load_universe` returns 13,966 NaN cells, of
which 45 are *interior* holes — 39 symbols each missing the same date, **2010-02-06, a
Saturday** (see §7 / BUG 1). I repaired them with `panel.ffill()`, forward-fill from the
past only. `ffill` never backfills, so the 13,921 pre-listing NaNs (`eternal`,
`maxhealth`, `hdfclife`, `sbilife`, `indigo`, `coalindia`) are preserved and no price
history is fabricated. Without this repair the signal panel is silently wrong for `period`
bars after the hole and the vectorised replica does not match the catalog strategy.

---

## 3. Harness fidelity check (run before any result was trusted)

A vectorised replica of `EnsembleSignalsStrategy.signal()` was checked against the real
class, bar by bar, on 24 of 48 symbols (dense coverage of the first 250 bars post-warmup,
then every 8th bar; ~19,000 bars per variant):

```
V1_20_14_2: 18993 bars -> 0 mismatches  PASS
V2_10_14_2: 19040 bars -> 0 mismatches  PASS
V3_50_14_2: 18920 bars -> 0 mismatches  PASS
V4_20_7_2:  18993 bars -> 0 mismatches  PASS
V5_20_14_3: 18993 bars -> 0 mismatches  PASS
```

It did **not** pass on the first attempt. See §7 — the first failure exposed a real bug
in `load_universe`.

Reconstruction of the two matching indicator definitions: `EMA` is the prefix-stable
recursion seeded at the first bar (`ewm(span, adjust=False)`), matching cryptobot's
`ema()`; `RSI` is the **simple, not Wilder-smoothed**, RSI over the last `rsip+1` closes,
matching cryptobot's `rsi()` exactly (first valid value at index `rsip`).

---

## 4. TRAIN (2016-01-01 → 2023-12-31) — selection only

Net of 21.92 bps all-in. Selection rule fixed in advance: **max TRAIN Calmar**.

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Avg names | Long frac |
|---------|-------|--------|--------|--------|----------|-----------|-----------|-----------|
| V1 20/14/2 | 15.34 | 0.69 | −26.32 | 0.58 | 3.97 | 1.56 | 28.4 | 51.1% |
| **V2 10/14/2 (selected)** | 17.79 | **0.91** | **−11.49** | **1.55** | 4.04 | 1.76 | 28.8 | 45.7% |
| V3 50/14/2 | 14.09 | 0.60 | −29.33 | 0.48 | 3.90 | 1.45 | 26.9 | 50.4% |
| V4 20/7/2 | 17.13 | 0.85 | −19.07 | 0.90 | 4.04 | 1.71 | 28.6 | 47.0% |
| V5 20/14/3 | 13.92 | 0.63 | −24.53 | 0.57 | 4.07 | 1.48 | 28.3 | 42.0% |
| buy & hold | 18.38 | 0.78 | −34.92 | 0.53 | 2.64 | 1.18 | 22.2 | — |
| nsealgo composite | **21.30** | 0.96 | −32.92 | 0.65 | 1.96 | 1.00 | 21.8 | — |

**Selected: V2** (`period=10, rsip=14, min_votes=2`), on TRAIN Calmar 1.55 vs 0.53 for
buy-and-hold. On TRAIN this looked genuinely good — V2 beat buy-and-hold on Sharpe
(0.91 vs 0.78) and cut the drawdown from −34.9% to −11.5% at almost identical CAGR. That
"ensemble as a drawdown filter" story is what the TRAIN window sells.

V5 (`min_votes=3`, i.e. unanimous) was clearly worse on TRAIN — tightening the quorum
hurt, which is the first hint that the ensemble adds nothing over its own members.

---

## 5. TEST (2024-01-01 → 2026-10-01) — evaluated once, unchanged

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Avg names | Long frac |
|---------|-------|--------|--------|--------|----------|-----------|-----------|-----------|
| V1 20/14/2 | 1.57 | −0.33 | −18.06 | 0.09 | 4.07 | 1.03 | 27.5 | 49.3% |
| **V2 10/14/2 (selected)** | **2.18** | **−0.28** | **−15.48** | 0.14 | 4.09 | 1.02 | 28.4 | 44.1% |
| V3 50/14/2 | 0.60 | −0.39 | −20.66 | 0.03 | 3.96 | 0.99 | 26.4 | 48.3% |
| V4 20/7/2 | 3.31 | −0.19 | −15.31 | 0.22 | 4.08 | 1.06 | 27.8 | 45.5% |
| V5 20/14/3 | 1.87 | −0.33 | −14.90 | 0.13 | 4.15 | 1.04 | 28.8 | 39.6% |
| **buy & hold** | 2.60 | −0.22 | −16.86 | 0.15 | 2.76 | 0.70 | 21.3 | — |
| **nsealgo composite** | **6.55** | 0.07 | −14.84 | 0.44 | 2.07 | 0.55 | 21.3 | — |

Selected variant, TEST calendar years: 2024 **+15.92%**, 2025 **+2.90%**,
2026 (to 10-01) **−10.93%**.
Buy-and-hold, same years: +18.60%, +3.12%, −12.12%.

### TEST vs buy-and-hold (selected variant)

- Return: **worse by 0.42 pp/yr** (2.18% vs 2.60%).
- Drawdown: **better by 1.38 pp** (−15.48% vs −16.86%). This *did* transfer, unlike most
  catalog strategies in this project — but it is worth only 1.4 pp of drawdown and cost
  0.4 pp/yr of return, so it is a wash, not an edge.
- Sharpe: **worse** (−0.28 vs −0.22).
- Turnover: **55% higher** (4.09 vs 2.76 x/yr) for a worse return.

### vs nsealgo composite

**Worse on everything.** 2.18% vs 6.55% CAGR, Sharpe −0.28 vs 0.07, Calmar 0.14 vs 0.44,
at 1.7× the turnover. The composite is the benchmark that matters for deployment, and the
ensemble signal does not come close.

### Negative control — random signal, 20 seeds, same % of bars long

TEST CAGR: median **+5.58%**, range +2.44% to +7.44%.
**The selected variant lost to 20 of 20 random seeds**, by a median 3.4 pp/yr.
This is the same structural failure the momentum-gate strategies hit: the per-symbol trend
flag removes the best names from a book that is already ranked on 126-day momentum.

### Cost stress (selected variant, TEST CAGR%)

| double slippage (10 bps) | triple (15 bps) | zero cost |
|---|---|---|
| 1.76 | 1.35 | 2.60 |

Gross (zero-cost) 2.60% vs net 2.18% → cost drag ~0.42 pp/yr, consistent with the
reported 1.02 %/y drag against a compounding book. **The strategy is not cost-killed** —
it is simply not selected, by a coin flip or by buy-and-hold.

---

## 6. Sanity checks

1. **Plausibility — PASS.** 1.6–3.3% CAGR, nowhere near the 40–50% unlevered ceiling.
2. **Weight count — PASS.** 26.4–28.8 names held against the 22 target; the excess is
   `max_names=30` in `PortfolioConfig` plus the turnover-budget blend retaining a few
   residuals. Not the 48-name accretion bug.
3. **Signal liveness — PASS.** Long 39.6–51.1% of bars. Genuinely deployed, not a
   de-facto-cash strategy.
4. **Cost drag — PASS / low.** 0.99–1.06 %/y, charged against compounding equity.
   Gross is positive, net is positive; the strategy fails on selection, not costs.
5. **Negative control — FAIL. Lost to random 20/20.**

---

## 7. Bugs found (full write-up in `research/agent_ensemble/BUGS.md`)

**BUG 1 (HIGH) — `load_universe` returns internal NaNs that silently poison rolling and
recursive indicators.** `loader.py:250-252` pivots per-symbol frames onto their *union*
index after C6 has only asserted no-NaN *within* each symbol. The result contains a
Saturday, **2010-02-06**, that is missing from the raw CSV of **39 of 48** symbols, plus
2–3 isolated holes in three others. Any `panel.rolling()` / `panel.ewm()` built directly
on the returned panel is wrong for `period` bars after every hole. My first verification
attempt caught it: the replica disagreed with the real catalog class on 44–116 bars per
variant. `run_backtest` itself survives (it uses `pct_change(fill_method=None).fillna(0.0)`
and `min_periods=20`), so the failure is invisible in the results — it just silently
degrades the signal. I repaired it with `panel.ffill()` (past-only; pre-listing NaNs are
preserved, no fabricated price history), after which the replica is bit-faithful.

**BUG 2 (LOW) — dead code** at `ensemble_signals_strategy.py:31-32`: a NaN guard that adds
0. Harmless, but it hides the real behaviour — during warmup `closes[-1] > sma(...)` is
`False`, so the leg votes **−1**, not 0.

---

## 9. Why it fails — TRAIN-only mechanism diagnostic (`diag.py`)

Nothing below reads TEST. These are diagnostics of the mechanism, not parameter variants.

### 9.1 It is not a 3-member ensemble; it is one vote plus noise

| pair | identical sign |
|------|----------------|
| SMA vs EMA | **93.4%** |
| SMA vs RSI | 61.2% |
| EMA vs RSI | 65.2% |
| all three | 60.7% |

SMA(10) and EMA(10) are the same opinion stated twice. The ensemble agrees with its own
best member — the SMA leg — **92.6%** of the time. Voting three near-identical trend
indicators and demanding a quorum of 2 does not manufacture consensus; it manufactures a
2-of-3 filter with a redundant member, which is why it degrades exactly like a single
trend gate.

### 9.2 On TRAIN the signal is very nearly non-predictive

Mean forward 21-day return by signal state (TRAIN, 94,800 name-day cells):

| state | n | mean fwd 21d |
|-------|---|---------------|
| long (+1) | 43,187 | +1.946% |
| short (−1) | 31,840 | **+1.901%** |
| flat (0) | 19,773 | +1.827% |
| *universe mean* | — | *+1.909%* |

Long-minus-flat is **+0.12 pp over 21 days** — about 0.07%/yr of edge, and long names beat
the universe mean by 0.04 pp. **The short state is not worse than the long state.** There
is essentially no directional information in this signal.

### 9.3 The quorum is a *negative* filter, even on TRAIN

Forward 21d mean by raw vote sum, TRAIN:

| votes | n | mean fwd |
|-------|---|----------|
| −3 | 23,048 | +1.894% |
| −2 | 12,771 | +1.514% |
| −1 | 7,169 | +2.023% |
| 0 | 1,597 | +2.191% |
| 1 | 7,005 | +2.096% |
| **2** | 8,673 | **+2.326%** |
| 3 | 34,537 | +1.846% |

Non-monotone, and `votes≥2` vs `votes∈{0,1}` is **−0.170 pp**: requiring the quorum picks
*worse* forward returns than a weaker filter. The `votes=3` bucket (+1.846%) is below the
universe mean — the unanimous state is the *worst* well-populated bucket.

Per-leg ablation (TRAIN):

| leg | on (+1) | off (−1) | spread |
|-----|---------|----------|--------|
| SMA | +1.979% | +1.824% | **+0.155 pp** |
| EMA | +1.948% | +1.860% | +0.088 pp |
| RSI | +1.890% | +1.923% | **−0.033 pp (wrong-signed)** |

The RSI leg is the *worst* of the three and it is **negative**. Requiring `RSI>55` as a
condition for buying removes better names than it adds. And where the ensemble and its own
SMA leg disagree, the ensemble is the worse pick: `ensemble ∩ sma` = +1.946% (n=43,187) vs
`sma-only` = **+2.178%** (n=7,050).

### 9.4 The TRAIN Calmar advantage was one 33-day event

The whole reason V2 won on TRAIN Calmar (1.55 vs BH 0.53) is visible in *where* each
maximum drawdown occurred:

| | TRAIN MaxDD | episode | worst DD in 2018 | in 2020 | in 2022 |
|---|---|---|---|---|---|
| V2 selected | −11.49% | 2021-10-18 → 2022-06-20 (245d) | −11.17% | −11.02% | −11.28% |
| buy & hold | −34.92% | **2020-02-19 → 2020-03-23 (33d)** | −11.96% | **−34.92%** | −13.40% |

Buy-and-hold's entire TRAIN MaxDD *is* the COVID crash. In every other year BH's worst
drawdown is −12% to −13%. V2's COVID drawdown (−11.02%) is indistinguishable from its
2018 and 2022 drawdowns (−11.17%, −11.28%). So the signal did **not** persistently manage
risk — it happened to be flat for 33 specific days in Feb–Mar 2020, and that single
episode is the whole TRAIN Calmar edge.

Breadth does carry weak market-timing information (corr(breadth, forward 21d market
return) = +0.062; forward market return by breadth quintile Q1 +1.28% → Q5 +2.20%), which
is the mechanism. But a correlation of 0.06 is not a risk-management system, and TEST
confirms it: the drawdown advantage shrank from 23.4 pp to 1.4 pp out of sample.

---

## 10. Verdict

**No — `ensemble_signals` does not make money on NSE.** Out-of-sample it returns
**+2.18% CAGR / Sharpe −0.28 / MaxDD −15.48% / Calmar 0.14** against **2.60% / −0.22 /
−16.86% / 0.15** for buy-and-hold and **6.55%** for the nsealgo composite — worse on
return, Sharpe and Calmar, better on drawdown by 1.4 pp, at 55% higher turnover. It lost
to a **random signal with identical exposure in 20 of 20 seeds** (median 5.58% CAGR). It is
not cost-killed (gross 2.60% → net 2.18%), so the finding is a failure of *selection*, not
of execution.

### Most likely reason

**The ensemble is not an ensemble.** SMA(10) and EMA(10) agree on 93.4% of bars, so a
`min_votes=2` quorum is a single trend filter with a redundant member, and that redundant
member is the RSI leg — which is **wrong-signed on TRAIN (−0.033 pp)**. Demanding RSI
confirmation removes better names than it adds (`votes≥2` is −0.170 pp against a weaker filter), and the whole book is then ranked on
126-day momentum that the flag has already partially destroyed. The TRAIN Calmar win was a
single 33-day COVID episode, not a property of the signal.

---

### The one thing I would try next

**Do not build the book from this signal. Use vote breadth as a *continuous* exposure
scaler, not a name filter** — i.e. `blend_with_cash` on the 126-day momentum book, sized
by ensemble breadth, so the signal controls how much risk is taken rather than *which*
names are taken. The TRAIN quintile table (Q1 +1.28% → Q5 +2.20% forward market return)
is the only evidence in this strategy, and it is evidence about *exposure*, not about
cross-sectional selection. Expect the honest ceiling to be a few tenths of a percent a
year, and re-test breadth as a scaler **without** reusing this TEST window, because
selecting V2 already spent it.

### Bottom line for the catalog

`ensemble_signals` should be retired as a standalone entry. It is, however, the cleanest
example in the catalog of a specific anti-pattern worth writing down: **correlated
indicators voted together do not add confidence, they add a filter that removes the best
names.** Any future "multi-signal" strategy in this repo should be required to publish the
pairwise agreement matrix of its members *and* the per-leg forward-return spread before its
TRAIN numbers are allowed to count. Two of three legs here would have failed that check on
its own.

---

## 11. Protocol compliance

- Parameters chosen on TRAIN only; TEST evaluated once, unchanged, after V2 was frozen.
- **5 variants declared, 5 run. No threshold tuned against the equity curve. No extra
  variant run at any point, including after seeing TEST.**
- Signal verified bit-faithful against the catalog class before any result was used.
- No lookahead: SMA/EMA/RSI/momentum all use closes up to and including *t*;
  `run_backtest` holds those weights from *t+1* (`held.shift(1) * rets`). Forward-fill is
  past-only.
- Costs = full Indian delivery stack incl. 18% GST, netted at 21.92 bps per round trip.
- Survivorship bias (today's NIFTY-50, backfilled) applies to every table.
- Nothing committed.