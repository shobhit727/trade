# `gap_strategy` → NSE NIFTY-50 — validated TEST result

**Agent:** gap · **Source:** `src/cryptobot/strategies/catalog/gap_strategy.py`
**Date:** 2026-10-08 · **Timeframe:** `1d` (daily bars only — see §1.3)
**Scratch:** `research/agent_gap/` · nothing committed · `src/`, `tests/`, `GOAL.md`, `reports/` untouched
**Reproduce:** `s1_data.py` → `s2_train.py` → `s3_test.py` → `s4_verify.py`

---

## Verdict

**No. This strategy does not make money on NSE out of sample.** The TRAIN-selected variant
returns **TEST CAGR +3.24%, Sharpe −0.19** net of the full Indian delivery stack, against
buy-and-hold **+8.16% / Sharpe +0.18** — it loses by **4.92pp per year** on return. Its
Sharpe is **negative**, so it did not even clear the 6.5% Indian T-bill proxy that
`compute_metrics` subtracts. It loses to the nsealgo composite by **3.31pp/yr**, and it
beats a random signal at matched liveness on only **2 of 5 seeds** — exactly what a coin
does. GOAL.md's 3% net/month target (~42.6% annualised, per `GOAL.md` line 13) is
missed by a factor of ~13.

The as-shipped signal is worse than "no edge": it is a **coin flip with a 1-day lag**, and
the negative Sharpe is the honest consequence of paying 1.03%/yr in costs to trade on it.

---

## 1. The strategy as shipped

```python
def signal(self, closes, highs, lows, volumes):
    if len(closes) < 2:
        return 0
    gap = (closes[-1] - closes[-2]) / closes[-2]     # 1-bar close-to-close RETURN
    if gap > self.config.threshold:  return 1
    if gap < -self.config.threshold: return -1
    return 0
```

Returns `+1` / `-1` / `0`. Long-only book ⇒ only the `+1` half is tradeable.

### 1.1 Bug A — `GapConfig.period` is dead config

`GapConfig.period` (default 2) is read **only** by `warmup()`. `signal()` looks back exactly
one bar regardless, so `GapConfig(period=50)` and `GapConfig(period=2)` emit
byte-identical signals. A caller sweeping `period` to tune this strategy would be measuring
pure noise. Same class of defect as the `donchian_channel` window-includes-today bug:
declared config that never reaches the signal.

**Repair, disclosed:** I give `period` its obvious intended meaning — the gap lookback `L`,
i.e. `gap = closes[-1] / closes[-1-L] - 1`. V1 (`L=1`) is exactly the shipped behaviour;
V2–V5 use the repair. V1 vs V2–V5 is therefore a *semantic* change, disclosed here rather
than dressed up as tuning.

### 1.2 Bug B — it is not a gap, and the default threshold is a no-op

The class is `GapStrategy`, the file is "Gap breakout", but `closes[-1]/closes[-2] - 1` is a
**1-bar close-to-close return**, not a price gap. A real gap is the overnight jump
`open[t] / close[t-1] - 1`; the shipped code cannot see `open` at all and ignores its own
`highs`/`lows`/`volumes` arguments.

Worse, the shipped default `threshold=0.0` is a **no-op**: a daily return is essentially
never exactly zero, so the signal is `±1` on ~100% of bars. Measured, it fires on **49.25%**
of TRAIN name-bars — the share you get from the sign of a random variable. **The default
configuration is a coin flip.**

### 1.3 Timeframe

Daily bars. This is a close-to-close signal, so `1d` is native. `1h` (~2y) and `5m`/`15m`
(~7 weeks) are far too short to validate anything and were not used. **No intraday evidence
is claimed.**

---

## 2. Data

`load_universe("data/nse")` → **48 symbols**, panel **4,629 daily bars**,
**2008-01-01 → 2026-10-01** (Asia/Kolkata).

| cleaning rule | rows |
|---|---|
| rows in | 274,541 |
| rows out | 208,226 |
| dropped pre-2008 vendor artifacts | 66,312 |
| dropped non-positive prices | 0 |
| dropped extreme moves | 3 |
| excluded symbols | `adanient`, `jiofin` (too few bars) |

