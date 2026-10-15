# Fast-path validation — exhaustive

**Question:** is `research/optimize/fastpath.py` provably a no-op on results?
**Run:** 84 strategies × 48 symbols × (shipped default + 5 random configs), TRAIN and
TEST, plus edge cases, determinism and rebind-completeness checks.

## Result: **YES — 51,520 comparisons, 0 divergences, 0 errors**

| phase | what | result |
|---|---|---|
| R1/R2 | all 84 strategies × 48 symbols, default + 5 random configs, TRAIN+TEST | **51,520 comparisons, 0 divergences, 0 errors** (5045 s) |
| R3 | edge lengths: `n < period`, `n == period`, `n == period+1`, `n == 2*period`, constant series, single spike, fractional period | 842 cases → **96 divergences, all one class** (below) |
| R4 | container types: list, tuple, numpy array, deque | 80 cases, **0 failures** |
| R5 | rebind completeness across all 84 catalog modules | **0 escaped top-level**; uninstall incomplete (below) |
| R6 | determinism, in-process and cross-process | **identical**; cross-process matches in-process |
| R7 | control pair | 10 cases, 0 divergences |

## Two defects the exhaustive run found (both since fixed)

**1. Fractional `period` was silently accepted.** 96 of the 842 R3 cases. The original
raises `TypeError` on `values[-2.5:]`; the wrapper `int()`d the period and returned a
number instead. A no-op must reproduce the error, so `_dyn`/`_dyn3` now pass
non-integral periods straight through. Re-run: **0 divergences.**

This class is unreachable from the sweep — every Config field feeding these functions is
typed `int` — but it was a genuine behavioural difference.

**2. `uninstall()` restored only the indicators module.** All **42** catalog modules kept
holding wrappers, so installing the fast path in one test left the process patched for
every later test. `uninstall()` now walks all modules and reverses every rebind.
Verified: **0 modules still wrapped** afterwards.

## Verdict

The fast path is result-preserving across the entire catalogue. Every strategy's equity
curve, total tax, total fees, turnover, exposure, trade count and per-trade fields are
identical with it installed and uninstalled.

Separately confirmed against the recorded sweep: replaying **20 saved pairs** after all
fixes gives max |ΔCAGR| = **1.8e-3**, attributable to whole-share flooring alone. The
4,032-row artefact is intact.
