# `kama_strategy` on NSE NIFTY-50 — **NEGATIVE RESULT**

Source: `src/cryptobot/strategies/catalog/kama_strategy.py`
Signal: `close > KAMA(period)` → +1 else −1. Catalog default `period=20`, with
`fast=2, slow=30` hard-coded by the library.
Scratch: `research/agent_kama/` — `run.py` (protocol), `verify_kama.py` (indicator
equivalence), `results.json`, `turnover_diag.json`, `run.log`.

---

## 0. Provenance (required header record)

```python
from nsealgo.provenance import provenance; provenance()
```

```
{'engine': 'd93815344bd3', 'loader': 'c1badf5f7df8', 'costs': 'ba350aef75b3', 'panel': '389b082b832f'}
```

Data panel ends **2026-10-01**. Every number below is net of the **21.92 bps** all-in
round trip charged by `run_backtest` (`CostModel(delivery, slippage_bps=5)`:
`round_trip_bps(1e5)=11.92`, `all_in_round_trip_bps(1e5)=21.92`) unless the row says
otherwise. The 11.92 bps statutory-only figure appears once, in the cost-stress table,
and is labelled as such. Not mixed anywhere.

---

## 1. Verdict

> **No. `kama_strategy` does not make money on NSE NIFTY-50 out of sample.**
> Selected variant V2 (`period=10`) returned **0.36% CAGR, Sharpe −0.50, MaxDD −18.23%**
> over TEST (2024-01-01 → 2026-10-01), against **8.26%** for literal buy-and-hold and
> **2.58% median** for a random signal with identical exposure. It beat **0 of 20**
> random draws. **All five variants** lost to the random median, to momentum-only, and
> to the nsealgo composite. It is not cost-limited — at zero cost it still only reaches
> 1.15% CAGR.

---

## 2. Declared parameter budget — declared before any run, honoured

`period` is the only strategy parameter (`fast`/`slow` are hard-coded inside
`cryptobot.strategies.indicators.kama` and are not exposed by `KamaConfig`). Rebalance
frequency (monthly) and the 126-day momentum lookback are fixed harness settings, not
strategy variants.

| Variant | `period` |
|---------|---------|
| V1 | 20 (catalog default) |
| V2 | 10 |
| V3 | 30 |
| V4 | 55 |
| V5 | 75 |

**Selection rule fixed in advance: max TRAIN Calmar.** Selection used TRAIN only; the
winner (V2, `period=10`, Calmar 1.00) was then run unchanged on TEST.

**Variants tested: 5. Exceeded 5: no.**
**TEST looked at before selection was locked: no.** Selection was computed and printed
before the TEST block executed. Two diagnostics (ablation, turnover sweep) were run on
**TRAIN only** and are labelled as diagnostics, not variants; neither was selected on.

---

## 3. Data

- `load_universe("data/nse")` daily close panel, cleaned. **4,625 bars × 48 symbols,
  2008-01-01 → 2026-10-01.** Cleaning dropped 66,312 pre-2008 vendor rows, 3 extreme
  moves, 539 frozen bars (`bajajauto`, `nestleind`), and excluded `adanient`, `jiofin`.
- TRAIN 2016-01-01 → 2023-12-31 (1,973 sessions). TEST 2024-01-01 → 2026-10-01
  (684 sessions).
- **Daily bars only.** 1m/5m/15m/30m banned or far too short — not used. No intraday
  claim is made anywhere in this report.