| set | window | bars | symbols |
|---|---|---|---|
| TRAIN | 2016-01-01 → 2023-12-31 | 1,975 | 48 |
| **TEST** | **2024-01-01 → 2026-10-01** | **685** | 48 |

**Every TEST number below is quoted against an end date of 2026-10-01.** 2026 is a partial
year (9 months) and is labelled as such wherever it appears.

### 2.1 Signal diagnostics

`gap = close[t]/close[t-L] - 1`, flag = `gap > threshold`. Book capped at 22 names.

| ID | L | thr | TRAIN %flag | TEST %flag | TRAIN n/day | TEST n/day |
|---|---|---|---|---|---|---|
| V1 | 1 | 0.000 | 49.25% | 49.52% | 23.6 | 23.8 |
| V2 | 1 | 0.010 | 24.44% | 22.18% | 11.7 | 10.6 |
| V3 | 5 | 0.000 | 52.24% | 51.46% | 25.1 | 24.7 |
| V4 | 5 | 0.010 | 40.59% | 38.04% | 19.5 | 18.1 |
| V5 | 21 | 0.000 | 56.41% | 54.84% | 27.1 | 26.3 |

Two things fall out before any return is computed:

1. **V1 is a coin.** 49.25% flagged is the sign of a random variable.
2. **V1 barely filters.** It flags 23.6 names/day against a 22-name book, so ~94% of flagged
   names get in. As a selection criterion it is close to a no-op.

### 2.2 The degeneracy problem, and the construction it forces

The raw signal is **degenerate as a cross-sectional score**. Measured on V1: **23.6 names
tied at `+1.0` per day on TRAIN** (min 0, max 48), 23.8 on TEST. `build_rebalance_weights`
breaks ties with `np.argsort(..., kind="stable")` — i.e. **by column order, the alphabet**.
Passing the raw signal would buy a book chosen by ticker spelling.

So the flag is used as a **mask** and momentum ranks the survivors — the brief's §5
construction verbatim:

```python
score = (panel / panel.shift(126) - 1.0).where(gap_flag).rank(axis=1, pct=True)
```

**This determines what the strategy even is.** Once the rank key is momentum, the gap flag's
only remaining job is choosing *which names get ranked at all*. That makes the
**momentum-only ablation** the load-bearing control of this report, not a formality. If
momentum-only matches the strategy, the gap signal is decoration.

Fixed harness, untuned: `PortfolioConfig()` defaults exactly as shipped (22 names, 12%
single name, 25% sector, 10% cash, 0.35 turnover budget, `max_names=30`), monthly
rebalance, 126d ranking key. Decisions on day *t* use closes up to *t*; the engine holds
them from *t+1*.

---

## 3. Declared parameter budget

Written before any run. **5 variants used, 5 declared. No variant was added, removed, or
re-scoped — including after the verification defect in §6.1 was found and fixed.**

| ID | `L` (gap lookback) | `threshold` | note |
|---|---|---|---|
| **V1** | 1 | 0.000 | **as shipped** — baseline |
| **V2** | 1 | 0.010 | threshold at the shipped 1-bar lookback |
| **V3** | 5 | 0.000 | multi-bar gap, threshold off |
| **V4** | 5 | 0.010 | multi-bar gap + threshold |
| **V5** | 21 | 0.000 | monthly-horizon gap, threshold off |

**Selection rule, declared before running:** highest TRAIN Sharpe net of 21.92 bps; ties
broken toward lower turnover. Applied once, on TRAIN, before TEST was read.

**Not counted** (brief §7 controls, not strategy variants): buy-and-hold, the nsealgo
composite, the momentum-only ablation, and the random-signal control at matched liveness.

---

## 4. TRAIN results (2016-01-01 → 2023-12-31) — net of 21.92 bps

### 4.1 The five declared variants

