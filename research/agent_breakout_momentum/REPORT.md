# `breakout_momentum_strategy` on NSE NIFTY-50 — validation report

**Agent:** `breakout_momentum` · **Source:** `src/cryptobot/strategies/catalog/breakout_momentum_strategy.py`
**Data:** `data/nse/*_1d.csv` (primary daily substrate), 48 symbols, 2008-01-01 → 2026-10-01
**Split:** TRAIN 2016-01-01 → 2023-12-31 (1975 bars) · TEST 2024-01-01 → 2026-10-01 (685 bars)
**Costs:** `CostModel(segment="delivery", slippage_bps=5)` → 11.92 bps statutory + 10 bps
slippage = **21.92 bps all-in round trip**, charged on every rebalance of compounding equity.

---

## 0. Verdict (one sentence, asked for first)

> **No. This strategy does not make money on NSE. Out-of-sample it returned 1.45% CAGR
> against 8.16% for buy-and-hold, with a negative Sharpe of −0.62, and its stock-selection
> information is statistically zero.**

Everything below is the evidence.

---

## 1. What the strategy generates

```
hh = donchian_high(highs, period=20)     # max(highs[-20:])  -- INCLUDES today's bar
m  = roc(closes, mom_period=10)          # close/close[-10] - 1
+1 if close >= hh and m > 0
-1 if close <= ll and m < 0
```

Not crypto-specific (no funding, liquidations, peg, options IV or basis), so the brief §8
"no NSE meaning" exit does not apply. Adapted to NSE as **long-only** (short leg dropped —
Zerodha delivery cannot short) plus the brief §5 cross-sectional construction: flagged
names ranked by 126-bar trailing momentum percentile, held in the engine's
`PortfolioConfig` book (22 target names, 12% single, 25% sector, 10% cash, 35% turnover
budget), monthly rebalance.

### 1.1 The port is bit-exact — but the signal is nearly dead

I drove the real `BreakoutMomentumStrategy.signal()` object bar-by-bar over 7,980
post-warmup bars of 3 real symbols and compared to my vectorised panel: **0 mismatches.**
The implementation is faithful.

The problem is what faithfulness reveals. `donchian_high` takes `max(highs[-period:])`,
which **includes today's high**. Since `high ≥ close` always, `close ≥ hh` can only hold
when today's close equals today's high *and* today's high is the 20-day maximum — a
"closed exactly at the day's high" condition, not a channel breakout:

| condition | % of 208,226 finite symbol-bars |
|---|---|
| `close == today's high` | 0.628% |
| `today's high == 20d high` | 14.475% |
| both (the real breakout test) | 0.267% |
| **both and `ROC(10) > 0` — the shipped signal** | **0.031%** |

65 symbol-bars in the whole 18.8-year sample, in only 49 distinct sessions (2008: 16,
2009: 22, 2011: 2, 2012: 1, 2026: 24).

> **In the entire TRAIN window the shipped strategy fires exactly ZERO times.**
> CAGR 0.00%, 0 positions, 0 trades. It is not a weak strategy; it is a non-strategy.
> This is far below the brief §6.3 liveness floor of ~5%.

### 1.2 The ROC conjunct is logically redundant with the breakout condition

For the *excluded*-bar channel, `close[t] ≥ max(high[t-20..t-1])` implies
`close[t] ≥ high[t-k] ≥ close[t-k]` for every `k ≤ 20`, hence `ROC(k) ≥ 0` always. The
catalog's strict `ROC(k) > 0` therefore rejects *only* bars where `close[t] == close[t-k]`
exactly — flat price series. Verified exhaustively: the rejected bars number 493 (k=5),
488 (k=10), 478 (k=20), and **every one has momentum shortfall exactly 0.0**.

Consequence: for any `mom_period ≤ period`, the momentum filter is a stale-price guard
and nothing else. Confirmed in the full backtest — V2 and V3 below match to 12 decimal
places on CAGR.

---

## 2. Declared parameter budget — 5 variants, declared before any return was computed

Written up in full in [`DECLARED_BUDGET.md`](DECLARED_BUDGET.md). Only firing rates and
data structure were inspected beforehand (a signal that never fires cannot be tuned);
no CAGR, Sharpe or return was seen before the declaration existed.

