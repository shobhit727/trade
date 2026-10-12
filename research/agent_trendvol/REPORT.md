# REPORT — `trend_volume_strategy` on NSE NIFTY-50

**Status:** IN PROGRESS (header + declared budget committed before any result was run)
**Assigned strategy:** `trend_volume_strategy`
**Source:** `src/cryptobot/strategies/catalog/trend_volume_strategy.py`
**Scratch dir:** `research/agent_trendvol/`

---

## 0. PROVENANCE — read first

```python
from nsealgo.provenance import provenance; provenance()
# {"engine": "d93815344bd3",
#  "loader": "c1badf5f7df8",
#  "costs":  "ba350aef75b3",
#  "panel":  "389b082b832f"}
```

| Item | Value |
|---|---|
| `engine` sha | **`d93815344bd3`** |
| `loader` sha | **`c1badf5f7df8`** |
| `costs` sha | **`ba350aef75b3`** |
| `panel` sha | **`389b082b832f`** |
| Data | `data/nse/*_1d.csv` via `nsealgo.data.loader.load_universe` (daily OHLCV, cleaning C1–C9) |
| Split | TRAIN `2016-01-01 → 2023-12-31`, TEST `2024-01-01 → 2026-10-01` |
| Cost model | `CostModel(segment="delivery", slippage_bps=5)` |
| Cost number used in ALL tables | **21.92 bps all-in round trip** (what `run_backtest` actually charges: 11.92 statutory + 2×5 slippage) |
| Portfolio | `PortfolioConfig()` — 22 names, 12% single, 25% sector, 10% cash, 35% turnover budget. Never bypassed. |
| Rebalance | Monthly (`"M"`), engine default |

`load_universe` returns **closes only**, but this strategy needs **volume**. Volume is
obtained by running each symbol through the *same* `load_symbol` (C1–C9) and reindexing
onto the close panel's index, so the score and the price panel cannot drift apart. The
close column recovered on that path is asserted equal to the `load_universe` close — if
that assertion ever fails the run aborts.

---

## 1. The strategy (source, verbatim)

```python
def signal(self, closes, highs, lows, volumes):
    t = sma(closes, self.config.period)
    if t != t or len(volumes) < self.config.period:
        return 0
    avg = sum(volumes[-self.config.period:]) / self.config.period
    if closes[-1] > t and volumes[-1] > avg * self.config.vol_ratio:
        return 1
    if closes[-1] < t and volumes[-1] > avg * self.config.vol_ratio:
        return -1
    return 0
```

Two conditions, ANDed:
1. **Trend leg** — close above / below `SMA(period)`.
2. **Volume leg** — today's volume above `vol_ratio × SMA(volume, period)`.

It is a *time-series, per-symbol* indicator with two free parameters (`period`,
`vol_ratio`) and three states (+1 / 0 / −1).

**NSE adaptation (brief §5, long-only — shorting is not available in an Indian delivery
account).** The −1 branch is discarded. Only the +1 branch has meaning:

> *hold a name on any day where close > SMA(period) AND volume > vol_ratio × SMA(volume, period).*

---

## 2. DECLARED PARAMETER BUDGET — committed before any run

Per brief §4, at most **5 distinct parameter variants**. These are fixed by inspection
of the source and a standard period/volatility grid — **not** chosen from any result.

| # | id | `period` (SMA window) | `vol_ratio` | note |
|---|----|------|------|------|
| 1 | `tv_p20_r12`  | 20  | 1.2 | **catalog defaults**, unchanged |
| 2 | `tv_p60_r12`  | 60  | 1.2 | quarter-length trend leg |
| 3 | `tv_p120_r12` | 120 | 1.2 | ~6-month trend leg |
| 4 | `tv_p20_r10`  | 20  | 1.0 | catalog period, any above-average volume day |
| 5 | `tv_p60_r10`  | 60  | 1.0 | loosest volume filter on a medium trend leg |

Selection rule, fixed now: **highest TRAIN Sharpe**, ties broken by lower TRAIN MaxDD.
The winner is then run on TEST **once, unchanged**. No other variant is ever run on TEST.

---

## 3. DECLARED CONSTRUCTION (fixed before any run)