| ID | L | thr | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | Avg names |
|---|---|---|---|---|---|---|---|---|---|
| V1 | 1 | 0.000 | 15.63% | 0.68 | −30.71% | 0.51 | 4.03x/y | 1.60%/y | 28.7 |
| V2 | 1 | 0.010 | 16.17% | 0.76 | −29.15% | 0.55 | 4.06x/y | 1.62%/y | 27.6 |
| V3 | 5 | 0.000 | 19.19% | 0.98 | −12.82% | 1.50 | 3.99x/y | 1.86%/y | 27.7 |
| **V4** | **5** | **0.010** | **19.64%** | **1.02** | **−13.94%** | 1.41 | 4.10x/y | 1.91%/y | 28.9 |
| V5 | 21 | 0.000 | 17.11% | 0.78 | −30.43% | 0.56 | 3.93x/y | 1.66%/y | 27.2 |

**Selected: V4** by the declared rule (Sharpe 1.02). Runner-up V3 at 0.98.

### 4.2 Negative control on TRAIN — random names, same n/day as V1

| seed | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| 11 | 14.92% | 0.61 | −33.80% |
| 29 | 16.63% | 0.74 | −29.61% |
| 47 | 14.00% | 0.57 | −36.78% |
| 83 | 15.78% | 0.68 | −30.01% |
| 101 | 15.65% | 0.68 | −29.94% |

**The shipped signal is indistinguishable from a coin.** V1 scores 0.68 inside a random band
of 0.57–0.74, with one random seed (29, 0.74) beating it. On TRAIN the `L=5` variants look
better (0.98 / 1.02 vs a random ceiling of 0.74) — but §5 shows that does not survive.

### 4.3 Ablation on TRAIN — momentum only, no gap filter

| | CAGR | Sharpe | MaxDD | Turnover | Cost drag | Avg names |
|---|---|---|---|---|---|---|
| momentum-only | 18.38% | 0.78 | −34.92% | 2.64x/y | 1.18%/y | 22.2 |

Momentum-only beats V1 (0.78 vs 0.68), V2 and V5 outright — so for 3 of 5 variants the gap
filter is **actively harmful**. Only the `L=5` filter adds anything, and what it adds is a
drawdown reduction (−13.9% vs −34.9%), which is a trend-filter effect, not a gap effect.

### 4.4 References on TRAIN

| book | CAGR | Sharpe | MaxDD | Turnover |
|---|---|---|---|---|
| nsealgo composite | 21.30% | 0.96 | −32.92% | 1.96x/y |
| buy-and-hold (net) | 22.17% | 0.91 | −37.97% | 0.00x/y |
| **V4 (selected)** | 19.64% | **1.02** | **−13.94%** | 4.10x/y |

V4 is the only book here with Sharpe above 1.0, and it does so with half the drawdown — on
TRAIN it looks genuinely good. This is exactly the trap the brief warns about: a strategy
that only wins in-sample is a trap, and reporting it as a win is worse than reporting
nothing. **§5 is where it dies.**

---

## 5. TEST results (2024-01-01 → 2026-10-01) — net of 21.92 bps

The selected variant, evaluated **once**, parameters unchanged from TRAIN.

### 5.1 Headline table

| Label | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | Avg names |
|---|---|---|---|---|---|---|---|
| **V4 gap+momentum (selected)** | **+3.24%** | **−0.19** | −15.56% | 0.21 | 4.10x/y | 1.03%/y | 28.3 |
| ABLATION momentum-only | +2.60% | −0.22 | −16.86% | 0.15 | 2.76x/y | 0.70%/y | 21.3 |
| V1 as-shipped (L=1) | +5.47% | −0.02 | −13.72% | 0.40 | 4.10x/y | 1.07%/y | 27.6 |
| **nsealgo composite** | **+6.55%** | **+0.07** | −14.84% | 0.44 | 2.07x/y | 0.55%/y | 21.3 |
| **buy-and-hold (net)** | **+8.16%** | **+0.18** | −15.91% | 0.51 | 0.00x/y | 0.00%/y | 48.0 |

Sharpe is annualised against the 6.5% Indian T-bill proxy (`compute_metrics` default), so
**a negative Sharpe means the strategy did not beat holding T-bills.**

### 5.2 Head-to-head

| comparison | return | drawdown |
|---|---|---|
| vs buy-and-hold | **worse by 4.92pp/yr** (3.24% vs 8.16%) | **better by 0.35pp** (−15.56% vs −15.91%) |
| vs nsealgo composite | **worse by 3.31pp/yr** (3.24% vs 6.55%) | **worse by 0.72pp** (−15.56% vs −14.84%) |

