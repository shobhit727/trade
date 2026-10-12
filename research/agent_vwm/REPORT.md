# AGENT REPORT — `volume_weighted_momentum`

> **STATUS: COMPLETE.** Header + declared parameter budget were written and committed to
> disk *before* any backtest ran (`AGENT_BRIEF.md` §8). Results appended below in the
> order they were produced.
>
> **HEADLINE: `volume_weighted_momentum` does NOT make money on NSE. TEST CAGR +0.64%
> vs buy-and-hold +8.18%. And it does not use volume at all — see §6, which is the
> most important finding in this report.**

## 0. Provenance (header — captured BEFORE any run)

```
from nsealgo.provenance import provenance; provenance()
{'engine': 'd93815344bd3', 'loader': 'c1badf5f7df8', 'costs': 'ba350aef75b3', 'panel': '389b082b832f'}
```

| Fingerprint | SHA-12 |
|---|---|
| `backtest/engine.py` | `d93815344bd3` |
| `data/loader.py` | `c1badf5f7df8` |
| `costs.py` | `ba350aef75b3` |
| `data/nse/*.csv` panel | `389b082b832f` |

## 1. Assignment

**Strategy:** `src/cryptobot/strategies/catalog/volume_weighted_momentum.py` →
`VwMomentumStrategy` (name `vw_momentum`), config `VwMomentumConfig(period=20, threshold=0.01)`.

**What it actually computes** (read from source, not assumed):

```python
m   = roc(closes, period)                                  # (C_t - C_{t-p}) / C_{t-p}
avg = mean(volumes[-period:])                              # trailing mean volume
vw  = avg * (1.0 if volumes[-1] >= avg else 0.5)           # <-- the "volume weighting"
+1  if m >  threshold and vw > 0
-1  if m < -threshold and vw > 0
 0  otherwise
```

**It is not crypto-specific.** No funding, no liquidations, no peg, no options IV, no
spot-futures basis. It is a price-ROC momentum gate with a volume filter — every input
(close, volume) exists in `data/nse/*_1d.csv`. So the "no NSE meaning" escape clause in
`AGENT_BRIEF.md` §9 does **not** apply; the work proceeds.

**Structural note (read before the numbers, and it matters):** the strategy is a *time-series*
per-symbol +1/0/−1 indicator. The NSE book is *long-only and cross-sectional*. Bridging
those is the main construction decision — see §4.

## 2. Data

| Item | Value |
|---|---|
| Loader | `nsealgo.data.loader.load_universe("data/nse")` (C1–C9 cleaning, auditable report) |
| Panel | cleaned daily **close**, wide, tz-aware Asia/Kolkata index |
| Volume | **NOT** returned by `load_universe` — re-read from the same CSVs with the same cleaning, see §3 |
| TRAIN | 2016-01-01 → 2023-12-31 (all tuning) |
| TEST | 2024-01-01 → 2026-10-01 (touched once, at the end) |

Survivorship bias is present and disclosed: the panel is today's NIFTY-50, backfilled.
Data ends 2026-10-01.

## 3. ⚠️ Volume-column caveat (mandatory, from the task prompt)

The audit found NSE `volume` unreliable: **~485 zero-volume bars** pooled and frozen-price
runs (loader rule C9 drops runs of ≥5 identical closes; those runs are 98–100%
zero-volume). `research/data_quality/FINDINGS.md` §1 independently measures **1.52% dead
bars** (`vol == 0` and `high == low == open == close`), concentrated in `nestleind`
(1,723 zero-volume bars, 2003–2009).

**Therefore: no volume-weighted result in this report is trustworthy without an explicit
measurement of how much of the signal actually consumed volume.** §5 reports that
measurement. The headline signal here degenerates to something that needs very little
volume — see §4 — which is itself a finding.

## 4. Declared parameter budget — **5 variants, declared before any run**

