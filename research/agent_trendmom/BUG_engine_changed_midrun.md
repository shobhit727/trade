# BUG / INCIDENT — the shared backtest engine changed mid-run, and it flips the result

**Severity: CRITICAL for reproducibility.** Discovered by `research/agent_trendmom` while
trying to explain why the same script produced two different sets of numbers.

> **Update, 14:11:08.** This happened **twice**. `engine.py` was edited again six minutes
> after the first fix, refining `_exit_allocation` to sell positions all-or-nothing instead
> of truncating them. sha256 `c155806c…` → `6dbee619…`. §2b below records the second delta.
> Recommendation 1 below is now urgent rather than advisory: **the harness is being edited
> faster than the experiments can be trusted.**

**I did not cause this and did not modify any file under `src/nsealgo/**`.** I ran
`git status` / `git diff` to confirm, and the change is in someone else's working tree.

---

## 1. What happened

`src/nsealgo/backtest/engine.py` was rewritten at **2026-10-09 14:05:28 IST** while my
agent session was in flight. The rewrite is uncommitted (it sits in the working tree as a
modification to `b2c9b28`). The function that changed is **`apply_turnover_budget`**, and
the change is behavioural, not cosmetic:

**Before** — one scalar `lam` scaled the *whole* book toward the new target, then the
result was thinned:

```python
lam = min(1.0, budget / changed)
out = _thin(cur + lam * (tgt - cur), max_names)
```

**After** — exits and adoptions are separated. Forced exits are unconditional and paid for
first; only the leftover budget scales adoption:

```python
wanted   = tgt > DEAD_WEIGHT_EPS
kept     = tgt[wanted].nlargest(max_names).index
to_zero  = (cur > 0) & ~held_by_target
out      = cur.where(~to_zero, 0.0)
...  # exits spend `cap`; adoption spends whatever is left
```

The new version's own docstring says the old one was wrong: a name that had dropped out of
the target only decayed by `1 - lam` per rebalance, so `_thin` (which kills a weight only
below `DEAD_WEIGHT_EPS = 1e-4`) carried the residue for months. The delivered book then
held mostly names the signal did not want.

**The old version is the one that shipped every number in `reports/VALIDATION_v1.md`, in
`AGENTS.md`, and in every `research/agent_*/REPORT.md` written before 14:05:28 today.**

## 2. Why it matters — it changes the ANSWER, not just the precision

Same strategy, same data, same costs, same declared 5-variant budget, same declared
selection rule (max TRAIN Sharpe). Only the engine differs.

| | OLD engine | NEW engine (`sha256 c155806c…`) |
|---|---|---|
| **Selected on TRAIN** | **V5** (5/20/10, thr 1%) — Sharpe 0.76 | **V3** (50/200/60, thr 1%) — Sharpe 0.64 |
| **V5 TRAIN Sharpe** | **0.76** | **0.31** |
| **V3 TRAIN Sharpe** | 0.64 | 0.64 |
| **Selected variant, TEST CAGR** | **+3.13%** | **−0.27%** |
| **Selected variant, TEST Sharpe** | −0.24 | −0.44 |
| **Selected variant, TEST MaxDD** | −15.01% | −22.58% |
| Avg names held, TEST | 28.4 (over the 22 limit) | 17.2 |
| V5 TEST CAGR | +3.13% | +0.53% |

**The selection flipped from a variant that looks like a modest success to a variant that
is unambiguously a failure, and the out-of-sample headline moved 3.4 pp of CAGR.**

Note that V3's TRAIN Sharpe (0.64) is *identical* under both engines while V5's collapses
from 0.76 to 0.31 — which is exactly why the selection moved. `apply_turnover_budget` is
not a rounding detail; it decides what the book actually holds.

## 2b. The second edit (14:11:08) — smaller, but still visible

`_exit_allocation` was changed from a proportional truncation
(`np.minimum(ordered, max(0, cap - already))`) to all-or-nothing sales
(`fits = ordered.cumsum() <= cap`). Same strategy, same data, same costs:

