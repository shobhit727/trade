# nsealgo — NSE NIFTY-50 systematic trading

**Read [`GOAL.md`](GOAL.md) first.** It is the binding constitution: capital, targets,
hard risk limits, anti-fraud rules, and the gates that must all pass before any real
capital is deployed.

> ## Current status: 10.97% annualised out-of-sample — Band D — not capital-authorised
>
> | | |
> |---|---|
> | **OOS annualised** | **10.97%** (walk-forward, 2008-01-01 → 2026-10-01, 19.0y) |
> | **OOS monthly** | **+0.871%** |
> | Requested target | 3.000%/month (42.6% annualised) |
> | **Bias-corrected** | **≈3.7%/yr** — see "Known limitations" |
> | OOS Sharpe | **0.44** (was 0.66 at the previous end date) |
> | OOS max drawdown | **−12.91%** |
> | Band | **D** (was C) |
> | Verdict | ⛔ **NO DEPLOY** — **four** gates fail |
>
> Full evidence: [`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md) — **read the
> addendum at the top first**; the body of that file is the superseded v1 measurement,
> kept as the historical record.

> ### ⚠️ Read this before quoting any number from this repo
>
> **27 extra trading days — about six weeks — moved OOS Sharpe from 0.66 to 0.44 and the
> band from C to D.** Same code, same costs, same parameters. The change was the data end
> date and nothing else.
>
> That is a fragility signal about the **strategy**, not a data defect. A result whose band
> depends on where you stop measuring is not a result that gets capital, and no number from
> this system should be quoted without its end date attached.

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
4,629 trading days).

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

Full Indian delivery stack, calibrated to **published line-by-line itemisations**:

```
Rs 1,40,000 buy + Rs 1,47,000 sell  ->  Rs 334.67  ->  11.66 bps of turnover
```

Matches two independent published figures (11.65 / 11.66 bps). Includes STT 0.1% both
sides, stamp 0.015% buy-side, exchange txn 0.00307%, SEBI, DP ₹15.93/sell, and 18% GST
on (brokerage + txn + SEBI). Measured drag: **3.11%/yr** on the current window (was
3.03%/yr to 2026-08-25 — the model is unchanged, the window is longer). CI fails if the
calibration drifts.

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
├── data/loader.py    Cleaning rules C1-C7 + auditable CleaningReport
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
after cleaning, 4,629 trading days, 2008-01-01 → 2026-10-01.

**The local panel was accidentally deleted and re-fetched on 2026-10-06** with
`tools/recover_nse_data.py` (yfinance, retrying both `auto_adjust` modes, atomic writes,
verified against the committed audit summary in `research/_audit_1d.csv`). **49/50 symbols
verified.** The recovery is faithful, and it is provably so: truncating the recovered panel
back to 2026-08-25 and re-running the walk-forward reproduces the original v1 result —
13.37% / Sharpe 0.65 / −15.38% against the recorded 13.40% / 0.66 / −15.41%, with the
same parameters selected in every fold. The recovery also extends the panel by 27 sessions
to 2026-10-01, which is what moved the headline numbers. See
[`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) §0.

Verified properties:
- **Corporate-action adjusted post-2008** (10 known bonus dates, no −50% signature)
- **Structurally clean**: 0 duplicate timestamps, 0 non-positive prices in 47 of 48 symbols
- **Full Indian cost stack** applied on every fill, calibrated to published itemisations

Verified limitations: survivorship bias, no dividends, pre-2008 slice poisoned by vendor
artifacts (hence the 2008+ restriction).

## Known limitations

1. **~7.3%/yr of data bias.** Survivorship (today's NIFTY-50 backfilled to 2008; no
   Satyam/IL&FS/DHFL/Yes Bank/Vodafone Idea in the panel) **plus dividends being absent
   entirely** (price return only). Quantified by `research/verify_corporate_actions.py` on
   the v1 window and **carried forward unchanged** — it is a property of the universe
   construction, not of the end date. Bias-corrected, the strategy is ≈3.7% not 10.97%
   (was ≈6.1% not 13.40%), and ≈9.7% for the benchmark.
   **This invalidates "beats the official index TRI"** — corrected, the strategy is *below*
   the index on return; halving the drawdown is the only claim left standing.
   *Corporate actions post-2008 are verified adjusted* (10 bonus dates, no −50% signature).
