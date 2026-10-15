# Per-stock sweep — where the alpha actually comes from

**Question:** is a long/flat, mostly-invested book achievable in this catalog, and if so
does it have an edge?
**Data:** 4,032 pairs, engine `502028fd3954`, budget 12, 0 failures.

## 1. Yes — but only two strategies can do it

Median exposure across the catalogue is **0.301**. But exposure is a property of the
*strategy*, and two of the 84 can run a nearly always-invested book:

| strategy | best exposure | stocks >60% exposure | mean alpha vs B&H |
|---|---|---|---|
| `williams_r_strategy` | **96.9%** | 47/48 | −3.86% |
| `rsi_momentum_strategy` | **96.9%** | 45/48 | −4.04% |
| `open_range_breakout` | 93.7% | 13/48 | −7.94% |
| `cumulative_delta_strategy` | 77.5% | 12/48 | −9.32% |
| catalogue median | 30.1% | — | −7.29% |

Max exposure achieved by *any* pair: 96.9%. 259 of 4,032 pairs exceed 60%.

So the structural objection ("monthly binary gates keep the book in cash 70% of the
time") is real but **not universal** — it is true of the catalogue median and false of
its best two members.

## 2. But the alpha is not what it looks like

Alpha against buy-and-hold decomposes into two channels:

```
alpha  =  avoidance  +  timing
avoidance = (1 - exposure) x (risk_free - stock_CAGR)   <- gain from being OUT
timing    = alpha - avoidance                          <- value of WHICH days you were in
```

| group | n | alpha | = avoidance | + timing |
|---|---|---|---|---|
| all pairs | 4032 | −7.29% | **+0.30%** | **−7.59%** |
| exposure > 0.6 | 259 | −9.12% | −1.42% | −7.70% |
| `williams_r_strategy` | 48 | −3.86% | +0.28% | **−4.14%** |
| `rsi_momentum_strategy` | 48 | −4.04% | +0.65% | **−4.69%** |
| exposure < 0.3 | 2012 | −6.22% | +0.73% | −6.95% |

**The timing channel is negative for every group, without exception.** It is positive in
only **8.5%** of the 4,032 pairs. The avoidance channel is positive in exactly **50.0%**
— a coin flip.

## 3. What this means

This is stronger than "no edge". The signals are not merely uninformative; on this data,
in this catalogue, with monthly rebalancing and a single name per book, they
**consistently pick worse days than holding**.

Raising exposure does not rescue it. The two strategies that can run ~97% invested lose
*less* than the catalogue average (−3.9% vs −7.3%), and that improvement comes entirely
from a slightly positive avoidance channel. Their timing channel is still −4.1% and
−4.7%: at near-full exposure they are very nearly buy-and-hold, and slightly worse at it.

## 4. What this rules out

- **Not a lever to pull.** No amount of parameter search moves the timing channel from
  −7.6% toward 0; that would require a different signal.
- **Not fixable by sizing or rebalance frequency.** The timing channel is negative in
  91.5% of pairs regardless of exposure band.
- **Not evidence the factors are worthless.** `reports/FACTOR_EVIDENCE.md` stands on its
  own evidence; what fails here is these particular implementations as long/flat,
  single-name, monthly books.

## 5. Not tested (and therefore not claimed)

Shorting (`ALLOW_SHORT=False` throughout), multi-name portfolios, position sizing, and
frequency other than monthly. A strategy that is short a stock it has a bearish signal on
would convert part of this negative timing into something; the current engine cannot
express it, and this document says nothing about whether that would help.