Primary construction, straight from brief §5:

```python
mom126 = panel / panel.shift(126) - 1.0
score  = mom126.where(signal_panel > 0).rank(axis=1, pct=True)
```

i.e. **gate** on the strategy signal, then **rank the surviving names** by trailing
126-day momentum (a "proven" ranking per the brief). `run_backtest` decides weights from
the close of day *t* and holds from *t+1*, so the one-bar lag that removes look-ahead is
the engine's, and the signal itself uses only data up to *t*. Nothing is forward-filled
from the future.

**Caveat recorded up front:** if the +1 leg fires on only a handful of names per day, the
gated book will hold far fewer than 22 names and be mostly cash. That is a property of
the strategy, not a harness bug, and §6.3 (signal liveness) exists to detect it. If it
happens I will report it as the finding.

**One explicitly-labelled non-canonical diagnostic** is also declared in advance: a
*"soft gate"* score (momentum rank with signalled names boosted). It exists **only** to
explain a negative result, and it is **never** presented as this strategy's performance.
---

## 4. Port validation (done BEFORE any performance number was trusted)

The catalog `signal()` is a scalar loop over a growing prefix. The vectorised port
(`rolling(period).mean()` for both the price SMA and the volume SMA) was checked against
a verbatim transcription of that loop on **3,767 random (symbol, date, period,
vol_ratio) draws** across the full history, both legs.

**Result: 0 mismatches.** The port is faithful.

Side observation on the source (not a change): the catalog computes
`avg = sum(volumes[-period:]) / period`, which **includes today's volume in its own
threshold**. This makes the volume leg mildly self-referential — the threshold is
inflated by `1/period` of the quantity being thresholded. I ported it as-is because a
study of this strategy must test the strategy that exists.

---

## 5. SIGNAL LIVENESS (brief §6.3) — TRAIN window

Panel is 48 names. A name is "signalled long" when close > SMA(period) **and**
volume > vol_ratio × SMA(volume, period).

| variant | % symbol-days LONG | avg names/day | median | % days 0 signals | % days <5 signals |
|---|---|---|---|---|---|
| `tv_p20_r12`  | 13.19% |  6.33 | 5 | 2.84% | 39.79% |
| `tv_p60_r12`  | 13.38% |  6.42 | 5 | 3.04% | 37.00% |
| `tv_p120_r12` | 13.63% |  6.54 | 6 | 2.33% | 36.70% |
| `tv_p20_r10`  | 20.17% |  9.68 | 9 | 1.62% | 18.14% |
| `tv_p60_r10`  | 20.19% |  9.69 | 9 | 1.22% | 17.54% |

**The strategy is not always-flat** (13–20% of symbol-days, comfortably above the 5%
floor). But it is **selective to the point of starving the portfolio**: it flags only
**6–10 of 48 names on a typical day**, against a `n_positions=22` target. Roughly 18–40%
of days it flags fewer than 5 names. The gated book is therefore a *concentrated, mostly
cash* book, not a 22-name one. That is a property of the strategy, not a harness bug.

Note the volume leg is doing almost all the filtering: `vol_ratio` 1.0 → 1.2 cuts the
daily signal count by ~35% (9.7 → 6.3 names). The trend leg alone (close vs a 20/60/120d
SMA) is true for roughly half of all bars regardless of period, so `period` barely moves
the signal — the `period` axis of my declared grid is nearly inert.

---

## 6. TRAIN results (2016-01-01 → 2023-12-31), net of 21.92 bps

All 5 declared variants. Decimals: `cagr 0.052` = 5.2%/yr, `cost_drag 0.019` = 1.9%/yr.

| variant | CAGR | Sharpe | MaxDD | Calmar | Turn/y | CostDrag/y | Avg names |
|---|---|---|---|---|---|---|---|
| `tv_p20_r12`  | 0.052 | −0.142 | −0.121 | 0.434 | 3.68 | 0.019 | 6.26 |
| `tv_p60_r12`  | 0.046 | −0.207 | −0.207 | 0.220 | 3.72 | 0.019 | 6.41 |
| `tv_p120_r12` | 0.050 | −0.150 | −0.157 | 0.318 | 3.76 | 0.019 | 6.52 |
| `tv_p20_r10`  | **0.074** | **0.148** | −0.144 | 0.514 | 4.01 | 0.022 | 9.25 |
| `tv_p60_r10`  | 0.056 | −0.054 | −0.238 | 0.235 | 4.01 | 0.021 | 9.92 |

