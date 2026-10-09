# Agent Report — `flag_pattern`

**Status: IN PROGRESS (header + budget committed before any run).**
Append-only. Nothing below the header existed when the budget was declared.

---

## 1. Assignment

| Field | Value |
|-------|-------|
| Assigned strategy | `flag_pattern` |
| Source | `src/cryptobot/strategies/catalog/flag_pattern.py` |
| Class | `FlagStrategy(SignalStrategy)`, `name = "flag"` |
| Docstring | `"""Flag breakout"""` |
| Mission | make one catalog strategy work on NSE NIFTY-50, honestly |

### 1.1 The shipped signal, verbatim

```python
def warmup(self, closes) -> int:
    return self.config.period

def signal(self, closes, highs, lows, volumes):
    if len(closes) < self.config.period + 2:
        return 0
    if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
        return 1
    if closes[-1] < closes[-2] and closes[-2] < closes[-3]:
        return -1
    return 0
```

### 1.2 Structural finding #1 — `config.period` is dead code

`FlagConfig.period` (default `5`) is referenced in exactly two places: `warmup()` and
the `len(closes) < period + 2` length gate. **The comparison logic itself is hardcoded
to a 3-bar window** (`[-1]`, `[-2]`, `[-3]`) and never reads `self.config.period`.

Consequence: the as-shipped strategy has **exactly one** possible signal — a 2-day
close-to-close momentum proxy — no matter what `period` is set to. The config knob is
decorative. This is a catalogue-quality bug, not a judgement call, and it means a
literal implementation would consume **0 of my 5-variant budget** (there is nothing to
vary). To spend the budget honestly on the strategy's *intended* meaning ("flag
breakout") I declare the 5 variants below explicitly, and I keep the literal signal as
V0 so the shipped code is measured on its own terms.

### 1.3 Structural finding #2 — no flag is in the code at all

The name promises a *flag*: a strong directional pole, a tight sideways consolidation,
then a breakout through the consolidation high. The code contains none of those
ingredients — no pole, no consolidation window, no range/volatility test, no breakout
level. It is a 2-day up-tick. So "make the strategy work on NSE" necessarily means
*reconstructing* the pattern the name describes. That reconstruction is disclosed as a
change to signal semantics (brief §5 permits it; the donchian agent did the same and
disclosed it).

### 1.4 Structural finding #3 — the short side is not expressible

`signal` returns `-1` on two down days. An Indian delivery account cannot short, and
`PortfolioConfig`/`run_backtest` are long-only. So `-1` is treated throughout as **not
long** (the name is dropped from the candidate set). This is a real constraint, not a
convenience: the shipped strategy's half of its logic is structurally unavailable here.

---

## 2. Data used

| Item | Value |
|------|-------|
| Loader (mandated) | `nsealgo.data.loader.load_universe("data/nse")` |
| Timeframe | **1d only** — this is a daily-bar, short-horizon indicator |
| Panel span | 2002-07-01 → 2026-10-01 (~24y, ~50 names) |
| Intraday | **not used.** 5m/15m are ~7 weeks and 1m/30m do not exist. A 2-day up-tick is a 1d pattern; there is no honest intraday validation available. |
| Survivorship | **PRESENT** — today's NIFTY-50 backfilled. Disclosed in every result. |
| Data end | **2026-10-01.** Every number in this report is valid only at this end date. |

## 3. Protocol (brief §4) — non-negotiable

| Set | Window | Purpose |
|-----|--------|---------|
| TRAIN | 2016-01-01 → 2023-12-31 | the only set any parameter is chosen on |
| TEST | 2024-01-01 → 2026-10-01 | evaluated **once**, at the end, unchanged |

Costs: `CostModel(segment="delivery", slippage_bps=5)`.
- `round_trip_bps(100_000)` = 11.92 bps (statutory only)
- `all_in_round_trip_bps(100_000)` = 21.92 bps — **this is what `run_backtest` charges**
  (`rt_bps + 2 × slippage_bps`, because a portfolio simulator never calls `fill_price`).