| # | name | channel | period | mom_period | changes |
|---|---|---|---|---|---|
| V1 | `FAITHFUL` | incl | 20 | 10 | — the catalog, verbatim |
| V2 | `EXCL20` | excl | 20 | 10 | channel convention → prior-20d high |
| V3 | `EXCL20_NOMOM` | excl | 20 | 0 | drop the ROC conjunct |
| V4 | `EXCL55` | excl | 55 | 10 | channel length 20 → 55 |
| V5 | `EXCL55_MOM63` | excl | 55 | 63 | confirmation horizon → 1 quarter |

One factor changed per step. **Exactly 5 were run. I did not run a 6th.** Fixed and held
identical across all five (not variants): 126-bar momentum ranking, monthly rebalance,
`PortfolioConfig()` defaults, the delivery cost stack.

**Selection rule fixed in advance:** highest TRAIN net CAGR, tie-break Sharpe then MaxDD.

---

## 3. TRAIN results (2016-01-01 → 2023-12-31) — all net of costs

| variant | live% | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Names |
|---|---|---|---|---|---|---|---|---|
| V1 `FAITHFUL` | **0.000%** | **0.00%** | 0.00 | 0.00% | 0.00 | 0.00x | 0.00% | 0.0 |
| V2 `EXCL20` | 7.303% | **6.47%** | 0.03 | −8.01% | 0.81 | 3.16x | 0.85% | 9.0 |
| V3 `EXCL20_NOMOM` | 7.303% | 6.47% | 0.03 | −8.01% | 0.81 | 3.16x | 0.85% | 9.0 |
| V4 `EXCL55` | 4.782% | 3.81% | −0.41 | −9.28% | 0.41 | 2.39x | 0.58% | 4.7 |
| V5 `EXCL55_MOM63` | 4.656% | 3.68% | −0.44 | −8.42% | 0.44 | 2.34x | 0.57% | 4.3 |
| *buy-and-hold (EW)* | — | *21.46%* | *0.90* | *−36.66%* | *0.59* | *0.12x* | *0.03%* | — |

V2 ≡ V3 exactly (`CAGR 0.064667722412` both) — the redundancy proof of §1.2 reproduced
inside the backtest, not just in numpy.

**Selection by the pre-declared rule: V2 `EXCL20`,** carried to TEST unchanged.

Already on TRAIN the verdict was visible: every live variant trailed buy-and-hold by
~15 pp/yr on return. The one thing they had going for them was drawdown — V2's −8.01%
vs buy-and-hold's −36.66%, 4.6× shallower. That is de-risking, not alpha.

### TRAIN yearly returns

| variant | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | pos |
|---|---|---|---|---|---|---|---|---|---|
| V1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0/8 |
| V2 | 5.3 | 3.8 | 1.5 | 3.0 | 9.5 | 12.4 | −1.2 | 19.5 | 7/8 |
| V4 | 4.5 | 2.3 | −3.0 | −1.2 | 3.3 | 13.2 | −0.9 | 14.1 | 5/8 |
| V5 | 4.0 | 1.7 | −3.0 | −0.3 | 3.1 | 13.2 | −0.9 | 13.2 | 5/8 |
| buy-and-hold | 8.7 | 38.4 | 0.9 | 15.6 | 27.8 | 43.8 | 7.9 | 38.6 | 8/8 |

---

## 4. TEST results (2024-01-01 → 2026-10-01) — the only accepted evidence

V2 `EXCL20`, parameters unchanged: `channel=excl, period=20, mom_period=10`.

| | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Avg names | Total return |
|---|---|---|---|---|---|---|---|---|
| **buy-and-hold (EW)** | **8.16%** | **0.18** | **−15.91%** | 0.51 | 0.36x | 0.08% | 47 | **+24.63%** |
| **`EXCL20` (this strategy)** | **1.45%** | **−0.62** | **−10.67%** | 0.14 | 2.70x | 0.63% | 7.6 | **+4.12%** |
| nsealgo composite | 6.55% | 0.07 | −14.84% | 0.44 | 2.07x | 0.55% | 21.3 | +19.50% |

**vs buy-and-hold (§7.4):**
- Return: **worse by 6.71 pp/yr** (1.45% vs 8.16%). 7.5× worse.
- Drawdown: **better by 5.24 pp** (−10.67% vs −15.91%). Shallower, the strategy's one
  genuine virtue.
