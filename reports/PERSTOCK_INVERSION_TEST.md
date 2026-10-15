# Inverted-signal test — does trading the opposite side rescue anything?

**Question.** `PERSTOCK_EDGE_VS_COST.md` found three signals with a *negative* gross
day-selection edge (`williams_r_strategy` −9.6 bp/day, `rsi_strategy` −9.3,
`bollinger_bands` −9.3) and flagged shorting as "the single most promising untested
direction". This tests that.

**Method.** Trade LONG when the strategy says SHORT (signal negated), same engine, same
cost stack, same TRAIN-select → TEST-once protocol. No shorting, no margin, no borrow —
purely a sign flip, which the existing long/flat engine can express.

TEST 2024-01-01 → 2026-10-01, 10 large-cap names, shipped default configs, CGT on.

| strategy | normal CAGR | **INVERTED** | buy-and-hold | inverted alpha |
|---|---|---|---|---|
| `williams_r_strategy` | +3.22% | **−3.73%** | −1.99% | −1.74% |
| `rsi_strategy` | −1.19% | **−3.03%** | −1.99% | −1.04% |
| `bollinger_bands` | +0.16% | **−1.39%** | −1.99% | +0.60% |
| `moving_average_cross` | −3.88% | −3.72% | −1.99% | −1.73% |

## Verdict: no, inversion does not rescue them

**Three of four got worse.** `williams_r_strategy` went from +3.22% to −3.73% — the
inverted version is the losing one, not the original.

Note `williams_r_strategy` inverted has `p_timing = 0.030`, which looks like a hit. It is
the same artefact the full sweep found: beating a random-timing null whose median CAGR is
−15.15%/yr says nothing, and the pair still trails its own buy-and-hold by 1.74pp/yr.

## Correction to the previous report

`PERSTOCK_EDGE_VS_COST.md` said shorting was "the single most promising untested
direction" on the strength of the −9.6 bp/day TRAIN reading. **That reading did not hold
out-of-sample.** The sign of the day-selection edge on TRAIN is not the sign that persists
into TEST, so the "inverted" framing was an artefact of measuring on the training window
and reading it as a property of the signal rather than of that window.

This is the same error in a new place: a statistic computed on TRAIN, treated as a durable
fact. The correction matters more than the negative result, because acting on it — going
short `williams_r` — would have lost money.

## Scope

10 stocks, default configs only, no parameter search. This is a bounded probe, not a
sweep: it is enough to reject the hypothesis cheaply, not enough to conclude nothing
in the catalogue could ever work inverted. A full inverted sweep would cost the same
35 minutes as the original and, on this evidence, is not worth running before the edge-
versus-cost gap is addressed — that gap (signal worth ~24 bp/yr against a ~131 bp/yr
bill) is the binding constraint, and inverting does not change either side of it.
