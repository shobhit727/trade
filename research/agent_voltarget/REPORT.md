# `volatility_target` on NSE NIFTY-50 — validation report

**Verdict: NO. This strategy does not make money on NSE.** It loses out-of-sample to
buy-and-hold by 5.59pp/yr and to the existing nsealgo composite by 3.45pp/yr, with a
*deeper* drawdown than both. Its signal is not merely weak out of sample — out of
sample it is **significantly worse than random** at the name-day level
(−5.86 bps/day vs everything else, Welch p = 0.0014).

Source: `src/cryptobot/strategies/catalog/volatility_target.py`
Scripts: `research/agent_voltarget/` — `harness.py`, `step0_audit.py`,
`step1_train.py`, `step2_test.py`, `step3_controls.py`, `step4_signal_power.py`
Data: `load_universe("data/nse")` — 48 symbols, 4,625 daily bars, 2008-01-01 →
2026-10-01. TRAIN 2016-01-01 → 2023-12-31 (1,973 bars), TEST 2024-01-01 →
2026-10-01 (684 bars).
All numbers net of the full Indian delivery stack at **21.92 bps** round trip
(11.92 bps statutory + 2 × 5 bps slippage) — the figure `run_backtest` actually charges.

> ⚠️ **Survivorship bias is present and is not corrected for.** The NIFTY-50 panel is
> today's constituents backfilled to 2008. Every number here inherits that bias.
> Quote these results with their end date attached.

---

## 0. The strategy, and the one thing it gets wrong

`VolTargetStrategy.signal(closes, highs, lows, volumes)`:

```python
b = atr(highs, lows, closes, self.config.period)      # SMA of last `period` true ranges
if b != b:                                            # NaN warmup guard
    return 0
if closes[-1] > closes[-2] and b / max(closes[-1],1e-9) < self.config.target * 2:
    return 1
if closes[-1] < closes[-2] and b / max(closes[-1],1e-9) < self.config.target * 2:
    return -1
return 0
```

A genuine two-part flag, verified mechanically on 440 synthetic bars
(`harness.verify_source_signal`, 440/440 match):

| check | result |
|---|---|
| signal == (direction) AND (`ATR/close < 2×target`) | **440 / 440 bars** |
| `target` live? (`0.002` / `0.01` / `0.05` → long share 0% / 51.8% / 52.0%) | **yes** |
| `period` live? (`period=60` vs `14`) | **yes** |

Unlike `adx_trend`, neither parameter is dead code. Both reach the decision. The
strategy is a **low-volatility-regime + 1-bar-continuation** flag. Everything that
follows is about whether that flag has information content on Indian equities.

**The unit error is the finding.** `target=0.01` is compared against `ATR/close`, so
the effective threshold is **2.0% of price**. Measured on NSE:

| window | mean | p25 | **median** | p75 | p95 |
|---|---|---|---|---|---|
| TRAIN | 2.79% | 2.03% | **2.53%** | 3.21% | 4.67% |
| TEST | 2.31% | 1.82% | **2.18%** | 2.65% | 3.62% |

A 2.0% daily ATR/price is the **25th percentile in TRAIN**. The default threshold is
calibrated for 24/7 crypto, where a 2% daily range is unremarkable; on Indian large
caps it is a quiet-market screen, not a volatility regime. And TEST volatility is
*lower* than TRAIN, so the same fixed threshold admits **67% more** names out of
sample than in:

| threshold | TRAIN name-days | TEST name-days |
|---|---|---|
| NATR < 2% | 22.5% | **37.6%** |
| NATR < 3% | 66.2% | **86.1%** |
| NATR < 4% | 86.6% | 97.1% |

Any threshold fixed on TRAIN is therefore a *different* rule in TEST. That is a real
structural hazard for this strategy, and it is disclosed here before the results.

## 1. DECLARED PARAMETER BUDGET

**5 variants, declared before any backtest ran. Budget not exceeded — see §8.**