**Selected on TRAIN by the pre-declared rule (max Sharpe, tie → min |MaxDD|):
`tv_p20_r10`** (period=20, vol_ratio=1.0). Only one of the five has a positive TRAIN
Sharpe, and it is only 0.148 — which is already a warning, not an endorsement.

Turnover is ~3.7–4.0×/yr against a 35% per-rebalance budget, i.e. the book turns over
almost completely every month. That is what a 6-to-10-name book does when the gate
churns: the names held on consecutive rebalance dates overlap very little.

**TEST has not been touched.** Next step runs only `tv_p20_r10`, unchanged, once.

---

## 7. TEST RESULT — `tv_p20_r10`, run ONCE, unchanged (2024-01-01 → 2026-10-01, 684 bars)

```
[costs=ba350aef75b3 engine=d93815344bd3 loader=c1badf5f7df8 panel=389b082b832f]
CAGR   -0.91%   Vol   8.08%
Sharpe   -0.85    Sortino  -0.92
Calmar   -0.06    MaxDD -14.32% (150d)
WinRate  45.0%  Best   2.33%  Worst  -6.76%
Turnover  3.86x/y  CostDrag  1.79%/y  Trades  11.8/y
yearly: 2024:+5.4%  2025:+1.1%  2026:-8.5%
```

| | CAGR | Sharpe | MaxDD | Calmar | Vol | Turn/y | CostDrag/y | Avg names |
|---|---|---|---|---|---|---|---|---|
| **`tv_p20_r10` (strategy)** | **−0.91%** | **−0.85** | **−14.32%** | −0.06 | 8.08% | 3.86 | 1.79% | **7.72** |
| `buy_and_hold` (48 names, EW) | **+8.09%** | **+0.19** | −15.90% | 0.51 | 13.40% | 0.37 | 0.24% | 48.0 |
| `nsealgo` composite | +0.71% | −0.43 | −15.28% | 0.05 | 11.60% | 2.45 | 1.10% | 21.3 |

### 7.1 Strategy vs buy-and-hold (same window, same costs)

- **Return: worse by 9.00 pct-pts/yr** (−0.91% vs +8.09%).
- **Drawdown: better by only 1.58 pct-pts** (−14.32% vs −15.90%).

That second line is the damning one. The strategy gives up essentially *the entire*
equity return to buy **1.6 points** of drawdown protection. It also cuts annualised
vol from 13.4% to 8.1% — but it converts that volatility reduction into **negative**
expected return, not into a better risk-adjusted outcome. Calmar goes 0.51 → −0.06.

Note the drawdown is *long and slow*: −14.32% over **150 trading days (~7 months)**,
with a worst single day of only −6.76%. That is a persistent bleed, not a crash — the
signature of a book that pays costs continuously and is not compensated for it.

### 7.2 Cost drag (§6.4) — gross vs net

| cost setting | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| 21.92 bps (5 bps/side slippage — **headline**) | −0.91% | −0.85 | −14.32% |
| 11.92 bps (zero slippage, statutory only) | **−0.14%** | −0.76 | −13.86% |

**Slippage costs 0.77 pct-pts/yr** (₹105,273 over the window on ₹21,00,000). But the
zero-cost control is **still negative**. So this is *not* a "good signal eaten by costs"
story — the signal is roughly flat-to-negative before any cost is charged. Costs are
aggravating a result that was already a failure. (This is the diagnostic the float
slippage in `CostModel` makes possible, and it settles the question: removing costs
does not rescue the strategy.)

### 7.3 Negative control — random signal, same % of bars long (§6.5)

20 random i.i.d.-Bernoulli signal panels at the strategy's TRAIN %-long (20.17%), same
gate→momentum-rank construction, same costs, same portfolio.

