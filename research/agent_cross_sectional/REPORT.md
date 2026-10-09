# `cross_sectional_strategy` on NSE NIFTY-50 — agent report

**Status:** IN PROGRESS (header + declared budget written before any run by me)
**Assigned strategy:** `src/cryptobot/strategies/catalog/cross_sectional_strategy.py`
(`CrossSectionalStrategy`, name = `cross_sectional`)
**Agent:** `cross_sectional`
**Scratch dir:** `research/agent_cross_sectional/`

---

## 1. What the strategy actually is (read before anything else)

```python
def signal(self, closes, highs, lows, volumes):
    m = roc(closes, self.config.period)          # close[t] / close[t-period] - 1
    if m != m:
        return 0
    return 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)
```

`roc()` is a pure **trailing** return. The whole strategy is therefore:

> **the sign of the `period`-bar return, gated by a symmetric `threshold` deadband.**

There is **no cross-sectional information in it at all**, despite the name. Nothing in the
file compares one symbol to another; "cross-sectional" is a misnomer. This matters for
interpretation, so it is stated before any number is produced.

Long-only translation (the NSE book cannot short, and §5 of the brief forbids it):
> be long a name on the days its `period`-bar return is outside the `±threshold` deadband.

Per brief §5, the book is then built by ranking the signalled names cross-sectionally and
handing the score panel to `run_backtest`, which applies the `PortfolioConfig` constraints.

---

## 2. DECLARED PARAMETER BUDGET — exactly 5 variants, no more

Declared in `research/agent_cross_sectional/common.py` (`VARIANTS`), before any backtest.

| tag | period | threshold | rank_days | rebalance | note |
|-----|--------|-----------|-----------|-----------|------|
| V1 | 20 | 0.015 | 20 | M | catalog defaults, ranked by its own 20d ROC |
| V2 | 20 | 0.015 | 126 | M | same flag, ranked by 6m momentum (brief §5) |
| V3 | 60 | 0.05 | 60 | M | slower signal, wider deadband |
| V4 | 126 | 0.08 | 126 | M | 6m signal — the evidence-backed horizon |
| V5 | 20 | 0.015 | 20 | W | catalog defaults but weekly rebalance |

* `period`/`threshold` = the strategy's own parameters (catalog defaults are 20 / 0.015).
* `rank_days` = the horizon used to *rank* the names the strategy flags. `rank_days == period`
  is the pure reading ("buy the strongest of my own signalled names"); `rank_days > period`
  is the brief §5 construction ("rank the signalled names by longer trailing momentum").

**Selection rule (declared, fixed):** highest **TRAIN** Sharpe, tie-break lower TRAIN MaxDD.
Only the winner is ever run on TEST. A 6th variant is not permitted and will not be run.

**Split (non-negotiable):** TRAIN 2016-01-01 → 2023-12-31 (all tuning).
TEST 2024-01-01 → 2026-10-01 (touched once, at the end).

---

## 3. Data

`data/nse/<symbol>_1d.csv` via `nsealgo.data.loader.load_universe("data/nse")` — daily bars
only (1d is the primary substrate; 1m is unusable and 5m/15m cover ~7 weeks, so **no intraday
work is attempted**). Daily bars only, as the brief mandates.

