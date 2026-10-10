# `macd_strategy` on NSE NIFTY-50 — COMPLETE

> **STATUS: finished.** The header and the declared parameter budget (§2) were written
> and committed to this file **before any backtest was run**; sections were appended as
> results landed. Nothing here is back-filled after the fact.
>
> **Verdict (§9): NO — not a pass.** Out-of-sample 4.07% CAGR vs buy-and-hold 8.18%.
> The largest finding of this run is not the strategy but a reproducibility defect in
> the shared harness (§10).
>
> **All TEST numbers verified byte-identical across repeated runs** on engine
> `3ceaee89028c72ed`. `ruff check` clean. No file outside `research/agent_macd/` was
> created or modified by this work.

Source: `src/cryptobot/strategies/catalog/macd_strategy.py`
Scratch: `research/agent_macd/` (this directory). No file under `src/nsealgo/**`,
`src/cryptobot/**` or `tests/**` was modified.

**Not crypto-specific** — MACD is a textbook daily-bar trend indicator with direct NSE
meaning. Proceeding with the full protocol.

---

## 1. The assigned strategy, verbatim behaviour

```python
@dataclass
class MacdConfig:
    fast: int = 12
    slow: int = 26
    signal: int = 9
    quantity: Decimal = Decimal("1")

def warmup(self, closes) -> int:  return self.config.slow

def signal(self, closes, highs, lows, volumes):
    line = macd(closes, self.config.fast, self.config.slow)
    sig  = macd_signal(closes, self.config.fast, self.config.slow, self.config.signal)
    if line != line or sig != sig or line == sig:
        return 0                                  # NaN (warmup) or exact tie
    return 1 if line > sig else -1                # +1 = MACD line above signal line
```

So it is a **binary trend state**, not a crossover event: `+1` while
`MACD(fast, slow) > signal_line`, `−1` otherwise, `0` during warmup. `quantity` is
irrelevant to a portfolio-level backtest.

**The "signal line" is a SIMPLE mean, not an EMA.** `macd_signal` in
`src/cryptobot/strategies/indicators.py` is literally `np.mean(line[-sig:])`. That is
*not* the textbook MACD signal line (an EMA of the MACD line). It is a valid
histogram-style trigger and a known variant, but it means `signal` behaves as an
arithmetic-mean confirmation window rather than an exponential one. I reproduce the
catalog exactly and do **not** "fix" it — the assignment is to test *this* strategy.

**Warmup-length bug (minor, harmless).** `warmup()` returns `self.config.slow` (26), but
`macd_signal` needs `slow + signal` bars before it stops returning NaN. The declared
warmup is short by `signal` bars. Harmless here (those bars produce `0` = "not long").
Recorded in §9.

**Long-only consequence:** a delivery account cannot hold the `−1` state, so only the `+1`
branch is holdable. The `−1` names are *excluded*, not shorted.

---

## 2. DECLARED PARAMETER BUDGET — 5 variants, fixed before running

Rebalance held at **monthly** for every variant (engine evidence note; not part of the
budget). The MACD parameter axes are (a) fast/slow and (b) the signal confirmation length.

| Variant | fast | slow | signal | rationale |
|---------|------|------|--------|-----------|
| V1 | 12 | 26 | 9 | **catalog default** — classic 12/26/9 |
| V2 | 12 | 26 | 5 | signal axis alone (V2 vs V1 isolates confirmation length) |
| V3 | 5 | 20 | 9 | fast swing pair |
| V4 | 20 | 50 | 9 | slower swing pair |
| V5 | 10 | 100 | 9 | near-regime filter |

**Selection rule, fixed in advance: maximise TRAIN Calmar** (CAGR / |MaxDD|) — the
statistic matching `GOAL.md` §2.3's joint return-and-drawdown bands. TRAIN only.

**Budget accounting: 5 declared, 5 tested, 0 exceeded.** No deviation.

---

## 3. Protocol and construction (fixed before running)

| Set | Window | Purpose |
|-----|--------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | selection only |
| **TEST** | 2024-01-01 → 2026-10-01 | touched **once**, after freezing |

- Data: `load_universe("data/nse")` → **48 symbols, 4625 bars, 2008-01-01 → 2026-10-01**,
  13,916 NaN cells (names not yet listed / delisted gaps — expected on a backfilled panel).
  Cleaning: 274,541 rows in → 208,226 out; 66,312 dropped pre-2008; 3 extreme days dropped;
  `adanient`, `jiofin` excluded.
