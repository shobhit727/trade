# `donchian_channel` → NSE NIFTY-50 — validated TEST result

**Agent:** donchian · **Source:** `src/cryptobot/strategies/catalog/donchian_channel.py`
**Date:** 2026-10-07 · **Data:** `data/nse` daily, 48 symbols, 2008-01-01 → 2026-10-01
**Scratch:** `research/agent_donchian/` · nothing committed · `src/`, `tests/`, `GOAL.md`, `reports/` untouched

---

## Verdict

**No. This strategy does not make money on NSE out of sample.** TEST CAGR **+2.05%** net
of the full Indian delivery stack, **Sharpe −0.43**, against buy-and-hold **+8.16% /
Sharpe +0.18**. It loses to the market by **6.11pp per year** and fails `GOAL.md` Gate 3
(1 of 3 years positive; needs ≥60%). It does not beat a random signal of the same live
fraction on every seed.

---

## 1. The signal, and a bug in it that has to be reported first

`cryptobot.strategies.indicators.donchian_high(highs, p)` returns `max(highs[-p:])` — the
channel window **includes today**. Since `close <= high` always holds,

```
close >= max(highs[-p:])   ⟺   close == high_today == max(window)
```

The long signal can therefore only fire when the close sits *exactly* on the day's high
*and* that high is the window maximum. Measured over the whole panel:

| quantity | value |
|---|---|
| name-bars where `close >= max(high[-20:])` | 555 |
| name-bars where `close == high` | 1,300 |
| **both — i.e. the long signal firing** | **555** |
| total name-bars | 222,192 |
| **long-fire rate** | **0.2498%** |

Signal liveness by window (fraction of name-bars long):

| variant | TRAIN | TEST |
|---|---|---|
| `literal p=10` | **0.00%** | 0.12% |
| `literal p=20` | **0.00%** | 0.07% |
| `literal p=55` | **0.00%** | 0.04% |
| `literal p=100` | **0.00%** | 0.04% |

**The as-shipped strategy holds nothing at all on TRAIN.** Its TRAIN backtest is a book of
zero names, 0.00% CAGR, 0.00 Sharpe, 0.00% MaxDD. It cannot be selected, and it is
reported here as the baseline it is. This is a genuine bug in `donchian_channel.py`, not a
tuning artefact.

**Disclosure of the one semantic change I made.** To have anything to test, I used the
textbook Donchian definition instead: the channel is the **prior** `p` bars with today
excluded, `close > max(high[t-p : t])`. That is the standard breakout, it is the only
change from the shipped code, and it is a change to the strategy's *meaning* — not a
parameter tweak. It is counted against the 5-variant budget below (V1 vs V2–V5) rather
than hidden.

---

## 2. Declared parameter budget — 5 variants, frozen before any backtest

Written to `research/agent_donchian/PARAMETER_BUDGET.md` before the first equity curve was
computed. **5 tested, 5 declared. Not exceeded.**

| # | Label | Semantics | Period |
|---|---|---|---|
| V1 | `literal_p20` | as shipped (window includes today) | 20 |
| V2 | `breakout_p20` | classic Donchian (prior *p* bars) | 20 |
| V3 | `breakout_p55` | classic Donchian | 55 |
| V4 | `breakout_p10` | classic Donchian | **10 ← selected** |
| V5 | `breakout_p100` | classic Donchian | 100 |

Held constant across all five and **not** tuned, so the entire budget is spent on the
channel period: ranking lookback **126d** trailing momentum (brief §5 form), monthly
rebalance, `PortfolioConfig()` defaults (22 / 12% / 25% / 10% cash / 35% turnover budget —
not bypassed), `CostModel(segment="delivery", slippage_bps=5)`, long-only.

**Selection rule, declared before the TRAIN numbers were seen: highest TRAIN Sharpe,
tie-break Calmar.** TRAIN 2016-01-01 → 2023-12-31:

| Label | CAGR | Sharpe | MaxDD | Calmar | Turn | Drag | N |
|---|---|---|---|---|---|---|---|
| `literal_p20` | 0.00% | 0.00 | 0.00% | 0.00 | 0.00x | 0.00% | 0.0 |
| `breakout_p20` | 6.47% | 0.03 | −8.01% | 0.81 | 3.16x | 0.85% | 9.0 |
| `breakout_p55` | 3.81% | −0.41 | −9.28% | 0.41 | 2.39x | 0.58% | 4.7 |
| **`breakout_p10`** | **9.45%** | **0.40** | **−8.35%** | **1.13** | 3.47x | 1.03% | 13.4 |
| `breakout_p100` | 3.31% | −0.55 | −8.56% | 0.39 | 2.02x | 0.49% | 3.0 |
| *ref: buy & hold* | 22.17% | 0.91 | −37.97% | 0.58 | — | — | 48 |
| *ref: composite* | 21.14% | 0.96 | −32.92% | 0.64 | 2.08x | 1.02% | 21.9 |

