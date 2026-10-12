# Catalog Strategies That Are Structurally Inapplicable to NSE NIFTY-50 Cash

**Agent:** `agent_inapplicable` · **Date:** 2026-10-12
**Scope:** 7 assigned catalog strategies, of 85 catalog files / 91 registry entries.

**Verdict in one line:** the interesting finding is *not* that these strategies need
data we lack — it is that **four of them never read that data at all**. `funding_basis`,
`funding_trend`, `spot_futures` and `stablecoin_peg` are crypto-*named* but compute plain
`close`-only z-scores and SMA deviations. They are **technically runnable** and
**semantically empty**: the crypto label describes an intent that is absent from the code.
Only `nse_intraday` is genuinely inapplicable (banned by mandate), and only
`stablecoin_peg` has a truly dead knob.

---

## 0. What the NSE panel actually contains (checked, not assumed)

All 250 files in `data/nse/` were scanned. The **only** header across the entire panel —
in `data/nse/` and everywhere else in `data/` — is:

```
ts,open,high,low,close,vol        (ts = epoch ms)
```

There is **no** funding rate, no spot/perp pair, no futures price, no basis, no OI, no
borrow, no stablecoin price, no options IV, no margin field.

| tf | files | bars/sym (min/med/max) | span |
|----|-------|------------------------|------|
| 1d | 50 | 774 / 6025 / 6678 | 2000-01-03 → 2026-10-01 |
| 1h | 50 | 1625 / 3228 / 3237 | 2024-11-18 → 2026-10-06 |
| 15m | 50 | 832 / 843 / 848 | 2026-08-18 → 2026-10-06 |
| 30m | 50 | 442 / 442 / 442 | 2026-08-18 → 2026-10-06 |
| 5m | 50 | 2464 / 2475 / 2480 | 2026-08-18 → 2026-10-06 |

**Daily bars are stamped 05:30 IST** (`minute_of_day == 330`), not at the 09:15 open.
This one fact silently disables `nse_orb` — see §1.7.

---

## 1. Classification table

| # | Strategy | Required data | In NSE panel? | Runnable? | Actual signal | Dead / inert knobs | Verdict |
|---|----------|---------------|---------------|-----------|---------------|--------------------|---------|
| 1 | `funding_basis` | `closes` only. **No funding rate is read anywhere.** | n/a — doesn't need it | **Yes** (but meaningless) | `+1` if `close > SMA(period)`, `-1` if `close < SMA(period)`; `threshold=0.0` by default so it is **never flat** | `threshold` **live but defaults to 0.0 = disabled**; the strategy is **bit-identical to `meta`** at defaults (6675/6675 bars) | **Structurally mislabelled.** No NSE meaning. Duplicate of `meta`. |
| 2 | `funding_trend` | `closes` only. **No funding rate is read.** | n/a | **Yes** (but meaningless) | `+1` if `ROC(period) > threshold` **and** `close > SMA(period)`; `-1` on the mirror; flat otherwise (20.6% flat) | none — `period` and `threshold` both live | **Structurally mislabelled.** A generic ROC+SMA trend filter; nothing to do with funding. |
| 3 | `spot_futures` | `closes` only. **No spot or futures price is read.** | n/a | **Yes** (but meaningless) | `-1` if `zscore(closes) > entry`, `+1` if `zscore(closes) < -entry`, else flat | **`sma(closes, period)` is computed then discarded** — `m` is used *only* as a NaN guard and never enters a comparison. **`period` does not set the z-window** (`zscore()` spans the full 300-bar buffer). See §2.1 | **Structurally mislabelled + a compute-then-discard bug.** |
| 4 | `stablecoin_peg` | `closes` only. **No stablecoin price is read.** | n/a | **Yes** (but meaningless) | `-1` if `(close - SMA)/SMA > +0.005`, `+1` if `< -0.005` | **`entry` is INERT — 15/15 perturbations produced byte-identical output.** `signal()` hardcodes `0.005` and never reads `self.config.entry`. See §2.2 | **Structurally mislabelled + genuinely dead knob.** |
| 5 | `basket` | `closes` only | ✅ present | **Yes — fully** | `+1` if `ROC(period) > threshold`, `-1` if `< -threshold`, else flat (16.3% flat) | none | **Genuinely runnable.** Misnamed: operates on a *single symbol*, no basket/cross-sectional logic. Trialled → **fails** (§3). |
| 6 | `meta` | `closes` only | ✅ present | **Yes — fully** | `+1` if `close > SMA(period)`, else `-1`. **Never returns 0** (0.30% flat) | none | **Genuinely runnable.** "Meta-strategy" is a misnomer: no ensemble, no sub-strategies, no weighting. Trialled → **fails** (§3). |
| 7 | `nse_intraday` (`nse_orb` + `vwap_revert`) | **intraday bars + per-bar IST timestamps** (`ts`) | ⚠️ 15m exists but only ~7 weeks | **No** | `nse_orb`: breakout of the first `range_bars` session bars; `vwap_revert`: fade >`z_entry` σ from session VWAP. Both flat at 15:25 IST | `range_bars`/`z_entry` live — but on daily bars `nse_orb` is **100% flat** and `vwap_revert` silently computes a **cumulative-since-2000** VWAP | **BANNED** — `GOAL.md` §1.1/§4.1 ban intraday. Also silently flat if `ts` is not passed. |