- Signal → score (brief §5): `score = (panel/panel.shift(126) − 1).where(signal > 0).rank(axis=1, pct=True)`
  — 126d trailing momentum ranked only among names flagged long that day.
- No lookahead: `run_backtest` decides weights on the close of *t* and earns returns from
  *t+1* (`held.shift(1) * rets`). The EMA recursion is causal/prefix-stable by construction.
- Portfolio: `PortfolioConfig()` defaults — 22 names, 12% single name, 25% sector, 10%
  cash, monthly rebalance, 35% turnover budget, max 30 names. Not bypassed.
- Costs: `CostModel(segment="delivery", slippage_bps=5)`; `round_trip_bps(100_000)` =
  **11.92 bps**, `all_in_round_trip_bps(100_000)` = **21.92 bps**. **Every number here is
  net of 21.92 bps** because every number comes from `run_backtest`. The 11.92 figure is
  never quoted as a result.
- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed throughout.
- **End date is part of every result: 2026-10-01.**

### Fidelity check (brief §6 sanity check 6)
The vectorised signal was verified **bar-by-bar against the literal catalog call**
(`MacdStrategy.signal` on every rolling prefix, 700 bars × 3 symbols × 5 variants):

```
max_abs_diff_on_defined_bars = 0.0     (all 5 variants)
invented_signal_bars        = 0        (all 5 variants)
```

Bit-identical. What is measured here is exactly what the catalog strategy computes.

### Infrastructure pin (see §10 — this turned out to be essential)
```
backtest/engine.py  3ceaee89028c72ed
backtest/metrics.py cee64ba266002ccd
costs.py            d954b222987fb877
data/loader.py      edc6423de148c40e
factors/core.py     2e0826b235aa00a8
```
A byte-identical copy is saved at `research/agent_macd/PINNED_engine.py.snapshot`.

---

## 4. TRAIN results (selection only) — 2016-01-01 → 2023-12-31

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Live% |
|---------|-------|--------|--------|--------|----------|----------|--------|-------|
| V1 12/26/9 | 11.59 | 0.58 | −9.24 | 1.25 | 4.09 | 2.73 | 18.4 | 48.6% |
| V2 12/26/5 | 12.97 | 0.70 | −10.32 | 1.26 | 4.07 | 2.97 | 18.6 | 48.6% |
| **V3 5/20/9** | **13.35** | **0.73** | −9.62 | **1.39** | 4.06 | 2.95 | 18.9 | 48.5% |
| V4 20/50/9 | 9.08 | 0.32 | −19.83 | 0.46 | 4.09 | 2.48 | 17.8 | 49.2% |
| V5 10/100/9 | 10.93 | 0.52 | −13.13 | 0.83 | 4.07 | 2.68 | 18.0 | 49.3% |
| MOM_ONLY (ablation) | 17.56 | 0.73 | −35.21 | 0.50 | 2.64 | 2.29 | 21.8 | 100% |
| COMPOSITE (nsealgo) | 20.72 | 0.93 | −32.94 | 0.63 | 1.97 | 1.97 | 21.8 | 100% |

**SELECTED: V3 (fast=5, slow=20, signal=9)** — highest TRAIN Calmar 1.39.
All five variants were positive in 8 of 8 TRAIN calendar years (`yearly_pos_frac` 1.00).

TEST was untouched until this point.

---

## 5. TEST results — 2024-01-01 → 2026-10-01 (touched once)

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Live% |
|---------|-------|--------|--------|--------|----------|----------|--------|-------|
| **V3 5/20/9 (SELECTED)** | **4.07** | **−0.21** | **−11.38** | **0.36** | **4.11** | **2.03** | **17.7** | 49.3% |
| V1 12/26/9 (catalog) | 6.18 | 0.00 | −11.88 | 0.52 | 4.15 | 2.14 | 18.6 | 48.9% |
| V2 12/26/5 | 4.42 | −0.17 | −11.70 | 0.38 | 4.13 | 2.06 | 18.3 | 48.7% |
| V4 20/50/9 | 0.97 | −0.59 | −14.26 | 0.07 | 4.15 | 2.00 | 18.6 | 48.4% |
| V5 10/100/9 | 1.09 | −0.57 | −16.04 | 0.07 | 4.16 | 2.04 | 18.7 | 48.4% |
| MOM_ONLY (ablation) | 1.58 | −0.30 | −18.82 | 0.08 | 2.77 | 1.39 | 21.3 | 100% |
| COMPOSITE (nsealgo) | 6.04 | 0.03 | −15.22 | 0.40 | 2.08 | 1.10 | 21.3 | 100% |
| **BUY-AND-HOLD (brief §4.5)** | **8.18** | **0.18** | **−15.90** | **0.51** | 0.0 | one-off | 48 | 100% |