> **All strategy results in this report are net of 21.92 bps per unit of one-way
> turnover.** Buy-and-hold pays one round trip only, charged once on day 1 — the
> generous reading for the benchmark.

Portfolio constraints: `PortfolioConfig()` default — 22 names, 12% single-name cap,
25% sector cap, 10% cash buffer, 35% turnover budget. Not bypassed.

---

## 4. DECLARED PARAMETER BUDGET — 5 variants, fixed before any run

Declared at time of writing, before any script executed. **TRAIN-only selection.**

| # | Name | Signal (long iff) | Knobs varied |
|---|------|-------------------|--------------|
| **V0** | `LITERAL` | `c_t > c_{t-1} > c_{t-2}` (exactly as shipped) | none — the shipped code |
| **V1** | `RUN3` | 3 consecutive higher closes | run length 2 → 3 |
| **V2** | `RUN5` | 5 consecutive higher closes | run length 2 → 5 |
| **V3** | `FLAG_5` | pole ≥ +10% over 20d **and** last 5d range ≤ 3% **and** `close > max(high, prior 5d)` | pole len/thr, consol len/width |
| **V4** | `FLAG_10` | pole ≥ +10% over 20d **and** last 10d range ≤ 5% **and** `close > max(high, prior 10d)` | consolidation widened |

Rationale for the shape of the budget:
- V0 is mandatory (measure the shipped thing).
- V1/V2 spend 2 variants on the *only* knob the shipped code exposes in spirit (the run
  length), bracketing it at 3 and 5. A longer run of consecutive up-days is a noisier
  but more selective continuation signal.
- V3/V4 spend 2 variants on reconstructing the pattern the strategy is *named after*.
  Longer continuation runs are the most plausible fix for a signal that fires on ~25% of
  bars; a real flag is the only interpretation of the name worth testing.
- Ranking lookback is held fixed at **126d (6-month) momentum** for all 5 variants — the
  brief's recommended construction — so the entire budget is spent on the signal itself.
- Rebalance fixed at **monthly** (`rebalance="M"`), the engine's documented default and
  the cheapest turnover.

**Rules I am holding myself to:**
1. No variant is added, dropped or re-parameterised after seeing TRAIN results. If a
   variant is abandoned, that is recorded here as an abandoned budget slot.
2. If the selection between variants is decided by anything other than TRAIN metrics,
   that is disclosed as a broken protocol.
3. TEST is opened exactly once, for the single TRAIN-selected variant.
4. If I exceed 5 variants I will say so in §9 rather than hide it.

---

## 5. Results

*(appended below as runs complete)*
### 5.0 Data audit (brief §2 mandatory step)

`load_universe("data/nse")` → 4,629 bars × **48** symbols, index **tz-aware
Asia/Kolkata**, 2008-01-01 → 2026-10-01 (the brief's "2002-07-01" start is not
actually present — `load_universe` drops pre-2008 vendor artifacts, so **real usable
history is 2008→, ~18.7y**). 6.29% NaN (late listings + panel gaps).

```
rows in            : 274,541      dropped pre-2008   : 66,312
rows out           : 208,226      dropped extreme    : 3
excluded symbols   : ['adanient', 'jiofin']
```

| Audit | Result |
|-------|--------|
| Names/day (TRAIN) | min 44, median 46 |
| Names/day (TEST) | min 47, median 48 |
| Late joiners (start after 2016-01-01) | `sbilife` 2017-10-03, `hdfclife` 2017-11-17, `maxhealth` 2020-08-21, `eternal` 2021-07-23 |
| TRAIN bars / TEST bars | 1,975 / 685 |
| OHLC invariants on raw CSVs (TRAIN+TEST, 127,704 bar-cells) | **0 violations** of `low≤open`, `low≤close`, `low≤high`, `open≤high`, `close≤high`, all prices > 0 |
| `(high−close)/close` | median 1.10%, p99 7.09% — a normal intraday profile |
| `high == close` exactly | 1,300 bars (0.62%) — rounding-level ties |