**Survivorship bias is PRESENT** (today's NIFTY-50 backfilled to 2002). Every number in this
report is biased optimistic for that reason and must be read that way.

---

## 4. Cost basis

`CostModel(segment="delivery", slippage_bps=5)` — the full Indian delivery stack.

Because all results go through `run_backtest` (a portfolio simulator that never calls
`fill_price`), the engine charges `all_in_round_trip_bps(100_000)` = **21.92 bps**
(11.92 statutory + 2 × 5 bps slippage). **Every backtest number below is net of 21.92 bps.**
The 11.92 bps figure is never quoted as a result.

---

## 5. Prior interrupted run — what I inherited and what I verified

A previous run of this assignment left `common.py`, `00_load.py`, `10_verify_signal.py`,
`20_train_select.py`, `20_train.json`, `30_test_eval.py`, `30_test.json`, `40_diagnose.py`,
`50_sanity.py`, `60_final.py` and two equity CSVs. **It left no `REPORT.md`.**

Inherited state to be verified, not trusted:
* the 5-variant budget above was already declared in `common.py`;
* TRAIN had been swept and a variant selected (`20_train.json` → selected `V1`);
* **TEST had already been evaluated once by that run** (`30_test.json` exists). I re-run the
  identical frozen variant purely to verify reproducibility — that is a re-computation, not a
  second selection. **Disclosure: TEST was not first touched by me.** No parameter was changed
  after TEST was seen, by either run.
* one defect found on inspection and fixed by me before re-running: the declared
  tie-break "lower TRAIN MaxDD" was implemented as `sort_values(["sharpe","maxdd"],
  ascending=[False, False])`, which is *higher* MaxDD. It did not change the outcome (V1's
  TRAIN Sharpe 0.573 is the unique maximum, no tie), but the code is now correct.

Verification log: appended below as it is produced.

---## 6. Verification log

### V1 — data audit (`00_load.py`) ✅ reproduced
```
rows in 274,541 -> out 208,226 | dropped pre-2008 66,312 | extreme 3
excluded: ['adanient','jiofin']   symbols 48   panel (4629, 48)
index 2008-01-01 -> 2026-10-01 Asia/Kolkata   NaN cells 13,966
```
48 symbols, 4,629 daily bars, ~244 bars/yr. TRAIN 2016–2023 and TEST 2024–2026 both
fully covered. Survivorship bias present (today's NIFTY-50 backfilled).

### V2 — signal equivalence (`10_verify_signal.py`) ✅ reproduced, PASS
The vectorised `strategy_signal` was compared bar-by-bar against the **actual catalog
class** `CrossSectionalStrategy.signal` over all 48 symbols, all params of V1/V3/V4:

| params | bars compared | result |
|--------|---------------|--------|
| period 20, thr 0.015 (V1) | 206,367 | **IDENTICAL** |
| period 60, thr 0.05 (V3) | 202,711 | **IDENTICAL** |
| period 126, thr 0.08 (V4) | 196,788 | **IDENTICAL** |

Zero mismatches. The harness measures the strategy I was assigned, not a lookalike.

**Signal liveness (name-bar fraction) — V1 params:** long 48.4% / flat 19.0% / short 32.6%
on TRAIN; long 45.1% / flat 19.1% / short 35.8% on TEST. Comfortably above the 5% liveness
floor, so the "always flat" failure mode is ruled out.

### V3 — TRAIN sweep of the 5 declared variants (`20_train_select.py`) ✅ reproduced
Selection rule: max TRAIN Sharpe, tie-break shallowest TRAIN MaxDD.

| tag | period | thr | rank_days | reb | CAGR % | Sharpe | MaxDD % | Calmar | Turn x/y | Cost %/y | avg names |
|-----|--------|-----|-----------|-----|--------|--------|--------|--------|----------|----------|-----------|
| **V1** | 20 | 0.015 | 20 | M | 13.49 | **0.573** | −29.66 | 0.45 | 4.09 | 1.49 | 29.3 |
| V2 | 20 | 0.015 | 126 | M | 11.37 | 0.421 | −30.68 | 0.37 | 3.82 | 1.22 | 27.2 |
| V3 | 60 | 0.050 | 60 | M | 14.05 | 0.556 | −34.83 | 0.40 | 3.66 | 1.38 | 23.3 |
| V4 | 126 | 0.080 | 126 | M | 13.74 | 0.523 | −35.44 | 0.39 | 2.95 | 1.04 | 18.7 |
| V5 | 20 | 0.015 | 20 | W | 13.27 | 0.557 | −21.12 | 0.63 | 14.56 | 5.05 | 20.8 |

**SELECTED ON TRAIN: V1** (Sharpe 0.573, unique maximum — no tie, so the tie-break was not
exercised). Reproduces the inherited `20_train.json` to the digit.

**Note on `avg names` ≈ 29 > `n_positions` = 22:** this is the engine's own designed
behaviour, not residual accumulation. `apply_turnover_budget` blends toward each new target
under a 35%/rebalance budget and then `_thin`s to `max_names = 30`, so a book that cannot
rotate fast enough legitimately carries between 22 and 30 live positions. Verified against
the engine source (`src/nsealgo/backtest/engine.py:312`, `:292`) and by the count check in
step 50 below (max never exceeds 30).

---

## 7. V4 — the single TEST evaluation (variant frozen on TRAIN)

`30_test_eval.py`. V1, selected on TRAIN, evaluated **unchanged** on TEST 2024-01-01 →
2026-10-01 (685 bars, 2.81 y). Costed with the engine's `all_in_round_trip_bps` =
**21.92 bps** round trip.

### 7.1 TEST result — net of the full Indian delivery stack

| metric | **STRATEGY V1** | buy-and-hold | random control (5 seeds) | nsealgo composite |
|---|---|---|---|---|
| **CAGR %** | **−0.18** | **+8.21** | +5.75 | +1.99 |
| Sharpe | **−0.52** | +0.19 | −0.02 | −0.31 |
| MaxDD % | **−20.08** | −15.91 | −14.91 | −14.94 |
| Calmar | −0.01 | 0.52 | 0.39 | 0.13 |
| Sortino | −0.63 | +0.25 | −0.02 | −0.40 |
| Vol % | 11.16 | 13.44 | 10.64 | 11.82 |
| Total % | −0.49 | +24.78 | +17.02 | +5.70 |
| Turnover x/yr | 4.13 | 0.36 | 4.11 | 2.43 |
| **Cost drag %/yr** | **1.00** | 0.04 | 1.05 | 0.57 |
| Trades /yr | 11.75 | 0.36 | 11.75 | 11.75 |
| Win rate % | 51.97 | 53.87 | 51.91 | 50.66 |
| **avg names held** | **28.84** | 48 | 28.8 | — |

Nominal cost actually charged: **Rs 59,124** on the Rs 21,00,000 book over 2.81 y
(≈ 1.00 %/yr). Costs paid on equity, not on a bare turnover fraction.

Yearly (TEST):

| year | strategy | buy-and-hold |
|---|---|---|
| 2024 | +13.29% | +20.00% |
| 2025 | −0.28% | +13.34% |
| 2026 (to 01 Oct) | −11.92% | −8.26% |

### 7.2 Head-to-head against buy-and-hold (identical window, identical costs)

* **Return: WORSE by 8.38 pp/yr** (−0.18% vs +8.21% CAGR).
* **Drawdown: WORSE (deeper) by 4.18 pp** (−20.08% vs −15.91%).

It lost on *both* axes. There is no risk-adjusted argument for holding it.

### 7.3 Random-signal control — **FAILED**
Matched on cross-sectional *selectivity*: on every rebalance date it picks the same number
of random names the strategy had eligible, so it carries the same turnover and the same cost
drag (4.11 x/yr vs 4.13 x/yr) but zero signal. Five seeds:

| seed | 1 | 2 | 3 | 4 | 5 | mean |
|---|---|---|---|---|---|---|
| CAGR % | 3.76 | 5.78 | 5.75 | 5.85 | 7.60 | **+5.75** |
| Sharpe | −0.19 | −0.01 | −0.01 | −0.01 | +0.15 | −0.02 |
| MaxDD % | −17.10 | −12.28 | −14.10 | −15.96 | −15.10 | −14.91 |

**The coin flip beat the strategy by 5.92 pp/yr of CAGR and 0.51 of Sharpe.** Every one of
the five seeds beat it. Beating a coin flip is the minimum bar and this is below it.

### 7.4 vs the nsealgo composite — **LOST**
Composite +1.99% CAGR / Sharpe −0.31 / MaxDD −14.94% vs the strategy's −0.18% / −0.52 /
−20.08%. The strategy is worse by 2.17 pp CAGR and takes a *deeper* drawdown than the
house default. It does not deserve to replace the composite.

---

## 8. V5 — sanity checks (brief §6). All PASS; the failure is real.

| check | result |
|---|---|
| **1. Plausibility** | TRAIN CAGR 13.49%, TEST −0.18%. Nowhere near the 40–50% unlevered ceiling → no lookahead, no mis-indexed score, no compounding bug. **PASS** |
| **2. Weight count** | avg 28.84 names held, **MAX 30 = `max_names` exactly**, 0 rows above 30. Max single weight 8.40% (cap 12%), invested 75.7% (target 90%). No residual accumulation. **PASS** |
| **3. Signal liveness** | long on **43.3 %** of name-bars in TEST (flat 21.5 %, short 35.2 %). Far above the 5 % floor — the "effectively always flat" failure mode is ruled out. **PASS** |
| **4. Cost drag** | 1.00 %/yr. **Not the cause of the failure**: at *zero* cost the strategy still only makes **+0.24 % CAGR**, and doubling slippage takes it to −0.59 %, tripling to −1.00 %. There is no gross edge for costs to destroy. **The strategy is unviable, and cost reduction cannot rescue it** (GOAL.md §6.4 forbids trying anyway). |
| **5. Random control** | see §7.3 — lost by 5.92 pp. **FAIL** |
| **6. No-lookahead, empirical** | Truncating the panel at 2020-06-30 / 2023-06-30 / 2025-03-31 / 2026-04-30 and re-running reproduces the full-history equity curve **bit-identically** at every cut (max diff < 1e-12, 3,074–4,519 overlapping bars). No future bar reached a past decision. **PASS** |
| **7. Cost model sanity** | `.venv/bin/python -m nsealgo.cli costs` → 11.92 bps statutory round trip at Rs 1,00,000/side vs 11.65–11.66 bps published. Engine charges 21.92 (statutory + 2 × 5 bps slippage). **PASS** |

---

## 9. V6 — WHY it failed (diagnostics; V1 stays frozen)

### 9.1 The signal is *negatively* predictive on both windows

Long leg = ROC20 > +1.5 %, short leg = ROC20 < −1.5 %, measured against the forward
21-bar return:

| window | leg | n | mean fwd 21d | annualised | win % | t |
|---|---|---|---|---|---|---|
| TRAIN | long | 45,890 | +1.865% | +21.67% | 58.4 | +46.0 |
| TRAIN | flat | 14,642 | +1.889% | +21.95% | 59.0 | +26.5 |
| TRAIN | short | 30,859 | +2.060% | **+23.93%** | 59.8 | +36.4 |
| TEST | long | 14,725 | +0.651% | +7.57% | 53.4 | +10.6 |
| TEST | flat | 6,117 | +0.667% | +7.75% | 52.7 | +7.4 |
| TEST | short | 11,028 | +1.238% | **+14.38%** | 56.3 | +17.9 |

**Long-minus-short spread: −2.26 pp/yr on TRAIN, −6.82 pp/yr on TEST.**

The strategy's short leg — the names that have fallen hardest — earned roughly **twice** the
annualised forward return of its long leg. Cross-sectional rank IC of ROC20 vs forward 21d
is likewise negative on both windows (TRAIN −0.0331, t = −8.16, positive on only 13.7 % of
days; TEST −0.0193, t = −2.17).

At a ~1-month horizon on Indian large caps, a 20-day return is a **reversal** signal, not a
momentum signal. A long-only book built on this signal is *structurally long the losing side*.
The long-only restriction is not what killed it — the long leg itself is the wrong leg.

### 9.2 It was already behind buy-and-hold on TRAIN — the Sharpe was beta

| variant | TRAIN CAGR % | Sharpe | MaxDD % | edge vs buy-and-hold |
|---|---|---|---|---|
| **buy-and-hold (TRAIN)** | **+22.19** | 0.91 | −37.97 | — |
| V1 | +13.49 | 0.57 | −29.66 | **−8.70 pp/yr** |
| V2 | +11.37 | 0.42 | −30.68 | −10.82 |
| V3 | +14.05 | 0.56 | −34.83 | −8.14 |
| V4 | +13.74 | 0.52 | −35.44 | −8.45 |
| V5 | +13.27 | 0.56 | −21.12 | −8.92 |

**Variants beating buy-and-hold on TRAIN: 0 of 5.** The TRAIN window rose +22.20 %/yr
equal-weight. Any long-only book prints a respectable Sharpe on a tape like that; V1's
0.573 was riding beta, not alpha. The selection rule had no way to notice, because Sharpe
was the declared criterion and Sharpe was inflated by the market. This is the root cause and
it was **visible in TRAIN** — the run did not need TEST to reveal it.

### 9.3 The `threshold` gate is non-binding, so the strategy is barely a strategy

With period 20 / ±1.5 %, the gate leaves 21.7 of 48 names eligible on an average day, and
**≥22 names are eligible on ~50 % of days**. On those days the deadband excludes nobody
from contention and the book degenerates to *"the 22 names with the highest 20-day ROC"* —
i.e. plain 20-day momentum ranking with no strategy-specific content at all. The strategy
is essentially a **slightly noisy momentum ranking**, and the noisy part is a reversal signal.

### 9.4 The 126-day horizon was tested and did not rescue it either

V4 (period 126 / ±8 %, the horizon the engine's own evidence doc favours) scored 13.74 %
TRAIN CAGR, still 8.45 pp/yr behind buy-and-hold. Top-quintile forward-21d return by
lookback confirms the horizon effect is weak in both windows (TRAIN: 20d +16.9, 60d +21.3,
126d +22.4 %/yr; TEST: 20d +10.9, 60d +7.5, 126d +10.3 %/yr). No variant in the declared
budget produced alpha.

### 9.5 Regime, for completeness
TRAIN: equal-weight +22.20 %/yr, vol 16.72 %, maxDD −37.97 %, 57.9 % of days up.
TEST: +8.25 %/yr, vol 13.44 %, maxDD −15.91 %, 53.9 % of days up. TEST was a weaker tape,
but buy-and-hold still made 8.21 %/yr there, so the regime does not explain the failure.

---

## 10. Verdict

> **No. `cross_sectional_strategy` does not make money on NSE NIFTY-50.**
> Out-of-sample it returned **−0.18 % CAGR (Sharpe −0.52, MaxDD −20.08 %)**, against
> **+8.21 % CAGR** for buy-and-hold over the identical window — **8.38 pp/yr worse on
> return and 4.18 pp deeper in drawdown**, worse than a matched random signal
> (−5.92 pp), and worse than the nsealgo composite (−2.17 pp). It was already 8.70 pp/yr
> behind buy-and-hold on TRAIN, before TEST was ever opened.

**Most likely reason.** The signal is a **reversal** signal on this panel, not a momentum
signal. Over the forward 21-bar return, the strategy's *short* leg (ROC20 < −1.5 %) earned
+23.93 %/yr on TRAIN and +14.38 %/yr on TEST, versus +21.67 % and +7.57 % for its long leg.
The long-minus-short spread is **−2.26 pp/yr (TRAIN) and −6.82 pp/yr (TEST)**, and the rank IC
of ROC20 against forward 21d is negative on both windows (t = −8.16 and −2.17). A long-only
delivery book built on that signal is therefore *structurally long the losing side*, and the
±1.5 % gate is non-binding on ~half of all days, so the strategy adds no selectivity to
plain 20-day ranking — it only adds cost. Costs are not the problem (gross of everything the
strategy still only makes +0.24 % CAGR), so there is nothing for a cheaper execution to rescue.

**The one thing I would try next.** Invert the signal — rank by *negative* trailing momentum
(buy the 22 names with the **worst** 126-day ROC, filtered by a deep negative deadband) — and
re-test it under exactly this protocol. The evidence for the inverted leg is already in §9.1
and it is the only thing in this report that points anywhere positive. I have **not** run it:
it would be a 6th variant and the declared budget is 5. Flagging it as the next agent's job,
with the caveat that the whole 24-year panel is one survivorship-biased backfilled universe
and an inverted signal is exactly the shape of finding that gets over-fitted.

---

## 11. Protocol compliance statement

* **Parameter budget: 5 variants declared, 5 variants run, 0 exceeded.** Declared in
  `common.py::VARIANTS` before any backtest; TRAIN swept once (`20_train_select.py`), one
  winner frozen, one TEST evaluation (`30_test_eval.py`). Steps 40/50/60 are *diagnostics on
  the frozen V1* — they compute no new candidate and select nothing.
* **TEST discipline.** Selected on TRAIN by the declared rule (max TRAIN Sharpe). V1
  evaluated on TEST unchanged. *Full disclosure:* the interrupted prior run had already
  produced a TEST evaluation before I started; I re-ran the **identical frozen variant** to
  verify reproducibility (it matched digit-for-digit) rather than making a second selection.
  No parameter was altered after TEST was visible, by either run.
* **No lookahead.** Every factor is trailing; `run_backtest` lags weights one bar; verified
  empirically by the truncation test (§8 row 6) — equity curves are bit-identical to <1e-12
  at four different cut dates.
* **Costs.** Every backtest number is net of 21.92 bps all-in (11.92 statutory + 2 × 5 bps
  slippage), the rate `run_backtest` actually charges. The 11.92 bps statutory figure is used
  only inside the `nsealgo.cli costs` sanity check, never as a result. The buy-and-hold
  benchmark is charged a real one-way deployment cost at the same stack.
* **Constraints not bypassed.** Default `PortfolioConfig` (22 picks, 12 % single name, 25 %
  sector, 10 % cash, 35 % turnover budget, 30 max names) throughout; verified ≤ 30 names,
  ≤ 12 % single weight.
* **Survivorship bias is present** (today's NIFTY-50 backfilled to 2008; `eternal` and
  `maxhealth` only have 2020+/2021+ history; `adanient` and `jiofin` excluded by the loader
  as too new). Every number above is biased optimistic on that account. The failure is so
  large (8.38 pp/yr) that bias cannot rescue it.
* **Daily bars only.** No intraday claim is made. `1m` does not exist; `5m`/`15m` cover
  ~7 weeks and were not used.
* **Lint:** `.venv/bin/ruff check research/agent_cross_sectional/` → *All checks passed!*
* **Not committed.** No commit, no push. Nothing in `src/**`, `tests/**`, `GOAL.md` or
  `reports/**` was modified.

---

## 12. Artifacts

| file | contents |
|---|---|
| `REPORT.md` | this report |
| `BUGS.md` | 4 findings: 1 engine issue in `src/nsealgo/backtest/engine.py` (no effect on this result, live-hazard), 2 harness defects I fixed, 1 structural finding about the assigned strategy |
| `common.py` | strategy signal, score construction, declared `VARIANTS`, benchmark, random control, formatting |
| `00_load.py` | mandatory data audit |
| `10_verify_signal.py` | proves the vectorised signal == the catalog class (206k bar comparisons) |
| `20_train_select.py` / `20_train.json` | TRAIN sweep + the TRAIN-only selection |
| `30_test_eval.py` / `30_test.json` | the single TEST evaluation + controls |
| `40_diagnose.py` | why it failed (§9) |
| `50_sanity.py` | causality test, weight count, plausibility, liveness |
| `60_final.py` | all-variants-vs-benchmark, cold-start check, consolidated numbers |
| `test_equity_V1.csv`, `test_equity_bh.csv` | TEST equity curves |

Reproduce: `.venv/bin/python research/agent_cross_sectional/{00_load,10_verify_signal,20_train_select,30_test_eval,40_diagnose,50_sanity,60_final}.py`