`breakout_p10` selected. **Every variant, including the winner, trailed buy-and-hold on
TRAIN by a wide margin** — the TRAIN result was already a warning.

**What TEST was touched before this run:** `recon.py` measured *signal liveness only*
(long/short/flat counts) on TEST. It computed **no return, equity curve or performance
metric on TEST**, and selected nothing. No TEST return was inspected before the single
post-selection run.

---

## 3. TEST — 2024-01-01 → 2026-10-01, the selected variant, unchanged

| Label | CAGR | Sharpe | MaxDD | Calmar | Turn/yr | Cost drag | Avg names |
|---|---|---|---|---|---|---|---|
| **`donchian breakout_p10`** | **2.05%** | **−0.43** | **−14.56%** | **0.14** | 3.11x | 0.76% | 9.9 |
| buy & hold (same window) | 8.16% | +0.18 | −15.91% | 0.51 | — | 0.22% one-off | 48 |
| `nsealgo` composite (same panel) | 1.99% | −0.31 | −14.94% | 0.13 | 2.43x | 0.57% | 22.5 |
| *gross, zero cost (diagnostic only)* | *2.75%* | *−0.35* | *−14.01%* | *0.20* | *3.11x* | *—* | *9.9* |

Total return 5.88% over 33 months. Annualised vol 8.94%. Costs paid ₹44,916 on ₹21,00,000.
Sharpe uses the 6.5% Indian T-bill proxy, so a *negative* Sharpe with positive CAGR means
"made money, but less than cash".

### vs buy-and-hold

| | strategy | buy & hold | delta |
|---|---|---|---|
| return | 2.05% | 8.16% | **−6.11pp/yr — worse** |
| drawdown | −14.56% | −15.91% | **+1.35pp — better** (smaller loss) |
| Sharpe | −0.43 | +0.18 | −0.61 |
| Calmar | 0.14 | 0.51 | −0.37 |

It buys slightly less drawdown for a large amount of return. That is the whole trade.

### vs the `nsealgo` composite

CAGR 2.05% vs 1.99% (**+0.06pp**, a tie) and Sharpe −0.43 vs −0.31 (worse). It does **not**
beat the composite. Both are weak in this window; neither is a reason to deploy.

### Cost drag (brief §6.4)

Gross +2.75% → net +2.05%, **0.70pp/yr**. Gross is positive *and* net is positive, so
costs are not what kills this — but they take a quarter of the edge, and gross is positive
only by 0.70pp in the first place. **Not a cost failure. A signal failure.**

### Calendar years

| Year | buy & hold | donchian | alpha |
|---|---|---|---|
| 2024 | +19.87% | +16.37% | −3.50% |
| 2025 | +13.34% | **−4.51%** | **−17.85%** |
| 2026 (to 10-01) | −8.26% | −4.72% | +3.54% |

Positive years **1/3 = 33%** (`GOAL.md` Gate 3 needs ≥60%). Years beating buy & hold: 1/3.

---

## 4. Negative control — random signal, same live fraction

Five fixed seeds (0–4), identical pipeline, identical cost model, random names flagged at
the strategy's own 8.80% live fraction.

| seed | CAGR | Sharpe | MaxDD | avg names |
|---|---|---|---|---|
| 0 | +3.46% | −0.56 | −6.70% | 5.9 |
| 1 | −5.91% | −2.26 | −16.85% | 5.0 |
| 2 | −0.39% | −1.41 | −7.48% | 4.3 |
| 3 | −2.73% | −1.86 | −10.48% | 5.2 |
| 4 | +0.17% | −1.40 | −6.98% | 3.9 |

- strategy **+2.05%** vs random mean **−1.08%** (range −5.91% .. +3.46%)
- beats random **mean**: **yes**
- beats **every** random seed: **no** — seed 0 got +3.46% by luck
- Sharpe: −0.43 vs random mean −1.50

So it clears the "not a coin flip" bar only on average, and the single best random seed
beat it. That is consistent with "weak and unstable", not "an edge".

**Caveat, disclosed not fixed:** the control matches the brief's requirement (same % of
bars long) but holds fewer names (4–6 vs 9.9). The real signal is autocorrelated — a name
that breaks out stays flagged several days — so out of the same live fraction it
accumulates a wider book. The control is therefore *harder* on return and *easier* on
diversification. Fixing the mismatch would mean adding a parameter, which the budget does
not allow.

---

## 5. Sanity checks (brief §6) — all run, all pass

1. **Plausibility** — CAGR 2.05%, nowhere near the 40–50% unlevered ceiling. No lookahead,
   no mis-indexed panel, no compounding bug.