---

## 2. Dead knobs and correctness bugs (evidence)

Method: `research/agent_inapplicable/knob_audit.py` replays each strategy's full
daily-bar history for 5 NSE symbols, perturbing one config field at a time and comparing
the emitted signal series byte-for-byte. A knob whose perturbation leaves output
**identical** is inert. All results below are measured, not read off the source.

### 2.1 `spot_futures` — the SMA is computed and thrown away, and `period` is a decoy

```python
z = zscore(closes)                      # spans the whole 300-bar buffer
m = sma(closes, self.config.period)     # computed...
if z != z or m != m: return 0           # ...used ONLY as a NaN guard
if z > self.config.entry:  return -1    # m's VALUE never appears here
```

This is the same defect class as the `supertrend` ATR finding. Worse, the measured
window is *not* `period`:

| measure | value |
|---------|-------|
| `zscore()` over the 300-bar buffer | **2.153976** |
| manual z over the last **30** bars (what `period=30` implies) | 0.923389 |
| manual z over the last **60** bars | 1.476161 |

`indicators.zscore(values)` takes no period argument and averages over its entire input;
the input is `SignalStrategy`'s `_maxlen=300` buffer. So `period` here only controls
warmup and the initial NaN gate — the actual lookback is **hardcoded at 300 bars**.
`period` still perturbs output (14/15 trials, because it shifts the warmup start), so it
is not *fully* inert, but it does not do what its name implies.

### 2.2 `stablecoin_peg` — `entry` is a genuinely dead knob

`config.entry` defaults to `2.0`, but `signal()` compares against the literal `0.005`:

```python
if dev > 0.005:  return -1      # hardcoded — config.entry never read
if dev < -0.005: return 1
```

Measured: perturbing `entry` over `{0.0, 1.0, 5.0}` × 5 symbols left the signal series
**identical in 15/15 trials**. Any operator tuning this knob would see *zero* change and
could reasonably conclude the strategy is robust. It is not tunable.

Secondary point: even the intended ±0.005 band is economically mis-transplanted. A 0.5%
deviation from a 60-day SMA on a ₹1,400 NSE equity is *routine noise* (measured: 93.3%
of daily bars are non-flat), not a peg dislocation.

### 2.3 `quantity` is inert **with respect to `signal()`** for all seven

10/10 perturbations identical for every strategy. This is **not a catalog bug** — it is by
design: `quantity` is consumed by the base class `SignalStrategy.feed()` for order sizing
(`signal_base.py:135`), never by `signal()`. Reported for completeness only.

### 2.4 `funding_basis(threshold=0.0)` ≡ `meta(period=20)`, exactly

At default settings `funding_basis` reduces to `close > SMA` (because `dev > 0.0` ⟺
`close > SMA`, and `dev < -0.0` ⟺ `close < SMA`). Measured over RELIANCE's full history:

```
bars compared : 6675
identical     : 6675  (100.00%)
disagreements : 0
```

Two catalog entries, two registry names, one strategy. `threshold` is the only thing that
separates them — and it **defaults to 0.0**, i.e. disabled.

### 2.5 `nse_intraday` — two silent failure modes

Daily bars carry `minute_of_day == 330`, and `SESSION_START` is 09:15 = **555**:

- **`nse_orb` is 100% flat on daily bars** (0.00% long, 0.00% short, 100% flat over
  32,052 bars). The guard `if mod < 555: return 0` fires on every bar. No error, no
  warning — it just never trades.