- **Survivorship bias is present** (today's NIFTY-50 backfilled over 18y) and is disclosed
  with every number. It inflates *all* rows including buy-and-hold, so it does not
  explain the underperformance, but it does mean none of these CAGRs is a forecast.

---

## 4. Indicator fidelity

`research/agent_kama/verify_kama.py` compares my vectorised `kama_panel` against the real
`cryptobot.strategies.indicators.kama`, bar for bar, on a 900-bar synthetic panel with
regime flips, a constant series (to exercise the `vol == 0` branch) and injected NaNs,
for all five declared periods:

```
period= 10  max_rel_diff=0.000e+00  first_finite_bar=10  OK
period= 20  max_rel_diff=0.000e+00  first_finite_bar=20  OK
period= 30  max_rel_diff=0.000e+00  first_finite_bar=30  OK
period= 55  max_rel_diff=0.000e+00  first_finite_bar=55  OK
period= 75  max_rel_diff=0.000e+00  first_finite_bar=75  OK
OK: vectorised kama_panel == catalog kama (to float precision)
```

**Bit-identical, not merely close.** No catalog bug found in `kama` — unlike the Hull
line (`agent_hull_ma` found `2*WMA(n) - WMA(n/2)`, swapped), `kama` matches its own
definition. The catalog strategy is correct as written; it simply does not work here.

---

## 5. Signal diagnostic (TRAIN) — the flag is not just useless, it is anti-predictive

Before any portfolio was built, I measured whether the raw time-series flag carries any
21-day forward-return content at all. Two weightings are shown because they genuinely
disagree and quoting only one would be cherry-picking:

- **day-equal** — mean over days of (cross-sectional mean among long names − same among
  short names). This is what a daily-rebalanced book earns, and the t-stat belongs here.
- **obs-equal** — every (day, symbol) observation weighted equally.

| variant | long% | fwd21 when long | fwd21 when short | spread day-eq | spread obs-eq | t | negative years |
|---------|-------|-----------------|------------------|---------------|---------------|---|----------------|
| V1_20 | 46.9% | 1.927% | 1.952% | **−0.602%** | −0.025% | −7.60 | 8/8 |
| V2_10 | 46.3% | 1.983% | 1.879% | **−0.404%** | +0.104% | −5.36 | 6/8 |
| V3_30 | 48.1% | 1.826% | 2.101% | **−0.758%** | −0.275% | −9.25 | 8/8 |
| V4_55 | 49.4% | 1.807% | 2.141% | **−0.531%** | −0.334% | −6.48 | 7/8 |
| V5_75 | 49.4% | 1.781% | 2.181% | **−0.412%** | −0.400% | −4.99 | 6/8 |

**This is the core finding.** Under the weighting that matters for a rebalanced book, the
21-day return of names *above* their KAMA is **worse** than names below it, by 0.4–0.8%
per 21 days, with t-stats of −5 to −9 and negative spread in 6–8 of the 8 TRAIN years.
It is not a knife-edge result: it is a robustly negative signal. (The obs-equal column
is near zero — it disagrees because the long/short counts per day vary; both are ≤ 0 for
four of five periods, and the day-equal one is the honest estimator here.)

Mechanically this is exactly what a trend filter does in a mean-reverting cross-section:
it systematically buys the names that have already run up (and are therefore due to
revert over the next month) and sells the laggards. That is the mirror image of the
Indian evidence cited in `nsealgo/factors/core.py` — continuation, not reversal. KAMA is
a reversal filter wearing a trend filter's clothes.

---

## 6. TRAIN (2016-01-01 → 2023-12-31) — selection only

All net of 21.92 bps.

| variant | period | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Long% |
|---------|--------|-------|--------|--------|--------|----------|-----------|-------|-------|
| V1_20 | 20 | 12.13 | 0.52 | −22.08 | 0.55 | 3.87 | 2.91 | 18.7 | 46.9% |
| **V2_10 (selected)** | **10** | **16.25** | **0.85** | **−16.17** | **1.00** | 3.84 | 3.38 | 19.0 | 46.3% |
| V3_30 | 30 | 12.65 | 0.56 | −18.90 | 0.67 | 3.84 | 2.95 | 18.8 | 48.1% |
| V4_55 | 55 | 12.90 | 0.56 | −18.96 | 0.68 | 3.62 | 2.74 | 18.8 | 49.4% |
| V5_75 | 75 | 13.95 | 0.62 | −21.55 | 0.65 | 3.53 | 2.76 | 18.8 | 49.4% |
| momentum-only (no KAMA filter) | — | 17.56 | 0.73 | −35.21 | 0.50 | 2.64 | 2.29 | 21.8 | — |
| BH-literal (`panel.pct_change().mean(axis=1)`) | — | 22.24 | 0.91 | −37.97 | 0.59 | — | — | 48 | — |
| nsealgo composite | — | 20.72 | 0.93 | −32.94 | 0.63 | 1.97 | 1.97 | 21.8 | — |

TRAIN looks like a win — and that is precisely the trap this protocol exists to catch.
V2 has Sharpe 0.85 and **half the drawdown** of everything else. Note though that the
TRAIN headline is *not* alpha: at the default 35% turnover budget the KAMA book is only
**72.6% invested** vs 88.6% for momentum-only, so a large part of the Calmar advantage is
cash, not signal (quantified in §6.2).

### 6.1 Diagnostics (TRAIN only — not variants, not selected on)

**Ablation — momentum with and without the KAMA filter, same harness:**

| TRAIN | CAGR% | Sharpe | MaxDD% |
|-------|-------|--------|--------|
| momentum only (no filter) | 17.56 | 0.73 | −35.21 |
| momentum + KAMA(10), tb=0.35 | 16.25 | 0.85 | −16.17 |

**Turnover-budget sweep (is the filter dead, or just underinvested?):**

| TRAIN, V2 | turnover_budget | invested% | names | CAGR% | Sharpe | MaxDD% |
|-----------|-----------------|-----------|-------|-------|--------|--------|
| KAMA(10) | 0.35 (default) | 72.6% | 19.0 | 16.25 | 0.85 | −16.17 |
| KAMA(10) | 0.70 | 87.3% | 19.0 | 19.55 | 0.96 | −16.95 |
| KAMA(10) | 1.00 | 87.4% | 19.0 | **19.61** | 0.96 | −16.56 |
| momentum-only | 0.35 | 88.6% | 21.8 | 17.56 | 0.73 | −35.21 |
| momentum-only | 1.00 | 89.1% | 21.8 | 17.79 | 0.74 | −35.21 |

**Honest reading:** once fully invested, the KAMA filter *does* beat momentum-only on
TRAIN (19.61% vs 17.79% CAGR) and cuts the drawdown in half (−16.56% vs −35.21%). So on
TRAIN the filter is a working risk overlay, and the 35% turnover budget was converting
most of it into idle cash. **None of this transfers** — see §7. I did not re-select on
these numbers and did not re-run TEST with them; doing so would be exactly the
"tune until the curve looks good" the brief forbids.

### 6.2 Why the KAMA book is underinvested (engine mechanism, not a data artifact)

| book (TEST) | invested% | names | flat days | turnover x/y | cost %/y |
|-------------|-----------|-------|-----------|--------------|---------|
| KAMA(10) | 67.6% | 17.8 | 21 | 3.91 | 1.90 |
| KAMA(20) | 69.3% | 18.0 | 21 | 3.79 | 1.89 |
| momentum-only | 87.2% | 21.3 | 21 | 2.77 | 1.39 |
| nsealgo composite | 87.2% | 21.3 | 21 | 2.08 | 1.10 |

The KAMA filter deletes names from the target. `apply_turnover_budget`
(`engine.py:354-430`) then finds fewer wanted names, spends its allowance on compulsory
exits, and has little surplus left to adopt new ones — so the book drifts into cash and
stays there. This is engine design shared by every row above; the KAMA book is just the
one that triggers it hardest. It is also why KAMA's turnover (3.91×/yr) is *higher* than
momentum-only's (2.77×/yr) despite holding fewer names: exiting is unconditional and
cheap-ish, adoption is rationed.

---

## 7. TEST (2024-01-01 → 2026-10-01) — touched once, after selection was locked

| row | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Total ret |
|-----|-------|--------|--------|--------|----------|-----------|-------|-----------|
| V1_20 | 1.25 | −0.41 | −18.33 | 0.07 | 3.79 | 1.89 | 18.0 | +3.5% |
| **V2_10 (selected)** | **0.36** | **−0.50** | **−18.23** | **0.02** | 3.91 | 1.90 | 17.8 | +1.0% |
| V3_30 | 0.59 | −0.44 | −18.79 | 0.03 | 3.74 | 1.84 | 18.3 | +1.7% |
| V4_55 | 0.22 | −0.45 | −19.06 | 0.01 | 3.58 | 1.78 | 18.0 | +0.6% |
| V5_75 | −0.36 | −0.48 | −19.54 | −0.02 | 3.47 | 1.71 | 18.4 | −1.0% |
| **buy-and-hold, engine (momentum-only book)** | **1.58** | −0.30 | −18.82 | 0.08 | 2.77 | 1.39 | 21.3 | +4.5% |
| **buy-and-hold, literal (`panel.pct_change().mean(axis=1)`)** | **8.26** | **+0.20** | **−15.90** | **0.52** | — | entry only | 48 | +24.9% |
| **nsealgo composite** | **6.04** | **+0.03** | **−15.22** | **0.40** | 2.08 | 1.10 | 21.3 | +17.9% |

Selected V2: **0.36% CAGR over 2.7 years — a total return of +1.0%.** Every single
variant is negative-Sharpe. The TRAIN story (Sharpe 0.85, Calmar 1.00) did not survive
one bar of out-of-sample data.

### 7.1 Sanity checks (brief §6)

1. **Plausibility.** ✅ 0.36% CAGR is nowhere near the 40–50% unlevered ceiling. No
   lookahead, no compounding bug, no mis-indexed panel. The failure is real, not a bug.
2. **Weight count.** avg 17.8 names vs the 22 configured. **Not** residual-weight
   accumulation: max single weight 6.10% (cap 12%), gross = net = 67.6% (long-only, no
   shorts), max names 22, and the shortfall vs momentum-only's 21.3 is fully explained by
   the turnover-budget mechanism in §6.2. The book is underinvested, not over-diversified.
3. **Signal liveness.** 43.5% of bars long. Healthy — nowhere near the ≤5% always-flat
   failure mode. The strategy was genuinely long roughly half the time and still lost.
4. **Cost drag.** 1.90%/yr. Gross would be ~2.3% CAGR; net is 0.36%. The strategy is
   *barely* cost-viable at all, and not rescued by costs (see the stress table below).
5. **Negative control.** ❌ **FAILS, unambiguously.** 20 random-signal controls with the
   same % of bars long, same harness:

   ```
   TEST random CAGR sorted: 0.68 0.70 0.74 1.33 1.34 1.36 2.14 2.24 2.39 2.45
                            2.70 2.99 3.28 3.29 3.78 3.87 4.00 4.03 4.52 5.43
   median 2.58%   min 0.68%   max 5.43%
   ```

   Selected V2 beat **0 of 20**. Its Sharpe (−0.50) is below **all 20** random Sharpes
   (worst random −0.64, best −0.08). A coin flip with identical exposure beats this
   strategy *every single time*. Note the coin flip is not weak here — the median random
   book makes 2.58% because momentum ranking inside it still works; KAMA's filter is
   what destroys the return.

### 7.2 Cost stress (selected V2, TEST)

| cost model | round trip | TEST CAGR% |
|------------|-----------|-----------|
| zero slippage (**statutory only — `round_trip_bps`, not the engine's charge**) | 11.92 bps | 1.15 |
| **base (`slippage_bps=5`) — all headline numbers** | **21.92 bps** | **0.36** |
| `slippage_bps=10` | 31.92 bps | −0.42 |
| `slippage_bps=15` | 41.92 bps | −1.20 |

Cost drag ≈ 0.4 pp of CAGR per 5 bps of slippage. **This is not a cost-limited result.**
At *zero* cost the strategy makes 1.15% — still below the random median (2.58%), below
momentum-only (1.58%), and far below buy-and-hold (8.26%). Removing costs does not rescue
it. The conclusion would be identical at any plausible cost assumption.

### 7.3 TEST yearly returns (%)

| book | 2024 | 2025 | 2026 (to 10-01) |
|------|------|------|-----------------|
| KAMA V2_10 | +12.59 | +1.14 | −11.29 |
| momentum-only (engine BH) | +17.91 | +1.32 | −12.53 |
| nsealgo composite | +21.91 | +6.61 | −9.31 |
| buy-and-hold (literal) | +20.40 | +13.35 | −8.26 |

KAMA lags every benchmark in two of three years and the 2026 partial year is a loss for
everything (a market drawdown, not a KAMA-specific failure).

---

## 8. TEST vs buy-and-hold, and vs the composite

| | KAMA V2_10 | BH-literal | BH-engine | composite | random median |
|---|---|---|---|---|---|
| CAGR | 0.36% | **8.26%** | 1.58% | 6.04% | 2.58% |
| Sharpe | −0.50 | **+0.20** | −0.30 | +0.03 | — |
| MaxDD | −18.23% | **−15.90%** | −18.82% | −15.22% | — |
| Calmar | 0.02 | **0.52** | 0.08 | 0.40 | — |

- **vs buy-and-hold (literal, the brief's benchmark): worse by 7.90 pp CAGR and worse on
  drawdown by 2.33 pp.** It is worse on *both* axes. There is no risk-adjusted consolation.
- **vs buy-and-hold through the engine (momentum-only book, identical harness,
  constraints and cost path): worse by 1.22 pp CAGR, better on drawdown by 0.59 pp.**
  The drawdown "win" is an artefact of holding ~20% more cash (§6.2), not of selection.
- **vs nsealgo composite: worse by 5.68 pp CAGR and worse on Calmar (0.02 vs 0.40).**
  The project already has a better strategy than this one, built from documented factors.

**Note on the two buy-and-hold rows.** They differ by 6.7 pp CAGR because they are
different books: BH-literal is equal-weight across all 48 names (NIFTY-50 beta), while
BH-engine is the 22-name concentrated momentum book the strategy is built on. The
literal figure is the market benchmark the brief asks for; the engine figure is the
like-for-like control. KAMA loses to both.

---

## 9. Why it failed, and what I would try next

**Most likely reason (in order of confidence):**

1. **The signal is anti-predictive at the monthly horizon** (§5). KAMA is a trend filter;
   buying what is above its own moving average in a cross-section systematically buys
   the recently-extended names, and Indian equities exhibit short-term *continuation*
   rather than reversal (the evidence base `nsealgo/factors/core.py` is built on). The
   filter therefore fights the momentum ranking it is applied to. This is visible at the
   raw-signal level, before any portfolio is built, with t-stats of −5 to −9 — the
   strongest evidence in this report, and it explains the TEST result directly.
2. **The turnover budget converts the filter into cash.** On TRAIN, fully investing the
   KAMA book lifted CAGR from 16.25% to 19.61% and halved the drawdown (§6.1). The
   mechanism is real but it did not survive out of sample, and tuning the budget on TRAIN
   to chase it would be precisely the overfitting this protocol forbids.
3. **Not costs.** Cost drag is 1.90%/yr and the zero-cost control still loses to a coin
   flip. No cost assumption rescues this.

**The one thing I would try next:** do not spend more time on KAMA as a *stock-selection*
filter. If KAMA has any value at all it is as a **market-level regime gate** — scale
exposure to 0 or 1 on the index depending on whether the *index* is above its KAMA — which
is the one way a time-series indicator avoids the cross-sectional reversal trap that
§5 exposes. That is a different strategy from the assigned one, so I have not run it.

**A harness note worth carrying forward:** `load_universe` returns 48 symbols whose
NaN pattern means the book is flat for the first 21 sessions of every TEST window (the
engine drops the first rebalance date, `engine.py:472`). That costs ~3% of the window and
affects every row in the table equally, so it does not change any conclusion — but it is
worth knowing before comparing absolute CAGRs across agents.

---

## 10. Reproduce

```bash
.venv/bin/python research/agent_kama/verify_kama.py   # indicator equivalence, exits 1 on mismatch
.venv/bin/python research/agent_kama/run.py           # full protocol, ~73 s, writes results.json
.venv/bin/ruff check research/agent_kama/
```

No file under `src/` or `tests/` was modified by this study.