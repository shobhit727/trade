# nsealgo — NSE NIFTY-50 systematic trading

**Read [`GOAL.md`](GOAL.md) first.** It is the binding constitution: capital, targets,
hard risk limits, anti-fraud rules, and the gates that must all pass before any real
capital is deployed.

> ## Current status: 13.40% annualised out-of-sample — not capital-authorised
>
> | | |
> |---|---|
> | **OOS annualised** | **13.40%** (walk-forward, 2008→2026) |
> | **OOS monthly** | **+1.054%** |
> | Requested target | 3.000%/month (42.6% annualised) |
> | **Bias-corrected** | **≈6.1%/yr** — see "Known limitations" |
> | OOS Sharpe | 0.66 |
> | OOS max drawdown | −15.41% |
> | Band | **C** (needs Sharpe ≥ 0.7 and benchmark outperformance) |
> | Verdict | ⛔ **NO DEPLOY** — 3 gates fail |
>
> Full evidence: [`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md)

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

**Universe:** 48 NIFTY-50 symbols, daily bars, 2008-01-01 → 2026-08-25 (18.9y).

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
max drawdown is −40.9% (fails the Band C limit); with it, −15.4%.

**Portfolio:** 22 names, monthly rebalance with a 35% turnover budget, inverse-vol
weighted, 12% single-name / 25% sector caps, 10% cash buffer.

## Costs

Full Indian delivery stack, calibrated to **published line-by-line itemisations**:

```
Rs 1,40,000 buy + Rs 1,47,000 sell  ->  Rs 334.67  ->  11.66 bps of turnover
```

Matches two independent published figures (11.65 / 11.66 bps). Includes STT 0.1% both
sides, stamp 0.015% buy-side, exchange txn 0.00307%, SEBI, DP ₹15.93/sell, and 18% GST
on (brokerage + txn + SEBI). Measured drag: **3.03%/yr**. CI fails if this drifts.

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

Yes. All results come from `data/nse/*_1d.csv` — 50 real OHLCV series, 68MB, 48 symbols
after cleaning, 4,602 trading days, 2008-01-01 → 2026-08-25.

Verified properties:
- **Corporate-action adjusted post-2008** (10 known bonus dates, no −50% signature)
- **Structurally clean**: 0 duplicate timestamps, 0 non-positive prices in 47 of 48 symbols
- **Full Indian cost stack** applied on every fill, calibrated to published itemisations

Verified limitations: survivorship bias, no dividends, 6-week staleness, pre-2008 slice
poisoned by vendor artifacts (hence the 2008+ restriction).

## Known limitations

1. **~7.3%/yr of data bias.** Survivorship (today's NIFTY-50 backfilled to 2008; no
   Satyam/IL&FS/DHFL/Yes Bank/Vodafone Idea in the panel) **plus dividends being absent
   entirely** (price return only). Bias-corrected, the strategy is ≈6.1% not 13.40%, and
   ≈11.5% for the benchmark. **This invalidates "beats the official index TRI"** — corrected,
   it roughly matches the index while halving the drawdown. Quantified by
   `research/verify_corporate_actions.py`.
   *Corporate actions post-2008 are verified adjusted* (10 bonus dates, no −50% signature).
2. **Data ends 2026-08-25**, ~6 weeks stale. Needs a Kite historical backfill before live.
3. **Sharpe 0.66 vs 0.7 required.** The regime overlay's whipsaw costs upside in sharp
   recoveries (2020, 2021).
4. **Income tax is not modelled.** LTCG 12.5% / STCG 20% is a real ~2–4%/yr drag.
5. **Intraday is permanently banned** — 1m data is 6 days. Independently, a 240-variant
   intraday sweep cleared 0 variants even against a perfect-maker cost floor.

## Reports

| File | Contents |
|------|----------|
| [`reports/DATA_AUDIT.md`](reports/DATA_AUDIT.md) | Coverage, data quality, the 2005 split artifacts, cleaning plan |
| [`reports/FACTOR_EVIDENCE.md`](reports/FACTOR_EVIDENCE.md) | Cited evidence survey driving the factor choices |
| [`reports/VALIDATION_v1.md`](reports/VALIDATION_v1.md) | Walk-forward OOS, gate checks, the 7 bugs found and fixed |