- **`vwap_revert` degrades into a different strategy.** Its day-rollover test is
  `mod < d["mod"]`; with `mod` pinned at 330 that is `330 < 330` = **False**, so the
  accumulator **never resets**. The "session VWAP" becomes a cumulative-since-2000 VWAP.
  Measured on daily bars: 47.1% short vs 0.8% long — a wildly asymmetric artefact of the
  broken reset, not a reversion signal.
- **`ts` is an optional kwarg on `feed()`.** Any caller that omits it gets
  `_last_ts() -> None -> mod is None -> return 0`, i.e. **both strategies 100% flat with
  zero diagnostics** (measured: 100% flat for both). A silently dead strategy is worse
  than an error.

---

## 3. Trials for the two genuinely runnable strategies

`basket` and `meta` need only `close`, so they were run under the full
`AGENT_BRIEF.md` protocol. **The other five were not backtested** — §4/§1.7 explain why,
and per brief §9 forcing a backtest out of a strategy that carries no NSE meaning would
manufacture a result rather than measure one.

**Declared parameter budget (fixed before any run, 5 variants each):**
`basket` = period ∈ {10, 20, 60, 120} at threshold 0.015, plus period 20 @ threshold 0.05.
`meta` = period ∈ {10, 20, 50, 100, 200}. No further variants were run.

**Protocol:** TRAIN 2016-01-01→2023-12-31 for selection; TEST 2024-01-01→2026-10-01 read
**once** at the end; `run_backtest` at the full **21.92 bps** all-in stack (verified:
`round_trip_bps=11.92`, `all_in_round_trip_bps=21.92`); `PortfolioConfig()` defaults
(22 names, 12% single, 25% sector, 10% cash, monthly rebalance, 0.35 turnover budget);
signals turned into a cross-sectional score by ranking signalled names on 126-day momentum
(long-only). **Sharpe is computed against rf = 6.5%** (`DEFAULT_RF_ANNUAL`), so a positive
CAGR with negative Sharpe means the book failed to clear the risk-free hurdle.

### TRAIN (selection window, net of 21.92 bps)

| strategy | variant | CAGR | Sharpe | MaxDD | Calmar | Turn/yr | Names | % bars long |
|---|---|---|---|---|---|---|---|---|
| basket | p10 t.015 | 11.63% | 0.58 | −12.98% | 0.90 | 4.10 | 17.0 | 55.9% |
| basket | p20 t.015 | 10.19% | 0.39 | −24.43% | 0.42 | 4.08 | 18.3 | 57.5% |
| basket | p60 t.015 | 14.12% | 0.57 | −32.22% | 0.44 | 3.36 | 19.3 | 62.0% |
| **basket** | **p120 t.015** | 15.83% | **0.64** | −35.55% | 0.45 | 2.92 | 20.2 | 65.6% |
| basket | p20 t.05 | 6.24% | 0.01 | −21.67% | 0.29 | 4.01 | 13.9 | 60.9% |
| meta | p10 | 13.95% | 0.71 | −13.24% | 1.05 | 3.96 | 19.7 | 49.3% |
| meta | p20 | 12.19% | 0.55 | −21.21% | 0.57 | 3.98 | 19.6 | 50.7% |
| meta | p50 | 14.95% | 0.71 | −17.65% | 0.85 | 3.74 | 19.8 | 52.8% |
| **meta** | **p100** | 17.23% | **0.81** | −20.81% | 0.83 | 3.22 | 20.2 | 54.4% |
| meta | p200 | 16.30% | 0.66 | −36.14% | 0.45 | 2.83 | 20.9 | 55.8% |

Selected on TRAIN Sharpe: **`basket` p120_t0.015** and **`meta` p100**.

### TEST (out-of-sample, net of 21.92 bps) — **read once**

| strategy | variant | CAGR | Sharpe | MaxDD | Calmar | Turn/yr | Names | % bars long |
|---|---|---|---|---|---|---|---|---|
| basket | p10 t.015 | 0.77% | −0.53 | −15.02% | 0.05 | 4.02 | 16.1 | 55.9% |
| basket | p20 t.015 | −0.86% | −0.63 | −22.59% | −0.04 | 3.98 | 17.6 | 57.5% |
| basket | p60 t.015 | −1.36% | −0.54 | −23.73% | −0.06 | 3.37 | 18.9 | 62.0% |
| **basket** | **p120 t.015** ←sel | **1.00%** | **−0.34** | **−20.28%** | 0.05 | 2.94 | 19.8 | 65.6% |
| basket | p20 t.05 | −1.32% | −0.89 | −16.00% | −0.08 | 3.98 | 12.0 | 60.9% |
| meta | p10 | 0.60% | −0.49 | −16.77% | 0.04 | 3.97 | 18.8 | 49.3% |
| meta | p20 | −0.50% | −0.57 | −20.60% | −0.02 | 3.90 | 18.4 | 50.7% |
| meta | p50 | 0.16% | −0.44 | −21.32% | 0.01 | 3.63 | 19.3 | 52.8% |
| **meta** | **p100** ←sel | **0.74%** | **−0.37** | **−19.51%** | 0.04 | 3.18 | 19.7 | 54.4% |
| meta | p200 | 2.13% | −0.25 | −17.86% | 0.12 | 2.84 | 20.6 | 55.8% |