It is worse on **both** return *and* Sharpe against both references, and worse on drawdown
too against the composite. Its only edge is a 0.35pp drawdown improvement over
buy-and-hold — inside the noise of a 685-bar sample, and bought with 4.10x/yr turnover
against buy-and-hold's zero.

### 5.3 Sanity checks (brief §6)

| check | result | verdict |
|---|---|---|
| 1. Plausibility | CAGR +3.24%, no impossible figure | ✅ |
| 2. Weight count | 28.3 avg names; by year 2024:25.2, 2025:30.0, 2026:30.0 — pinned at the shipped `max_names=30` cap, never near 48 | ✅ bounded |
| 3. Signal liveness | **38.04%** of name-bars flagged, 18.3 names/day — 7.6x the 5% floor, so not "effectively always flat" | ✅ |
| 4. Cost drag | gross **+3.75%** → net **+3.24%**; costs cost **0.51pp/yr**. **Gross is also below buy-and-hold**, so costs are not the cause — the signal is | ⚠️ |
| 5. Negative control | random band Sharpe −0.34..−0.04; selected beat **2/5** seeds (coin = 2.5/5) | ❌ **no edge** |

On check 5 the detail is damning: seeds 11 and 29 (0.11 and 0.13 negative Sharpe) both beat
the selected variant, and only seed 83 (0.34) is clearly worse. The selected variant sits in
the middle of the random band.

**GOAL.md Gate 3** (positive in ≥60% of years): 2/3 → nominally PASS. But 2026 is partial
and negative: 2024 **+14.0%**, 2025 **+3.3%**, 2026 **−7.2%** (partial, to 2026-10-01).

### 5.4 Two findings that matter more than the headline

**(a) The as-shipped variant beat the one I selected.** V1 returned **+5.47% / −0.02** versus
V4's **+3.24% / −0.19**. TRAIN-based selection picked the *worse* of the two out of sample —
a 2.23pp/yr selection loss. With only 5 variants and 33 rebalances in TEST, that is not
surprising, but it does mean the TRAIN ranking carried no information about TEST ordering.

**(b) The gap filter contributes essentially nothing.** V4 vs momentum-only: **+0.64pp CAGR,
+0.029 Sharpe**. Once you rank by momentum — which the brief's §5 construction *requires*,
because the raw signal is degenerate — the flag is adding a rounding error's worth of
selection. What little it adds is a short-term trend tilt, which the nsealgo composite
already owns, at **half the turnover** (2.07x vs 4.10x) and half the cost drag (0.55% vs
1.03%).

### 5.5 Disclosure — I looked at TEST, and here is every time it changed something

Per brief §4.4 this must be stated. TEST was read **twice**, once before and once after a
harness fix, and never to choose a parameter.