**Data verdict: clean.** Note the `adanient`/`jiofin` exclusions mean the "50 NIFTY-50"
panel is 48 names; the book is therefore 22 of 48, not 22 of 50.

#### Two audit bugs of my own, recorded because the brief asks for them

1. My first integrity check asserted `close >= high`. That is **backwards** — the close
   is normally *below* the session high, so it flagged 100% of bars as violations. The
   real invariant is `close <= high`, which holds on 208,224/208,226 bars (the 2
   "violations" are `high == close` down to 1.1e-16, i.e. float noise).
2. My second check asserted `open <= close`. That is **not an OHLC invariant either** —
   it fails on every down day, which is why it "found" 66k violations on 127,704 cells
   (53.2% ≈ the down-day frequency).

Both were my harness's errors, not data errors. Recorded because an agent that reports
"66,117 OHLC violations" without checking the direction of its own inequality would have
filed a fake bug against `src/nsealgo/data/loader.py`.

### 5.1 Signal equivalence check (done before any backtest)

`literal_signal()` was verified **bar-for-bar against the shipped
`FlagStrategy.signal()`** on 16,000 synthetic bars (40 names × 400 bars), calling the
catalog code one bar at a time.

| Check | Result |
|-------|--------|
| Comparable bars | 16,000 |
| Disagreements | 76 — **all in bars t=2..5** |
| Disagreements at/after the catalog's own warmup gate (t≥7) | **0** |

The 76 are pure warmup: the shipped `len(closes) < period + 2` gate forces `0` for the
first `period`=5 bars, my vectorised version is free from bar 2. **Signal logic is
identical.** This is the dead-`period` artifact observed from a third angle.

Catalog signal liveness on random data: 24.1% long / 24.6% short / 51.3% flat — so the
shipped signal is *not* dead, it is roughly a coin-weighted up/down tick.

One real trap caught here: "2 consecutive up days" must be implemented as the **chain**
`c_t > c_{t-1} > c_{t-2}`. The looser `(c_t > c_{t-1}) & (c_t > c_{t-2})` is a different,
much loosier condition — it fires on closes `10, 9, 11`, which the shipped code rejects.
Had I used the loose form, V0 would have been a different strategy from the one I was
supposed to measure.

### 5.2 TRAIN results — 2016-01-01 → 2023-12-29, 1,975 bars, net of 21.92 bps

```
  Label                      CAGR   Sharpe    MaxDD  Calmar    Turn    Drag      N
  --------------------------------------------------------------------------------
  V0_LITERAL               14.75%     0.78  -14.19%    1.04   3.75x   1.40%   25.1
  V1_RUN3                   9.11%     0.33  -13.81%    0.66   3.46x   1.12%   16.8
  V2_RUN5                   3.99%    -0.47   -9.70%    0.41   1.85x   0.48%    2.3
  V3_FLAG5                 -0.10%    -9.24   -2.26%   -0.04   0.08x   0.02%    0.1
  V4_FLAG10                 0.24%    -6.24   -1.72%    0.14   0.19x   0.04%    0.1
  BH_equalwt               22.17%     0.91  -37.97%    0.58   0.00x   0.00%   48.0
  composite                21.14%     0.96  -32.92%    0.64   2.08x   1.02%   21.9
  rand_ITERAL              14.76%     0.81  -11.60%    1.27   3.73x   1.36%    nan
  rand_FLAG5               -0.07%   -11.79   -1.72%   -0.04   0.04x   0.01%    nan
```

Signal liveness on TRAIN:

```
  variant         frac long  frac short  names flagged
  V0_LITERAL        25.69%      23.24%           11.9
  V1_RUN3           12.66%      10.84%            5.9
  V2_RUN5            3.08%       2.28%            1.4
  V3_FLAG5           0.11%       0.00%            0.1
  V4_FLAG10          0.11%       0.00%            0.1
```

