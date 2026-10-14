# Per-stock sweep — exposure decomposition

**Question:** do the 4,032 pairs have timing skill, or are they just under-invested?
**Data:** `PERSTOCK_test_results.jsonl`, engine `502028fd3954`, budget 12, 0 failures.

## 1. Against an exposure-matched benchmark, they lose

Exposure-matched buy-and-hold = `exposure x stock_CAGR + (1 - exposure) x 6.5%` (T-bill cash leg).

| group | n | CAGR | alpha vs B&H | **alpha vs matched B&H** | beat matched |
|---|---|---|---|---|---|
| all pairs | 4032 | −0.87% | −7.29% | **−7.59%** | **8.5%** |
| exposure ≥0.6 & sig vs null | 185 | +2.40% | −6.72% | **−5.72%** | **16.8%** |
| exposure ≥0.6 (any) | 266 | +1.85% | −8.87% | −7.58% | 12.0% |
| exposure <0.6 | 3766 | −1.07% | −7.18% | −7.59% | 8.3% |

Only **8.5%** of pairs beat simply being invested the same fraction of the time with **no
timing at all**. The edge is strongly asymmetric: **+3.05%** when a pair wins,
**−8.58%** when it loses.

`corr(alpha_vs_matched, exposure) = −0.091` — this is not an exposure artefact. The
strategies genuinely destroy value relative to a naive constant-fraction hold.

## 2. CORRECTION: the timing null is a straw man

Earlier I reported "2,145 pairs beat their own timing null — 10x chance — so the signal is
real." **That framing was wrong.** The null's **median CAGR is −15.15%/yr**.

A random-timing book that flips in and out of one volatile stock, paying 21.92 bps per
switch, loses catastrophically. Beating a −15% benchmark is not evidence of anything.

Confirming this directly: strategies that beat the null turn over **10.54x/yr**; those
that lose to it turn over **3.27x/yr**. The "winners" are the *higher*-turnover books.
`corr(turnover, CAGR) = +0.042`, i.e. turnover explains nothing. The apparent edge was
never a cost effect either — it was a bad benchmark.

## 3. Verdict

- There is **no demonstrable timing skill**. 91.5% of pairs lose to a naive
  constant-fraction hold.
- The high-exposure subset is **not** an exception: 83.2% still lose.
- The strategy families best represented at high exposure (`rsi_momentum_strategy` 26,
  `williams_r_strategy` 24) are **not** candidates for a larger budget search on this
  evidence.

**Do not escalate to `--budget 40`.** A deeper search over a set that loses to a
constant-fraction buy-and-hold 91.5% of the time finds more of the same, at 3x compute,
and — given 4,032 hypotheses were already tested — it would manufacture false positives
rather than remove them.

## 4. Structural diagnosis

Median exposure **0.301**. The catalog's monthly-rebalanced binary gates leave the book in
cash ~70% of the time. Whatever the gates know, they cannot express it in a way that
survives a fair benchmark.

## 5. What this does NOT say

- It does not say the *factors* are worthless — `reports/FACTOR_EVIDENCE.md` stands.
- It does not say no strategy exists; it says **none of these 84, on this data, at this
  cost, under this tax treatment, at this exposure, beats holding the stock.**
- It does not test shorting, sizing, or combining strategies — `ALLOW_SHORT=False`
  throughout, and the engine holds at most one name.