| # | name | flag | ranking |
|---|------|------|---------|
| V1 | `V1_flag_mom126` | up-day AND `NATR14<2%` (brief's recipe) | 126d momentum |
| V2 | `V2_flag_lowvol` | same flag | −60d realised vol |
| V3 | `V3_flag_momvol` | same flag | 126d momentum ÷ 60d vol |
| V4 | `V4_atronly_mom126` | `NATR14<2%` only — **drops the 1-bar direction test** | 126d momentum |
| V5 | `V5_flag3pct_mom126` | up-day AND `NATR14<3%` (`target=0.015`) | 126d momentum |

Held constant: monthly rebalance; `PortfolioConfig()` defaults (22 target / 30 max
names, 12% single name, 25% sector, 10% cash, 35% turnover budget);
`CostModel(segment="delivery", slippage_bps=5)`; ATR = SMA of trailing true ranges,
matching `cryptobot.strategies.indicators.atr` exactly.

Selection rule fixed in advance: **highest TRAIN Sharpe**, tie-break Calmar. The winner
is frozen to `frozen.txt` and read once.

## 2. TRAIN (2016-01-01 → 2023-12-31) — the selection set

```
label                   set       CAGR%  Sharpe   MaxDD%  Calmar  Turn/y  Cost/y%  Names    Total%  Yr+
V1_flag_mom126         TRAIN      5.22   -0.20   -13.06    0.42    2.83     1.51    5.5      50.9   62%
V2_flag_lowvol         TRAIN      5.17   -0.21   -13.06    0.40    2.83     1.51    5.6      50.3   62%
V3_flag_momvol         TRAIN      5.18   -0.20   -13.06    0.40    2.83     1.51    5.5      50.5   62%
V4_atronly_mom126      TRAIN      7.13    0.12   -10.98    0.65    3.12     1.82    8.9      74.6   75%
V5_flag3pct_mom126     TRAIN      7.19    0.12   -22.32    0.32    4.00     2.29   15.3      75.3   75%
TRAIN buy-and-hold     TRAIN     21.49    0.90   -36.66    0.59    0.12     0.13   48.0     382.8  100%

SELECTED: V4_atronly_mom126 (Sharpe 0.12, Calmar 0.65)
```

**Frozen: `V4_atronly_mom126`** (`frozen.txt`).

Three things were visible on TRAIN and are flagged, not acted on:

1. **V1/V2/V3 are indistinguishable** (5.17–5.22%). The 1-bar direction flag halves an
   already-thin universe, and at 5.5 held names the *ranking never gets to choose*. The
   signal, not the ranking, determines the entire result.
2. **Every variant loses to buy-and-hold by 14–16pp/yr on TRAIN.**
3. **Sharpe 0.12 net of a 6.5% risk-free rate** — the winner barely beat cash in TRAIN,
   and 22% of its CAGR came from holding fewer names, i.e. from cash, not from alpha.

## 3. TEST (2024-01-01 → 2026-10-01, 684 bars) — the reportable number

Frozen `V4_atronly_mom126`, evaluated unchanged. `step2_test.py` refuses to run if
`frozen.txt` is not one of the five declared names.

```
label                   set       CAGR%  Sharpe   MaxDD%  Calmar  Turn/y  Cost/y%  Names    Total%  Yr+
V4_atronly_mom126      TEST       2.59   -0.40   -16.14    0.16    3.81     1.90   14.4       7.4   67%
TEST buy-and-hold       TEST       8.18    0.18   -15.90    0.51    0.36     0.10   48.0      24.6   67%
nsealgo composite       TEST       6.04    0.03   -15.22    0.40    2.08     1.10   21.3      17.9   67%
```

| comparison | return | drawdown | Sharpe |
|---|---|---|---|
| **vs buy-and-hold** (identical window, identical 21.92 bps) | **−5.59pp/yr** | **−0.24pp (deeper)** | −0.58 |
| **vs nsealgo composite** | **−3.45pp/yr** | **−0.92pp (deeper)** | −0.43 |

It is worse on return **and** worse on drawdown. There is no risk-adjusted consolation
prize here — the strategy is not a lower-beta version of the market that trades return
for stability, it is simply worse.

Year-by-year (2026 partial, through 2026-10-01):

| | 2024 | 2025 | 2026* |
|---|---|---|---|
| strategy | +9.78% | +14.33% | −14.41% |
| buy-and-hold | +20.13% | +13.35% | −8.47% |
| composite | +21.91% | +6.61% | −9.31% |

Sharpe is **−0.40 net of 6.5% risk-free**. The book lost to cash in every
risk-adjusted sense.

## 4. Sanity checks

| # | check | result |
|---|---|---|
| 1 | Plausibility | 2.59% CAGR — far inside the 40–50% ceiling. No lookahead, no compounding bug |
| 2 | Weight count | 14.4 avg names, config max 30, target 22. Max top weight 7.10% vs 12% cap. **Not** 48 — no residual accretion |
| 3 | Signal liveness | V4 mask active on 37.64% of TEST name-days, median 16 eligible names/bar, 3.4% of bars with zero. Above the ~5% floor — the book is genuinely long, not flat |
| 4 | Cost drag | 1.90%/yr. Cost stress (below) moves CAGR 2.59 → 3.37 at zero slippage, 1.81 at 2×, 1.04 at 3×. **Costs are not the reason this fails** — it fails at zero cost too |
| 5 | Negative control | 15/20 random-flag seeds, exact binomial p = 0.041. **Beats a coin, but loses to the market.** See §5 for why that p-value is misleading |
| 6 | Beta | **β = 0.52**, daily corr 0.82 vs equal-weight market. Half-beta book, and still half the market's return |
| 7 | **Engine reproducibility** | `src/nsealgo/backtest/engine.py` was modified by another agent **twice while this ran**. All scripts now assert the engine's *executable code* hash (AST with docstrings stripped, `773e723c…`) and abort on drift. Every step was re-run under one pin; TRAIN and TEST output are byte-identical across the last two engine revisions, confirming those edits were non-behavioural |

Cost stress (`GOAL.md` §6.4), frozen variant, TEST:

| model | round trip | CAGR | Sharpe | MaxDD |
|---|---|---|---|---|
| zero_cost | 11.92 bps | 3.37% | −0.31 | −15.62% |
| **base** | **21.92 bps** | **2.59%** | **−0.40** | **−16.14%** |
| double_slippage | 31.92 bps | 1.81% | −0.49 | −16.65% |
| triple_slippage | 41.92 bps | 1.04% | −0.58 | −17.16% |

Robust to costs, still bad. That is the point.

## 5. Negative controls — and why "beats a coin" is not the same as "has an edge"

| control | construction | mean TEST CAGR | strategy beats | p |
|---|---|---|---|---|
| A | random flag, same frequency, ranking fixed | 1.12% | 15/20 | 0.041 |
| B | pure random signal, no ranking | 1.15% | 15/20 | 0.041 |

The `p = 0.041` looks like significance. **It is not, and reading it that way is the
trap this report exists to avoid.** Both controls land at ~1.1% because the eligible
universe is *small and the turnover budget binds* — the cost floor for a book that
rebalances 3.8×/yr is around 1–2% CAGR, and a random flag in a 37.6%-frequency mask
reproduces it almost exactly. The strategy reaches 2.59%, i.e. it clears the coin by
about 1.4pp/yr. Meanwhile buy-and-hold, over the identical window at the identical cost,
returns 8.18%. The honest reading of control A is: *the flag is worth about the cost of
running the book, not the cost of running it.*

Mechanically, controls A and B return identical statistics because the frozen variant's
mask admits a mean of **18.1 names against a 22-name target**, and **60% of TEST bars
have fewer eligible names than the target**. When the mask admits fewer names than the
book wants, the engine holds all of them and **the ranking is a no-op**. The score — the
entire momentum machinery — does not get to choose on most days. That is the real reason
V1/V2/V3 are identical too.

## 6. Where the damage comes from — ablations

Diagnostic runs *after* the frozen TEST number; not used for selection.

| ablation | TRAIN CAGR% | TRAIN Sharpe | TEST CAGR% | TEST Sharpe | TEST MaxDD% | TEST turn |
|---|---|---|---|---|---|---|
| C1 momentum only, **no flag** | 17.56 | 0.73 | **1.58** | −0.30 | −18.82 | 2.77x |
| C2 flag only, equal-weight | 5.15 | −0.21 | **3.06** | −0.51 | −12.67 | 3.53x |
| C3 vol regime only + mom rank | 7.13 | 0.12 | 2.59 | −0.40 | −16.14 | 3.81x |
| C4 direction only + mom rank | 10.94 | 0.44 | 3.51 | −0.24 | −12.37 | 4.09x |
| C5 **frozen V4** | 7.13 | 0.12 | 2.59 | −0.40 | −16.14 | 3.81x |
| C6 buy-and-hold | 17.56 | 0.73 | 8.18 | 0.18 | −15.90 | 0.36x |

Two decompositions, both pointing the same way:

**On TRAIN, the flag costs 10.4pp/yr** (17.56 → 7.13). TRAIN and TEST agree that adding
the volatility filter makes things worse — so this is not a TEST-window artefact.

**Within the flag, the direction half is the active ingredient and the vol half is the
drag.** C4 (direction only) reaches 3.51% TEST; C3 (vol only, the frozen variant) gets
2.59%. Adding the vol filter to the direction signal *subtracts 0.92pp/yr*. Meanwhile
C1 shows the momentum ranking with no flag at all gets 1.58% — worse than the flag does.
So on TEST the flag is doing *something*, and on TRAIN it is clearly destroying value.
The two windows disagree about the sign, which is itself the finding: **there is no
stable edge in this flag in either direction.**

## 7. Does the signal have information content at all? (diagnostic)

Name-day level, next-day return by regime group. This is the cleanest test of the
strategy's actual claim — no portfolio construction, no costs, no ranking.

TRAIN, `NATR14 < 3%`:

| group | n | mean bps/day | t | p |
|---|---|---|---|---|
| flagged (up-day & calm) | 32,668 | +9.32 | 10.69 | 0.000 |
| up-day but high vol | 13,935 | +9.90 | 4.39 | 0.000 |
| calm but down day | 30,027 | +6.40 | 6.87 | 0.000 |
| neither | 14,620 | +11.84 | 5.43 | 0.000 |

**flagged − all-other-groups: +0.73 bps/day, Welch t = 0.58, p = 0.56.** On TRAIN the
flag carries **no** information beyond the unconditional mean.

TEST, `NATR14 < 3%`:

| group | n | mean bps/day | t | p |
|---|---|---|---|---|
| flagged (up-day & calm) | 13,958 | **+0.26** | 0.20 | 0.842 |
| up-day but high vol | 2,292 | +15.50 | 3.26 | 0.001 |
| calm but down day | 14,277 | +0.63 | 0.50 | 0.618 |
| neither | 2,255 | **+31.37** | 6.21 | 0.000 |

**flagged − all-other-groups: −5.86 bps/day, Welch t = −3.20, p = 0.0014.**

Same conclusion at the default 2% threshold: TRAIN +0.32 bps (p = 0.82),
TEST **−4.82 bps (p = 0.015)**.

This is the core negative finding, and it survives both thresholds and both windows:
**the flagged group is the worst-performing regime group out of sample, and it is
significantly so.** The group the strategy is built to hold earns +0.26 bps/day; the
group it is built to avoid — high-volatility, down-day names — earns +31.37 bps/day, a
120× difference. Whatever the strategy's authors intended, on recent NSE data its
eligibility rule selects the worst bucket available.

## 8. Protocol compliance

- Parameters selected on **TRAIN only**, by a rule declared before any run.
- **TEST read once**, in `step2_test.py`, after `frozen.txt` was written from TRAIN Sharpe.
- **Parameter budget: 5 variants tested, exactly as declared. Not exceeded.** Every
  additional configuration in this report (`C1`–`C4`, cost-stress models, threshold
  tables) is labelled a post-hoc diagnostic and was not available to selection.
- No lookahead: every score input on day *t* uses closes through *t*; `run_backtest`
  shifts held weights by one bar.
- **Infrastructure hazard found and contained.** Another agent modified
  `src/nsealgo/backtest/engine.py` twice during this run (turnover-budget logic was
  rewritten). The first occurrence moved the same frozen variant from 3.50% to 2.09%
  TEST CAGR with no change to any input of ours. Every script now calls
  `assert_engine_pinned()`, which hashes the engine's executable code (AST, docstrings
  stripped) and aborts on drift, so results produced under different engine behaviour
  cannot be silently mixed. **Every number in this report comes from one pin**
  (`773e723c…`); TRAIN and TEST output are byte-identical across the last two engine
  revisions, so those two edits were cosmetic.

