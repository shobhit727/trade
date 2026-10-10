# BUG / OBSERVATION LOG — `relative_strength` agent run

Bugs are the most valuable output of this exercise. **Nothing under `src/**` was
modified.** These are findings only.

---

## B1 — `DataFrame - Series` silently column-aligns and returns an all-NaN panel.
## Severity: **HIGH as a silent-wrong-result class.** Caught in my own harness.

**Where:** any cross-sectional construction of the form `panel - panel.median(axis=1)`.

**Mechanism.** In pandas, `df - series` aligns the Series' **index** against the
DataFrame' **columns**. My panel has date-index × 48 symbols, so the median Series is
indexed by date and the alignment is against symbol names:

```
date ∩ symbols = ∅
⇒ result is a (4625 × 4673) frame that is entirely NaN
⇒ no exception, no warning
```

`r - r.median(axis=1)` produced a **4,625 × 4,673 all-NaN** DataFrame. The correct form is
`r.sub(r.median(axis=1), axis=0)`.

**Why this one matters more than it looks.** The failure did not crash — it propagated
straight through the engine and printed a perfectly respectable-looking results row:

```
rel-to-median p126 t0.08    0.00%    0.00    0.00    0.00%    0.00   0.00   0.00%    0.0
```

A strategy that returned *exactly zero*, with *exactly zero* Sharpe, *exactly zero*
drawdown and *zero* names held, printed in the same format as a real result. The only
tell was the `Names` column reading `0.0`. A reader scanning CAGR/Sharpe/MaxDD would
have read it as "this variant is flat" rather than "this variant was never constructed".

This is the same failure surface as `research/agent_cross_sectional/BUGS.md` §B1 (an
all-NaN score row ⇒ engine emits an all-zero target and liquidates the book), arriving
from a completely different direction. **Any harness that can produce an all-NaN score
panel is one refactor away from reporting a fabricated zero.** Guard added to my own
code:

```python
assert rel.shape == roc.shape, f"broadcast blew up: {rel.shape} vs {roc.shape}"
assert flagged_per_day > 1.0, f"degenerate signal: only {n} names flagged per day"
```

**Suggested general guard for any agent harness** (not applied — I may not modify
`src/**`): assert `np.isfinite(score.to_numpy()).any()` and
`np.nansum(score > 0, axis=1).mean() > 1` immediately before calling `run_backtest`.

---

## B2 — `run_backtest` accepts a completely non-functional score panel and returns a
## valid-looking `Metrics` object. Severity: **HIGH as a live-trading / reporting hazard.**

**Where:** `src/nsealgo/backtest/engine.py`, `run_backtest`.

**Observed behaviour** (TRAIN window, unmodified engine and cost model):

| score panel passed in | raises? | CAGR | Sharpe | MaxDD | turnover | avg names |
|---|---|---|---|---|---|---|
| **entirely NaN** | **no** | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.0 |
| all NaN except one name | **no** | 0.0195 | −1.1853 | −9.34% | 0.01 | 1.0 |

An all-NaN score panel produces `cagr=0, sharpe=0, maxdd=0, turnover=0, avg_names=0` and
**no exception and no log line**. That row is indistinguishable in a formatted table from
"the strategy was correct and correctly did nothing". It is the numerical form of a
fabricated result: every metric is a real number and none of them mean anything.

The single-name case is worse in a different way — it silently runs a **1-name book**,
well inside every `PortfolioConfig` limit, and reports it as a legitimate backtest.

**Root cause chain** (same as `agent_cross_sectional` §B1): `build_rebalance_weights`
does `if not valid.any(): continue`, leaving the target row at zero, and
`apply_turnover_budget` cannot throttle a target of zero because the 35% budget is
measured target-to-target. So a degenerate score is not merely un-flagged, it is
*actively interpreted* as "sell everything, immediately, for free".

**Suggested fix (not applied).** In `run_backtest`, before computing weights:

```python
finite = np.isfinite(sc.to_numpy(dtype=float))
if finite.sum() == 0:
    raise ValueError("score panel is entirely non-finite -- refusing to report a "
                     "0.00/0.00/0.00 backtest as a result")
if (np.isfinite(sc.to_numpy(dtype=float)).sum(axis=1) == 0).mean() > 0.02:
    logger.warning("%.1f%% of score rows are entirely non-finite; the book will be "
                   "liquidated on those dates for free", ...)
```

The second check is the one that matters for live trading: it converts a silent,
un-costed, un-budgeted full liquidation into a visible warning.

---

## B3 — `RelativeStrengthStrategy.warmup()` under-reports by one bar, so the strategy
## emits a real **flat** signal where it should emit **no signal**. Severity: LOW.

`roc()` requires `len(closes) > period` (`if len(closes) <= period: return nan`), i.e.
`period + 1` bars. `warmup()` returns `period`. So on exactly bar `period` the
`SignalStrategy.feed` guard (`len(closes) < self.warmup(...)`) lets `signal()` through,
`roc()` returns NaN, and the strategy returns a flat `0` — indistinguishable from a
genuine flat. One bar out of ~4,600; harmless in practice, but it means the flat branch
is reachable for two different reasons, which is exactly the ambiguity that makes
"signal liveness" hard to audit.

---

## B4 — a NaN at either endpoint of the lookback silently becomes **flat**, not
## **no-data**. Severity: MEDIUM for any live deployment.

`roc()` only reads `closes[-1]` and `closes[-period-1]`, so it is immune to NaNs in the
*interior* of the window (verified: a NaN mid-window still returns the correct signal).
But a NaN at **today** or at **exactly `period` days ago** propagates to `m = NaN`, and
`signal()` returns `0` via `if m != m: return 0`.

```
clean window, ROC = 0.02            -> signal  1
NaN in the middle of the window      -> signal  1     (fine)
NaN at t (today)                     -> signal  0     <-- looks exactly like "flat"
NaN at t - period                    -> signal  0     <-- looks exactly like "flat"
```

The catalog's own docstring convention elsewhere in this repo is that NaN means
*untradeable* (that is how I modelled it in the NSE book). Here a data gap is
indistinguishable from a deliberate flat, and in a long-only cross-sectional book those
two produce *opposite* actions — one says "sell it", the other says "we have no idea".
A single vendor gap can therefore force an unintended exit. Worth a `return None` (which
`feed` already handles as "no signal") instead of `return 0`.

---

## B5 — observation about the assigned strategy: the name is wrong, and the shipped
## default is not a meaningful NSE configuration. Severity: documentation.

`relative_strength_strategy.py` is named for a **cross-sectional** concept but contains no
cross-symbol comparison whatsoever. `roc()` is purely per-symbol time-series. This is the
same mislabelling `research/agent_cross_sectional/BUGS.md` §B4 recorded for
`cross_sectional_strategy`, in a second file — so it is systematic across the catalog, not
a one-off.

Separately, the shipped default `threshold=0.005` against a 20-day ROC is far too loose to
mean anything: on the TRAIN window it puts **53.7%** of symbol-bars in the long branch and
only **5.5%** in the flat branch, i.e. the three-way branch is nearly a two-way branch and
the `0` case is close to dead code. The `-1` branch is likewise unusable in a long-only
Indian delivery account. See `REPORT.md` §4 for what the genuinely cross-sectional
reading does instead.