Total return over TEST: MACD(V3) **+11.83%** vs buy-and-hold **+24.64%**.

Calendar years (%):

| | 2024 | 2025 | 2026 (to Oct 1) |
|---|---|---|---|
| MACD V3 | 12.00 | 1.87 | −1.99 |
| MOM_ONLY | 17.91 | 1.32 | −12.53 |
| COMPOSITE | 21.91 | 6.61 | −9.31 |
| Buy-and-hold | 19.87 | 13.35 | −8.27 |

TRAIN calendar years for V3 (%): 2016 +4.36, 2017 +20.06, 2018 +2.44, 2019 +5.84,
2020 +35.94, 2021 +23.60, 2022 +1.92, 2023 +18.39.

**Selection did not transfer.** The TRAIN winner (V3) ranked *third of five* on TEST, and
the variant TRAIN ranked 4th (V4, Calmar 0.46) was nearly the worst out of sample. I am
reporting the pre-registered selection, not re-selecting on TEST. The catalog default V1 —
which TRAIN ranked 3rd — happened to be the best TEST variant; that is disclosed, not
adopted.

---

## 6. Sanity checks (brief §6)

| # | Check | Result |
|---|-------|--------|
| 1 | **Plausibility** | ✅ 4.07% CAGR, well inside the 40–50% unlevered ceiling. No lookahead bug. Equity check: final equity 1.1183 → implied CAGR 4.07% = reported 4.07%. |
| 2 | **Weight count** | ✅ avg 17.7 names (median 22, max 22). No residual accumulation. *Note: this was 28.6 under the pre-rewrite engine — see §10.* |
| 3 | **Signal liveness** | ✅ 49.3% of (name, bar) cells long. Far above the ~5% floor. Not an always-flat book. |
| 4 | **Cost drag** | ✅ Gross positive, net positive. 2.03%/y drag. Stress: zero-cost 4.93%, double-slippage 3.22%, triple-slippage 2.37% — **the result survives triple slippage**. |
| 5 | **Negative control** | ⚠️ **Weak.** See §7. |
| 6 | **Signal fidelity** | ✅ Bit-identical to the catalog call, 0 invented bars. |
| + | Constraints | ✅ max single weight 10.07% (cap 12%), max sector 19.81% (cap 25%). |
| + | Concentration | Top-5 names = 38.9% of P&L (V1) — dispersed, not a handful of lucky bets. |

**Structural note on the 21 empty days.** The book holds 0 names on the first 21 TEST
sessions, then starts on 2024-02-01. This is a *warm-up artefact*, not strategy
behaviour: `run_backtest` computes inverse-vol scaling from a 60-day rolling std with
`min_periods=20`, and the first bar with 22 valid vol readings is 2024-01-30, so the
January rebalance produces an all-zero target. It costs ~1 month of a 33-month TEST
window and is identical across every variant and every comparator, so it does not
distort the comparison — but it is a harness limitation worth knowing about.

---

## 7. Negative control: random signal, same % of bars long

50 seeds, same construction, same costs, same TEST window, long fraction matched to
MACD's 49.3%:

| | MACD V3 (selected) | MACD V1 (catalog) | Random median | Random p10–p90 |
|---|---|---|---|---|
| CAGR% | **4.07** | **6.18** | 3.39 | 1.39 – 5.42 |
| Sharpe | **−0.21** | **0.00** | −0.31 | −0.52 – −0.07 |
| MaxDD% | −11.38 | −11.88 | −11.21 | −13.96 – −9.28 |