**Selection (TRAIN only): `V0_LITERAL`, Sharpe 0.78 — the highest of the five.** The
shipped signal wins. Its two near-neighbours in the budget (V1, V2) are monotonically
worse, so there is no run-length improvement to be had.

#### 5.2.1 Three TRAIN findings that already matter

**(a) V3/V4 — the reconstructed "real flag" — are functionally dead.** They flag a name
on **0.11% of bars**, ~0.1 names per day, and the book averages **0.1 names**. A flag
needs a 20-day pole ≥ +10%, a 5-day range ≤ 3%, *and* a breakout through the prior 5-day
high, simultaneously, on a daily NIFTY-50 name. That conjunction almost never happens.
Their Sharpe of −9.24 is an artifact of a near-zero-variance, near-zero-return series
(2.3% MaxDD over 8 years is 6.6%/yr) — it is not a risk-adjusted failure, it is
"never trades". Per brief §6.3 these are effectively always-flat and any comparison is
meaningless. **My reconstructed flag pattern is the one variant family that is
categorically unusable on daily NSE data as specified.**

> Protocol note: I printed a 5%-liveness eligibility floor but did not actually enforce
> it in the selection code (the condition was a no-op). It did not change the outcome —
> V0 has the top TRAIN Sharpe either way — but the floor should have been real.

**(b) The negative control ties the real signal.** A *random* flag with the same
long-fraction scores **14.76% CAGR / Sharpe 0.81** (seed 0), versus the real signal's
**14.75% / 0.78**. Across 5 seeds random CAGR is `[14.76, 14.59, 13.87, 10.71, 12.57]`,
mean 13.30%. **The real signal is inside the random distribution and does not beat it.**
On TRAIN, `V0`'s flag carries essentially zero information.

**(c) Why the flag barely matters: the book is mostly not the flag.** V0 flags ~11.9 of
48 names per day but the book holds **25.1 names**. The turnover budget
(`apply_turnover_budget`) blends toward a new target rather than replacing it, so dropped
names decay instead of exiting, and the book accretes up to `max_names=30`. Most of the
capital is therefore riding 126d momentum plus drift, with the flag acting only as a
weak screen. That is why V0, V1, V2 — signals with wildly different liveness (25.7% vs
3.1%) — all land in the same 4–15% CAGR band.

**(d) On TRAIN, V0 loses to both benchmarks on return.** BH 22.17% vs V0 14.75%;
composite 21.14% vs V0 14.75%. V0 does win on **drawdown** (−14.19% vs BH −37.97%), and
its Calmar 1.04 beats BH 0.58 and composite 0.64. So on TRAIN this is a
lower-return/lower-drawdown trade, not an alpha source.

---

## 6. TEST — 2024-01-01 → 2026-10-01, 685 bars, 48 names, **net of 21.92 bps**

Opened once, for `V0_LITERAL` only, loaded from `winner.json`. Not one TEST number was
used to choose anything.

```
  Label                      CAGR   Sharpe    MaxDD  Calmar    Turn    Drag      N
  --------------------------------------------------------------------------------
  V0_LITERAL                0.73%    -0.76  -11.71%    0.06   3.05x   0.67%   19.0
  BH_equalwt                8.16%     0.18  -15.91%    0.51   0.00x   0.00%   48.0
  composite                 1.99%    -0.31  -14.94%    0.13   2.43x   0.57%   22.5
```

Signal liveness on TEST: **23.99%** of bars long, 23.70% short, 11.5 names flagged/day.
Average names held: **19.0** (target ~22 — no weight accumulation).

Yearly returns (TEST):

| Year | V0_LITERAL | BH_equalwt | composite |
|------|-----------|------------|-----------|
| 2024 | −1.25% | +19.87% | +8.47% |
| 2025 | +5.33% | +13.34% | +7.10% |
| 2026 (to 01 Oct) | −1.87% | −8.26% | −9.01% |

**Positive in 1 of 3 calendar years** — GOAL.md §5 Gate 3 wants ≥60%. Fails.

### 6.1 Test-vs-train collapse