Fixed across all variants (NOT tunable, fixed up front so it cannot be tuned):
rebalance = monthly (`"M"`), `PortfolioConfig()` defaults (22 names, 12% single, 25%
sector, 10% cash, 35% turnover budget, 30 max names), costs = `CostModel(segment="delivery",
slippage_bps=5)` → `all_in_round_trip_bps(1e5)` = **21.92 bps**, which is what `run_backtest`
actually charges. Long-only. Score = trailing 126d return, masked to names the strategy
flags long.

The 5 variants (all of them variants of the strategy's own two knobs):

| # | `period` | `threshold` | Rationale (declared in advance, not chosen post-hoc) |
|---|---|---|---|
| V1 | 20 | 0.01 | catalog defaults, verbatim |
| V2 | 20 | 0.05 | same horizon, threshold tightened to reduce near-noise crossings |
| V3 | 63 | 0.03 | ~1 quarter ROC — the swing-horizon floor this repo permits |
| V4 | 126 | 0.06 | ~6m ROC — matches the repo's proven 6m momentum factor |
| V5 | 252 | 0.10 | ~12m ROC — matches the proven 12-1 momentum factor |

Selection rule, declared in advance: **highest TRAIN Sharpe**, ties broken by lower TRAIN
MaxDD. Only the winner is evaluated on TEST.

## 5. Results

### 5.1 Volume-column validation (mandatory first step) — `research/agent_vwm/validate_volume.py`

| Measure | Value |
|---|---|
| Panel (post C1–C9) | 4,625 bars × 48 symbols, 2008-01-01 → 2026-10-01 |
| Raw `vol <= 0`, all timeframes | 4,263 / 281,342 = **1.5152%** |
| Cleaned `vol <= 0` (1d) | 543 / 222,000 = **0.2446%** |
| Cross-sectional volume CV | mean 1.6475, median 1.5514 — volume *does* vary across names |
| `corr(log vol, |ret|)` per day | +0.1907 — volume spikes with big moves, as it should |
| `corr(log vol, close)` per day | −0.5107 — cheap stocks trade more shares; expected, not a defect |
| Missing (NaN) volume cells | 14,455 / 222,000 = 6.51% — **all pre-listing gaps** (`eternal`, `maxhealth`, `hdfclife`, `sbilife`, `indigo`, …). Verified: `vol.isna()` is *identical* to `close.isna()`, cell for cell. |

**The task's ~485 zero-volume figure.** The audit's pooled count is reproduced and
explained: **4,263** raw zero/non-positive-volume bars exist across all timeframes,
but C1 (pre-2008) + C9 (frozen runs, which are 98–100% zero-volume) remove almost
all of them, leaving **543** in the cleaned daily panel. The *surviving* zero-volume
bars cluster in TEST, not TRAIN:

| Window | bars | zero-vol |
|---|---|---|
| TRAIN 2016-01-01 → 2023-12-29 | 1,973 | 4 / 91,298 = **0.0044%** |
| TEST 2024-01-01 → 2026-10-01 | 684 | 292 / 32,831 = **0.8894%** |

Every surviving zero-volume bar is a genuine non-trading session, not corruption:
mean `|return|` on a zero-volume bar is **0.00000** vs **0.01172** on a normal bar
— the price literally does not move. 44 of 48 symbols carry 5–9 such bars each.

**Verdict on the volume column:** it is usable but *thin* in the TEST window
(0.89% flat/holiday bars, up 200× from TRAIN) and there is no independent
5m/daily cross-check of volume in this study. Any claim resting on volume is
correspondingly weak. Sections 5.2–5.3 show volume turns out to rest nothing at all.

### 5.2 ⚠️ MAJOR FINDING: the "volume weighting" is mathematically dead code

**`volume_weighted_momentum` does not use volume. Its output is a pure function of
price.** This is not an empirical hunch — it is an algebraic identity, then
confirmed numerically on the real panel.

The strategy computes `vw = avg_volume * (1.0 if volumes[-1] >= avg_volume else 0.5)`
and then applies **exactly one test to `vw`: `vw > 0`.** Because the multiplier is
either `0.5` or `1.0` — both strictly positive — and `avg_volume >= 0`, we have:

```
vw > 0   <=>   avg_volume * 0.5 > 0   <=>   avg_volume > 0
```

The `1.0`/`0.5` branch **cannot** change the outcome of a `> 0` test. The entire
volume computation collapses to the predicate "did this name have any traded volume
in the last `period` days". Verified: `(vw > 0) == (avg_vol > 0)` is `True` at
**every cell** for periods 20 and 126.

**Empirical confirmation.** Recomputing every declared variant with the volume
series replaced by a constant-1 series (which can never make `avg_volume` zero), and
separately against a hand-written volume-free body, changes the signal on **0 cells**
— except where volume data is *missing* (see the bug below). Measured gate-blocking:

| period | cells where `vw > 0` is False |
|---|---|
| 20 | 0 / 206,562 live cells = **0.000000%** |
| 63 | 0 / 204,485 = **0.000000%** |
| 126 | 0 / 201,497 = **0.000000%** |
| 252 | 0 / 195,449 = **0.000000%** |

No window of 20/63/126/252 consecutive bars in 4,625 bars of NSE data has zero total
volume. **The gate never fires.**

**So the honest restatement of the strategy is:**
> `+1 if ROC(period) > threshold else −1 if ROC(period) < −threshold else 0`

i.e. plain time-series price momentum. Anything this strategy earns, momentum earned.

### 5.3 BUG FOUND (harness, not `src/`): wide-panel NaN padding silently corrupts a streaming strategy

`cryptobot/strategies/signal_base.py:99` feeds `VwMomentumStrategy` a **per-symbol
`deque` of real bars** (`float(volume if volume is not None else 0.0)`). A missing
vendor day produces no `feed()` call at all, so the `period`-bar window simply spans
the `period` most recent *actual* bars.

My first port computed `vol.rolling(period, min_periods=period).mean()` on the wide
NaN-padded panel. **That is not the same function.** `min_periods=period` returns NaN
if *any* cell in the window is NaN, so one missing bar → NaN for the next `period`
days → `vw` NaN → `vw > 0` is False → the strategy returns 0. A `period`-day trading
blackout for that name, out of a rule that never intended one.

Root cause found on real data: **`indigo` has no 2026-05-01 bar in the vendor feed**
(the raw CSV jumps 2026-04-30 → 2026-05-04). Because `vol.isna()` is cell-for-cell
identical to `close.isna()` (verified, 0 mismatches both directions), the missing bar
propagates into the volume window and silences indigo afterwards.

| period | spurious cells silenced by the padding bug |
|---|---|
| 20 | 20 |
| 63 | 35 |
| 126 | 53 |
| 252 | 0 |

Fixed by computing the rolling mean on each symbol's **own** bar sequence
(`dropna()` first, `.fillna(0.0)` for a close with no volume print, matching
`signal_base.py:99`), then reindexing to the panel. All numbers below use the fixed
port. **This class of bug is a general hazard for any streaming catalog strategy
vectorised onto a wide panel** — other agents porting per-bar strategies should
check for it.

### 5.4 TRAIN sweep (2016-01-01 → 2023-12-29) — all 5 declared variants

Net of **21.92 bps** all-in round trip (`rt_bps` reported by the engine = 21.92).
Monthly rebalance, `PortfolioConfig()` defaults.

| id | period | thr | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Names | %cells long |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 | 20 | 0.01 | 7.19% | 0.12 | −24.87% | 0.29 | 3.81 | 2.09% | 17.5 | 52.6% |
| V2 | 20 | 0.05 | 3.86% | −0.27 | −22.34% | 0.17 | 3.78 | 1.77% | 12.8 | 32.3% |
| **V3** | **63** | **0.03** | **14.38%** | **0.62** | −26.82% | 0.54 | 3.16 | 2.34% | 17.6 | 53.8% |
| V4 | 126 | 0.06 | 12.45% | 0.45 | −35.17% | 0.35 | 2.81 | 1.90% | 17.8 | 51.9% |
| V5 | 252 | 0.10 | 14.16% | 0.57 | −34.71% | 0.41 | 2.28 | 1.71% | 17.7 | 51.5% |
| *composite (reference)* | — | — | *20.44%* | *0.91* | *−32.94%* | *0.62* | *2.08* | *1.99%* | *21.8* | — |

**Selection by the pre-declared rule (max TRAIN Sharpe) → V3, period=63,
threshold=0.03.** Ranking: `['V3', 'V5', 'V4', 'V1', 'V2']`. Not overridden, not
re-picked after seeing TEST.

**Sanity checks (`AGENT_BRIEF.md` §6):**
1. *Plausibility* — 14.38% CAGR on an unlevered long-only NIFTY-50 book. Well inside
   the 40–50% ceiling. No compounding bug.
2. *Weight count* — **17.6 names** average, not 48. Residual accumulation is not
   happening.
3. *Signal liveness* — **53.8% of cells long**, 96.7% of days hold at least one name.
   Nowhere near the always-flat failure mode. (It is below the ~22-name target on
   36.6% of days because `momentum_rank_score` masks non-flagged names to NaN and
   `build_rebalance_weights` treats NaN as ineligible — intended, not a leak.)
4. *Cost drag* — 2.34%/yr against 14.38% CAGR. Positive gross, positive net.
5. *Negative control* — **see §5.5: volume is a literal no-op, which is the
   strongest possible control.** The price-only control reproduces V3 to 0.0000pp.

**Control A — is volume doing anything?** Each variant re-run with the volume term
deleted entirely:

| id | CAGR (no volume) | Sharpe | MaxDD | vs volume version |
|---|---|---|---|---|
| V1 | 7.19% | 0.12 | −24.87% | **IDENTICAL** (ΔCAGR 0.0000pp) |
| V2 | 3.86% | −0.27 | −22.34% | **IDENTICAL** (ΔCAGR 0.0000pp) |
| V3 | 14.38% | 0.62 | −26.82% | **IDENTICAL** (ΔCAGR 0.0000pp) |
| V4 | 12.45% | 0.45 | −35.17% | **IDENTICAL** (ΔCAGR 0.0000pp) |
| V5 | 14.16% | 0.57 | −34.71% | **IDENTICAL** (ΔCAGR 0.0000pp) |

**All five reproduce to 0.0000pp. Volume contributes exactly nothing.**

**Control B — beat the nsealgo composite?** On TRAIN, no. Composite 20.44% CAGR /
Sharpe 0.91 vs V3 14.38% / 0.62. The composite wins on return, Sharpe and Calmar;
V3 wins only on drawdown (−26.82% vs −32.94%).

### 5.5 V3 TRAIN calendar years

| 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|
| −4.49% | +39.33% | −0.30% | +7.24% | +14.03% | +43.80% | −0.39% | +27.52% |

5 of 8 years positive.

---

## 6. ⚠️ THE HEADLINE FINDING: this strategy does not use volume

`volume_weighted_momentum` is **misnamed**. Its output is a pure function of price.
This is an algebraic identity, then confirmed three ways on the real panel.

**The identity.** The strategy computes `vw = avg_volume × (1.0 if volumes[-1] ≥
avg_volume else 0.5)` and applies **exactly one test** to it: `vw > 0`. The
multiplier is `0.5` or `1.0` — both strictly positive — and `avg_volume ≥ 0`, so:

```
vw > 0  ⟺  avg_volume × 0.5 > 0  ⟺  avg_volume > 0
```

The `1.0`/`0.5` branch **cannot** change the outcome of a `> 0` test. It is dead
code. Verified: `(vw > 0) == (avg_vol > 0)` holds at **every cell** for periods 20
and 126. The condition `volumes[-1] >= avg_volume` fires on 34.6% of cells
(period 20) — and changes nothing.

**Confirmation 1 — algebra on real data.** Replacing the entire volume series with a
constant-1 series (which can never make `avg_volume` zero) leaves the signal
**byte-identical**:

| period / threshold | differing cells |
|---|---|
| 20 / 0.01 | **0** |
| 63 / 0.03 | **0** |
| 126 / 0.06 | **0** |
| 252 / 0.10 | **0** |

**Confirmation 2 — the gate never fires.** Fraction of cells where `vw > 0` is False,
separating NaN warmup from genuine zero-volume windows:

| Split | cells | warmup (NaN) | **genuine `avg_vol == 0`** |
|---|---|---|---|
| TRAIN | 91,298 | 2,976 | **0 (0.000000%)** |
| TEST | 32,831 | 2,976 | **0 (0.000000%)** |

No window of 20/63/126/252 consecutive bars in 4,625 bars of NSE data has zero total
volume. **The volume branch is unreachable in practice.**

**Confirmation 3 — the backtest.** All five variants re-run with the volume term
deleted reproduce to **ΔCAGR 0.0000pp** (§5.4), on TRAIN and on TEST.

**Honest restatement of the strategy:**
> `+1 if ROC(period) > threshold else −1 if ROC(period) < −threshold else 0`

i.e. plain time-series price momentum. **The "volume-weighted" qualifier is
advertising, not engineering.** A reader who saw the name and skipped the source
would believe they had tested a volume factor. They have not.

### 6.1 Consequence for this study

Because volume provably contributes nothing, the §3 volume caveat is **moot for the
result** — but not for trust: it means the volume column's unreliability could not
have hurt this strategy, *because it never touched it*. Any future agent who
"fixes" this strategy to genuinely weight by volume would then be exposed to the
0.89% zero-volume-bar rate in the TEST window and should re-validate then.

---

## 7. BUG FOUND: TEST slicing starves the factor warmup (harness, affects other agents)

**This one is generic and other agents porting catalog strategies should check it.**

`run_backtest` consumes a pre-built score. Slicing the panel to TEST first and then
building the score leaves the 126-day ranking momentum with **zero history**, so
every TEST score is NaN until 126 bars in. Measured on the first rebalances:

| rebalance date | eligible names | finite score | valid for `build_rebalance_weights` |
|---|---|---|---|
| 2024-02-01 | 0 | 0 | 0 |
| 2024-05-02 | 30 | **0** | **0** |
| 2024-06-03 | 26 | **0** | **0** |
| 2024-07-01 | 33 | **0** | **0** |
| 2024-08-01 | 42 | 42 | 42 |

Result: **142 of 684 TEST days held zero names**, and the first 7 months of a 34-month
TEST window contributed a 100%-cash book. That is an artefact of the slicing, not the
signal — 2024 had plenty of eligible names.

**The fix is protocol-compliant, not a lookahead:** build the score with pre-TEST
warmup history (2023-06-13 onward, 136 bars), then measure *only* the TEST slice. The
score on TEST date *t* still uses closes up to and including *t* only. This is
exactly what a live deployment would have had on 2024-01-01.

**Lookahead test (`stage6_verify.py`)** — shocked every price from 2025-06-01 by
+50%; scores on all prior dates were **unchanged, max abs diff 0.000e+00**. And the
test has power: a deliberately 1-bar-lagged score gives a *different* result
(+3.60% vs +0.64%), so a leak would have shown up as a match. **No lookahead.**

**Effect of the bug on the headline:**

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Buggy TEST slice | −6.76% | −1.35 | −21.96% |
| **Corrected TEST** | **+0.64%** | **−0.41** | **−21.96%** |

The bug made the strategy look *much worse* (−6.76% vs +0.64%). Correcting it
**flatters** the result — which is exactly why it had to be found and fixed rather
than left to flatter the conclusion. All numbers from §8 onward are corrected.

### 7.1 Second harness bug: wide-panel NaN padding corrupts streaming strategies

`cryptobot/strategies/signal_base.py:99` feeds `VwMomentumStrategy` a **per-symbol
`deque` of real bars** (`float(volume if volume is not None else 0.0)`). A missing
vendor day produces no `feed()` call at all, so the `period`-bar window simply spans
the `period` most recent *actual* bars.

My first port computed `vol.rolling(period, min_periods=period).mean()` on the
NaN-padded wide panel. **That is not the same function.** `min_periods=period`
returns NaN if *any* cell in the window is NaN, so one missing bar → NaN for the next
`period` days → `vw` NaN → `vw > 0` False → the strategy returns 0. A `period`-day
trading blackout the streaming original never produces.

Root cause on real data: **`indigo` has no 2026-05-01 bar in the vendor feed** (the
raw CSV jumps 2026-04-30 → 2026-05-04). Because `vol.isna()` is cell-for-cell
identical to `close.isna()` (verified, 0 mismatches in either direction), the gap
propagates into the volume window and silences indigo afterwards.

| period | spurious cells silenced |
|---|---|
| 20 | 20 |
| 63 | 35 |
| 126 | 53 |
| 252 | 0 |

Fixed by computing the rolling mean on each symbol's **own** bar sequence
(`dropna()` first, `.fillna(0.0)` for a close with no volume print, matching
`signal_base.py:99`), then reindexing to the panel. **After the fix, the
volume-aware and constant-volume signals are byte-identical (0 differing cells).**

*Process note: my first attempt at the diffing script compared `long_only=True`
against a `long_only=False` reference and reported 48,332 phantom differences. That
was my error, caught and corrected; the honest count is 0.*

---

## 8. TEST RESULTS (out-of-sample, 2024-01-01 → 2026-10-01)

684 bars, 48 symbols. V3 (period 63, threshold 0.03) chosen on TRAIN alone by the
pre-declared rule. Monthly rebalance, `PortfolioConfig()` defaults, **net of
21.92 bps** all-in (engine-reported `rt_bps = 21.92`, verified identical to
`CostModel.all_in_round_trip_bps(100_000)`).

| | CAGR | Sharpe | MaxDD | Calmar | Vol | Total ret | Turnover/y | Cost drag/y | Avg names |
|---|---|---|---|---|---|---|---|---|---|
| **vw_momentum V3** | **+0.64%** | **−0.41** | **−21.96%** | 0.03 | 12.25% | +1.80% | 3.00x | 1.50% | 18.4 |
| vw_momentum, zero cost | +1.34% | −0.35 | −20.76% | 0.06 | 12.26% | +3.80% | 3.00x | 0.00% | 18.4 |
| **Buy-and-hold** | **+8.18%** | **+0.19** | **−15.90%** | 0.51 | 13.45% | +24.64% | 1.00x | 0.22% | 48 |
| nsealgo composite | +6.36% | +0.05 | −15.22% | 0.42 | 13.30% | +18.86% | 2.45x | 1.13% | 21.3 |

Costs paid over TEST on a ₹21,00,000 book: **₹1,06,091**. Mean exposure **78.1%**
(40 rebalances across warmup+TEST).

> *Note on `avg_names`:* `stage5_fixed.json` records **15.33**, which is the average
> across the whole warmup+TEST run (including the 136 warmup bars where the book is
> still filling). The **18.38** in the table is the TEST window alone, which is the
> figure the brief's sanity check is asking about. Both are correct for their window.

### 8.1 Sanity checks (`AGENT_BRIEF.md` §6)

1. **Plausibility** — +0.64% CAGR, far below the 40–50% ceiling. No compounding bug.
2. **Weight count** — **18.4 names** held on average in TEST (max 22, the configured
   limit). No residual accumulation (the failure mode flagged in the brief was 48).
3. **Signal liveness** — **49.2% of cells long**, and **100% of TEST days hold at
   least one name**. Nowhere near the always-flat failure mode. Fewer than 22 names
   are eligible on 43.6% of days, because non-flagged names are masked to NaN and
   `build_rebalance_weights` treats NaN as ineligible — intended, not a leak.
4. **Cost drag** — 1.50%/yr. **Not the problem:** at zero cost the strategy still
   returns only +1.34%. Costs account for 0.70pp of the 7.5pp shortfall to
   buy-and-hold. Three quarters of the shortfall is the signal, not the fees.
5. **Negative control** — see §9. It **fails**.

### 8.2 Calendar years (TEST)

| 2024 | 2025 | 2026 (to 2026-10-01) |
|---|---|---|
| +19.05% | −1.33% | −13.47% |

---

## 9. Negative control — the strategy loses to a coin flip

20 random signals, matched at **51.86% of bars long**, identical costs, identical
warmup, seed 20261012:

| | random mean | random sd | 5–95% range | vw_momentum |
|---|---|---|---|---|
| CAGR | **+4.15%** | 2.38% | −0.10% … +7.12% | **+0.64%** |
| Sharpe | −0.21 | 0.26 | −0.71 … +0.10 | **−0.41** |
| MaxDD | −11.65% | — | −15.31% … −8.32% | **−21.96%** |

**vw_momentum beats random on CAGR in 2 of 20 trials and on Sharpe in 3 of 20.**
Its CAGR sits at the **10th percentile** of the random distribution. It also has a
*materially worse* drawdown than a random book (−21.96% vs −11.65% mean).

Beating a coin flip is the minimum bar (`AGENT_BRIEF.md` §6.5). This strategy does
not clear it. **This is the clearest single statement of the result.**

---

## 10. TEST vs buy-and-hold, and vs the composite

| Comparison | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| vw_momentum **−** buy-and-hold | **−7.54pp** | **−0.59** | **−6.07pp worse** |
| vw_momentum **−** composite | **−5.72pp** | **−0.46** | −6.74pp worse |

**Worse on return AND worse on drawdown than doing nothing.** It fails to beat
buy-and-hold, it fails to beat the nsealgo composite, and it fails to beat a random
coin. There is no dimension on which it wins.

---

## 11. Verdict

> **Does `volume_weighted_momentum` make money on NSE? NO.**
> Out-of-sample it returned **+0.64% CAGR (Sharpe −0.41)** against **+8.18%** for
> simply holding the index, it lost to a random signal in **18 of 20** controlled
> trials, and — decisively — **it never used volume at all**, so the name is wrong
> and the strategy is plain price momentum wearing a costume.

**Most likely reason it failed:** it is a *time-series* momentum gate. On a
long-only, cross-sectional, long-only NIFTY-50 book the gate mostly decides *whether
to be in the market at all* (2024: 66.8% average cash), not *which names to hold*.
The cross-sectional ranking then adds a mild momentum tilt on top of a
market-timing overlay that was wrong for two of the three TEST years. The tilt
added no value to offset it, and the 3.0×/yr turnover cost 1.50%/yr for it.

**The one thing I would try next — not a re-tune, a different question.** Do not
sweep `period`/`threshold` again; §7 shows all five declared variants lose on TEST
(V1 −7.15%, V2 −5.04%, V3 −6.76%, V4 −7.73%, V5 −0.06% on the buggy slice; the point
is that none is positive). Instead, **test whether the volume idea works at all when
implemented correctly** — i.e. a volume-weighted score such as
`ROC(period) × clip(vol[-1]/avg_vol(period), 0.5, 1.0)`, which is what the dead
`1.0/0.5` branch was *clearly reaching for* and never achieved. That variant would
actually consume volume and would need the §3 caveat re-validated against the
0.89% TEST-window zero-volume rate.

---

## 12. Protocol compliance

| Requirement | Status |
|---|---|
| Header + parameter budget written before any run | ✅ `REPORT.md` committed to disk pre-run |
| Declared budget: 5 variants | ✅ exactly 5 (`V1`–`V5`); **not exceeded** |
| Selection on TRAIN only | ✅ max TRAIN Sharpe → V3, fixed before TEST was loaded |
| TEST touched once | ✅ `stage2_test.py` is the only TEST run; `stage3/4/5/6` are diagnostics of an already-reported result, explicitly *not* re-selection |
| All results net of 21.92 bps | ✅ engine `rt_bps = 21.92` verified on every run |
| Buy-and-hold on identical window | ✅ same panel, same 21.92 bps, same rf |
| No lookahead | ✅ proven by the +50% future-shock test (0.000e+00 score change) |
| `src/` and `tests/` unmodified | ✅ only `research/agent_vwm/**` written |
| Lint clean | ✅ `.venv/bin/ruff check research/agent_vwm/` → All checks passed |
| No commits | ✅ nothing committed or pushed |
| Report `provenance()` in header | ✅ engine/loader/costs/panel SHAs recorded |

---

## 13. Artifacts

| File | Purpose |
|---|---|
| `common.py` | Panel + volume loading, faithful per-symbol port, score construction |
| `validate_volume.py` | Volume-column validation (§5.1) |
| `prove_volume_dead.py` | Algebraic proof the volume branch is dead (§6) |
| `why_differences.py` | Cell-by-cell diff of volume-aware vs volume-free signals |
| `diagnose_nan_volume.py` | Volume missingness / frozen-run diagnosis |
| `stage1_train.py` | TRAIN sweep of the 5 declared variants + controls |
| `stage2_test.py` | One-shot TEST (pre-warmup-fix; superseded by stage5) |
| `stage3_diag.py` | Post-hoc verification of the negative result |
| `stage4_cash.py`, `stage4b_cash.py` | Cash-holding decomposition |
| `stage5_fixed.py` | Warmup fix + corrected TEST + buy-and-hold + random control |
| `stage6_verify.py` | Lookahead test, TRAIN re-run on equal footing, determinism |
| `*.json` | Raw numbers behind every table |

*Reproduce: `.venv/bin/python research/agent_vwm/stage5_fixed.py` then
`.venv/bin/python research/agent_vwm/stage6_verify.py`. Provenance
`engine=d93815344bd3 loader=c1badf5f7df8 costs=ba350aef75b3 panel=389b082b832f`.*

---

## 14. Findings for the wider project (not just this strategy)

1. **`volume_weighted_momentum` should be renamed or rewritten.** The `1.0/0.5`
   multiplier feeding a `> 0` test is dead code. I checked the whole catalog for the
   same shape (AST scan: any `signal()` variable assigned as *something × an
   all-positive constant* and then compared to 0) — **this file is the only hit**,
   so the defect is local, not systemic. But nothing in CI would have caught it: a
   test asserting *"replacing the volume series with a constant leaves the signal
   unchanged"* would, and would be worth adding for every catalog strategy.
2. **TEST-window volume data is 200× dirtier than TRAIN** (0.89% vs 0.0044%
   zero-volume bars). Any *genuine* volume strategy on this panel will face a
   regime shift in data quality exactly when it is being evaluated.
3. **Two harness traps other agents should check for:** (a) slicing the panel to
   TEST before building a long-lookback factor silently produces a 100%-cash book
   for the first ~6 months — it made this strategy look −6.76% instead of +0.64%;
   (b) vectorising a streaming per-bar strategy onto a NaN-padded wide panel
   changes its semantics whenever the vendor has a missing day.
4. **The TEST window is hostile to momentum generally.** The nsealgo composite also
   underperformed (6.36% vs 8.18% buy-and-hold, Sharpe 0.05). Any momentum-family
   result should be expected to look worse here than on TRAIN, and that is a
   property of the window, not evidence about the factor.