## 9. Most likely reason it failed

**The strategy implements "volatility targeting" as a volatility *screen*, and then
uses it in a way the data does not support.** Real volatility targeting scales position
size inversely to realised volatility to hit a constant risk budget — a beta decision
that leaves expected return intact while cutting drawdown. This implementation does not
scale anything: it *excludes* high-volatility names entirely, which removes return
without removing risk, because the excluded names are exactly the ones that were
rebounding hardest in TEST (+31.37 bps/day).

Three compounding errors, in order of damage:

1. **Wrong unit.** `ATR/close < 2%` is a 25th-percentile screen on NSE, calibrated for
   crypto. It is not a volatility regime.
2. **1-bar continuation on a 5–60 day holding horizon.** The direction term is noise at
   the frequency it is evaluated and only halves an already-thin universe.
3. **The filter cannot be the ranking.** With a median of 4–16 eligible names against a
   22-name book, the cross-sectional score never gets consulted on most days — so no
   amount of ranking cleverness can rescue the construction.

The strategy is not dead in the trivial `adx_trend` sense (its parameters are live).
It is a **well-formed signal applied with the wrong calibration to the wrong horizon on
the wrong market**, and the out-of-sample evidence is negative rather than merely weak.

## 10. What I would try next — one thing

**Delete the eligibility filter and keep only what the flag's own logic implies:**
replace the binary screen with a continuous **inverse-volatility position size** on the
momentum composite that already exists in `nsealgo.factors.core`. That is what
"volatility targeting" means, it uses the strategy's own ATR input for its intended
purpose, and `PortfolioConfig.vol_lookback` already implements the sizing the engine
needs — so it is a change to the *factor*, not a new subsystem.