| | TRAIN | TEST |
|---|---|---|
| CAGR | 14.75% | **0.73%** |
| Sharpe | +0.78 | **−0.76** |

A 14pp/yr collapse and a sign flip on Sharpe. The TRAIN number was never an edge to
begin with (see §7) — but this is what the honest out-of-sample number looks like.

### 6.2 Test vs buy-and-hold — the brief's required comparison

| | V0_LITERAL | BH_equalwt | verdict |
|---|---|---|---|
| CAGR | 0.73% | 8.16% | **WORSE by 7.43pp/yr** |
| Total return | +2.07% | +24.64% | **WORSE** |
| Sharpe | −0.76 | +0.18 | **WORSE** |
| Calmar | 0.06 | 0.51 | **WORSE** |
| MaxDD | −11.71% | −15.91% | **BETTER by 4.20pp** |
| Turnover | 3.05x/yr | 0.00x | 3x the churn for 1/11th the return |

It loses badly on return and wins only on drawdown — and pays 0.67%/yr of cost drag plus
3.05x turnover to buy that.

### 6.3 Random-signal negative control (TEST)

Random names, identical long-fraction (23.99%), 5 seeds:

```
  rand_seed0  -0.38% / Sharpe -0.93 / MaxDD -12.01%
  rand_seed1  -0.07% / Sharpe -0.98 / MaxDD -11.05%
  rand_seed2  +1.70% / Sharpe -0.62 / MaxDD -11.67%
  rand_seed3  +3.81% / Sharpe -0.36 / MaxDD  -7.58%
  rand_seed4  +3.12% / Sharpe -0.44 / MaxDD  -9.46%
  random CAGR : mean +1.64%   min -0.38%   max +3.81%
  real   CAGR : +0.73%     real Sharpe -0.76   random Sharpe mean -0.66
```

**The real signal is WORSE than a coin flip on TEST**, and well inside the random range
(3 of 5 random seeds beat it). It does not beat the minimum bar. This is the single
clearest finding in the run.

### 6.4 Cost drag

| | Value |
|---|---|
| Gross CAGR (0 bps) | 1.41% |
| Net CAGR (21.92 bps) | 0.73% |
| Cost-induced CAGR | 0.68pp/yr (turnover 3.05x) |

Costs halve the return but are **not** the reason this fails: gross is only +1.41%, and
a gross +1.41% book with 23.99% liveness is not an edge either. Removing costs would not
rescue this strategy, so no cost-reduction is proposed (brief §6 forbids that move).

### 6.5 Did it beat the nsealgo composite?

**No.** Composite 1.99% CAGR / Sharpe −0.31 / MaxDD −14.94% vs V0's 0.73% / −0.76 /
−11.71%. The composite beats it on return *and* on Sharpe. It wins only on drawdown,
again by trading beta for it.

---

## 7. Diagnosis — why it fails

### 7.1 The signal has no information about forward returns (decisive)

Event study on the shipped signal, pooled across all 48 names, equal-weighted, **no
costs, no portfolio** — so this is the pure signal, uncontaminated by construction:

```
  set     h(days)    n_flag    flagged  unflagged    spread   t-stat
  ------------------------------------------------------------------
  TRAIN         1     23504     0.08%      0.09%    -0.01%    -0.58
  TRAIN         5     23504     0.40%      0.46%    -0.06%    -1.75
  TRAIN        21     23504     1.99%      1.92%     0.07%     1.02
  TRAIN        63     23504     5.99%      6.05%    -0.06%    -0.48
  TEST          1      7882     0.04%      0.04%     0.00%     0.20
  TEST          5      7874     0.13%      0.21%    -0.08%    -1.69
  TEST         21      7771     0.81%      0.87%    -0.07%    -0.72
  TEST         63      7351     2.41%      2.67%    -0.26%    -1.51
```

**Every single spread is under 0.3pp, and 6 of 8 have |t| < 1.8 with the *negative*
sign — i.e. flagged names did very slightly WORSE than unflagged ones.** The largest
t-stat in the table is −1.75, and it is on the wrong side. At 21-day horizon the TRAIN
spread is +0.07% (t=1.02) — economically nothing on a 48-name book.