| | `c155806c…` (14:05:28) | `6dbee619…` (14:11:08) | delta |
|---|---|---|---|
| **V3 (SELECTED) TEST CAGR** | **−0.27%** | **−0.27%** | **0.00** |
| **V3 TEST Sharpe / MaxDD / names** | −0.44 / −22.58% / 17.2 | −0.44 / −22.58% / 17.2 | **0.00** |
| V5 TRAIN CAGR | 9.02% | 9.04% | +0.02 pp |
| V4 TRAIN CAGR | 4.35% | 4.31% | −0.04 pp |
| V1 TRAIN CAGR | 6.24% | 6.25% | +0.01 pp |
| V1 TEST CAGR | −1.54% | −1.49% | +0.05 pp |
| V4 TEST CAGR | −1.54% | −1.42% | +0.12 pp |
| BH top-22 / EW BH / composite | unchanged | unchanged | 0.00 |

The **selected variant is invariant** across both post-14:05 versions, and so are the
benchmarks — so `agent_trendmom`'s headline conclusion survives. But **three of five variants
moved**, including one by 0.12 pp of OOS CAGR, and nothing about that is noise: it is a
deliberate change to what gets sold. A report generated one engine-version ago is not
wrong-by-rounding; it is answering a different question.

## 3. Contamination — some published numbers are now stale

Any agent report whose backtest ran **before 14:05:28 IST on 2026-10-09** used the old
engine. In this repo that includes (from `git status`, all untracked research dirs):
`agent_absolute_momentum`, `agent_adx_trend`, `agent_anchored_vwap`, `agent_atr_breakout`,
`agent_atr_trailing`, `agent_bb_squeeze`, `agent_bollinger_bands`,
`agent_breakout_momentum`, `agent_cci`, `agent_cmf`, `agent_cointegration`,
`agent_correlation_gate`, `agent_cross_sectional`, `agent_cumulative_delta`, `agent_dema`,
`agent_dispersion`, `agent_distance_ma`, `agent_donchian`, `agent_dual_ma`,
`agent_dual_momentum`, `agent_ema_cross`, `agent_fisher`, `agent_flag_pattern`,
`agent_gap`, `agent_gaussian`, `agent_hull_ma`, …

Their relative rankings may still be informative, but **their absolute CAGRs are not
comparable to anything produced after the cut-over, and the cross-agent "which catalog
strategy is best" table is invalid across the boundary.**

`agent_dual_ma` is a concrete example: it selected V5 (5/20 EMA) and reported **1.46%**
TEST CAGR. `agent_trendmom` — same selection rule, same engine generation — selected V3 and
reported **−0.27%**. Both are honest runs of honest harnesses; they are answering on
different books.

## 4. What I did about it

- Pinned `engine.py` **sha256 `c155806cfcb303b4400e710789d0380dc0dca8a2e81718a816342ed33330870e`**
  into `research/agent_trendmom/run.py`, which prints it on every execution and records it
  in `results.json`. Every number in `research/agent_trendmom/REPORT.md` was produced
  against that hash.
- Verified reproducibility: three consecutive executions of `run.py` gave byte-identical
  variant tables.
- Threw away the pre-14:05 numbers entirely rather than reporting the nicer of the two.

## 5. Recommendations (I am not making these changes — brief §9 forbids editing `src/`)

1. **Commit the engine change, or revert it — and stop editing it while experiments run.**
   Leaving a behaviour-changing harness edit uncommitted in a working tree shared by ~30
   concurrent agents is the actual bug here, and on 2026-10-10 it was done **twice in six
   minutes**, mid-flight.
2. **Stamp the engine hash into every backtest artefact.** A one-line
   `ENGINE_VERSION = sha256(engine.py)` in `run_backtest`'s `BacktestResult.diag` would make
   stale results self-identifying instead of requiring this post-mortem.
3. **Add a regression test on the delivered book, not just on constraints.** The old
   version satisfied every documented constraint (12% single name, 25% sector, 35%
   turnover) while holding 28 names against a 22-name limit. Assert
   `avg_names <= max_names` and `invested >= 1 - cash_buffer - tol` in `run_backtest`'s own
   test suite; both would have caught it.
4. **Serialise agent runs against the harness.** Multiple agents were importing
   `nsealgo` concurrently, so a mid-flight source edit silently forked every running
   experiment into two populations.

---

*Filed by `agent_trendmom`. Reproduce with:
`.venv/bin/python research/agent_trendmom/run.py` — the engine hash is printed on line 2
of the output and stored in `results.json` under `engine_sha256`.*