2. **The result is fragile.** 27 trading days moved Sharpe 0.66 → 0.44 and the band
   C → D. Nothing about the strategy changed. Until the band is shown to be stable as the
   window extends, this number is not trustworthy as a forward expectation.
3. **Two engine bugs were inflating the earlier numbers** — a breached single-name cap
   (25.66% against a 12% limit) and 48 held names against `max_positions` 30. Fixed; the
   pre-fix figures are not quoted as results. See below.
4. **OOS CAGR is now below the gate**, not just Sharpe: 10.97% vs 12% required, and
   6.00pp/yr behind the benchmark.
5. **Data ends 2026-10-01**, re-fetched 2026-10-06. Staleness is resolved, but the refresh
   is a **one-off recovery script, not an automated feed** — a Kite historical backfill
   path is still required before live.
6. **Income tax is not modelled.** LTCG 12.5% / STCG 20% is a real ~2–4%/yr drag.
7. **Intraday is permanently banned** — 1m data is 6 days. Independently, a 240-variant
   intraday sweep cleared 0 variants even against a perfect-maker cost floor.

## Two engine bugs that were hiding a breach of the risk limits

Found by the sanity checks in `research/benchmark_catalog.py`, fixed in
`src/nsealgo/backtest/engine.py` (on disk, **uncommitted**):

| Bug | Symptom | After the fix |
|-----|---------|---------------|
| Sector cap redistributed weight **without re-capping** the receiving names, so the 12% single-name cap was applied first and then invalidated | worst single weight **25.66%** against a 12% cap | worst single weight **10.80%** |
| Dead residual weights accumulated — positions below the material threshold were never dropped | **48 names** held against `max_positions` 30 | max names **30** |
| Worst sector weight | — | **22.50%** (25% cap) |

The fix cost 11.05% → 10.97% CAGR and 0.45 → 0.44 Sharpe. **Part of the earlier result was
earned by holding positions the risk rules forbid.** That is an artifact, not a return, and
the post-fix figures are the only ones to trust.

## Catalog benchmark: nothing already in this repo beats the composite

The ~85 crypto strategies in `src/cryptobot/strategies/catalog/` were ported to NSE daily
bars via a `SignalStrategy` adapter and run through **the same engine, the same Indian cost
stack, the same constraints, the same metrics**. `research/benchmark_catalog.py`.

| | Count | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| nsealgo composite | — | 17.57% | **0.88** | −18.51% | **0.95** |
| Best of 80 catalog strategies (`cumulative_delta_strategy`) | 80 | 15.92% | 0.76 | −17.43% | 0.91 |
| Pure 6-month momentum, same harness | — | 16.73% | 0.80 | −20.17% | 0.83 |
| **Random 50/50 mask**, same harness | — | 15.22% | **0.77** | −17.70% | 0.86 |

84 discovered, 80 evaluated, 2 never signalled, 2 crypto-only (funding/liq-hunt) skipped,
0 errors. **None beat the composite** on Sharpe or Calmar.

**Two caveats, stated because they change what this comparison means:**

1. **It is a full-window in-sample comparison, not walk-forward.** The composite baseline
   here carries the regime overlay (17.57% / 0.88), not the 0.44 OOS figure above. The two
   numbers are not comparable to each other and are not meant to be.
2. **The comparison mostly measures momentum, not strategy skill.** The adapter deliberately
   gives each catalog strategy the benefit of momentum ranking, and the top of the sweep is
   not a set of distinct strategies — the leading rows produce numerically identical books
   (correlation 1.000). The best catalog result (0.76) is *below* pure 6-month momentum
   (0.80) and within noise of a random 50/50 mask (0.77).

**The honest finding: no existing catalog strategy adds anything over momentum, and none
beats the composite.** The composite's entire margin over this field is 0.12 Sharpe — of the
same order as the 0.22 that 27 days of new data destroyed.

## Reports

| File | Contents |
|------|----------|
| [`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) | Coverage, data quality, the 2005 split artifacts, the 2026-10-06 data recovery, cleaning plan |
| [`reports/FACTOR_EVIDENCE.md`](reports/FACTOR_EVIDENCE.md) | Cited evidence survey driving the factor choices |
| [`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md) | **Addendum at the top = current v2 result.** Body = the superseded v1 measurement, kept as the historical record |