# `relative_strength` on NSE NIFTY-50 — validated NEGATIVE finding

**Verdict: NO. This strategy does not make money on NSE.** Out-of-sample it returned
**−0.36% CAGR with a Sharpe of −0.48**, losing to buy-and-hold by **8.54pp of annual
return while taking 7.20pp more drawdown**, losing to the nsealgo composite by 6.40pp,
and losing to a random coin flip **20 times out of 20**.

> Sections 0–1 were written **before any backtest was run**, per AGENT_BRIEF §8, and
> declare the parameter budget in advance. Sections 2–8 were appended as results arrived.
> Bugs are in **`BUGS.md`** (two of them are the most serious findings in this run).

---

## 0. Header (pre-registration)

| item | value |
|------|-------|
| **Assigned strategy** | `relative_strength` |
| **Source** | `src/cryptobot/strategies/catalog/relative_strength_strategy.py` |
| **Symbol** | `RelativeStrengthStrategy` |
| **Agent dir** | `research/agent_relstrength/` |
| **Data** | `data/nse/<symbol>_1d.csv` via `nsealgo.data.loader.load_universe` |
| **Primary timeframe** | `1d` (2002-07-01 → 2026-10-01, 50 symbols) |
| **TRAIN window** | 2016-01-01 → 2023-12-31 |
| **TEST window** | 2024-01-01 → 2026-10-01 (touched **once**, at the end) |
| **Cost model** | `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps** per complete rotation charged by `run_backtest` |
| **Portfolio** | `PortfolioConfig()` — unmodified: 22 names, 12% single name, 25% sector, 10% cash, 35% turnover budget, monthly rebalance |
| **Date written** | pre-run (this header) |

### The signal, verbatim from the catalog

```python
m = roc(closes, period)                       # (C_t - C_{t-period}) / C_{t-period}
if m != m: return 0                            # NaN guard
return 1 if m > threshold else (-1 if m < -threshold else 0)
```

`warmup = period`. `roc()` returns NaN when `len(closes) <= period`, so no signal
exists for the first `period` bars — those name-days are **untradeable**, not flat.

**Crypto-specific? No.** No funding, no liquidations, no peg, no IV, no spot-futures
basis. It has a perfectly ordinary NSE meaning (short-horizon price momentum per
symbol), so this is a real result, not a §9 early exit.

### ⚠ Name/content mismatch — flagged before running

Despite the name `relative_strength`, **nothing in the file compares one symbol to
another.** `roc()` is a pure per-symbol time-series function. This is a *time-series*
momentum gate mislabelled as a relative-strength strategy. It is therefore **not**
the classic cross-sectional "RS vs NIFTY-50" strategy. I will evaluate the shipped
code as-is (I am not permitted to modify `src/cryptobot/**`), and I will *additionally*
measure whether a genuinely cross-sectional reading of the same idea — ROC relative to
the universe median — adds anything, clearly labelled as a construction change with
its own budget.

---

## 1. Declared parameter budget — committed before any backtest

The strategy has exactly **two** knobs: `period` and `threshold`. Everything else —
the score construction (6-month trailing momentum ranked inside the flagged subset),
the portfolio config, the rebalance frequency, the cost model — is **fixed, not
tuned**, per AGENT_BRIEF §5.

| # | `period` | `threshold` | rationale (declared in advance) |
|---|----------|-------------|-------------------------------|
| **V1** | 20 | 0.005 | **catalog default, verbatim** — `RelativeStrengthConfig()` |
| **V2** | 20 | 0.030 | isolates `threshold` at the catalog horizon |
| **V3** | 60 | 0.030 | quarter-scale gate; the plausible "real" reading of the strategy |
| **V4** | 126 | 0.080 | aligns the gate horizon with the 6-month rank horizon |
| **V5** | 5 | 0.005 | 1-week gate — direct falsification test of the reversal hypothesis |

**Budget: 5 variants. Not exceeded.** If it is exceeded I will say so here rather
than hide it.

**Selection rule, fixed in advance:** highest **TRAIN Sharpe**; ties broken by
highest TRAIN Calmar, then by TRAIN CAGR. The winner is carried to TEST **unchanged**.
The other four are deliberately *not* evaluated on TEST, so "TEST touched once" is
literally true rather than approximately true.

**Rules I am holding myself to**
- Parameters chosen on TRAIN only. TEST is read exactly once, at the end.
- No lookahead: a signal at date *t* uses closes up to and including *t*; the engine
  holds `shift(1)` weights, so execution is from *t+1*.
- Signals are built on the **full** panel and then **sliced** to the window, so warm-up
  is satisfied by pre-window history (which a live system would also have).
- Costs mandatory. Everything reported is net of **21.92 bps** per rotation.
- Long-only. `signal == -1` maps to **flat**, never to a short.

---

## 2. Results

*(appended as produced — nothing below this line existed at pre-registration time)*
### Step 00 — fidelity, liveness, and the forward-return profile (**TRAIN only**, `00_fidelity.py`)

**Data loaded as specified:** `load_universe("data/nse")` → 48 symbols × 4,625 daily bars,
2008-01-01 → 2026-10-01, 6.27% NaN cells. Cleaning dropped 66,312 pre-2008 vendor rows,
3 extreme events, and 2 symbols (`adanient`, `jiofin`).

**Fidelity — my vectorised ROC *is* the catalog's ROC.** 124 probes per period on the
longest clean symbol, compared bar-by-bar against `cryptobot.strategies.indicators.roc`:

| period | probes | max abs diff vs catalog `roc()` |
|--------|--------|-------------------------------|
| 5 | 124 | 1.110e-16 |
| 20 | 124 | 1.110e-16 |
| 60 | 123 | 1.110e-16 |
| 126 | 121 | 1.110e-16 |

Floating-point noise only. This is the shipped strategy, not a lookalike.

*(Harness bug found and fixed in my own probe before it could mislead: my first fidelity
slice used `series[i-period-1 : i+1]`, a `period+2` window, while the guard demanded
`period+1` — so all 492 probes silently `continue`d and reported `n_probes=0`. Caught by
a `None` format crash, not by the test itself.)*

**Liveness + is the gate even predictive?** TRAIN 2016–2023, forward horizon 21 bars
(~1 month). `long%`/`flat%`/`short%` are the catalog's own three-way branch.

| variant | long% | flat% | short% | flagged/day | days w/ 0 flagged | mean fwd 21d **flagged** | mean fwd 21d **unflagged** | t |
|---|---|---|---|---|---|---|---|---|
| V1 roc20 t0.5% | 53.7% | 5.5% | 40.8% | 24.1 | 56 | 1.82% | 2.03% | **−3.42** |
| V2 roc20 t3% | 40.8% | 30.8% | 28.4% | 18.3 | 92 | 1.83% | 1.97% | −2.42 |
| V3 roc60 t3% | 52.1% | 17.7% | 30.2% | 23.1 | 98 | 1.83% | 2.02% | −3.07 |
| V4 roc126 t8% | 49.3% | 29.8% | 20.9% | 21.5 | 184 | 1.70% | 2.11% | **−6.72** |
| V5 roc5 t0.5% | 47.2% | 11.9% | 40.9% | 21.2 | 23 | 1.97% | 1.86% | +1.74 |

Liveness is healthy — 47–54% of symbol-bars long, 18–24 names flagged per day, far above
the 5% "effectively always flat" floor. This is not a degenerate strategy.

**But four of the five gates are ANTI-predictive.** The names the ROC gate *keeps* have
*worse* forward 21-bar returns than the names it *throws away*, at t = −2.4 to −6.7. The
longer the ROC horizon, the worse it gets (V4: −6.72). Only the 5-day gate (V5) is
positive, and at t = +1.74 that is not significant. On Indian large caps, a ~1-month
forward window, price ROC is a **reversal** signal, not a continuation signal — so a
long-only book gated on it is structurally long the losing side.

This independently reproduces `research/agent_cross_sectional/BUGS.md` §B4 (that audit
found ROC20 IC of −0.0331, t = −8.16 on TRAIN), from a different code path. The
mechanism looks general to short-horizon ROC on this panel.

### Step 01 — TRAIN sweep, all 5 declared variants (`01_train_sweep.py`)

TRAIN 2016-01-01 → 2023-12-31, 1,973 bars, 48 names, net of **21.92 bps/rotation**.

References first (same engine, same window, same costs):

| reference | CAGR | Sharpe | Sortino | MaxDD | Calmar | Turn/y | Cost/y | Names | TopW |
|---|---|---|---|---|---|---|---|---|---|
| **buy-and-hold** (equal weight) | **21.49%** | 0.90 | 1.06 | −36.66% | 0.59 | — | — | — | — |
| **nsealgo composite** | 20.72% | 0.93 | 1.10 | −32.94% | 0.63 | 1.97 | 1.97% | 21.8 | 6.25% |

The 5 declared variants:

| variant | CAGR | Sharpe | Sortino | MaxDD | Calmar | Turn/y | Cost/y | Names |
|---|---|---|---|---|---|---|---|---|
| V1 roc20 t0.5% | 10.94% | 0.44 | 0.57 | −24.19% | 0.45 | 4.02 | 2.63% | 19.2 |
| V2 roc20 t3% | 6.35% | 0.03 | 0.04 | −25.84% | 0.25 | 4.08 | 2.25% | 16.3 |
| V3 roc60 t3% | 13.25% | 0.53 | 0.65 | −30.33% | 0.44 | 3.42 | 2.45% | 18.5 |
| **V4 roc126 t8%** | **15.11%** | **0.61** | 0.69 | −35.59% | 0.42 | 3.09 | 2.44% | 17.8 |
| V5 roc5 t0.5% | 11.74% | 0.53 | **0.71** | **−14.46%** | **0.81** | 4.07 | 2.90% | 19.2 |

**Selection (rule fixed in advance: max TRAIN Sharpe):** → **V4 = ROC(126) > +8%**.

Two things were already true on TRAIN and I am not going to talk myself out of either:

1. **Every variant loses badly to both references.** The whole family runs 6–15% CAGR
   against buy-and-hold's 21.49% and the composite's 20.72%. Not one variant is close.
2. **Cost drag is high and structurally so**: 2.25–2.90%/yr versus the composite's 1.97%.
   Turnover of 3–4 rotations/yr is driven by the *gate* flipping names in and out, not by
   the 6-month rank underneath.

There is also a revealing disconnect: **V4 had the worst forward-return profile in
Step 00 (t = −6.72, the most anti-predictive gate) and the best TRAIN Sharpe.** Its win
came from holding a *less* book — turnover 3.09 vs 4.07 — not from picking better names.
That is a churn effect, not an alpha effect, and churn effects are exactly what a
different market regime erases.

---

## 3. TEST results — 2024-01-01 → 2026-10-01, net of the full Indian delivery stack

**TEST was touched exactly once, by `02_test_eval.py`, and only on V4** (the variant the
pre-declared TRAIN-Sharpe rule selected). The other four declared variants were never
evaluated here. 684 bars, 48 names, 33 monthly rebalances.

| name | CAGR | Sharpe | Sortino | MaxDD | Calmar | Turn/y | Cost/y | Names | TopW |
|---|---|---|---|---|---|---|---|---|---|
| **`relative_strength` V4 = ROC(126) > +8%** | **−0.36%** | **−0.48** | **−0.57** | **−23.10%** | **−0.02** | 3.17 | 1.57% | 16.8 | 7.45% |
| nsealgo composite | 6.04% | 0.03 | 0.04 | −15.22% | 0.40 | 2.08 | 1.10% | 21.3 | 6.07% |
| buy-and-hold (equal weight) | 8.18% | 0.18 | 0.25 | −15.90% | 0.51 | — | — | — | — |

Detail on the selected variant:

- total return **−1.02%** over 2.75 years, vol 12.37%, win rate 51.0%
- best day +3.82%, worst day −7.39%
- max drawdown **−23.10%, and 502 of 684 trading days underwater (73% of the window)**
- **₹92,290 of costs paid on ₹21,00,000** = 4.39% of capital across the whole window
- yearly: **2024 +18.16% · 2025 −0.13% · 2026 (to 01-Oct) −16.12%**

Signal liveness on TEST: long on **45.7%** of symbol-bars, **21.9** names flagged per day,
**zero** all-empty days. Well above the 5% floor — this is not an always-flat strategy.
It genuinely holds ~17 names and genuinely loses money doing it.

### 3a. vs buy-and-hold — worse on return, and dramatically worse on drawdown

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| relative_strength V4 | −0.36% | −0.48 | −23.10% |
| buy-and-hold | 8.18% | 0.18 | −15.90% |
| **delta** | **−8.54pp** | **−0.66** | **−7.20pp (worse)** |

It paid 3.17 rotations/yr and 1.57%/yr of cost to lose **8.54pp of annual return** versus
doing nothing *and* to take **7.20pp more drawdown** while doing it. That is not a close
call on either axis.

### 3b. Cost drag — costs are NOT the problem (`GOAL.md` Gate 4)

| model | slippage/side | CAGR | Sharpe | MaxDD | drag/y |
|---|---|---|---|---|---|
| zero cost | 0 bps | +0.27% | −0.42 | −22.03% | 0.86% |
| **base** | 5 bps | **−0.36%** | **−0.48** | **−23.10%** | 1.57% |
| double | 10 bps | −1.00% | −0.53 | −24.15% | 2.26% |
| triple | 15 bps | −1.62% | −0.58 | −25.19% | 2.95% |

Costs cost 0.63pp of CAGR at the base setting. But **at literally zero cost the strategy
still returns only +0.27%** against buy-and-hold's 8.18%. This is not a strategy being
eaten by fees — the gross return is already worse than the index. Fees only finish the job.

### 3c. Random-signal control — the minimum bar is not cleared. It is not close.

20 seeds each, matched to the strategy's 45.7% bar-liveness, identical engine, identical
costs:

| control | CAGR mean | CAGR range | Sharpe mean | Sharpe range | MaxDD mean |
|---|---|---|---|---|---|
| random **gate** on the same 6m score | **+3.26%** | 0.20 – 9.86 | −0.33 | −0.62 – +0.40 | **−10.95%** |
| fully **random** score | **+3.01%** | 0.61 – 6.41 | −0.36 | −0.66 – +0.03 | **−11.37%** |
| **`relative_strength` V4** | **−0.36%** | — | **−0.48** | — | **−23.10%** |

**A random gate on the very same momentum score beats this strategy 20 times out of 20.**
A fully random score also beats it 20/20 on CAGR. The strategy loses to the coin flip on
CAGR in every single seed, and on Sharpe in 12–13 of 20.

Worse still, the strategy's drawdown is **more than double** the average random book's
(−23.10% vs −10.95% / −11.37%). So it is not merely picking worse names — the gate is
actively concentrating the book into the names that were about to fall.

### 3d. vs the nsealgo composite

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| relative_strength V4 | −0.36% | −0.48 | −23.10% |
| `build_composite_score` | 6.04% | 0.03 | −15.22% |
| **delta** | **−6.40pp** | **−0.51** | **−7.88pp (worse)** |

It beat the composite on nothing: return, risk-adjusted return, and drawdown all lose.

---

## 4. Why — TRAIN-only diagnosis (`03_diagnose_train.py`, never saw TEST)

The holdout was already spent on V4, so every diagnostic below is TRAIN-only.

### 4a. The gate subtracts. Removing it is free money.

| TRAIN 2016–2023 | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Names |
|---|---|---|---|---|---|---|---|
| V4 as shipped (ROC gate) | 15.11% | 0.61 | −35.59% | 0.42 | 3.09 | 2.44% | 17.8 |
| **no gate (pure 6m momentum rank)** | **17.56%** | **0.73** | −35.21% | **0.50** | 2.64 | 2.29% | 21.8 |
| **inverted gate** (keep the ROC's *short* leg) | 12.25% | 0.48 | **−32.53%** | 0.38 | 2.70 | 1.80% | 8.2 |

**Gate effect on TRAIN CAGR: −2.45pp.** The strategy *is* plain 6-month momentum, damaged
by its own filter. And even the stripped version (17.56%, Sharpe 0.73) still loses to
buy-and-hold (21.49%, 0.90) and to the composite (20.72%, 0.93). The failure is layered:
the filter subtracts, and what remains was never good enough.

Note the inverted gate is *worse* (12.25% vs 15.11%), so the gate is not purely backwards —
it does carry some weak positive information. It just carries less than the churn it costs.

### 4b. The rank IC explains the whole thing

Cross-sectional rank IC of ROC vs forward 21-bar return, TRAIN 2016–2023:

| ROC period | IC | t | % of days IC > 0 |
|---|---|---|---|
| 5 | **−0.0243** | **−5.41** | 44.8% |
| 20 | **−0.0450** | **−9.79** | 42.9% |
| 60 | −0.0148 | −2.76 | 48.6% |
| **126** (the selected V4) | **−0.0090** | −1.61 | 49.6% |
| 252 | +0.0042 | +0.71 | 53.0% |

Short-horizon ROC on NIFTY-50 is a **reversal** signal, strongly and significantly so
(IC −0.045 at 20 days, t = −9.79). The effect decays monotonically to **zero by ~6
months**. V4 — the variant TRAIN Sharpe selected — sits exactly at the zero point.

So the selected variant is a **pure noise filter**: an information-free gate sitting on
top of a decent momentum rank, adding turnover (3.09 vs 2.64) and cost (2.44%/yr vs
2.29%/yr) while subtracting nothing. That is also why V4 won on TRAIN Sharpe despite
having the *worst* forward-return profile in Step 00 — its edge was less churn, not
better picks, and churn advantages are the first thing a regime change takes away.

### 4c. A genuinely *cross-sectional* reading — better, but still not enough

The name promises relative strength against something; the file compares against zero.
Measuring ROC against the **universe median** on the same day, TRAIN only:

| TRAIN variant | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Names |
|---|---|---|---|---|---|---|
| rel-to-median p126 t8% | **19.25%** | **0.83** | −31.85% | 0.60 | 3.38 | 14.2 |
| rel-to-median p60 t3% | 14.58% | 0.60 | −33.28% | 0.44 | 3.76 | 17.5 |
| rel-to-median p20 t0.5% | 6.26% | 0.04 | −38.37% | 0.16 | 4.11 | 20.6 |
| *buy-and-hold* | *21.49%* | *0.90* | *−36.66%* | *0.59* | — | — |
| *nsealgo composite* | *20.72%* | *0.93* | *−32.94%* | *0.63* | — | — |

The honest version of the idea is worth **+4.14pp of TRAIN CAGR and +0.22 Sharpe** over
the shipped implementation (19.25% vs 15.11%) — the mislabelling is real and costs
something. **But even the correct version still loses to buy-and-hold by 2.24pp and to
the composite by 1.47pp.** So the implementation is not the whole story; the underlying
idea is simply not competitive on this panel in this form.

**This was measured on TRAIN only and deliberately not carried to TEST.** Promoting it
would have meant a second look at the holdout with a construction that TRAIN had just
handed me — exactly the failure the protocol exists to prevent. It is reported as a
TRAIN observation, not a result.

### 4d. Integrity checks — all PASS

| check | result |
|---|---|
| Vectorised ROC == catalog `roc()` | max abs diff **1.110e-16** at all four periods, 492 probes |
| **No look-ahead** — shock every price after 2023-12-31 by +5%, +30%, −30% | TRAIN end equity **3.1203362902 in all three runs**, bit-identical |
| Avg names held (TRAIN) | **17.8** (cap 30) — no residual-weight accretion |
| Avg top weight / max any day | 7.45% / **10.80%** (cap 12%) — respected |
| Plausibility | TRAIN 15.11%, TEST −0.36% — nowhere near the 200% tell |
| Cost charged by engine | **21.92 bps** round-trip = 11.92 statutory + 10.0 slippage ✓ |
| Degenerate/all-NaN score rows in the reported run | 0 days on TEST |

Signals are built on the full panel and then **sliced** to the window, so the rolling
warm-up is satisfied by pre-window history — which a live system would also have. A signal
at date *t* uses closes up to and including *t*; `run_backtest` holds `shift(1)` weights,
so execution is from *t+1*.

---

## 5. Bugs found

Written up in full in **`BUGS.md`**. Summary of the four that matter:

- **B2 (src/nsealgo, HIGH)** — `run_backtest` accepts an entirely-NaN score panel and
  returns `cagr=0, sharpe=0, maxdd=0, avg_names=0` with **no error and no warning**. That
  row is indistinguishable in a table from a real "flat" result. My own harness hit this
  from a different direction (B1) and it printed `0.00% / 0.00 / 0.00` as if it were a
  finding. A degenerate score is also *actively interpreted* as a free, un-budgeted full
  liquidation.
- **B1 (pandas trap, HIGH)** — `df - df.median(axis=1)` silently aligns the Series index
  against the DataFrame' **columns** and returns a 4,625 × 4,673 all-NaN frame instead of
  raising. Compounding hazard with B2.
- **B4 (src/cryptobot, MEDIUM)** — a NaN at *today* or at *exactly `period` days ago*
  makes `RelativeStrengthStrategy.signal()` return `0` (flat), indistinguishable from a
  deliberate flat. In a long-only book that is the difference between "sell it" and "no
  idea", from one vendor gap.
- **B3 (src/cryptobot, LOW)** — `warmup()` returns `period` but `roc()` needs
  `period + 1`, so one bar emits a real flat where it should emit no signal.
- **B5 (observation)** — `relative_strength` contains no cross-sectional comparison at
  all, and its shipped default flags 53.7% of bars, leaving the `0` branch near-dead. This
  is the second catalog file with the same mislabelling (`agent_cross_sectional` §B4).

---

## 6. Disclosures

- **Survivorship bias is present** — today's NIFTY-50 backfilled to 2008. It affects every
  strategy in this study equally, including both baselines, so it does not create the
  gap; it inflates all levels.
- **The TEST window was intrinsically hard for everything**: the nsealgo composite itself
  managed only 6.04% CAGR / Sharpe 0.03, and buy-and-hold 8.18% / 0.18. That is context,
  not an excuse — the strategy underperformed *both* by a wide margin, and a strategy that
  only works in good windows is not deployable against a 3%/month target.
- The composite figure is a **like-for-like control in the same engine and window**, not
  the headline walk-forward number in `reports/`.
- Roughly 6.3% of panel cells are NaN (newer listings). `run_backtest` treats a missing
  bar as a 0% return for that symbol, identically for every strategy tested.
- **The end date matters enormously.** TEST ends 2026-10-01; the window includes the 2026
  drawdown (−16.12% in 2026 to 01-Oct). A result quoted without its end date is not
  comparable — see `AGENTS.md`.
- V4 was selected by the pre-declared rule (max TRAIN Sharpe). V5 had the best TRAIN
  **Calmar** (0.81) and V4 had the worst TRAIN MaxDD among V1/V3/V5. Re-selecting after
  seeing TEST would be exactly the protocol violation this study exists to avoid, so it was
  not done, and V5 was never evaluated on TEST.

---

## 7. Plain verdict

**No — `relative_strength` does not make money on NSE.** Out-of-sample it returned
**−0.36% CAGR with a Sharpe of −0.48 and a −23.10% drawdown**, losing to buy-and-hold by
**8.54pp of annual return while taking 7.20pp more drawdown**, losing to the nsealgo
composite by 6.40pp, and losing to a random coin flip **20 times out of 20** — with
more than double the random books' drawdown.

**Most likely reason:** the ROC gate is not a relative-strength signal at all — it is a
short-horizon per-symbol momentum gate, and on NIFTY-50 at a ~1-month horizon short-horizon
ROC is a **reversal** signal (rank IC −0.045, t = −9.79 at 20 days). The variant TRAIN
selection happened to land on the 126-day horizon, where that IC has decayed to zero, so
the gate carries no information at all and can only subtract — costing **−2.45pp of TRAIN
CAGR** and ~0.45 rotations/yr of extra turnover while the 6-month momentum rank underneath
does all the (already insufficient) work.

**The one thing I would try next:** drop the gate and stop ranking by ROC. The evidence
here is that ROC at every horizon I measured (5–252 days) is either a reversal signal or
noise on this panel, and the composite — which blends momentum with a volatility and
liquidity overlay — beats it by 6.40pp on TEST with 7.88pp less drawdown. Concretely:
use `build_composite_score` as the score outright, and if a time-series overlay is wanted,
add it as **exposure** via `nsealgo.factors.regime.exposure_series` rather than as a
name filter — the binding constraint here is drawdown (−23%), not return. That is a
strategy-composition change, not a parameter tweak, so it needs its own declared budget,
and I did not run it: doing so would have turned TEST into a second training set.

---

## 8. Reproduce

```bash
cd research/agent_relstrength
../../.venv/bin/python 00_fidelity.py      # ROC fidelity, liveness, fwd-return profile (TRAIN)
../../.venv/bin/python 01_train_sweep.py   # 5 declared variants, TRAIN only -> picks V4
../../.venv/bin/python 02_test_eval.py     # THE single TEST evaluation (+ controls, costs)
../../.venv/bin/python 03_diagnose_train.py# TRAIN-only ablation, IC, integrity checks
```

Order matters: `02` reads `selected` out of `train_result.json`, so it is impossible to run
before the TRAIN selection exists.

Nothing under `src/nsealgo/**`, `src/cryptobot/**`, `tests/`, `GOAL.md` or `reports/` was
modified. Nothing was committed.