A signal with no measurable forward-return information cannot produce an edge under any
portfolio construction. That is the root cause; the benchmark losses are the symptom.

### 7.2 The information is not merely absent, it is unstable in sign

| Period | 21d spread | t |
|---|---|---|
| TRAIN 2016-2019 | **−0.36%** | −4.18 |
| TRAIN 2020-2023 | **+0.40%** | +3.89 |
| TEST 2024-2026 | −0.07% | −0.72 |

Both TRAIN halves are individually "significant" at |t| ≈ 4, in **opposite directions**.
That is not a decaying edge; that is a coin being read twice. This is precisely the
pattern that produces a handsome in-sample Sharpe (V0's +0.78 on TRAIN) and nothing at
all out of sample.

### 7.3 Ablation — the flag is not what is being traded

TEST window, three constructions:

| Construction | CAGR | Sharpe | MaxDD | N |
|---|---|---|---|---|
| A: signal + 126d-momentum rank (**the shipped construction**) | 0.73% | −0.76 | −11.71% | 19.0 |
| B: 126d momentum only, **flag removed** | 2.60% | −0.22 | −16.86% | 21.3 |
| C: flag only, no momentum rank | 6.35% | +0.05 | −15.61% | 25.4 |

Adding the flag to momentum makes things *worse* (B 2.60% → A 0.73%), while the flag
alone beats momentum alone (C 6.35% > B 2.60%). Combining two weak things is worse than
either — an interaction effect, which is what noise does. None of A/B/C reaches
buy-and-hold's 8.16%.

### 7.4 Mechanism: only ~27% of the book is the strategy's own idea

| Set | names flagged | book holds | deployed weight in a *currently* flagged name |
|---|---|---|---|
| TRAIN | 11.9 / 48 | 25.1 | **27.8%** |
| TEST | 11.5 / 48 | 19.0 | **27.0%** |

The signal flags ~12 of 48 names on any day, but ~73% of deployed capital sits in names
the flag is **not** currently flagging. Cause: `apply_turnover_budget` blends toward each
new target (`cur + λ(tgt−cur)`) instead of replacing the book, so abandoned names decay
over months rather than exiting, and the book accretes toward `max_names=30`. This
engine behaviour is *correct and deliberate* (it is what makes the 35% turnover budget
realistic) but it means a sparse time-series flag has very little control over what is
actually held. That explains why V0/V1/V2 — with wildly different liveness (25.7% /
12.7% / 3.1%) — all landed in the same 4–15% CAGR band: they were all mostly trading
126d momentum plus drift.

**This is a harness-level finding worth carrying to other agents:** any catalog strategy
that flags only a few names will underperform its own signal, and variants of different
liveness will be hard to tell apart. Compare signals on the event study first; the
backtest is not a sensitive instrument for sparse signals.

### 7.5 Why the "real flag" reconstruction (V3/V4) was unfixable

V3/V4 require, simultaneously on the same bar: a 20-day pole ≥ +10%, a 5-day range
≤ 3%, and a close above the prior 5-day high. That fired on **0.11% of bars / 0.1 names
per day** — a book of 0.1 names. On daily NIFTY-50 bars a genuine flag-and-breakout
setup is a rare multi-week event, not a daily signal; and a ₹21L book cannot be
meaningfully run from ~0.1 candidates. Both V3/V4 slots were spent, both dead. I am not
re-allocating them, per the budget rule.

---

## 8. Verification performed (all passed)

| Check | Result |
|---|---|
| **Signal equivalence** | `literal_signal()` == shipped `FlagStrategy.signal()` on all 16,000 comparable bars (76 diffs are warmup-only, 0 beyond the catalog's own gate) |
| **No lookahead** | Truncating the panel at 2018-06-30 / 2021-03-31 / 2024-12-31 / 2026-01-31 leaves every signal and score value on or before the cut **bit-identical** |
| **Engine lag** | `run_backtest` credits weights from t+1 (`held.shift(1) * rets`) — confirmed in source |
| **Cost figure** | `round_trip_bps` = 11.92, `all_in_round_trip_bps` = 21.92, engine `diag['round_trip_bps']` = **21.92**. All reported numbers are net of 21.92. |
| **Drag reconciles** | 3.05x × 21.92 bps = 0.67%/yr = reported drag |
| **Constraints** | max single name 10.80% (cap 12%), max total 82.83% (cap 90%), max names 30 (cap 30), min weight 0.000 → long-only enforced, no shorts expressible |
| **Plausibility** | CAGR 0.73% — far below the 40–50% ceiling; no compounding/lookahead bug |
| **Determinism** | Re-running TEST reproduces CAGR 0.0073108178 / Sharpe −0.7623451599 exactly |
| **Lint** | `ruff check research/agent_flag_pattern/` — all checks passed; all 4 scripts exit 0 |
| **src/ untouched** | No file under `src/nsealgo/`, `src/cryptobot/` or any test was modified. Nothing committed. |

---

## 9. Protocol compliance

| Rule | Status |
|---|---|
| Parameters chosen on TRAIN only | ✅ selection used TRAIN Sharpe alone |
| TEST evaluated once, unchanged | ✅ `s2_test.py` reads `winner.json`, selects nothing |
| Parameter budget ≤ 5 variants | ✅ **exactly 5 run**: V0_LITERAL, V1_RUN3, V2_RUN5, V3_FLAG5, V4_FLAG10. No 6th. No variant re-parameterised after seeing results. |
| Budget declared before running | ✅ §4 of this report, written before any script executed |
| Buy-and-hold over identical window | ✅ §6.2 |
| Random negative control | ✅ §6.3 — and it failed to be beaten |
| Composite comparison | ✅ §6.5 |
| Costs net of 21.92 bps | ✅ §8 |
| No lookahead | ✅ proven by truncation test |
| Lint | ✅ clean |
| No commit | ✅ nothing committed |

**Self-disclosed deviations** (neither changed the outcome):
1. The 5%-liveness eligibility floor I described in the selection code was printed but
   not actually enforced (the filter condition was a no-op). It did not matter: V0 has
   the highest TRAIN Sharpe whether or not V3/V4 are excluded.
2. `s2_test.py` was executed twice — the first run crashed on a pandas-3 API change
   (`DataFrame.applymap` removed) *after* all metrics were computed. The re-run is
   deterministic and produced identical numbers (verified in §8). No TEST number
   changed between the two executions and nothing was selected on TEST.

---

## 10. VERDICT

**No. `flag_pattern` does not make money on NSE NIFTY-50.**

Out-of-sample it earns **+0.73% CAGR / Sharpe −0.76** against buy-and-hold's
**+8.16% / +0.18**, and it **loses to a random coin flip** with the same fraction of
bars long (random mean +1.64%, real +0.73%). The underlying signal shows **no
measurable information about forward returns** in either TRAIN or TEST (all 8 event-study
spreads < 0.3pp, mostly negative, |t| < 1.8), and its apparent TRAIN edge flips sign
between sub-periods (−0.36% then +0.40%, both at |t| ≈ 4). It beats nothing: not
buy-and-hold, not the nsealgo composite, not a coin.

Its one redeeming property is drawdown (−11.71% vs −15.91%), and it pays 3.05x turnover
and 0.67%/yr of cost for it. That is a lower-beta artefact of the turnover budget, not
alpha.

### 10.1 Most likely reason

The strategy is **not a flag pattern at all** — it is a 2-day up-tick with a decorative
`period` parameter, and on daily bars a 2-day up-tick is a coin flip: equity drift
over 1–3 days is dominated by noise, giving an expected forward spread indistinguishable
from zero and empirically slightly *negative*. `flag_pattern` belongs in the "dead
catalogue code" bucket alongside the other strategies whose config knob is never read:
it looks like a breakout strategy but is a momentum stub, and the momentum it does have
is already fully present (and better) in the nsealgo composite.

### 10.2 The one thing I would try next

**Stop trying to fix this signal and fix the measurement instead: validate any new
catalog strategy with the event study (§7.1) *before* spending a backtest on it.** It is
costless, it needs no portfolio machinery, and it would have rejected `flag_pattern` in
seconds instead of 8 years of TRAIN Sharpe. If `flag_pattern` itself is to be revived,
the only version worth a run is the one that needs **no daily-bar confirmation at all** —
a genuine pole-then-consolidation pattern has to be measured on a lower frequency
(weekly bars, or a 20–40 day holding period with a much looser confirmation window),
because the daily-bar conjunction is arithmetically incapable of firing often enough to
fill a 22-name book. I would not spend any of my remaining budget on it.

---

*Agent: `flag_pattern`. Data end **2026-10-01** (survivorship bias present — today's
NIFTY-50 backfilled; `adanient`/`jiofin` excluded, so the universe is 48 names).
All results net of the full Indian delivery cost stack at 21.92 bps.
Scripts: `research/agent_flag_pattern/s0_audit.py`, `s0b_ohlc_integrity.py`,
`s0c_signal_equiv.py`, `s1_train.py`, `s2_test.py`, `s3_diagnose.py`, `s4_verify.py`,
plus `common.py`. Nothing committed.*

---

## 11. Data caveat found while auditing (does NOT affect any number above)

`data/nse/*_1d.csv` has **`high == open` exactly on 6.68% of bars** (8,531 / 127,704 in
TRAIN+TEST; `high == close` on only 0.39%). In a real market `high == open` should be a
rarity well under 1%. Concentrated in IT/pharma names (infy 228, drreddy 218, trent 218,
wipro 218, nestleind 215).

| | count | share |
|---|---|---|
| `high == open` exactly | 8,531 | **6.68%** |
| `high == close` exactly | 503 | 0.39% |

All three largest intraday ranges in TEST land on **2024-06-04** (Indian general
election results day — a real −20% index day: adaniports −19.8%, bel −18.1%,
ongc −17.1%, and `high == open` on all three), which confirms the *closes* are genuine.
But it also shows the `high` column degrades on exactly the violent bars.

**Impact on this run: none.** `V0_LITERAL` — the TRAIN-selected winner and every number
in §6 — reads **closes only**. The flag reconstructed from `high` enters only at V3/V4,
which were already dead on liveness grounds, so the caveat cannot change any conclusion.

**This is a cross-agent warning, not just a footnote.** Any other strategy in this
project whose breakout level is built from `high` (donchian, atr_breakout, squeeze,
triangle, rectangle, nr4, inside-bar, price_channel, resistance, open_range) is reading a
column that is wrong on ~7% of bars and specifically wrong on the largest moves — the
moves a breakout rule exists to catch. If the same vendor quirk suppresses the very
signal, those results are biased toward "no edge" for a reason that has nothing to do
with the strategy. Worth one shared check before any breakout result is trusted.

## 12. Final pipeline state

All scripts in `research/agent_flag_pattern/` exit 0 and `ruff check` passes:

| Script | Purpose |
|---|---|
| `common.py` | harness (signals, score, backtest, BH, controls, tables) |
| `s0_audit.py` | mandated `load_universe` audit + OHLC rebuild |
| `s0b_ohlc_integrity.py` | OHLC invariant audit + the `high==open` finding |
| `s0c_signal_equiv.py` | bar-for-bar equivalence vs the shipped `FlagStrategy.signal` |
| `s1_train.py` | **TRAIN-only**: runs the 5 declared variants, picks the winner |
| `s2_test.py` | **the single TEST run** of the TRAIN winner + all benchmarks |
| `s3_diagnose.py` | event study, ablation, mechanism — selects nothing |
| `s4_verify.py` | no-lookahead proof, cost confirmation, constraint + determinism checks |
| `*.json` | `train_results.json`, `winner.json`, `test_results.json` |