Percentile rank vs the 50 random draws:
- **selected V3: 58th percentile CAGR, 68th Sharpe, 54th MaxDD** — barely better than a
  coin flip. The selected variant does **not** clear the minimum bar.
- **catalog V1: 96th percentile CAGR and Sharpe, 62nd MaxDD** — does clear it.

So the MACD *signal* is real information, but the **TRAIN-selected parameter set throws it
away**. That is the central finding of this run, and it is a parameter-selection failure,
not a signal failure.

---

## 8. TEST vs the benchmarks

**vs buy-and-hold (the required comparison):**

| | MACD V3 | Buy-and-hold | Delta |
|---|---|---|---|
| CAGR | 4.07% | 8.18% | **−4.11 pp — worse** |
| Sharpe | −0.21 | 0.18 | **−0.39 — worse** |
| MaxDD | −11.38% | −15.90% | **+4.52 pp — better** |

MACD **loses to buy-and-hold on return by a wide margin and wins on drawdown by a
moderate one**. Best catalog variant V1 is still behind B&H on return (6.18 vs 8.18) and
still ahead on drawdown (−11.88 vs −15.90). The strategy trades ~40% of the return for
~28% of the drawdown — a poor exchange at any plausible utility.

**vs nsealgo composite:** composite 6.04% CAGR / 0.03 Sharpe / −15.22% MaxDD. MACD V3 is
**worse** on return (−1.97 pp) and Sharpe (−0.24), **better** on drawdown (+3.84 pp).
V1 is roughly level with the composite on return (6.18 vs 6.04) and better on drawdown.

**Rebalance-frequency stress (Gate 4, not a parameter choice):** M 4.07%, Q 4.74%,
**W −6.10%**. Weekly is catastrophic — consistent with the engine's evidence note and with
`GOAL.md` §5's turnover constraint.

---

## 9. Verdict

> ### Does `macd_strategy` make money on NSE NIFTY-50? **Yes — but barely, and it is not
> > better than doing nothing.**
>
> The pre-registered selection returned **4.07% CAGR net of 21.92 bps** out of sample
> against buy-and-hold's 8.18%. It beat a random signal on only the 58th percentile. The
> goal is 3%/month (≈43%/yr); this delivers 4.07%/yr. **This does not pass.**

**Most likely reason it failed:** the MACD gate is applied *on top of* a 126d-momentum
ranking, so it is not adding a new idea — it is filtering an existing momentum signal with
a momentum-flavoured indicator. The TRAIN→TEST parameter-selection step is where most of
the value leaked: TRAIN Calmar picked 5/20/9 (58th percentile vs random out of sample)
while the untuned catalog default 12/26/9 sat at the 96th percentile. The classic
MACD settings are the *slowest-moving* and *least churny* of the five, and the churny ones
paid 4.1x/yr of turnover for no compensating edge.

**The one thing I would try next:** drop the momentum-ranking layer and use MACD as a pure
**regime overlay** — hold the nsealgo composite's book when the broad market's MACD(12,26,9)
is positive and go to cash when it is negative. The evidence for this is already in the
table above: MACD's demonstrable contribution in this window is **drawdown control**
(MaxDD −11.4% vs momentum-only's −18.8%), not return. The ablation that matters is that
MOM_ONLY earned 1.58% at −18.82% while MACD-gated earned 4.07% at −11.38% — **the gate
added +2.5 pp of CAGR and 7.4 pp of drawdown control simultaneously.** That is the one
part of this strategy that demonstrably works, and it is worth testing on its own terms
rather than buried in a momentum book it does not need.

**Caveat carried forward:** all of this is contingent on the engine revision in §10. If
that rewrite is wrong, these numbers move materially.

---

## 10. MATERIAL FINDING: the shared backtest engine was rewritten mid-experiment

**This is the most valuable output of this run, and it is a bug in the experiment
infrastructure, not in the strategy.**

### Symptom
Re-running `research/agent_macd/run.py` produced **different numbers**. V1 TEST CAGR came
out 7.40% on one execution and 6.06% on the next, with the run log otherwise identical.
This is not acceptable and it was not in my code — `bisect2.py` reproduced bit-identical
CAGRs and bit-identical weight hashes across 3 processes × 3 in-process repeats.

### Root cause
`src/nsealgo/backtest/engine.py` is **actively being rewritten by another agent while
experiments are running against it.** `apply_turnover_budget` was replaced: the old code
blended the whole book toward the new target (`cur + λ(tgt − cur)`), the new code makes
exits unconditional and whole via `_exit_allocation` and gives the leftover budget only to
adoptions.

`git diff --stat src/nsealgo` mid-run showed `87 insertions(+), 28 deletions(-)`.

### Magnitude — this is not cosmetic

| Metric | Old engine (blend) | New engine (whole exits) |
|---|---|---|
| Avg names held (TEST) | 28.8 | 17.7 |
| TRAIN CAGR V1 | 17.24% | 11.59% |
| TEST CAGR V1 | 7.40% | 6.18% |
| TRAIN selection | V2 (12/26/5) | **V3 (5/20/9)** |
| Sharpe V1 TEST | 0.13 | 0.00 |

**The rewrite changed which variant TRAIN selects.** V2 → V3. A cross-agent edit
therefore silently changed another experiment's conclusions.

The rewrite's own docstring gives a plausible technical justification (blending left
positions the signal did not want at a fraction of intended weight), and the direction is
supported by brief §6.2 — a book holding 28.6 names when 22 are configured is the exact
"residual weights are accumulating" failure the brief warns about. So the change is
probably an improvement. **That does not make it safe.**