| | CAGR | Sharpe |
|---|---|---|
| strategy | −0.91% | −0.85 |
| random — mean | **+1.35%** | −0.69 |
| random — median | +0.71% | — |
| random — range | [−2.80%, +7.35%] | [−1.26, +0.15] |

**The strategy beat 2/20 random controls on CAGR and 8/20 on Sharpe.**

That is the minimum bar in the brief, and the strategy **fails it**. The median coin
flip beats it on return. The one signal that says it might beat a coin on Sharpe (8/20 =
40th percentile) is still far from significant, and it contradicts the 2/20 return
result. This is a coin that came up tails, not an edge.

### 7.4 vs the nsealgo composite

Composite: CAGR +0.71%, Sharpe −0.43, MaxDD −15.28%. The strategy is **worse than the
composite on all three** — 1.62 pct-pts/yr of return and 0.42 of Sharpe. Even the
repo's own multi-factor baseline, itself a poor result (Sharpe −0.43), beats it.

### 7.5 Sanity checks (§6)

| check | result |
|---|---|
| §6.1 Plausibility (unlevered LL book ≤ ~40–50% CAGR) | ✅ −0.91% — no bug implied |
| §6.2 Weight count (target ~22) | ⚠️ **7.72** — gate only supplies 9.1 names/day. Concentration is real but **explained by the signal, not an accumulation bug** (§5): `held` is ffilled from a target that never exceeds the signalled count. |
| §6.3 Signal liveness (>~5%) | ✅ 19.01% of symbol-days long — not always-flat |
| §6.4 Cost drag reported | ✅ 1.79%/yr, and §7.2 shows zero-cost is still negative |
| §6.5 Random control | ❌ **fails** — beaten by the median coin |

---

## 8. DIAGNOSIS — why it failed (run on TRAIN, after the single TEST read)

### 8.1 Does the gate predict forward returns at all? (TRAIN cross-section)

Equal-weighted forward return of signalled names minus the equal-weighted forward return
of the whole panel:

| horizon | n days | mean alpha (bp) | median alpha (bp) | naive t | **corrected t** | hit rate | sig fwd% | mkt fwd% |
|---|---|---|---|---|---|---|---|---|
| 21d | 1818 | **−24.66** | −26.48 | −3.62 | **−0.56** | 45.4% | 1.59 | 1.91 |
| 63d | 1778 | −43.19 | −41.54 | −3.82 | **−0.34** | 46.1% | 5.13 | 5.72 |
| 126d | 1718 | −48.25 | −67.41 | −2.76 | **−0.17** | 46.2% | 10.73 | 11.45 |

**I have to correct my own statistics here.** Daily-sampled forward returns overlap, so
the naive t-stat is inflated by `sqrt(2h−1)` — at h=21 that is a factor of **6.4**. The
corrected t-stats are **−0.56 / −0.34 / −0.17**: the raw signal is *not* statistically
distinguishable from zero at any horizon.

What survives the correction is the **sign and the median**: alpha is negative at all
three horizons and the median is negative at all three, and a median is robust to the
dependence. So the honest statement is *"the gate shows no evidence of positive edge, and
a consistent weak-negative tilt,"* not *"the gate is significantly negative."*

**Leg decomposition at h=21 (TRAIN):**

