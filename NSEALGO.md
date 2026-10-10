# nsealgo — NSE NIFTY-50 systematic trading

**Read [`GOAL.md`](GOAL.md) first.** It is the binding constitution: capital, targets,
hard risk limits, anti-fraud rules, and the gates that must all pass before any real
capital is deployed.

> ## Current status: 9.71% annualised out-of-sample — Band D — not capital-authorised
>
> | | |
> |---|---|
> | **OOS annualised** | **9.71%** (walk-forward, 2008-01-01 → 2026-10-01, 19.0y) |
> | **OOS monthly** | **+0.775%** |
> | Requested target | 3.000%/month (42.6% annualised) — **4.4× short** |
> | **Bias-corrected** | **≈3.6%/yr** (provisional — see "Known limitations" #1) |
> | OOS Sharpe | **0.34** |
> | OOS max drawdown | **−14.92%** |
> | OOS Calmar | **0.65** |
> | OOS positive years | **10/13 (77%)** |
> | Benchmark (same windows) | 17.12% CAGR / 0.68 Sharpe → **−7.41pp/yr** |
> | Band | **D** |
> | Verdict | ⛔ **NO DEPLOY** — six gate checks run, **four fail** |
>
> Full evidence: [`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md) — **read the
> addendum at the top first**; the body of that file is the superseded v1 measurement,
> kept as the historical record.

> ### ⚠️ Read this before quoting any number from this repo
>
> **The headline got worse three times, and every step down was a bug fix.**
>
> | Measurement | OOS CAGR | Sharpe | What changed |
> |---|---|---|---|
> | v1 | 13.40% | 0.66 | original measurement, data to 2026-08-25 |
> | v2 | 10.97% | 0.44 | +27 sessions, portfolio-limit fix (25.66% single name → 10.80%) |
> | v2b | 9.89% | 0.35 | **the engine was charging HALF the real cost stack** |
> | **v3 — current** | **9.71%** | **0.34** | **residual-weight dilution in `apply_turnover_budget`** |
>
> **Not one of the intermediate numbers was valid.** A reader who stopped at v1 was reading
> a figure **38% too high**.
>
> Separately: **27 extra trading days — about six weeks — moved Sharpe 0.66 → 0.44 and the
> band from C to D**, with no code change at all. A result whose band depends on where you
> stop measuring is not a result that gets capital. **No number from this system should be
> quoted without its end date attached.**

**The 3%/month target is not achievable.** It is 3.0–3.4× the entire long-run return of
the index (NSE NIFTY-50 TRI: 12.44% over 20 years, 14.2% since 1999), and Indian active
fund managers earn ≈0 net alpha after fees across 425 funds. Evidence:
[`reports/FACTOR_EVIDENCE.md`](reports/FACTOR_EVIDENCE.md).

---

## Quick start

```bash
# ---- research & tests run on the host venv (fast) ----
.venv/bin/python -m pytest tests/unit -q -k nsealgo      # 98 tests
.venv/bin/python -m nsealgo.cli costs                     # cost calibration
.venv/bin/python -m nsealgo.cli limits                    # hard risk limits
.venv/bin/python research/audit_data.py                   # data audit
.venv/bin/python research/validate.py                     # walk-forward OOS

# ---- the app runs in Docker ----
docker compose -f docker-compose.nse.yml build
docker compose -f docker-compose.nse.yml run --rm nsealgo paper --cycles 5
docker compose -f docker-compose.nse.yml run --rm nsealgo validate

# ---- research in a container, for reproducibility ----
docker compose -f docker-compose.research.yml run --rm research \
    python research/validate.py
```

## What it does

**Universe:** 48 NIFTY-50 symbols, daily bars, 2008-01-01 → 2026-10-01 (19.0y,
4,625 trading days).

**Signal** — cross-sectional blend, ranked daily, longer is better:

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Momentum 12-1 | 40% | Strongest documented Indian factor (Agarwalla/Jacob/Varma 2018) |
| Momentum 6m | 20% | Best long-only variant in India (Nigam & Pandey 2023) |
| Trend strength 200d | 25% | Bounded, robust trend proxy |
| Low volatility | 15% | Best-behaved long-only factor; cuts drawdown |

**Deliberately excluded, on evidence:**
- **Mean reversion** — Indian evidence shows short-term *continuation*. The only
  multiple-testing-corrected Indian study found 7/8 survivors were trend rules; RSI and
  Bollinger mean-reversion both failed. Retained only as a *negative control* that is
  asserted to underperform.
- **Value** — the Indian value premium "nearly ceased to exist" post-2008; 0 of 9 NSE
  factor indices showed significant out-of-sample alpha.
- **Size / liquidity** — real but unharvestable at ₹21 lakh.

**Risk overlay:** time-series-momentum gate on the equal-weight market proxy. Without it
max drawdown is −40.7% (fails the Band C limit); with it, −14.9%.

**Portfolio:** 22 names, monthly rebalance with a 35% turnover budget, inverse-vol
weighted, 12% single-name / 25% sector caps, 10% cash buffer. Both caps are now enforced
*simultaneously* and dead residual weights are dropped each rebalance — see
[Two engine bugs](#two-engine-bugs-that-were-hiding-a-breach-of-the-risk-limits).

## Costs

Full Indian delivery stack, calibrated to **published line-by-line itemisations**.

### Two numbers, and the difference matters

| Figure | Value | What it is |
|---|---|---|
| **Statutory** | **11.66 – 11.92 bps** | The exchange and regulatory stack only. Calibrated against two independent published itemisations. |
| **All-in charged by the backtest** | **≈ 21.9 bps** (21.92 at the agent-harness notional) | Statutory **+ 2 × 5 bps slippage** = statutory + 10. This is `CostModel.all_in_round_trip_bps`, and it is what `run_backtest` actually deducts. |
| **Stress (Gate 4)** | 31.9 / 41.9 bps | `double_slippage` / `triple_slippage` models. |

```
Rs 1,40,000 buy + Rs 1,47,000 sell  ->  Rs 334.67  ->  11.66 bps statutory
                                    +  2 x 5 bps  ->  21.66 bps all-in
```

**Both figures are quoted deliberately. Citing only 11.66 bps understates what the
backtest pays by nearly half, and citing only 21.9 bps hides that the model is calibrated
against published statutory rates.** The statutory stack includes STT 0.1% both sides,
stamp 0.015% buy-side, exchange txn 0.00307%, SEBI, DP ₹15.93/sell, and 18% GST on
(brokerage + txn + SEBI). CI fails if the calibration drifts.

**Both are per *total* turnover** — a full rotation of the book (sell 100%, buy 100%) is
`sum|dW| = 2.0`. The engine was, until 2026-10-09, multiplying that rate by *one-way*
turnover (`sum|dW|/2`) and therefore charging **exactly half** the real cost. See
[Four engine bugs](#four-engine-bugs-that-were-inflating-every-number-in-this-repo) and
[`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md) §0.3.

**Cost drag has not yet been re-measured on the final (v3) window.** The last recorded
**Measured on the final v3 window: 5.93%/yr** at 1.99x/yr turnover. The earlier figures
(3.11%/yr and 3.03%/yr) were both taken while the
half-cost bug was live, so both are **understated by ~2× in the cost term**. The correct
figure will be higher. It is left unstated here rather than guessed.

## Hard risk limits

Set in `src/nsealgo/risk/limits.py`, frozen, and re-asserted at import. No config flag,
env var, or CLI argument can raise them — CI checks them against `GOAL.md` §3.3.

| Limit | Value |
|-------|-------|
| Drawdown halt | −15% |
| Absolute drawdown (capital preservation) | −25% |
| Daily / weekly loss | −2% / −4% |
| Per-trade stop | −8% |
| Single name / sector | 12% / 25% |

## Architecture

```
src/nsealgo/
├── costs.py          Indian cost stack, Decimal, calibrated
├── data/loader.py    Cleaning rules C1-C8 + auditable CleaningReport
├── factors/
│   ├── core.py       Momentum / trend / low-vol + negative controls
│   └── regime.py     Time-series-momentum exposure gate
├── backtest/
│   ├── engine.py     Vectorised, cost-aware, one-bar-lagged (no look-ahead)
│   ├── metrics.py    244-day annualisation, correct drawdown, risk-free adj.
│   └── walkforward.py Sliding-origin OOS — the only evidence that counts
├── risk/limits.py    GOAL.md §3.3, frozen
├── execution/        Broker protocol + paper + Kite (live/paper parity)
└── live/engine.py    plan -> risk -> execute -> reconcile -> log
```

**Guarantees enforced by tests:**
- No look-ahead (future prices provably cannot change past signals)
- Costs charged on equity, not on bare turnover
- Slippage included in the backtest, so the Gate 4 stress test is not vacuous
- A genuine market crash survives data cleaning intact

## Is the data real?

Yes. All results come from `data/nse/*_1d.csv` — 50 real OHLCV series, 27.5MB, 48 symbols
after cleaning, 4,625 trading days, 2008-01-01 → 2026-10-01. (4,629 before cleaning rule
**C8** removed 4 bogus weekend dates.)

**The local panel was accidentally deleted and re-fetched on 2026-10-06** with
`tools/recover_nse_data.py` (yfinance, retrying both `auto_adjust` modes, atomic writes,
verified against the committed audit summary in `research/_audit_1d.csv`). **49/50 symbols
verified.** The recovery is faithful, and it is provably so: truncating the recovered panel
back to 2026-08-25 and re-running the walk-forward reproduces the original v1 result —
13.37% / Sharpe 0.65 / −15.38% against the recorded 13.40% / 0.66 / −15.41%, with the
same parameters selected in every fold. The recovery also extends the panel by 27 sessions
to 2026-10-01, which is what first moved the headline numbers. See
[`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) §0.

Verified properties:
- **Corporate-action adjusted post-2008** (10 known bonus dates, no −50% signature)
- **`close` is trustworthy** — matches the intraday last print on **97.12%** of days, and
  close-to-close returns respect the NSE 20% circuit limit
- **`high` / `low` are sound** — accurate to a median 0.15 / 0.10 rupees against true
  intraday max/min; the daily low is **never** above the true low (0.00%)
- **Structurally clean**: 0 duplicate timestamps; 47 non-positive-price rows and 114
  unadjusted-split bars, all in the excluded pre-2008 slice or `adanient`
- **Full Indian cost stack** applied on every fill, calibrated to published itemisations —
  and now charged at the **full** rate (see Costs)

Verified limitations: **the `open` column is corrupt** (wrong on 90.81% of days, outside
the true range on 20.12%), survivorship bias, no dividends, and a pre-2008 slice poisoned
by vendor artifacts (hence the 2008+ restriction). See Known limitations #6 and
[`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) §0.1.

## Known limitations

1. **Data bias: survivorship + no dividends, ~7.3%/yr measured on the v1 window.**
   - **Survivorship.** The universe is *today's* NIFTY-50 backfilled to 2008. No Satyam,
     no IL&FS, no DHFL, no Yes Bank, no Vodafone Idea in the panel — direct confirmation it
     is a survivor set. Delisted and removed constituents were never held. **Every number
     this repo reports is optimistic because of this and cannot be corrected locally** —
     fixing it needs a point-in-time constituent history, which does not exist here.
   - **Dividends are absent entirely.** The panel is **price return only**. The official
     NSE TRI (~12.44% over 20y) *includes* dividends; ours does not, so our price return
     understates total return by roughly the ~1.15%/yr NSE-50 dividend yield. This makes
     the bias **larger**, not smaller.
   - Bias-corrected, the strategy is **≈3.6%/yr, not 9.71%** (was ≈3.7% not 10.97%, and
     ≈6.1% not 13.40%). Benchmark bias-corrected ≈9.7%.
   - ⚠️ **The ≈3.6% figure is provisional and does not reconcile.** The ~7.3pp discount was
     measured on the v1 full window; 9.71 − 7.3 is ≈2.4%, not ≈3.6%. The discount has not
     been re-derived on the current window. **Do not quote ≈3.6%/yr as a measured figure.**
   - *Corporate actions post-2008 **are** verified adjusted* (10 documented bonus dates, no
     −50% signature). So the corruption is confined to the pre-2008 slice, which is why the
     window starts in 2008.
2. **No dividends, no income tax, no index-level products.** Price-return only, and LTCG
   12.5% / STCG 20% is a further real ~2–4%/yr drag that is not modelled at all. Both push
   the same direction: the reported number is not a take-home number.
3. **The result is fragile.** 27 trading days moved Sharpe 0.66 → 0.44 and the band
   C → D with no code change. Two subsequent bug fixes took it to 0.35 → 0.34. Until the
   band is shown to be stable as the window extends, this number is not trustworthy as a
   forward expectation.
4. **Four engine bugs were inflating every earlier number** — including one **critical**
   cost-charging bug that charged exactly half the real cost stack, and two portfolio-rule
   breaches. All fixed; the pre-fix figures are not quoted as results. See below.
5. **38 of 38 catalog strategies failed.** A walk-forward sweep of the crypto catalog on
   NSE daily bars — **38 agents, 38 negative, zero made money** — found that the catalog
   does not transfer to NSE. They are long/short crypto time-series indicators dropped into
   a long-only cross-sectional equity book, where `−1` means "a slightly different basket
   of 22 large caps", not "go to cash". Most could not beat a **coin flip**. Details in
   [`reports/CATALOG_TRIALS.md`](reports/CATALOG_TRIALS.md). The searches that find
   strategy edges here are not in the crypto catalog.
6. **The daily `open` column is corrupt; `high` and `low` are not.** `open` differs from
   the true first print on **90.81%** of days and sits outside the true range **20.12%** of
   the time. `close` matches intraday to the tick on 97.12% of days and is trustworthy;
   `high`/`low` are accurate to ~0.1–0.15 rupees. **Breakout strategies keyed to a 20-day
   rolling `high` are NOT impaired** (Donchian impact −0.08%) and must not be excluded —
   the earlier claim that they were broken was wrong. Only `open`-keyed logic
   (`open_range_breakout`, gap filters, overnight fills) is genuinely exposed. Full
   analysis: [`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) §0.1 and
   `research/data_quality/FINDINGS.md`.
7. **OOS CAGR is below the gate**, not just Sharpe: 9.71% vs 12% required, and
   7.41pp/yr behind the benchmark.
8. **Data ends 2026-10-01**, re-fetched 2026-10-06. Staleness is resolved, but the refresh
   is a **one-off recovery script, not an automated feed** — a Kite historical backfill
   path is still required before live.
9. **Intraday is permanently banned** — 1m data is 6 days. Independently, a 240-variant
   intraday sweep cleared 0 variants even against a perfect-maker cost floor.
10. **15m data is not independent evidence.** The 15m file is a bit-exact resample of the
    5m file (100.00% OHLC match on all four price columns). Any "5m corroborates 15m"
    argument is validating one source against itself.

## Four engine bugs that were inflating every number in this repo

All found by adversarial probing of the harness *while catalog trials were being run on
top of it*, all fixed in `src/nsealgo/backtest/engine.py` (on disk, **uncommitted**).

| # | Bug | Severity | Measured symptom | After the fix |
|---|-----|----------|------------------|---------------|
| 1 | **Cost charged at exactly half.** `all_in_round_trip_bps` is per *total* turnover; the engine multiplied by *one-way* turnover (`sum\|dW\|/2`). Ratio proven **0.500000**. | **CRITICAL** | **Every CAGR in the project was flattered**, and the **Gate 4 slippage stress ran at half strength**. | 10.97% → 9.89% CAGR, 0.44 → 0.35 Sharpe |
| 2 | **Residual-weight dilution.** `apply_turnover_budget` blended the whole book toward the new target, so a name the target no longer wanted decayed instead of exiting. | HIGH | **59% of a sparse book's weight was stale residue**; realised exposure averaged **~0.6 of the intended 0.9**. The book measured the harness, not the signal. | 9.89% → 9.71% CAGR. Now whole-position exits, all-or-nothing when budget-bound. |
| 3 | Sector cap redistributed weight **without re-capping** the receiving names, so the 12% single-name cap was applied first and then invalidated | HIGH | worst single weight **25.66%** against a 12% cap | worst single weight **10.80%** |
| 4 | Dead residual weights accumulated — positions below the material threshold were never dropped | HIGH | **48 names** held against `max_positions` 30 | max names **30**, worst sector **22.50%** |

**Stated plainly: every number this project published before 2026-10-09 was too high, and
bugs 1 and 3/4 were not subtle — they were breaches of the portfolio rules this repo's own
constitution mandates.** A backtest that quietly holds 25% in one name, or that pays half
the real cost, is not the strategy `GOAL.md` describes, whatever it prints. Any return
produced by breaching a limit is an artifact of the harness, not a return of the strategy.

**The only reason the current number is the current number is that someone went looking
for it.** Nothing in the routine pipeline caught any of the four.

### Reproducibility: `engine_sha`

`BacktestResult` now carries **`engine_sha`** — a hash of the engine source, computed at
import and printed with every result (`[engine <sha>]` in `BacktestResult.__str__`).

This exists because the engine was **rewritten by another process mid-experiment, twice**,
uncommitted, changing `apply_turnover_budget` both times. Dozens of agent reports were
produced against different engine revisions with no way to tell them apart; one agent
discarded an entire TRAIN table after discovering it had been measured on the old engine
(it showed Sharpe +0.42 where the fixed engine gave −0.08). **Without a fingerprint on the
result, an experiment is not reproducible.** If the `engine_sha` on a stored result does
not match the working tree, the result is stale and must be re-run rather than quoted.

## Catalog benchmark: 38 of 38 strategies failed

The ~85 crypto strategies in `src/cryptobot/strategies/catalog/` were ported to NSE daily
bars via a `SignalStrategy` adapter and run through **the same engine, the same Indian cost
stack, the same constraints, the same metrics**.

### (a) Walk-forward, out-of-sample — the evidence that counts

`reports/CATALOG_TRIALS.md`. One strategy per agent, parameters declared up front,
selected on **TRAIN 2016–2023**, evaluated once on **TEST 2024–2026**, net of the full
Indian delivery stack (**21.92 bps all-in**).

> ## 38 agents. 38 negative. Zero made money.

Not one beat plain buy-and-hold out of sample. Several lost to a **coin flip** — which
`research/AGENT_BRIEF.md` §6.5 names as the minimum bar. Full per-strategy table in
[`reports/CATALOG_TRIALS.md`](reports/CATALOG_TRIALS.md).

**Why, stated structurally rather than as a list of failures:** these are **long/short
crypto time-series indicators** dropped into a **long-only cross-sectional** NSE book. In
crypto, `−1` means cut to cash and dodge a 70% drawdown; in a delivery account `−1` maps
to "a slightly different basket of 22 large caps", beta ≈ 0.9. **The risk-control mechanism
these strategies were written around does not exist in this market.**

And the decisive repeat finding: **Indian equities continued; they did not reverse.**
Gated names' excess return was negative in *both* windows across multiple independent
strategies. Mean reversion is not merely absent in India — it is **inverted**. That
independently confirms why the reversal factors were removed from
`src/nsealgo/factors/core.py`.

**Costs were never the binding constraint.** Gross-vs-net gaps were small everywhere.
These strategies lost on **selection**, not on fees. Reducing turnover or costs would not
rescue any of them.

### (b) Full-window in-sample sweep — for completeness

`research/benchmark_catalog.py`.

| | Count | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| nsealgo composite | — | 17.57% | **0.88** | −18.51% | **0.95** |
| Best of 80 catalog strategies (`cumulative_delta_strategy`) | 80 | 15.92% | 0.76 | −17.43% | 0.91 |
| Pure 6-month momentum, same harness | — | 16.73% | 0.80 | −20.17% | 0.83 |
| **Random 50/50 mask**, same harness | — | 15.22% | **0.77** | −17.70% | 0.86 |

84 discovered, 80 evaluated, 2 never signalled, 2 crypto-only (funding/liq-hunt) skipped,
0 errors. **None beat the composite** on Sharpe or Calmar.

**Two caveats that change what this comparison means:**

1. **It is a full-window in-sample comparison, not walk-forward.** The composite baseline
   here carries the regime overlay (17.57% / 0.88), not the 0.34 OOS figure above. The two
   numbers are not comparable to each other and are not meant to be.
2. **It mostly measures momentum, not strategy skill.** The adapter deliberately gives each
   catalog strategy the benefit of momentum ranking, and the top of the sweep is not a set
   of distinct strategies — the leading rows produce numerically identical books
   (correlation 1.000). The best catalog result (0.76) is *below* pure 6-month momentum
   (0.80) and within noise of a random 50/50 mask (0.77).

**The honest finding: no existing catalog strategy adds anything over momentum, and none
beats the composite.** The composite's entire margin over this field is 0.12 Sharpe — of
the same order as the 0.32 that a data extension plus two engine bug fixes destroyed.

### (c) What the sweep actually produced: bugs, not strategies

The most valuable output of the 38 trials was the defect list. Eight broken crypto-catalog
strategies were found and fixed, plus one critical shared-indicator bug
(`indicators.py::hull()` had its two WMA terms swapped). In `nsealgo`, the **half-cost
charging bug** and the **residual-weight dilution** bug were found this way — and the
half-cost bug is the single reason every headline number in this project was previously
too high. See [Four engine bugs](#four-engine-bugs-that-were-inflating-every-number-in-this-repo).

## Reports

| File | Contents |
|------|----------|
| [`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) | Coverage, data quality, the 2026-10-06 data recovery, the **`open`-column defect**, the 114 split bars and 47 negative-price bars, cleaning plan C1–C8 |
| [`reports/FACTOR_EVIDENCE.md`](reports/FACTOR_EVIDENCE.md) | Cited evidence survey driving the factor choices |
| [`reports/CATALOG_TRIALS.md`](reports/CATALOG_TRIALS.md) | **38-agent walk-forward sweep: 38/38 negative.** The catalog-bugs list and the harness findings |
| [`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md) | **Addendum §0 = current v3 result (9.71% / 0.34 / Band D).** Body = the superseded v1 measurement, kept as the historical record |