### Why this matters beyond my one strategy
1. **Every research report in this repo produced today is unreproducible** unless it pins
   the engine revision. `reports/VALIDATION_v1.md` and every `research/agent_*/REPORT.md`
   written before the rewrite describe a different engine than the one in the tree now.
2. **No test caught it.** The engine has unit tests, but "results change when the module
   changes" is not something a unit test asserts. Nothing in the harness records which
   engine produced a number.
3. **Selection is not stable to it.** A parameter-selection decision inverted. Any
   conclusion phrased as "variant X is best" is only valid with the engine named.

### Recommended fix (small, high value)
Have `run_backtest` stamp its result with the engine revision:

```python
# in BacktestResult
engine_sha: str = field(default_factory=lambda: hashlib.sha256(
    Path(__file__).read_bytes()).hexdigest()[:16])
```

and have every research report print it in a provenance header. A run whose
`engine_sha` does not match the tree is stale, and should be re-run rather than quoted.
Better still: make `src/nsealgo` immutable during a research window, or copy the module
into each `research/agent_*/` directory and import the copy.

### Related crash observed
`src/cryptobot/strategies/catalog/cointegration_strategy.py` was mid-write and raised
`IndentationError` during an import, crashing a verification run. A partially-written
source file is importable-by-luck and will produce confusing failures rather than a clean
error. Relevant to any agent that imports the catalog package.

---

## 11. Other findings

1. **`MacdStrategy.warmup()` is too short.** It returns `self.config.slow` (26), but
   `macd_signal` needs `slow + signal` bars (35 for the default). The extra 9 bars return
   `0`. Harmless in a portfolio backtest; it would matter to a streaming engine that sizes
   its warm-up buffer from this value and starts trading 9 bars early.

2. **`macd_signal` is an SMA, not an EMA signal line.** Not a bug — a deliberate variant —
   but the parameter named `signal` does not mean what a MACD user expects it to mean, and
   V2 vs V1 in this run is really a test of arithmetic-mean vs a shorter arithmetic-mean
   window.

3. **The momentum-ranking layer is doing the work, not MACD.** The ablation is unambiguous:
   MOM_ONLY (pure 126d-momentum top-22) earns 1.58% at −18.82% MaxDD on TEST, while the
   MACD-gated version of the *same* ranking earns 4.07% at −11.38%. MACD's contribution is
   a real drawdown reduction. But the strategy as constructed is best described as
   "momentum, with a trend filter that removes the crashes" — not as a MACD strategy.

---

## 12. Reproducing this

```bash
.venv/bin/python research/agent_macd/run.py     # main experiment -> results.json
.venv/bin/python research/agent_macd/diag.py    # name counts, 50-seed random control
.venv/bin/python research/agent_macd/diag2.py   # exposure, cash days, concentration
.venv/bin/python research/agent_macd/diag3.py   # B&H calendar years, warm-up audit
```

Requires engine `3ceaee89028c72ed` (snapshot in `PINNED_engine.py.snapshot`). Verified
byte-identical across repeated executions on that revision.