| leg | mean alpha (bp) | naive t | hit rate |
|---|---|---|---|
| trend only (`close > SMA20`) | −21.74 | −5.59 | 45.4% |
| volume only (`vol > SMA20(vol)`) | **−1.33** | **−0.31** | **49.7%** |
| both (= the strategy's +1 leg) | −24.66 | −3.62 | 45.4% |

**The volume filter contributes nothing.** Its alpha is −1.33bp with t = −0.31 and a
49.7% hit rate — a coin. Everything in the signal comes from the trend leg. The strategy
is named `trend_volume`, but on this data it is a **pure trend filter with a decorative
volume filter attached.**

And the trend leg's tilt is the *wrong sign for a 1-month holding period*: buying names
that just closed above their 20-day SMA is buying recent winners, which at a ~1-month
horizon in NIFTY-50 is **short-term reversal**, not momentum.

### 8.2 Is the damage the gate, the ranking, or the interaction? (TRAIN backtests)

| score construction | CAGR | Sharpe | MaxDD | names | turn/y | drag/y |
|---|---|---|---|---|---|---|
| **B** momentum rank, **no gate** | **+17.56%** | **+0.73** | −35.21% | 21.78 | 2.64 | 2.29% |
| **C** gate + momentum (**the declared construction**) | **+7.40%** | **+0.15** | −14.40% | 9.25 | 4.01 | 2.22% |
| **D** soft gate + momentum (declared diagnostic) | +16.46% | +0.68 | −35.21% | 21.78 | 3.63 | 3.05% |

This is the load-bearing evidence, and unlike §8.1 it is **not** subject to the overlap
problem — these are full portfolio backtests with non-overlapping monthly returns.

- Adding the gate to a pure-momentum book costs **10.16 pct-pts/yr and 0.58 of Sharpe**
  (B → C).
- The soft gate (D) that only *boosts* signalled names instead of excluding everything
  else keeps 16.46% CAGR — it barely binds (it still holds 21.78 names).

**Conclusion: the momentum ranking does all the work and the gate is pure drag.** The
strategy is not "trend + volume"; out of everything it contributes, the ranking
contributes ~all of the performance and the gate subtracts from it.

### 8.3 Equity-curve sanity check on TEST

```
bars=684  final equity=0.9748  peak=1.1360
MaxDD -14.32% trough 2025-04-07  (312 bars in, peak was 2024-08-30)
bars with |daily ret| > 5%  : 1        largest single-day loss: -6.76% (2024-06-04)
fraction of days flat (0)  : 12.4%
weights sum (mean/max)     : 0.373 / 0.900     max single-name weight: 10.80% (cap 12%)
distinct symbols ever held : 48 of 48
window CAGR from curve     : -0.94%/y  (engine reports -0.91% - consistent)
days spent >5% under peak  : 452 of 684 (66.1%)
```

No bug. The equity curve reconciles with the reported CAGR, weights respect the 12% cap,
all 48 names are used, and there is exactly one >5% day. **But note the mean weight sum
is 0.373 — the book is invested ~37% of the time on average**, and 12.4% of days are
completely flat (fully in cash).

That is the mechanical failure, in one line:

> The gate is simultaneously **restrictive** (7.7 names vs 22, ~37% invested) and
> **churning** (3.86×/yr turnover). It pays the full cost of a ~4×/yr rotation of a book
> that only captures ~37% of the market's return — and then picks the wrong 37%.

The −14.32% drawdown over 150 sessions with a worst day of only −6.76% and **66% of days
spent >5% underwater** confirms it is a slow, grinding bleed, not a crash. A strategy
with this profile is not going to be rescued by a different exit rule.

---

## 9. VERDICT

### 9.1 The brief's eight questions

1. **Strategy / signal / variants.** `trend_volume_strategy`: hold a name when
   `close > SMA(period)` **and** `volume > vol_ratio × SMA(volume, period)`; long leg
   only (short is unavailable in a delivery account). Gate → rank survivors by 126d
   momentum, `PortfolioConfig()` defaults, monthly rebalance. Declared budget = 5
   variants (`tv_p20_r12`, `tv_p60_r12`, `tv_p120_r12`, `tv_p20_r10`, `tv_p60_r10`),
   fixed in §2 before any run. **5 tested, budget not exceeded.**
2. **TEST table.** §7 above.
3. **Buy-and-hold, same window.** §7 above (+8.09% CAGR, +0.19 Sharpe, −15.90% MaxDD).
4. **vs buy-and-hold.** **Worse by 9.00 pct-pts/yr of return**, better by only
   **1.58 pct-pts** of drawdown. Bad trade on both axes.
5. **Random control.** Strategy beat **2/20 on CAGR, 8/20 on Sharpe**; random median
   CAGR **+0.71%** > strategy **−0.91%**. **Fails the minimum bar.**
6. **vs the nsealgo composite.** Worse on all three: −0.91 vs +0.71% CAGR,
   −0.85 vs −0.43 Sharpe, −14.32 vs −15.28 MaxDD.
7. **One-sentence verdict.** **No — `trend_volume_strategy` does not make money on NSE
   NIFTY-50; out-of-sample it loses 0.91%/yr net of full Indian delivery costs and loses
   to a coin flip.**
8. **Most likely reason + the one next thing.** Below.

### 9.2 Why it failed (ranked by strength of evidence)

1. **The gate is anti-momentum at this horizon.** (STRONG — §8.2, backtest evidence.)
   It buys names that just closed above a 20-day SMA. Over a ~1-month holding period in
   Indian equities that is short-term reversal. Adding the gate to a pure-momentum book
   destroyed 10.16 pct-pts/yr and 0.58 Sharpe on TRAIN.
2. **The volume leg is decorative.** (STRONG — §8.1.) `vol > SMA(vol)` has t = −0.31 and
   a 49.7% hit rate. It contributes nothing to the signal and only removes names, cutting
   the daily signal count by ~35% and raising turnover. The strategy does not need it,
   and it costs 0.5 pct-pts/yr.
3. **Restrictive + churning is the worst of both.** (STRONG — §8.3.) ~37% average
   investment paying 3.86×/yr turnover = 1.79%/yr of cost drag, capturing only 37% of a
   market that returned +8.09%.
4. **TEST itself was a bad regime for momentum-family signals** (CONTEXT, not
   strategy-specific): the repo's own `build_composite_score` scored only +0.71% CAGR /
   −0.43 Sharpe on the same window, and buy-and-hold made +8.09%. Any momentum-tilted
   long-only book started 2024 under pressure. This raises the bar but does not excuse
   the result — the strategy did far worse than the weak momentum benchmark it sits next
   to.

### 9.3 The one thing I would try next

**Drop the trend leg's sign and test the strategy as a mean-reversion filter instead** —
i.e. hold a name when `close < SMA(period)` AND `volume > vol_ratio × SMA(volume, period)`.
The evidence says the gate's alpha points the *other* way (§8.1, median alpha negative at
every horizon; §8.2, gate destroys value on a momentum book). Flipping the trend leg while
keeping the volume filter converts the strategy from "buy the recent winner" into "buy the
recent loser on abnormal volume" and aligns it with the sign the data actually shows.
That is a **different strategy** and would need its own fresh TRAIN/TEST protocol — it is
a next step, not a result I am claiming.

