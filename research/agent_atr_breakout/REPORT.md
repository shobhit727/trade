# `atr_breakout_strategy` on NSE NIFTY-50 — VALIDATED NEGATIVE

**Agent:** `atr_breakout`  ·  **Scratch:** `research/agent_atr_breakout/`
**Data:** `data/nse/*_1d.csv` → 48 symbols, 2008-01-01 → 2026-10-01, 4,629 daily bars
**Protocol:** TRAIN 2016-01-01→2023-12-31 (selection) / TEST 2024-01-01→2026-10-01 (touched once)
**Costs:** `CostModel(segment="delivery", slippage_bps=5)` = 21.92 bps round trip
(statutory 11.92 + 2×5 slippage) @ ₹1L/position. Costs applied at every rebalance.

---

## 1. Strategy and signal

`src/cryptobot/strategies/catalog/atr_breakout_strategy.py` emits a per-symbol
time-series signal:

```
b = atr(high, low, close, period)      # mean of last `period` true ranges
m = sma(close, period)                 # simple moving average
+1 if close > m + multiplier*b
-1 if close < m - multiplier*b
 0 otherwise
```

Reproduced vectorised in `signal.py`. Note `indicators.atr` is an **un-smoothed
arithmetic mean of true ranges**, not Wilder's ATR — reproduced exactly, so this is
the same strategy and not a lookalike.

**Construction** (brief §5 — the book is long-only and cross-sectional, the signal is
not). ATR breakout becomes a *gate* on a momentum ranking:

```python
score = (close / close.shift(126) - 1.0).where(signal > 0).rank(axis=1, pct=True)
```

Unflagged names get NaN; `build_rebalance_weights` drops non-finite scores, so the book
only ever holds names the strategy actually selected. The short leg is discarded —
shorting does not exist in an Indian delivery account. That is a real cost, sized in §5.

### Declared parameter budget — 5 variants, fixed before any run

| tag | period | multiplier |
|-----|--------|-----------|
| V1 | 10 | 1.0 |
| V2 | 14 | 1.5 (catalog default) |
| V3 | 20 | 2.0 |
| V4 | 14 | 2.5 |
| V5 | 20 | 3.0 |

Five variants tested. Not exceeded.

---

## 2. TRAIN selection (2016-01-01 → 2023-12-31)

Liveness = fraction of (symbol, bar) cells the strategy says long.

| tag | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Names | Liveness |
|-----|------|--------|-------|--------|--------|--------|-------|----------|
| **V1** | **12.31%** | **0.58** | −14.36% | 0.86 | 3.99 | 1.34% | 25.8 | 19.66% |
| V2 | 8.88% | 0.30 | −13.83% | 0.64 | 3.86 | 1.15% | 21.1 | 14.86% |
| V3 | 5.87% | −0.03 | −14.86% | 0.40 | 3.73 | 0.97% | 16.9 | 13.30% |
| V4 | 3.67% | −0.57 | −6.56% | 0.56 | 1.81 | 0.46% | 2.3 | 3.60% |
| V5 | 4.72% | −0.30 | −5.92% | 0.80 | 2.07 | 0.54% | 3.2 | 4.24% |
| buy-and-hold | 22.17% | 0.91 | −37.97% | 0.58 | — | 0.22% | 46.3 | — |
| nsealgo composite | 21.30% | 0.96 | −32.92% | 0.65 | 1.96 | 1.00% | 21.8 | — |

**Selected on TRAIN by max Sharpe: V1 (period=10, multiplier=1.0).** Frozen from here.

Note that even on TRAIN — the set I was allowed to select on — V1 already trailed
buy-and-hold by 9.9pp and the composite by 9.0pp. That was visible before TEST and is
reported here rather than buried.

---

## 3. TEST result (2024-01-01 → 2026-10-01) — the deliverable

| | CAGR | Sharpe | MaxDD | Calmar | Turn/y | Cost/y | Names | Total |
|---|---|---|---|---|---|---|---|---|
| **V1 (strategy)** | **2.45%** | **−0.32** | **−17.04%** | 0.14 | 3.99 | 1.00% | 20.5 | +7.0% |
| V1 gross (0 cost) | 2.86% | −0.28 | −16.48% | 0.17 | 3.99 | 0% | 20.5 | +8.2% |
| buy-and-hold (equal weight) | 8.16% | 0.19 | −15.91% | 0.51 | — | 0.22% | 48.0 | — |
| nsealgo composite | 6.55% | 0.07 | −14.84% | 0.44 | 2.07 | 0.55% | 21.3 | +19.5% |

Cost drag: gross 2.86% → net 2.45% = **1.00%/yr**. Under triple slippage: 1.63%.

Calendar years: 2024 **+17.00%**, 2025 −1.84%, 2026 *(to 2026-10-01)* **−6.80%**.
**Positive in 1 of 3 years.** GOAL.md Gate 3 asks for ≥60%.

### vs buy-and-hold
- Return: **worse by 5.71pp/yr** (2.45% vs 8.16%).
- Drawdown: **worse by 1.14pp** (−17.04% vs −15.91%).
- Sharpe: worse (−0.32 vs 0.19).
- It loses on **both** return and risk. Not a risk-adjusted improvement.

### vs nsealgo composite
Worse on every metric: −4.10pp CAGR, −0.39 Sharpe, 2.20pp deeper drawdown.

---

## 4. Negative control — a random signal beats it 9 times out of 10

10 random signals with the identical 18.86% liveness, same engine, same costs.

