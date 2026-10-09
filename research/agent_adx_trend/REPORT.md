# `adx_trend` on NSE NIFTY-50 — validation report

**Verdict: NO. This strategy does not make money on NSE.** It loses out-of-sample
to buy-and-hold, to the existing nsealgo composite, and to its own momentum ablation.

Source: `src/cryptobot/strategies/catalog/adx_trend.py`
Scripts: `research/agent_adx_trend/` (`step0_audit`, `step1_train`, `step2_test`,
`step3_ablations`, `harness.py`)
Data: `load_universe("data/nse")` — 48 symbols, 4,629 daily bars, 2008-01-01 → 2026-10-01
All numbers net of the full Indian delivery stack at **21.92 bps** round trip
(11.92 bps statutory + 10 bps slippage across both legs).

---

## 0. The finding that settles it: the strategy has no signal

`AdxTrendStrategy.signal` computes an ATR over `config.period`, then **discards it** —
`a` is used only in a NaN warmup guard. The returned value is:

```python
return 1 if closes[-1] > closes[-2] else -1
```

Verified mechanically (`harness.verify_source_signal`), not by reading:

| check | result |
|---|---|
| signal equals `sign(close[t] − close[t−1])` | **370 / 370 bars** |
| `period` changes the signal in steady state? | **No** — `period=14` and `period=200` give identical signals on all 190 comparable bars |
| fraction of bars long | 45.3% (synthetic), **49.5%** on NSE TEST |

So `adx_trend` is a **1-bar sign-of-return** wearing an ADX label. `config.period` is
dead code. Any performance it shows is the ranking I wrapped around it, not the strategy.

**TEST-window direct test of the signal itself** — flag on bar *t* vs return on *t+1*
(comparing to *t* would be tautological, since the flag *is* `sign(ret[t])`):

| group | n | mean ret[t+1] |
|---|---|---|
| close[t] > close[t−1] | 16,241 | **+0.0263%** |
| close[t] ≤ close[t−1] | 16,589 | **+0.0459%** |
| spread | | **−2.0 bps/day** |

The spread is **negative**. In TEST the signal points the wrong way. It is not weak —
it is noise.

---

## 1. Declared parameter budget (written before any backtest)

**5 variants, all evaluated on TRAIN only. Budget not exceeded.**