2. **Weight count** — avg **9.9** names held (not 48; no residual accumulation). Max
   single-name weight **10.80%** ≤ 12% cap. Max sector weight **21.60%** ≤ 25% cap.
   Names held min/avg/max = 0 / 9.9 / 30 (`max_names=30`). 33 rebalances. Engine charged
   21.92bps round trip. Caps re-verified independently from the engine's own weight frame.
3. **Signal liveness** — long **8.80%**, short 7.86%, flat 83.35% on TEST. Above the 5%
   floor, so it is *not* the always-flat case. Shorts are discarded by `build_score`, so
   the book is long-only as required.
4. **Cost drag** — 0.76%/y, 3.11x turnover. Reported above.
5. **Negative control** — reported above.

### No-lookahead: proved, not asserted

A truncation test, not an argument: for 15 dates sampled across TEST, the signal and score
were rebuilt from a panel **truncated at t** and required to equal the vectorised value.

```
max |vectorised - truncated| = 0.000e+00
VERDICT: PASS - score at t depends only on data <= t
control: a deliberately leaked score differs by 0.941 (test can detect lookahead)
```

The second line matters: a test that always passes proves nothing, so a score with a
deliberate 5-day forward leak was run through the same comparison and it *does* differ.

### Data audit

`load_universe` cleaned 274,541 rows → 208,226 (dropped 66,312 pre-2008, 3 extreme,
excluded `adanient` + `jiofin`). Because `load_universe` returns only closes and this
strategy needs highs/lows, the OHLC panels were rebuilt with `load_symbol` (identical
C1–C6 rules) and then **asserted equal** to the mandated close panel. **Survivorship bias
is present** (today's NIFTY-50 backfilled) and applies to every number here.

---

## 6. Most likely reason it failed

**The signal is too sparse to fill the book, so the book is never built.**

`PortfolioConfig.n_positions=22` is a **maximum, not a target**. A 10-day breakout flags
only **4.22 of 48** names on a typical day (median 3). At a rebalance only those ~4 names
are eligible, and with `max_weight=12%` *k* names can never absorb more than *k* × 12% —
about **51%** — and the 25% sector cap clips that further when the flagged names cluster
(two banks cap at 24%). Measured result:

| Year | names flagged (mean) | names held (mean) | **% invested** |
|---|---|---|---|
| 2024 | 4.58 | 17.90 | 55.6% |
| 2025 | 4.29 | 3.55 | **24.3%** |
| 2026 | 3.67 | 7.92 | 32.7% |

Average investment over TEST: **37.8%**. Fully in cash on **86 of 685 days**.

So it missed the 2025 rally by **sitting in cash**, not by holding the wrong names. That
is structural under-deployment, not a wrong signal — and it explains why a *negative*
Sharpe coexists with positive CAGR: it earned 2% while holding a third of its capital.

Slower channels do **not** fix the sparsity — they make it worse, because a longer channel
is *harder* to break: long-fire rate falls monotonically with the period (p=10 → 8.46%,
p=20 → 6.23%, p=55 → 3.98%, p=100 → 3.15% of name-bars over the full panel). All of them
were rejected on TRAIN regardless. The sparsity is intrinsic to using a Donchian flag as a
hard eligibility filter on a 48-name universe.

**The one thing I would try next:** stop treating the breakout as an eligibility mask and
treat it as a **ranking input** — score every one of the 48 names by (position within its
own Donchian channel), hold all 22 unconditionally. That fills the book, keeps the
`GOAL.md` caps intact, and asks the real question the current design never asks: *is the
channel position of a name predictive, or only its being at the very top of it?* This
would be a new strategy, a fresh TRAIN/TEST split, and a new budget — not a re-tune of
this one.

**Second-order fix, cheaper:** the shipped `donchian_channel.py` is broken. `donchian_high`
/ `donchian_low` should exclude the current bar (`.shift(1)`) or the strategy is
permanently flat. That is worth fixing in the catalog regardless of the NSE result.

---

## 7. Files

| file | purpose |
|---|---|
| `PARAMETER_BUDGET.md` | the 5 variants + selection rule, frozen before any backtest |
| `common.py` | shared harness; OHLC loader, both signal semantics, score, controls |
| `recon.py` | panel audit + degeneracy proof + liveness by window |
| `run_train.py` | the 5 TRAIN variants, selects by the frozen rule → `train_results.json` |
| `run_test.py` | the single TEST run + benchmarks + controls → `test_results.json` |
| `verify.py` | truncation no-lookahead proof, constraint audit, diagnosis |

`.venv/bin/ruff check research/agent_donchian/` → **All checks passed.**
All four scripts re-run end-to-end and produce byte-identical output.