- Sharpe: −0.62 vs +0.18.

Net verdict: **it trades a 5 pp drawdown improvement for a 6.7 pp return loss.** That is
a bad trade for a 3%/month target. On the `GOAL.md` §5 gates it fails the return gate and
the positive-in-60%-of-years gate outright (1/3 years positive vs buy-and-hold's 2/3 and
the composite's 2/3 — 2025 −4.1%, 2026 −3.5%).

### TEST yearly returns

| | 2024 | 2025 | 2026* | pos/3 |
|---|---|---|---|---|
| buy-and-hold | +19.9 | +13.3 | −8.3 | 2/3 |
| `EXCL20` | +12.6 | −4.1 | −3.5 | **1/3** |
| nsealgo composite | +22.6 | +7.2 | −9.0 | 2/3 |

*2026 is partial (to 2026-10-01).

---

## 5. Sanity checks (§6) — all run, two caught real errors in my own work

| Check | Result |
|---|---|
| §6.1 plausibility (≤50% CAGR) | 1.45% — **OK**, no lookahead, no compounding bug |
| §6.2 weight count | mean 7.6, max 30 names; single-name max 0.108 ≤ 0.12; worst sector 0.225 ≤ 0.25; invested max 0.795 ≤ 0.90 — **all caps hold** |
| §6.3 liveness | 6.360% on TEST vs 7.303% on TRAIN — alive, not regime-specific |
| §6.4 cost drag | gross 1.72% → net 1.45%, drag only 0.63%/y — **costs are not the binding constraint** |
| §6.5 random control | see §6 below |

**Two self-caught errors, disclosed:**
1. Step 2 printed "CAP VIOLATION" for 86 bars. **My mistake**, not an engine bug:
   `PortfolioConfig` has two limits — `n_positions=22` is the *target* book size,
   `max_names=30` is the *hard cap* on carried names. I compared against the wrong one.
   Corrected in `03b`: max held = 30 = the cap, zero violations.
2. Step 3 reported the control percentile as "1th". A `:.0f` format on a 0–1 fraction.
   Correct value is 55th.

Both are in the scratch output files and left there rather than deleted.

Note on §6.2: holding only 7.6 names is **not** residual accretion (the failure mode the
brief warns about — holding 48). It is the sparse gate: ~3 of 48 names qualify on a
typical day. The 22-name figure is a target the signal cannot reach, not a limit it breaches.

---

## 6. Random-signal control (§7.5) — it does NOT beat a coin flip

20 random gates, bar-level long rate matched to the strategy's 6.360%, same momentum
ranking applied so the *only* difference is which names are flagged:

| | mean | sd | min | max |
|---|---|---|---|---|
| CAGR | 0.96% | 2.41% | −3.96% | 6.15% |
| Sharpe | −0.88 | 0.40 | −1.76 | −0.02 |

The strategy's 1.45% beats **11 of 20** controls — the **55th percentile**, exact one-sided
binomial **p = 0.412**. Indistinguishable from a coin flip.

Worse: the controls average Sharpe **−0.88** and the strategy is **−0.62**. **Beating a
set of coin flips that all lost money, while also losing money, is not an edge.** The
control fails, and so does the strategy.

---

## 7. Did it beat the nsealgo composite? — No

| | CAGR | Sharpe | Avg names |
|---|---|---|---|
| `EXCL20` | 1.45% | −0.62 | 7.6 |
| nsealgo composite | 6.55% | 0.07 | 21.3 |

**Loses by 5.11 pp/yr.** The composite is built from the same panel, the same engine and
the same costs, and holds 21 names against this strategy's 8. Note the composite *also*
trails buy-and-hold on TEST (6.55% vs 8.16%) — on this particular 2.75-year window a
plain equal-weight basket is hard to beat. But the strategy is behind both.

---

## 8. Why it fails — mechanism

Regression of the strategy's gross daily return on the equal-weight market, over all 685
TEST bars (unconditioned, so not biased by the strategy's own exposure):

```
strategy_gross = alpha + beta * market
  beta   0.338      alpha -0.277 bp/day   t = -0.19
  annualised alpha -0.68 pp/yr  (t = -0.19, indistinguishable from zero)
```

**Two independent failures:**

**(a) It structurally cannot fill its book — beta 0.34.** The gate qualifies a mean of
**3.4 names** of ~47 on each of the 34 rebalances (median 2). With `PortfolioConfig`'s hard
12% single-name cap, 3 qualified names can supply at most 36% of the book. The engine
therefore holds **30% invested / 70% cash** on average, and sat fully in cash on **7 of
34 rebalances** (zero names flagged) and at ≤36% on 23 of 34. The strategy participates
in roughly a third of the market's daily move.

**(b) The names it does pick carry no information — alpha ≈ 0.** Once exposure is removed
by the regression, the selection edge is −0.68 pp/yr with t = −0.19. There is no hidden
alpha being throttled by the cash drag; there is nothing to throttle.

**The root cause is a design mismatch, not bad luck.** Breakouts are *rare events*. This
is a per-symbol binary `+1/0/−1` signal being dropped into a cross-sectional book that is
mandated to hold 22 equal-ish positions. A signal that only speaks 6% of the time is a
signal that says "hold cash" 94% of the time. And the 12% cap means you cannot concentrate
into the 2–3 names you actually like to make up for the cash. **Not** evidence that
breakouts never work — evidence that this particular gate is incompatible with this
particular portfolio structure.

---

## 9. Most likely reason for failure, and the one thing to try next

**Reason:** signal frequency vs portfolio structure. The inclusive-channel bug (§1.1) is
the proximate cause — it turned a ~7%-of-bars signal into a 0.03%-of-bars signal, which
made the strategy untunable. Fixing the channel to the standard prior-N-day reading was
necessary but not sufficient: the resulting 6.4%-of-bars signal still cannot fill a
22-name book, and once you compare it fairly against the market, its selection
information is zero (t = −0.19).

**The one thing to try next:** stop using the breakout as an *entry gate* and use it as a
*weight* instead. Keep the composite's 21–22 names always invested, and let the Donchian
condition tilt weights — e.g. hold the 22 names as usual but overweight flagged names up
to the 12% cap and underweight unflagged ones. That keeps the book at ~90% invested, keeps
turnover low enough to be cheap, and converts the gate from a 94%-cash drag into a
modest tilt. If the gate has *any* real information (and here it demonstrably has
essentially none — t = −0.19) that is where it would show up; if the tilt produces no
change versus the composite, that is the clean negative result this report already points
to.

---

## 10. Honest summary

- Out-of-sample this strategy **loses to doing nothing**: 1.45% CAGR vs 8.16%, Sharpe −0.62.
- Its only genuine benefit is a shallower drawdown, bought by sitting in cash 70% of the time.
- It does not beat a random signal (55th percentile, p = 0.41) and does not beat the
  nsealgo composite (−5.11 pp/yr).
- Costs are *not* why it fails — drag is 0.63%/y. The signal is.
- The catalog version as shipped is worse than "fails": it is **mathematically inert**,
  firing zero times in 8 years of the tuning window, because `donchian_high` includes the
  current bar. That is worth fixing in `src/cryptobot/` regardless of NSE — it is a bug in
  the indicator's use, not a market finding.

**A strategy that loses out-of-sample is a useful, publishable result. This is one.**

---

### Reproduction

```bash
.venv/bin/python research/agent_breakout_momentum/step0_audit.py       # data + bit-exactness
.venv/bin/python research/agent_breakout_momentum/step1_train.py       # 5 declared variants, TRAIN
.venv/bin/python research/agent_breakout_momentum/step2_test.py        # TEST, run once
.venv/bin/python research/agent_breakout_momentum/step3b_diagnosis.py  # mechanism
.venv/bin/ruff check research/agent_breakout_momentum/                 # clean
```

Outputs `00_data_audit.txt`, `01_train_sweep.{txt,json}`, `02_test.{txt,json}`,
`03_diagnosis.txt` (superseded), `03b_diagnosis_corrected.txt` (authoritative).

**Constraints honoured:** nothing under `src/` or any test file was modified. No commit,
no push. `GOAL.md` and `reports/` untouched. Exactly 5 variants. TEST read once, for the
pre-declared TRAIN winner, with no parameter adjusted afterwards.