| # | name | construction |
|---|---|---|
| V1 | `V1_mom126` | flag = ret₁>0, rank by 126d momentum (brief's recipe) |
| V2 | `V2_mom252` | flag = ret₁>0, rank by 252d momentum |
| V3 | `V3_mom21` | flag = ret₁>0, rank by 21d momentum |
| V4 | `V4_trend14` | flag = ret₁>0, rank by 14d return (= `config.period`) |
| V5 | `V5_atr14` | flag = ret₁>0, rank by 14d move ÷ ATR₁₄ (a real trend-strength read) |

Held constant, not part of the budget: monthly rebalance, `PortfolioConfig` defaults
(22 target / 30 max names, 12% single name, 25% sector, 10% cash, 0.35 turnover budget),
`CostModel(segment="delivery", slippage_bps=5)`.

Selection rule fixed in advance: **highest TRAIN Sharpe** (tie-break Calmar), then that
one variant frozen and run once on TEST.

## 2. TRAIN (2016-01-01 → 2023-12-31, 1,975 bars) — the selection set

```
label                     set       CAGR%  Sharpe   MaxDD%  Calmar  Turn/y  Cost/y%  Names
V1_mom126                 TRAIN     15.63    0.68   -30.71    0.51    4.03     1.60   28.7
V2_mom252                 TRAIN     15.96    0.70   -30.70    0.52    3.99     1.57   28.6
V3_mom21                  TRAIN     13.60    0.55   -31.67    0.43    4.11     1.51   29.5
V4_trend14                TRAIN     14.20    0.59   -31.22    0.45    4.12     1.53   29.6
V5_atr14                  TRAIN     14.16    0.59   -31.39    0.45    4.11     1.52   29.5
TRAIN buy-and-hold        TRAIN     21.46    0.90   -36.66    0.59    0.12     0.13   48.0
```

**Selected: `V2_mom252`** (TRAIN Sharpe 0.70).

Two things were already visible on TRAIN and I flag them as warnings, not as reasons to
iterate: every variant lands in a 13.6–16.0% band regardless of ranking horizon (21d →
252d — a 12× change that moves CAGR by 2.4pp, which means the *ranking* is doing the work
and the *signal* is doing none), and all five lose to buy-and-hold on TRAIN.

## 3. TEST (2024-01-01 → 2026-10-01, 685 bars) — the reportable number

Frozen `V2_mom252`, evaluated unchanged, TEST touched exactly once:

```
label                     set       CAGR%  Sharpe   MaxDD%  Calmar  Turn/y  Cost/y%  Names   Total%  Yr+
strategy V2_mom252        TEST       5.62   -0.01   -14.69    0.38    4.09     1.07   27.9    16.6   67%
buy-and-hold (eq-wt)      TEST       8.16    0.18   -15.91    0.51    0.36     0.10   48.0    24.6   67%
nsealgo composite         TEST       6.55    0.07   -14.84    0.44    2.07     0.55   21.3    19.5   67%
random signal x20         TEST       5.37*   —       —        —       —       —       —       —       —
                                                    (*mean; median 5.20, p5 3.98, p95 7.81)
```

Year-by-year (2026 is partial, through 2026-10-01):

| | 2024 | 2025 | 2026* |
|---|---|---|---|
| strategy | +17.75% | +8.72% | −8.93% |
| buy-and-hold | +20.13% | +13.34% | −8.47% |
| composite | +22.57% | +7.16% | −9.01% |

### vs buy-and-hold, identical window and identical cost assumption

- **Return: worse.** 5.62% vs 8.16% CAGR = **−2.54pp/yr**.
- **Drawdown: better, marginally.** −14.69% vs −15.91% = **+1.22pp** shallower.
- Sharpe is **−0.01 net of the 6.5% risk-free rate** — the book earned less than cash.

### vs the nsealgo composite

**Worse by 0.93pp/yr** (5.62% vs 6.55%), on a slightly deeper drawdown. The existing
composite already captures this factor set better.

## 4. Negative controls

Two controls, 20 seeds each, TEST window:

| control | construction | mean CAGR | strategy beats |
|---|---|---|---|
| random flag + momentum rank | isolates the flag; ranking held constant | 5.37% | **12 / 20** |
| random signal, no ranking | pure coin, same % of name-days long | 4.92% | 14 / 20 |

The first control is the important one: it holds the ranking machinery fixed and
randomises only the signal. The strategy wins 12/20 — under a fair coin that is
**p ≈ 0.41 (two-sided ≈ 0.82)**. **Not significant.** The strategy is
indistinguishable from a coin flip dressed in a momentum ranking.

## 5. Ablations — where the damage comes from

Diagnostic runs *after* the frozen TEST result; not used for selection.

| | TRAIN CAGR% | TEST CAGR% | TEST MaxDD% | TEST turn |
|---|---|---|---|---|
| A1 momentum only, **no adx flag** | 20.54 | **8.82** | −16.18 | 1.97x |
| A2 adx flag only, all equal-weight | 20.02 | 6.66 | −14.40 | 0.16x |
| frozen V2 (flag + rank) | 15.96 | 5.62 | −14.69 | 4.09x |
| A3 equal-weight universe | 21.46 | 8.16 | −15.91 | 0.36x |

**Deleting the strategy's signal improves TEST CAGR from 5.62% → 8.82%.** TRAIN and TEST
agree on this, so it is not a TEST-window artefact.

Decomposition of the 3.20pp/yr the flag gives up:

| | pp/yr | share |
|---|---|---|
| extra turnover cost (0.53% vs 1.07% drag) | 0.53 | 17% |
| **worse name selection** | **2.66** | **83%** |

The flag is not merely expensive — it is **actively choosing worse names**. Half the
universe is discarded on 1-bar noise, and the survivors crowd into the same names.

## 6. Sanity checks

| # | check | result |
|---|---|---|
| 1 | Plausibility | 5.62% CAGR — far inside the 40–50% ceiling. No lookahead, no compounding bug |
| 2 | Weight count | 27.9 avg names (config hard-bounds at 30; diagnostic with `max_names=22` → 20.2). Max top weight 5.7% vs 12% cap. **Not** 48 — no residual accretion |
| 3 | Signal liveness | 49.5% of name-days long (floor ~5%). Genuinely long, not a flat book |
| 4 | Cost drag | gross 6.05% → net 5.62% = **only 0.43pp/yr**. Costs are *not* the reason this fails |
| 5 | Negative control | 12/20 random seeds — p ≈ 0.41. Fails the minimum bar |
| 6 | Beta | **β = 0.83, daily corr 0.93** vs equal-weight market. This is a slightly de-risked beta book, not an alpha book |

Cost stress (`GOAL.md` §6.4): 2× slippage (31.92 bps) → CAGR 5.19%, Sharpe −0.04. The
result is robust to costs and still bad — which is the point.

**Protocol compliance:** parameters were selected on TRAIN only; TEST was referenced for
the first time in `step2_test.py`, after `V2_mom252` was frozen. No TEST number
influenced any choice. The step-3 ablations touch both windows and are labelled
diagnostics.

## 7. Most likely reason it failed

**The strategy contains no signal.** `adx_trend.signal()` reduces to a 1-bar
sign-of-return whose TEST next-bar spread is −2.0 bps/day — negative. Used as an
eligibility filter in a long-only book, it throws away half the universe on one day of
noise, which degrades selection (83% of the damage) and doubles turnover (17%). Every
variant landed in a 13.6–16.0% TRAIN band no matter how the ranking was changed, which
is the tell: the ranking was carrying 100% of the load and the signal 0%.

Note the label is doubly misleading: `AdxTrendConfig.period` never reaches the decision,
and `atr` is called and thrown away. A strategy named after ADX that never computes ADX
is the bug, not a tuning problem.

## 8. What I would try next

**Delete it — do not tune it.** There is no parameter surface worth spending budget on,
because the only live input is a 1-bar sign.

If an ADX-shaped signal is wanted, it has to be a genuinely different strategy: Wilder
ADX with a **+DI/−DI crossover and a persistence/adx-threshold filter**, held on the
5–60 day horizon `GOAL.md` specifies — not a 1-bar sign. But A1 already shows the
working ingredient is 252d momentum ranking (8.82% TEST), which the nsealgo composite
already uses (6.55% TEST); so the honest expectation for a well-built ADX variant is
*neutral*, and it would need to beat A1 — not this — to be worth anything.

## 9. One reproduction note

The brief cites ~11.9 bps round trip. That is `CostModel.round_trip_bps` (statutory
only, matching the CLI). The backtest engine uses `all_in_round_trip_bps`, which adds
2 × 5 bps of slippage = **21.92 bps**, because a portfolio-level simulator never calls
`fill_price` and would otherwise charge zero slippage. Every number above is net of
21.92 bps. The brief's figure is correct for what it measures; it is not what the engine
charges.