### Controls on the identical TEST window

| control | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| **buy-and-hold** (equal-weight `panel.pct_change().mean(axis=1)`) | **8.05%** | **0.17** | **−16.80%** |
| random-signal control (`basket`, 65.6% bars long) | **4.10%** | −0.17 | −10.79% |
| random-signal control (`meta`, 54.4% bars long) | **3.94%** | −0.24 | −8.60% |
| `nsealgo` composite (`build_composite_score`) | 6.24% | 0.05 | −15.02% |

### Gross vs net (brief §6.4)

| variant | gross CAGR (0 bps) | net CAGR (21.92 bps) | drag | engine cost drag | turnover |
|---|---|---|---|---|---|
| basket p120 | 1.60% | 1.00% | 0.60%/yr | 1.47%/y | 2.94×/yr |
| meta p100 | 1.38% | 0.74% | 0.64%/yr | 1.59%/y | 3.18×/yr |

Neither is a "positive gross, killed by costs" case — both are **~1.4–1.6% CAGR gross**,
i.e. no edge to begin with. Costs shave ~0.6%/yr off an already-negligible return.

**Sanity checks:** avg names held 19.7–19.8 (≈22 target, no weight leakage ✓); signal
liveness 54–66% long (well above the 5% floor, so not an always-flat artefact ✓); CAGR
0.7–1.0% is far below the 40–50% plausibility ceiling, so no lookahead/compounding bug ✓.

### Verdict on the two runnable candidates

**No — neither `basket` nor `meta` makes money on NSE.** Both collapse from
TRAIN Sharpe 0.64/0.81 to TEST Sharpe −0.34/−0.37, i.e. a textbook in-sample-to-out-of-
sample inversion. Both lose to buy-and-hold on return (1.00%/0.74% vs 8.05%) *and* on
drawdown (−20.3%/−19.5% vs −16.8%). Both **lose to a random coin flip** at matched bar
coverage (4.10%/3.94% vs 1.00%/0.74%) — they fail the minimum bar in brief §6.5 — and
both lose to the existing `nsealgo` composite (6.24%). All 10 variants, including both
TRAIN-selected ones, have **negative TEST Sharpe**. There is no variant worth deploying.

Most likely reason: both reduce to a *time-series* trend/ROC gate that is then collapsed
into a 126-day momentum cross-sectional score. The gate adds no information the momentum
rank does not already contain, so it costs ~3×/yr of turnover (≈1.5%/yr) for no
incremental alpha. Next thing to try: nothing on these two — they are duplicates of
signal already in the composite, and the honest move is to retire them rather than
re-tune.

---

## 4. Future data and unrealistic fill assumptions

**No lookahead found in any of the seven.** Every signal is causal in the code:
`funding_*`, `basket` and `meta` use `closes[-1]` against trailing windows only;
`spot_futures`/`stablecoin_peg` use trailing SMA and z-scores; `nse_orb` builds its
opening range from bars strictly *before* the breakout bar; `vwap_revert` includes the
current bar in its own VWAP (contemporaneous, not future). The `nsealgo` engine's
one-bar lag (`run_backtest`: weights from date *t* earn returns from *t+1*) supplies the
rest. My `signal_panel` likewise uses `panel.shift(period)` and `rolling(period).mean()`,
which are trailing-only.

**Two fill/cost realism problems, both in `signal_base.feed()`, not in these strategies:**

1. **The protective stop is metadata only.** `signal_base.py:123-126` attaches
   `stop_price` to every entry order, but the engine *does not simulate stop fills*
   ("The backtest engine does not simulate stop fills, so this is metadata only"). Any
   backtest that runs these strategies through the catalog `feed()` path therefore holds
   losers to the exit rule rather than to the stop — an optimistic assumption.