I would **not** spend budget re-tuning `target`. The threshold table in §0 shows the
choice between 2% and 5% moves eligibility from 22% to 93% of name-days without ever
making the flagged group outperform the unflagged one — and §7 shows the sign of the
effect flips between windows. That is a coin with a dial on it, and turning the dial is
exactly the "tune until the curve looks good" the protocol forbids.

---

### Reproduction

```bash
.venv/bin/python research/agent_voltarget/step0_audit.py        # data + signal verification
.venv/bin/python research/agent_voltarget/step1_train.py        # TRAIN-only selection -> frozen.txt
.venv/bin/python research/agent_voltarget/step2_test.py         # TEST, read once
.venv/bin/python research/agent_voltarget/step3_controls.py     # controls, ablations, cost stress
.venv/bin/python research/agent_voltarget/step4_signal_power.py # name-day information content
```

### A note on the 11.92 vs 21.92 bps figure

The brief's `round_trip_bps(100_000)` = 11.92 bps is `CostModel.round_trip_bps`
(statutory only: STT both sides, stamp, exchange txn, SEBI, DP, GST). What
`run_backtest` actually charges is `all_in_round_trip_bps` = **21.92 bps**, because a
portfolio-level simulator applies weight changes directly and never calls
`fill_price`, so it folds in 2 × 5 bps of slippage explicitly. Every number in this
report is net of 21.92 bps. The brief's figure is correct for what it measures; it is
not what the engine charges, and quoting it as the loaded cost would overstate every
result in this report by roughly 0.8pp/yr at this turnover.