| | mean CAGR | median | best | worst |
|---|---|---|---|---|
| random | 5.61% | 5.00% | 9.64% | 2.44% |
| **V1** | **2.45%** | | | |

**V1 beats 1/10 random controls.** A coin flip with the same exposure is a better
strategy than this one. That is the minimum bar in the brief, and it is not cleared.

---

## 5. Why it fails

Three diagnostics, none of them re-tuning. The ablation is a *diagnostic*, not a
sixth variant, and nothing was selected on it.

**(a) The gate subtracts; it does not add.** Same 126-day momentum ranking, ATR gate
removed:

| TEST | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| momentum + ATR gate (V1) | 2.45% | −0.32 | −17.04% |
| momentum, no gate | 2.60% | −0.22 | −16.86% |

The ATR gate contributes **−0.16pp/yr**. The book was being carried entirely by the
momentum ranking underneath it; the breakout filter was pure drag. Both are far below
buy-and-hold's 8.16%, so even the momentum sleeve is not doing much in this window.

**(b) It is not a cost problem.** At zero cost the strategy returns 2.86% — still under
half of buy-and-hold. Costs trim ~0.4pp; the strategy is 5.7pp short. Cutting costs
would not rescue it (and `GOAL.md` §6.4 forbids trying).

**(c) TRAIN→TEST decay is the classic noise signature.** Sharpe 0.58 → −0.32. The
best of 5 variants on 8 years of one market regime is not evidence of an edge, and the
out-of-sample number says so plainly.

**(d) What the long-only restriction cost.** A synthetic short book built from the
−1 signals returns 6.80% (Sharpe 0.08) vs 2.45% long-only. So roughly 4.4pp/yr of the
strategy's information sits on the short side — untradeable in an Indian delivery
account. This is a structural handicap of the strategy *as a long-only Indian book*,
not a fixable parameter.

---

## 6. Sanity checks (brief §6)

| check | result |
|---|---|
| 1. Plausibility | CAGR 2.45% — far below the 40–50% unlevered ceiling. **OK** |
| 2. Weight count | 20.5 avg, max 30, bounded, no upward drift (first-3y 20.2 → last-3y 20.2). **OK** |
| 3. Signal liveness | 18.86% of symbol-bars long, well above the 5% floor. **Not** effectively flat |
| 4. Cost drag | 1.00%/yr; gross 2.86% is also below buy-and-hold. Strategy unviable **on signal, not on cost** |
| 5. Negative control | Lost to 9/10 random controls. **FAIL** |

Extra checks I added:

- **Caps hold:** max single-name weight 10.80% (cap 12%), max sector within 25%,
  daily weight sum ≤85.56%.
- **No lookahead:** delaying every weight decision degrades results monotonically
  (Sharpe 0.58 → 0.68 at +1d → 0.66 at +2d → −0.14 at +5d on TRAIN). The one-bar lag
  binds, so the pipeline is honest. If delayed results had been identical, every number
  in this report would be suspect.
- **Cost model:** verified against `nsealgo.cli costs` → 11.92 bps at ₹1L, matching the
  published 11.65–11.66 bps reference.
- **Survivorship bias is present** (today's NIFTY-50 backfilled) — disclosed per the
  repo convention. It affects buy-and-hold and the strategy equally.

**Protocol compliance:** TEST was opened exactly once, at §3, after V1 was frozen from
TRAIN at §2. No parameter was re-tuned after seeing TEST. No TEST result appears
anywhere in the selection path.

---

## 7. Verdict

**No. `atr_breakout_strategy` does not make money on NSE NIFTY-50.** It returns
2.45% CAGR out-of-sample against 8.16% for buy-and-hold, loses to a random signal
9 times in 10, and beats nothing on either return or drawdown.

**Most likely reason:** the breakout condition is a *volatility-scaled* filter
(`close > sma ± mult·atr`), which by construction fires on the most volatile,
already-extended bars. Those are precisely the bars a momentum rank then buys at the
top of the book — so the gate selects the most expensive entry point in the name and
provides no independent information. The ablation confirms it: the gate is worth
−0.16pp/yr versus not having it. Additionally, monthly rebalancing is a poor match for a
signal whose information decays in days, so ~4x/yr turnover pays to hold a stale gate.

**The one thing I would try next:** stop treating the breakout as a gate on momentum
and instead use it as a *timing* signal on a small, fixed, low-turnover core — i.e. hold
the momentum book and use ATR breakout only to decide entry timing into an *empty*
book, with a re-entry cooldown that lets realised volatility decay before re-arming.
That directly targets the measured problem (the gate picks extended bars) and would cut
turnover, which is the only lever that showed any effect here. I would not tune
`multiplier` or `period` further — 5 variants across the range already established that
the parameter surface is flat-to-negative.

---

## Files

| file | purpose |
|---|---|
| `common.py` | OHLC panel builder (same `load_symbol` cleaning path as `load_universe`) |
| `signal.py` | vectorised ATR-breakout signal, faithful to the catalog |
| `s1_train_explore.py` | TRAIN-only liveness + raw-signal diagnostics |
| `s2_train_select.py` | cross-sectional construction, 5-variant TRAIN selection |
| `s3_weight_check.py` | weight-count and cap sanity |
| `s4_test.py` | **the TEST run** + buy-and-hold + composite + random controls |
| `s5_verify.py` | lookahead test, cost stress, ablation, short-leg sizing |

Reproduce: `.venv/bin/python research/agent_atr_breakout/s2_train_select.py` then
`.venv/bin/python research/agent_atr_breakout/s4_test.py`