2. **Both intraday strategies emit `reduce_only`/short legs that cannot exist in the NSE
   delivery account.** `nse_orb` returns `-1` for 34.2% of 15m bars and `vwap_revert`
   returns `-1` on roughly half of its non-flat bars. `GOAL.md` §4 restricts the universe
   to NIFTY-50 **cash delivery**; there is no shorting and no intraday square-off. Their
   docstring explicitly claims "no delivery STT — pure intraday cost economics", which is
   a cost model that does not exist for this mission.

A third, softer realism issue: `vwap_revert` uses `volumes[-1]` as the VWAP weight. Per
`GOAL.md` §11.1 the panel is **survivorship-biased and dividend-incomplete**, so
volume-weighted prices carry that bias directly into the signal.

---

## 5. What this means for the catalog as a whole

**Counting.** The registry holds **91** entries, of which **85** are catalog modules (the
task brief said 84; the actual count is 85 files — `nse_intraday_trading.py` contributes
*two* registry names, `nse_intraday_trading` and `vwap_revert`, from one file).

Of the 7 assigned here, applying the same standard to the rest of the catalog:

| class | count (of these 7) | NSE candidates? |
|-------|--------------------|-----------------|
| Banned by mandate (intraday) | 1 (`nse_intraday`) | **No** — `GOAL.md` §1.1 |
| Requires data the panel lacks (funding, futures, peg, OI, IV) | **0** | n/a |
| Structurally mislabelled — crypto name, OHLCV-only code, no NSE meaning | 4 (`funding_basis`, `funding_trend`, `spot_futures`, `stablecoin_peg`) | **No** |
| Genuinely runnable OHLCV strategies | 2 (`basket`, `meta`) | Tested — **both fail** |

The registry also contains non-catalog crypto strategies the same test removes:
`funding_arbitrage`, `statistical_arbitrage`, `market_making`, `mean_reversion`,
`ml_strategy`, `trend_following`, plus catalog entries like
`liquidation_hunt_strategy` and `implied_realized_volatility` which need OI / options data
that does not exist here.

**Do the inapplicable strategies inflate the apparent catalogue size? Yes, materially.**
On the evidence here, the "84 strategies" headline overstates the real candidate pool by
roughly a third to a half: at least ~6 of these 7 are not NSE candidates (1 banned, 4
semantically empty, and — on the numbers — 2 runnable-but-failed), and only **one**
(`basket`) survived even as a legitimately distinct OHLCV strategy, with `meta` turning
out to be its bit-identical twin. Worse, the inflation is **not visible from the outside**:
the four mislabelled strategies look like rich crypto-specific machinery — basis carry,
funding trend, peg bands, spot-futures spread — and would each plausibly be counted as a
separate line of attack in a capability survey, while in reality all four are one or two
generic `close`-only indicators wearing a costume. **`funding_basis` and `meta` being
byte-identical at defaults** is the clearest single illustration: the catalog counts 91,
the registry exposes 91, and a naive read of the filenames implies far more independent
ideas than exist.

**Recommendations (no code changed — nothing under `src/` or `tests/` was touched):**
1. **Fix or delete `stablecoin_peg.entry`** — a config field that provably cannot change
   the signal is worse than no field, because it invites a tuning study that cannot work.
2. **Fix `spot_futures`**: either delete the discarded `m`, or pass `period` into a real
   windowed z-score instead of letting `zscore()` silently use 300 bars.
3. **Collapse `funding_basis` into `meta`** (they are identical at defaults) or give
   `funding_basis.threshold` a non-degenerate default.
4. **Fail loudly in `nse_intraday` when `ts is None`**, and guard the day-rollover so a
   constant `minute_of_day` cannot masquerade as a single long session.
5. **Add a capability manifest to the catalog** — an explicit per-entry `required_feeds`
   field. The inapplicability here was 100% decidable from the code without running
   anything, and a machine-readable field would make the whole catalog triageable in
   minutes instead of days.
6. **Re-baseline the "84 strategies" claim** in any planning document to the count that
   are actually OHLCV-only and daily-bar-legal, which is the number the mission cares about.

---

## Reproducing

```bash
.venv/bin/python research/agent_inapplicable/knob_audit.py   # dead-knob perturbation sweep
.venv/bin/python research/agent_inapplicable/trial.py        # TRAIN/TEST protocol, controls
.venv/bin/python research/agent_inapplicable/cost_drag.py     # gross vs net decomposition
```

All scripts are read-only with respect to `src/` and `tests/`; nothing was committed.