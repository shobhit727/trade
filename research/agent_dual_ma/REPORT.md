# `dual_moving_average` on NSE NIFTY-50 — NEGATIVE FINDING

Source: `src/cryptobot/strategies/catalog/dual_moving_average.py`
(EMA fast > slow → +1, else −1; default 20/50)
Scratch: `research/agent_dual_ma/run.py` (protocol), `research/agent_dual_ma/diag.py` (TRAIN-only diagnostic)

---

## 1. Construction

Daily bars, `load_universe("data/nse")` → 48 symbols, 4,629 bars, 2008-01-01 → 2026-10-01.
Cleaning: 274,541 → 208,226 rows (66,312 pre-2008 dropped, `adanient` + `jiofin` excluded,
3 extreme moves dropped). Survivorship bias is present (today's NIFTY-50 backfilled) and is
noted in every number below.

- Signal: `EMA(fast) > EMA(slow)` per symbol. Recursive EMA seeded at the first bar, so it
  matches `cryptobot.strategies.indicators.ema()` exactly.
- Long-only book, so only the +1 state is holdable (brief §5, and GOAL.md §3.1 — no shorts
  in an Indian delivery account).
- Cross-sectional score: 126d trailing momentum ranked **only among names flagged long**
  (brief §5 recipe).
- Portfolio: `PortfolioConfig()` defaults — 22 names, 12% single, 25% sector, 10% cash,
  monthly rebalance, 35% turnover budget. All enforced by `run_backtest`.
- Costs: `CostModel(segment="delivery", slippage_bps=5)` → **21.92 bps** all-in round trip
  on ₹1,00,000 notional. Charged on every rebalance against compounding equity.

### Declared parameter budget (5, declared before running)

| Variant | fast | slow |
|---------|------|------|
| V1 | 20 | 50 (catalog default) |
| V2 | 10 | 30 |
| V3 | 50 | 200 |
| V4 | 20 | 100 |
| V5 | 5 | 20 |

Rebalance frequency held at monthly throughout (the engine's evidence note; no Indian study
supports weekly). **5 variants tested, 0 exceeded.** The TRAIN-only ablations in
`diag.py` are diagnostics of the *mechanism*, not variants of the strategy — no reported
result depends on them.

Selection rule, fixed in advance: **max TRAIN Calmar**.

---

## 2. TRAIN (2016-01-01 → 2023-12-31) — selection only

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names |
|---------|-------|--------|--------|--------|----------|-----------|-------|
| V1 20/50 | 15.54 | 0.64 | −34.05 | 0.46 | 3.25 | 1.26 | 23.3 |
| V2 10/30 | 13.78 | 0.54 | −33.75 | 0.41 | 3.71 | 1.37 | 25.9 |
| V3 50/200 | 18.00 | 0.77 | −34.71 | 0.52 | 2.60 | 1.16 | 21.3 |
| V4 20/100 | 16.22 | 0.67 | −33.92 | 0.48 | 3.00 | 1.18 | 21.6 |
| **V5 5/20 (selected)** | **15.59** | **0.69** | **−28.25** | **0.55** | 3.93 | 1.57 | 27.4 |
| buy & hold | 18.38 | 0.78 | −34.92 | 0.53 | 2.64 | 1.18 | 22.2 |
| nsealgo composite | 21.30 | 0.96 | −32.92 | 0.65 | — | — | — |

Every DMA variant already trailed buy-and-hold on TRAIN. V5 was selected only because it
was the best *relative* Calmar and it happened to carry the shallowest drawdown.

---

## 3. TEST (2024-01-01 → 2026-10-01) — touched once, after selection was frozen

| variant | CAGR% | Sharpe | MaxDD% | Calmar | Turn x/y | Cost %/y | Names | Live% | Yrs+ |
|---------|-------|--------|--------|--------|----------|-----------|-------|-------|-------|
| V1 20/50 | 1.60 | −0.30 | −18.61 | 0.09 | 3.35 | 0.84 | 22.9 | 56.8% | 0.67 |
| V2 10/30 | 2.72 | −0.22 | −17.13 | 0.16 | 3.70 | 0.95 | 24.7 | 54.7% | 0.67 |
| V3 50/200 | 3.46 | −0.16 | −16.55 | 0.21 | 2.55 | 0.65 | 21.2 | 63.6% | 0.67 |
| V4 20/100 | 2.34 | −0.24 | −17.46 | 0.13 | 3.08 | 0.78 | 21.9 | 59.1% | 0.67 |
| **V5 5/20 (selected)** | **1.46** | **−0.32** | **−18.66** | **0.08** | 3.97 | 1.00 | 26.1 | 55.3% | 0.67 |
| **buy & hold** | **2.60** | **−0.22** | **−16.86** | **0.15** | 2.76 | 0.70 | 21.3 | — | — |
| **nsealgo composite** | **6.55** | **0.07** | **−14.84** | **0.44** | — | — | — | — |

Selected variant, TEST calendar years: 2024 **+16.27%**, 2025 **+3.29%**, 2026 (to 10-01)
**−13.28%**.
Buy-and-hold same years: +18.60%, +3.12%, −12.12%.

### TEST vs buy-and-hold

- Return: **worse by 1.14 pp/yr** (1.46% vs 2.60%).
- Drawdown: **worse by 1.80 pp** (−18.66% vs −16.86%).
- Sharpe: **worse** (−0.32 vs −0.22).
- Worse on every metric. The selection did not transfer: V5 was 4th of 5 on TRAIN Calmar
  relative to BH and last-but-one on TEST.

### Random-signal control (20 seeds, same % of bars long, same 126d ranking)

TEST CAGR: median **+5.11%**, range +3.43% to +8.71%.
**DMA (selected) lost to 20 of 20 random seeds.** A coin flip with the same exposure
beats this strategy by ~3.7 pp/yr.

### Cost stress (selected variant, TEST CAGR%)

| double slippage (10 bps) | triple (15 bps) | zero cost |
|---|---|---|
| 1.06 | 0.65 | 1.86 |

Gross (zero-cost) CAGR 1.86% vs net 1.46% → cost drag is only **~0.4 pp/yr**. The strategy
is not cost-killed; it simply has no edge to pay for the costs.

### Sanity checks

1. **Plausibility** — pass. 1.5–3.5% CAGR, nothing near the 40–50% unlevered ceiling.
2. **Weight count** — pass. 21.2–26.1 names held vs the 22 target; no residual accretion.
3. **Signal liveness** — pass. Long 53–64% of bars, well clear of the "effectively flat" 5%
   floor. The strategy was genuinely deployed.
4. **Cost drag** — pass/low. ~0.65–1.00 %/y, correctly charged on compounding equity.
5. **Negative control** — **FAIL. Lost to random 20/20.**

---

## 4. Why it fails (TRAIN-only diagnostic, `diag.py`)

The signal is **negatively** predictive on this universe.

Average forward 21d return of names, TRAIN:

| spans | flagged long | flagged not-long |
|-------|--------------|------------------|
| 20/50 | **+1.72%** | **+2.31%** |
| 50/200 | **+1.68%** | **+2.56%** |

The names in a downtrend (EMA fast below slow) *outperformed* the names in an uptrend by
50–90 bps over the next month. Applying the filter as a gate therefore deletes the
better half of the candidate set.

The mechanism is that the filter is redundant-but-harmful, not that it is noise. Because
the book already ranks by 126d momentum, the names an uptrend filter excludes are precisely
the highest-momentum names — the factor doing the work. Strip the filter entirely (pure
126d momentum ranking) and TRAIN goes to **18.38% / Sharpe 0.78 / Calmar 0.53**, i.e.
buy-and-hold momentum, exactly what the engine was built to do. The filter contributes
nothing and removes alpha.

Corroborating TRAIN ablations:

- Tightening the flag makes it monotonically worse — gap>0% 15.54% → gap>2% 11.31% →
  gap>5% 6.04% (Sharpe 0.00, book down to 5.5 names). More conviction in the signal, less
  money.
- Signal breadth has ~zero market-timing power: corr(EMA-20>50 breadth, forward 21d market
  return) = **−0.025**; for 50/200 it is **−0.122**, i.e. mildly wrong-signed.

So neither leg of the strategy works: the cross-sectional rank is a plain momentum rank in
disguise, and the trend gate is a mild negative-alpha screen.

---

## 5. Verdict

**No — `dual_moving_average` does not make money on NSE. It returns 1.46% CAGR out-of-sample
against 2.60% for buy-and-hold and ~5.1% for a random signal with identical exposure, losing
on return, drawdown and Sharpe alike, and it fails the negative-control bar 20/20.**

**Most likely reason:** the EMA-crossover gate is a redundant screen stacked on top of a
momentum rank that already captures the signal, and on NIFTY-50 in 2016–2023 it selected
*against* forward returns. Trend-following per-symbol has no marginal information once the
book is cross-sectional and long-only.

**One thing to try next:** drop the crossover entirely and treat DMA only as a *volatility
or regime* input — e.g. size the 126d-momentum book down when the 20/50 breadth reading is
low, instead of using it to exclude names. But note the TRAIN correlation above (−0.03,
−0.12) says that is unlikely to pay either; the honest expectation is that
`dual_moving_average` should be retired as a standalone entry and kept only as a
documentation case for why redundant filters on cross-sectional momentum destroy edge.

---

### Protocol compliance

- Parameters chosen on TRAIN only; TEST evaluated once, unchanged, after V5 was frozen.
- 5 variants declared, 5 run. No threshold tuning against the equity curve.
- No lookahead: EMA and momentum use closes up to and including *t*; `run_backtest` holds
  those weights from *t+1* (`held.shift(1) * rets`). No forward-fill from the future.
- Costs are the full Indian delivery stack including 18% GST, charged every rebalance.
- All reported numbers are net of costs unless explicitly labelled zero-cost.
- Survivorship bias (today's NIFTY-50, backfilled) applies to every table.