- **Run 1 (TEST #1):** selected variant returned **−3.27% CAGR / Sharpe −0.96**.
- **Between runs:** verification found a genuine defect in my own harness (§6.1). I fixed it,
  re-ran TRAIN (selection **unchanged**: still V4 — the fix did not alter which variant won),
  then re-ran TEST.
- **Run 2 (TEST #2, reported above):** **+3.24% / −0.19.**

**No parameter, threshold, variant, or selection rule was changed after seeing either TEST
number.** The fix was a warmup correction, applied uniformly to the strategy, the ablation,
the random control, and the composite. The verdict is negative under both the defective and
the fixed harness, so the fix changes the magnitude (−3.27% → +3.24%) but not the
conclusion. **I did not peek at TEST to tune, and I did not hide the re-run.**

---

## 6. Bugs found

### 6.1 In my own harness — the 126-bar warmup truncation (fixed, and a trap for other agents)

Verification printed `2024: 12.0` avg names and first weights on `2024-08-01`, when the
book should have been full from February. Cause: I sliced the panel to the window **first**
and computed the 126d momentum **inside the slice**, so the first 126 bars of every window
had NaN momentum and the book held nothing for ~6 months. Every strategy number in my first
pass was computed over a silently truncated window.

| window | defect | fixed |
|---|---|---|
| TRAIN | 17.39% CAGR / 0.89 Sharpe / 27.0 names | 19.64% / 1.02 / 28.9 |
| TEST | **−3.27% CAGR / −0.96 Sharpe** / 23.5 names | **+3.24% / −0.19** / 28.3 |

**Fix:** build the factor on the **full** panel, then slice. Using closes from before a
window is legitimate — it is not look-ahead. The effect is **6.5pp of CAGR on TEST**, which
is larger than the entire in-sample edge of the strategy.

> ⚠️ **This is likely not unique to me.** Any agent that slices first and scores second has
> the same defect, and it biases results *optimistically* on TRAIN (fewer names early,
> less turnover, less drag) while *pessimistically* on TEST. The donchian agent's
> buy-and-hold cross-check matches mine exactly (+8.16% / 0.18 / −15.91%), so the panels and
> cost model agree — but its strategy numbers may carry the same truncation and are worth
> re-checking. **`build_composite_score` has a 252-bar factor, so a composite scored
> inside a slice loses ~12 months.** Worth a repo-wide audit.

### 6.2 In `src/cryptobot/strategies/catalog/gap_strategy.py` (unchanged; reported only)

1. **Line 13 — `GapConfig.period` is dead config.** Read only by `warmup()`; never reaches
   `signal()`. Sweeping it yields byte-identical signals. A tuning harness would report
   "no sensitivity to period" and conclude the knob is robust, when in fact it is inert.
2. **Line 30 — mislabelled quantity.** Computes a close-to-close return, not a gap, despite
   the class name, the strategy name, and the file name. It cannot see `open` and ignores
   its own `highs`/`lows`/`volumes` arguments.
3. **Line 31 — the default `threshold=0.0` is a no-op.** A return is essentially never
   exactly zero, so the default config is a ±1-every-bar coin flip (49.25% measured). The
   only shipped default is also the only one that guarantees the strategy has no content.

### 6.3 Observed in shipped `nsealgo` infrastructure — *not* a bug, but worth knowing

`avg_names` is **28–30**, not the 22 the brief's §6.2 anticipates. This is shipped
`run_backtest` behaviour: `n_positions=22` sizes the *target* at each rebalance, while
`apply_turnover_budget` blends that target against the previous book and thins to
`max_names=30`, so names carried from adjacent rebalances survive between them. It is
bounded well below 48 and identical across agents, so I reported it rather than "fixing"
it — tuning it would be tuning infrastructure.

---

## 7. Why it failed, and the one thing to try next

**Most likely reason: the signal has no content to extract.** The shipped code reduces a
1-day return to its *sign*, which is a coin flip (49.25% measured). Everything downstream
— cross-sectional ranking, 22-name cap, 12% caps — is machinery for choosing between
symbols that a coin has already labelled. The TRAIN Sharpe of 1.02 came from the **126-day
momentum ranking key the brief mandated**, not from the gap signal; the ablation proves it
(+0.03 Sharpe from the filter, on TEST). The out-of-sample Sharpe of −0.19 is what
momentum-minus-4pp-of-costs looks like when the momentum is chosen for the wrong reason.
Corroborating evidence: the as-shipped V1 is inside the random band on both TRAIN (0.68 vs
0.57–0.74) and TEST (2/5 seeds beaten).

**The one thing I would try next — the real overnight gap.** `gap = open[t]/close[t-1] - 1`.
This is what the file is named after, what the shipped code cannot compute, and the only
untested repair that asks a *different question* rather than re-parameterising a coin flip.
It needs an OHLC panel (rebuildable with `load_symbol`, then checked for exact equality
against the `load_universe` close panel) and a genuine catalyst — Indian earnings, index
rebalance, weekend/regulatory events — otherwise it is a 1-day return wearing a different
hat and will fail identically. The honest prior is that it will also fail; but it is the
only variant left that is not the same experiment.

**What I would not do:** add more lookbacks or thresholds. The 5-variant budget already
spans `L ∈ {1, 5, 21}` × `threshold ∈ {0, 0.01}`, the trend-filter interpretation is already
refuted by the ablation, and the negative TEST Sharpe is not a tuning problem.

---

## 8. Full result table

### TEST (2024-01-01 → 2026-10-01), net of 21.92 bps — the only numbers that count

| Label | CAGR | Sharpe | MaxDD | Calmar | Turnover | Cost drag | Avg names |
|---|---|---|---|---|---|---|---|
| V4 gap+momentum (selected on TRAIN) | +3.24% | −0.19 | −15.56% | 0.21 | 4.10x/y | 1.03%/y | 28.3 |
| ABLATION: momentum-only | +2.60% | −0.22 | −16.86% | 0.15 | 2.76x/y | 0.70%/y | 21.3 |
| V1 as-shipped (L=1, thr=0) | +5.47% | −0.02 | −13.72% | 0.40 | 4.10x/y | 1.07%/y | 27.6 |
| nsealgo composite | +6.55% | +0.07 | −14.84% | 0.44 | 2.07x/y | 0.55%/y | 21.3 |
| buy-and-hold (net of 1 round trip) | +8.16% | +0.18 | −15.91% | 0.51 | 0.00x/y | 0.00%/y | 48.0 |

### Random-signal control on TEST, matched to the selected variant's liveness (18.3 names/day)

| seed | 11 | 29 | 47 | 83 | 101 |
|---|---|---|---|---|---|
| CAGR | +4.71% | +4.49% | +3.26% | +2.12% | +5.42% |
| Sharpe | −0.11 | −0.13 | −0.23 | −0.34 | −0.04 |

Selected variant beat **2/5**. Two random seeds beat it outright.

### Annual returns on TEST (2026 partial, to 2026-10-01)

| year | V4 | buy-and-hold |
|---|---|---|
| 2024 | +14.0% | +19.9% |
| 2025 | +3.3% | +13.3% |
| 2026 (partial) | −7.2% | −8.3% |
| **total** | **+9.4%** | **+24.6%** |

V4 trailed buy-and-hold in 2 of 3 years and gave up the whole gap in 2025. (These figures
were computed by `yearly_returns` on the two net return series; an earlier draft of this
report carried unverified numbers here, which is exactly the error the brief warns about —
they have been recomputed, not estimated.)

### Cost reconciliation for the selected variant

| | CAGR |
|---|---|
| gross (all costs removed) | +3.75% |
| net of 21.92 bps round trip | **+3.24%** |
| cost drag | −0.51pp/yr (1.03%/y of compounding equity) |

Costs are **not** the reason this fails: gross and net are both below buy-and-hold. Per
brief §3, these are net of **21.92 bps** (`all_in_round_trip_bps` = statutory 11.92 + 2 ×
5 bps slippage), which is what `run_backtest` actually charges. The 11.92 bps statutory
figure is not quoted as a result anywhere in this report.

---

## 9. Summary of the seven questions

| # | question | answer |
|---|---|---|
| 1 | Strategy, signal, variants | 1-bar return sign → +1/−1/0. 5 variants: `L ∈ {1,5,21}` × `threshold ∈ {0, 0.01}` (§3) |
| 2 | TEST metrics | CAGR **+3.24%**, Sharpe **−0.19**, MaxDD **−15.56%**, Calmar 0.21, turnover 4.10x/y, drag 1.03%/y, 28.3 names (§5.1) |
| 3 | Buy-and-hold, same window | **+8.16% / +0.18 / −15.91%** (§5.1) |
| 4 | Better or worse? | **Worse.** −4.92pp/yr return and −0.37 Sharpe vs B&H; −3.31pp/yr and worse drawdown vs composite (§5.2) |
| 5 | Random control | Beat **2/5** seeds, band −0.34..−0.04. Coin-level. **No edge** (§5.3) |
| 6 | Beat the nsealgo composite? | **No.** 3.24% vs 6.55%, Sharpe −0.19 vs +0.07, and worse drawdown (§5.2) |
| 7 | Does it make money on NSE? | **No.** Returns 3.24% net with a **negative** Sharpe — below T-bills — losing to buy-and-hold, to the composite, and to a coin flip (§Verdict) |

**Most likely reason:** the signal is the sign of a 1-day return — a measured coin flip —
so all the portfolio machinery is choosing between coin-labelled names; the apparent TRAIN
edge belonged to the mandated momentum ranking key, which the ablation isolates at +0.03
Sharpe on TEST. **Next thing to try:** the real overnight gap `open[t]/close[t-1] - 1`,
paired with a genuine catalyst.