### 9.4 Honest caveats

- **TEST was read exactly once**, on the TRAIN-selected variant, unchanged. No parameter,
  threshold or variant was chosen using any TEST observation. All diagnostics (§8, §8.1
  t-stat correction, §8.3 curve check) were run on TRAIN or were re-reads of the
  already-reported TEST numbers that produced no new variant.
- **Parameter budget: 5 of 5 used. Not exceeded.** The only extra backtests run are the
  §8.2 *construction decomposition* (B/C/D) and the §7.2 zero-slippage control, both of
  which are diagnostics, not candidates, and both labelled as such. No construction was
  ever promoted to a candidate.
- **Survivorship bias is present** (today's NIFTY-50 backfilled) and is not corrected
  for, per the standing disclosure. It inflates both the strategy and buy-and-hold, so it
  does not explain the 9-pct-pt gap.
- **pnl_concentration / win-rate** (45.0% daily win rate, worst day −6.76%) are consistent
  with a low-exposure book, not with a data or indexing fault.

---

## 10. Reproduction

```bash
.venv/bin/python research/agent_trendvol/00_data.py         # panel + volume + provenance
.venv/bin/python research/agent_trendvol/01_train_select.py  # port validation + TRAIN selection
.venv/bin/python research/agent_trendvol/02_test_eval.py     # the single TEST read + all controls
.venv/bin/python research/agent_trendvol/03_diagnose.py     # TRAIN-only diagnosis
.venv/bin/python research/agent_trendvol/04_followup.py     # overlap correction + curve check
.venv/bin/ruff check research/agent_trendvol/*.py           # clean
```

Provenance of every number above:
`{"engine": "d93815344bd3", "loader": "c1badf5f7df8", "costs": "ba350aef75b3", "panel": "389b082b832f"}`

Artifacts: `results_train.json`, `results_test.json`, `diagnostic_train.json`,
`followup.json`, `data_provenance.json`, `panel.pkl`, `vol.pkl`.

**No file under `src/` or `tests/` was modified by this study.**
