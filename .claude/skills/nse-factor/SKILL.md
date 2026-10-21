---
name: nse-factor
description: Design and implement a new cross-sectional factor for the NSE NIFTY-50 systematic book, then measure it honestly against a scrambled null and a do-nothing benchmark. Use when asked to propose, implement, or test a trading signal, alpha factor, ranking variable, or new idea for the nsealgo research programme.
---

# Designing a factor that survives contact with a null

You are contributing to a 35-wave search over NIFTY-50 signals. **Most signals
will not work.** That is the expected outcome, not a failure — the programme has
already falsified the price-only technical hypothesis four separate ways
(scrambled null p=0.386, walk-forward 6/13, PIT universe edge +0.41pp, and
holding-the-universe 8/13 on every metric).

Your job is to **find out**, not to find a winner. A factor that honestly shows
no edge is a useful result and will be reported as such.

## The four gates a factor must pass

Every cell you produce is measured against all four. A factor that fails any of
them is not a finding.

1. **Edge over its own scrambled null** — each date's cross-section permuted,
   preserving the score distribution while destroying the symbol↔score
   association. This is not a time-shift; shifting in time smuggles real lagged
   information back in.
2. **Edge over holding the universe** — the equal-weight universe with the
   *identical* cost stack. Beating a scrambled null is necessary, not sufficient.
3. **Walk-forward survival** — 13 annual folds, params selected once on the
   first fold. A p-value after post-hoc selection is not a p-value.
4. **Point-in-time universe** — lagged membership, not today's NIFTY-50.
   Survivorship is worth 1.6–7.2 pp/yr.

## Hard rules

- **No lookahead.** A factor may only use bars up to and including the current
  one. No `shift(-1)`, no centred rolling windows, no `df.iloc[i+1]`.
- **Pure function of the price panel.** Signature is
  `(px: pd.DataFrame) -> pd.DataFrame`, one column per symbol, higher = better.
  You get close prices. If you need OHLC you must add it to the panel loader
  first and say so.
- **One file per agent.** Write `research/sweep/factors_<yourid>.py` and register
  with `@factor("your_factor_name")`. **Never edit `harness.py`** — 40 agents
  run in parallel worktrees and a shared edit merges into conflicts.
- **No new dependencies.**
- **Decimal for money** — but factors are ratios, so float is correct there.
  Only the accounting layer uses Decimal.

## Reference implementations worth reading

`research/sweep/harness.py` contains 37 working factors. Read it before
writing yours — you will learn the house idioms (`.rolling()` with
`min_periods`, `np.isfinite` guards, `.replace(0, np.nan)` for divisions).

Good examples of different factor *families*:

| family | example | why it is interesting |
|---|---|---|
| momentum | `mom_12_1` | skips the last month to avoid short-term reversal |
| trend | `px_ma200` | distance above the 200dma |
| reversal | `rev_21` | the recent laggard ranks highest |
| volatility | `low_vol`, `idio_vol` | low vol is the best-behaved long-only factor in India |
| position | `high_52w`, `range_pos` | proximity to the 52-week high |
| microstructure | `autocorr`, `variance_ratio` | trending vs mean-reverting, from returns alone |
| proxy | `quality_proxy`, `value_proxy` | the price-only shadows of factors we cannot compute |

## Good factor design

**Prefer a family you have not tried.** The catalogue already covers momentum,
trend, reversal, volatility, position and liquidity. A new *idea* beats a new
parameterisation of an old one, always.

**Make the sign hypothesis explicit.** Write down, in a comment, why higher
should rank better and what mechanism produces the return. If you cannot
articulate it, the factor is noise-mining and the null will say so.

**Prefer ranks over z-scores for blends** — scale-free, outlier-proof. But test
z-scores too; they weight tails differently and sometimes find something ranks
miss.

**Test the opposite sign.** If your factor has a hypothesis, its negation is
also a hypothesis, and one of the two should work if the mechanism is real.
Run both and report which won.

## What to deliver

1. `research/sweep/factors_<yourid>.py` — the factor(s), with the sign
   hypothesis in a comment.
2. A measurement of every (factor, n_hold, buffer, clock) cell you own, on
   TEST and TRAIN, written to `tem/waves/wave<N>/agent<NN>.jsonl`.
3. A short report of what you found, including the failures.

## Running the measurement

```bash
# From your worktree. The harness does the work; you supply the factor.
PYTHONPATH=src:. .venv/bin/python -m research.sweep.run \
    --wave <N> --agent <yourid> --agents 40 --out tem/waves/wave<N>
```

Cells are sharded deterministically by `--agent`, and results are **appended**,
so re-running resumes rather than redoing.

## Reporting honestly

State the number, then the comparison. "Edge over null = +0.8pp on TEST" is a
result. "Promising!" is not.

If nothing works, say so plainly and explain what you ruled out. A clean
negative narrows the space for the next 34 waves, which is worth more than a
false positive.

**Never** report a factor as promising without its null comparison. The
programme's own history: a family that beat its null in 43/44 configs
(p=2.6e-12) was pure selection, and vanished under walk-forward.

See also `nse-wave-orchestration` (how the wave runs) and
`nse-signal-validation` (the full validation protocol).
