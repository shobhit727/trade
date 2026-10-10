# BUG — `run_backtest` silently under-invests the book (turnover budget × `_thin`)

Found while assigning `multi_factor_strategy` (see `REPORT.md`). Reported per
`AGENT_BRIEF.md` §8. **No file under `src/` was modified by me.**

> **⚠ STATUS: STILL OPEN.** Another agent concurrently rewrote
> `apply_turnover_budget` during my run (engine md5 `b515819…` → `24da076…`). That
> rewrite fixes the *stale-tail / position-count* half of the problem — its own
> docstring reaches the same diagnosis ("every headline number measured the dilution
> rather than the signal") — but **the under-investment survives it**: the book still
> holds **0.5954** of equity on the fixed engine vs **0.5934** before, against a
> configured 0.90. The dominant remaining cause is **not** `apply_turnover_budget`
> at all — see §3(c) and §6. Read §6 before attempting another fix.

**Component:** `src/nsealgo/backtest/engine.py`
**Functions:** `build_rebalance_weights` / `_project_constraints` (dominant),
`apply_turnover_budget` + `_thin` (secondary)
**Severity:** HIGH — it silently costs every *fast-rotating* strategy a large part
of its return, and it is invisible in the returned metrics.

All figures below were reproduced on engine md5
`24da076e8225a2d8b4283f888d6f2a3c`; the mechanism analysis in §3 was measured on
the pre-rewrite revision and is labelled where that matters.

---

## 1. Claim

`PortfolioConfig(cash_buffer=0.10)` says the book holds ~0.90 of equity.
`build_rebalance_weights` *intends* to emit targets summing to 0.90
(`w_full *= (1.0 - config.cash_buffer)`).

**The realised book does not hold 0.90.** For a strategy whose target book rotates
monthly it holds **0.595 of equity on average** — an unintended ~30% cash drag the
caller never asked for.

## 2. Reproduction

```
$ .venv/bin/python research/agent_multifactor/diag_weights.py
held book (full history)
  invested fraction : mean 0.5954  min 0.0000  max 0.9000
  names held        : mean 17.5  min 0  max 22
  implied cash      : mean 0.4046  (config asks for 0.10)

TARGET weights (as built by build_rebalance_weights, pre-budget)
  invested fraction : mean 0.8345  min 0.0000  max 0.9000
```

## 3. Mechanism

Measured stage by stage over 225 monthly rebalances (`diag_budget.py`):

```
  target total          0.8345   (config wants 0.90)
  demanded one-way turn 0.4818   (budget 0.35)
  lam                   0.7399
  total after blend     0.8337   names 32.0
  total after _thin     0.8165   names 28.0
  => weight lost in the BLEND : -0.0008
  => weight lost in _thin()   : -0.0172
  rebalances where turnover fit inside the budget: 33/225 (14.7%)
```

Two independent defects stack:

**(a) The turnover budget is smaller than a 22-name monthly rotation.**
A 22-name book rotating completely to a disjoint 22-name book demands a one-way
turnover of ~0.90 (sell 90%, buy 90% → `sum|dW|/2`). The default budget is
**0.35**. It therefore binds on **85.3% of rebalances**, with `lam ≈ 0.74`. This
is a *configuration* inconsistency: `n_positions=22` + monthly rebalance cannot be
honoured under a 0.35 turnover budget.

**(b) `_thin` destroys weight instead of redistributing it.**
Because `lam < 1`, old positions are never fully sold — they persist as residuals
(blended book: **32 names** vs the target's 22). `_thin` then enforces
`max_names=30` by **zeroing** the excess:

```python
return out.where(out.index.isin(out.nlargest(max_names).index), 0.0)
```

That mass becomes cash and is never reallocated, so ~1.7pp of book weight is
destroyed every rebalance. `_thin`'s own docstring says the drops are "not
tradable positions, so they are zeroed rather than carried" — true for a 1e-4
residual, but here it is firing on a systematic backlog created by (a).

Note the blend itself is innocent: it loses −0.0008, i.e. nothing.

**(c) Minor: the target itself is under-invested.** `sum(target)` averages 0.8345,
not 0.90, because `_project_constraints` leaves mass that no name can legally take
as cash. On illiquid tail dates it is far worse — `2026-10-01` produces a target
of **0.216 across 2 names**. This one is documented behaviour ("what nobody can
legally take is left as cash"), but the average shortfall is not surfaced.

## 4. Why it went unnoticed

`run_backtest` reports `diag["avg_names"]` but reports **nothing** about the
invested fraction. An under-invested book is indistinguishable from a cautious one
in the returned metrics. `avg_names` (17.5) also reads as a plausible "position
count" even though `n_positions=22` — the effective cap is `max_names=30`, and the
blended book routinely carries 32 names before thinning.

**The composite factor is immune.** Its turnover demand sits under the budget, so
it holds exactly 0.900 / 22.0 names at either budget. Any strategy that rotates
faster than the composite is silently penalised, and the project's own reference
implementation does not reveal it:

```
TRAIN
  V5         budget=0.35  CAGR  9.56%  Sharpe  0.33  invested 0.620
  V5         budget=1.0   CAGR 13.72%  Sharpe  0.56  invested 0.877
  composite  budget=0.35  CAGR 20.29%  Sharpe  0.90  invested 0.900
  composite  budget=1.0   CAGR 20.29%  Sharpe  0.90  invested 0.900
```

**Impact: 4.16pp of TRAIN CAGR for this strategy (9.56% → 13.72%) — about 36% of
the gross return — is lost to this mechanism rather than to the market or to costs.**

## 5. It does NOT explain the strategy's failure

Reported so this bug is not mistaken for a rescue:

```
TEST
  V5         budget=0.35  CAGR  1.79%  Sharpe -0.38  invested 0.628
  V5         budget=1.0   CAGR  1.31%  Sharpe -0.33  invested 0.849
```

Out of sample, removing the defect makes the strategy **slightly worse**. It is a
TRAIN-phase distortion of every fast-rotating result in this project, and a real
bug, but it is not the reason `multi_factor_strategy` fails.

## 6. Suggested fixes (not applied — `AGENT_BRIEF.md` §9 forbids editing `src/`)

**Read this first: the concurrent rewrite already did #2/#4 and it was not enough.**
The remaining shortfall is dominated by (c), so fix that first.

1. **Report it — do this regardless.** Add `diag["invested_fraction"]` (mean and min
   of `held.sum(axis=1)`) and `diag["budget_binding_frac"]` to `run_backtest`. This
   is the single change that would have caught the bug: every metric is currently
   blind to it. **Do this first, before any behavioural fix.**
2. **Attack `_project_constraints`, not the budget (§3c).** The target itself
   averages **0.8345**, not 0.90, and collapses to 0.216 on thin-coverage dates. The
   projection leaves un-placable mass as cash and the caller never learns. Either
   renormalise the projected target back to `1 - cash_buffer`, or expose the
   shortfall. Until the target is right, no budget value can fix the book.
3. **Reconcile the config.** `n_positions=22` with monthly rebalance demands ~0.90
   one-way turnover; `turnover_budget=0.35` is incompatible with it and binds on
   85% of rebalances. Raise the budget to >= ~0.9, or reduce `n_positions`. They
   are currently inconsistent with each other.
4. ~~Redistribute in `_thin`~~ — **done** by the concurrent rewrite.
5. ~~Renormalise the blended sleeve back to `1 - cash_buffer`~~ — the rewrite's
   exit-first/adopt-with-surplus logic supersedes the old `lam` blend. Verified
   insufficient on its own (0.5934 → 0.5954).

## 7. Concurrency note

`src/nsealgo/backtest/engine.py` was rewritten by another agent **twice while this
report was being produced**. All headline numbers here were re-verified against
md5 `24da076e8225a2d8b4283f888d6f2a3c` and are **byte-identical** across engine
revisions `b515819…` and `24da076…` — the strategy's verdict is robust to the
rewrite. `research/agent_multifactor/final_run.py` re-runs until the engine hash is
stable before and after, so any future re-run is safe to trust.

## 8. Repro

```
.venv/bin/python research/agent_multifactor/diag_weights.py   # headline symptom
.venv/bin/python research/agent_multifactor/diag_budget.py    # stage-by-stage
.venv/bin/python research/agent_multifactor/diag_engine.py     # attribution vs composite
.venv/bin/python research/agent_multifactor/disclosure_budget.py
.venv/bin/python research/agent_multifactor/final_run.py    # hash-pinned authoritative run
```