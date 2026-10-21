# 44. Session Learnings — Quant Research Validation Discipline

> **Last Updated**: 2026-10-19
> **Confidence**: High — every pattern below was paid for with a wrong result that had to
> be retracted.
> **Source**: 2026-10-19 session (Phases 0/1/2/2c/7/8 of the nsealgo per-stock programme).
> **Status**: Research-only. No capital deployed. Band D.

---

## 1. The five findings that changed a number

| # | Finding | Magnitude | Root cause |
|---|---|---|---|
| 1 | Cost stack understated | **1.469×** (21.92 → 32.32 bp) | bps-of-turnover documented, consumed as bps-of-notional |
| 2 | TRENT phantom crash in TEST | **−33%** on 2026-01-01 | unback-adjusted 1:1.5 bonus, below C5's 45% bar |
| 3 | Survivorship bias | **1.6–7.2 pp/yr** | today's NIFTY-50 backfilled to 2008 |
| 4 | Look-ahead in PIT membership | up to 1 month | current month's month-end used for every date in it |
| 5 | PIT panel NaN poisoning | 206 NaN bars, MaxDD −100% | membership masked into *prices* instead of *selection* |

Findings 1 and 2 had been silently corrupting **every** prior stored result. Both were
found only because a result was re-derived from first principles instead of trusted.

---

## 2. Patterns discovered

### Pattern: Derive constants from the canonical source, never restate them

**Context**: Any constant that exists in two places (engine + harness).

`research/optimize/config.py` carried `STATUTORY_BPS = 11.92` with a comment describing
it as bps-of-turnover (matching `nsealgo.costs.CostModel.round_trip_bps`, which divides by
2×notional), but `FeeSchedule._fee` charged it as bps-of-notional. A **1.469×**
understatement of the entire cost model, invisible for the life of the project.

**Implementation**: import and derive. A test then pins the two harnesses together.

```python
def _delivery_statutory_bps() -> D:
    """Delivery-equity statutory round trip, in bps of one-leg notional.

    Single source of truth is :class:`nsealgo.costs.CostModel`.
    """
    from nsealgo.costs import CostModel
    model = CostModel(segment="delivery", slippage_bps=D("0"))
    return model.round_trip_bps(CAPITAL_INR) * 2   # turnover-bps -> notional-bps
```

**Rule**: if a number appears in two modules, one imports the other. Never copy it.
When the unit is ambiguous, the import is what disambiguates it.

---

### Pattern: The "do nothing" benchmark is the test that matters

**Context**: Any claim that a strategy "works".

A signal-scrambled null answers *"does the ranking carry information?"*. It does **not**
answer *"would I have been better off just holding?"*. Both answers are required, and
they are different questions.

Phase 7 built an equal-weight universe benchmark with **identical treatment** (PIT
membership, 32.32 bp round trip, FIFO lots, STCG/LTCG, annual rebalance) and found the
book beat it in **8/13 folds on CAGR, 8/13 on Sharpe, 8/13 on MaxDD** — a coin flip, p=0.240.
Without that comparison, "no edge vs a scrambled null" would have been reported as
"mild alpha".

**Implementation**: benchmark the *do-nothing* alternative with the same cost stack.
A cost-free benchmark flatters the strategy and is worthless.

```python
# Benchmark = equal-weight the whole universe, same rebalance schedule, same costs.
bench = _bench(px, rebalance="A", tradable=pit_mask)
# The decision metric: does the book beat holding, risk-adjusted?
book_alpha = book.cagr - bench.cagr
dd_improvement = bench.dd - book.dd
```

---

### Pattern: Exposure is the first-order driver of long-only equity returns

**Context**: Any long/flat systematic equity book.

Phase 1 (9,024 runs) bucketed every result by exposure:

| exposure bucket | n | median CAGR | % positive |
|---|---|---|---|
| <30% | 1,612 | 0.000 | 30.6 |
| 30–40% | 624 | −0.029 | 32.7 |
| 40–50% | 1,001 | −0.046 | 24.1 |
| 50–60% | 732 | −0.016 | 39.1 |
| **>60%** | 543 | **+0.019** | **58.0** |

The >60% bucket was the only one with a positive median. A book in cash 55% of the time
cannot earn an absolute return **however cheap the trading is** — and cutting turnover 55×
(daily→annual) bought only ~0.8%/yr.

**Rule**: measure exposure before optimising anything else. If exposure is low, the
return is capped and no amount of signal work fixes it.

---

### Pattern: Selection must be charged to the hypothesis

**Context**: Any grid, sweep, or parameter search evaluated on a holdout.

Phase 2 looked like a triumph: the trend family beat its scrambled null in **43/44**
configs, binomial **p=2.6e-12**. Walk-forward over 13 annual folds erased it —
**6/13, p=0.778**. The 43/44 was selection: 44 configs on one 2.75-year window, and the
95th percentile of the 96-cell family was 60%.

**Implementation**: always report the *family* distribution, never the best cell alone.

```python
cells = df.groupby(["strategy", "rebalance"]).agg(pos=("cagr", lambda s: (s > 0).mean()))
print(cells.pos.describe(percentiles=[.5, .95]))   # the 95th pct is the real bar
print(f"cells at/above best: {(cells.pos >= best).sum()} of {len(cells)}")
```

**Rule**: a p-value computed *after* selecting the best of N cells is not a p-value.
Report the family's spread, then the walk-forward.

---

### Pattern: Detection rules must run before the rules they would otherwise react to

**Context**: Data cleaning, where rule N inspects adjacency that rule M has changed.

Rule C10 (unadjusted corporate actions) keys off the overnight gap. Written after C5
(extreme-move removal) and C9 (frozen-run removal), it fired on gaps those rules had
**created by deleting rows** — nestleind 2010-01-11 (3.8% raw, a 30%+ gap once the
adjacent freeze was dropped) and bajajfinsv twice (7.0% and 0.0% raw). A deletion is
not a corporate action.

**Implementation**: order detection before mutation, and say so in the code.

```python
# ORDER IS LOAD-BEARING: C10 runs BEFORE C5 and C9, on the raw series.
# Run after them and it fires on gaps those rules CREATED by deleting rows.
df = _apply_c10(df, symbol, rep)   # <- before any row deletion
```

---

### Pattern: Repair only what is provable; disclose the rest

**Context**: Any rule that modifies data.

The first C10 draft truncated the series at any ambiguous corporate action. Measurement
killed it: truncation would have **deleted the real 2008 crash** (bajajfinsv) and
duplicated C9's nestleind fix. The shipped rule only *rescales* a provable 1:x ratio and
records everything else without touching a row.

```python
nearest = min(C10_SPLIT_RATIOS, key=lambda r: abs(r - ratio))
if abs(nearest - ratio) <= C10_RESCALE_TOLERANCE * nearest:
    df.loc[df.index < event, ["open", "high", "low", "close"]] *= nearest
    rep.rescaled_actions.append((symbol, str(event.date()), float(nearest)))
else:
    # Disclosed, NOT modified. Price alone cannot separate a crash from a demerger.
    rep.unresolved_actions.append((symbol, str(event.date()), float(ratio), spread))
```

**Rule**: an unrepaired event that is *flagged* is recoverable; a silently deleted
drawdown is not. Under-cleaning is visible, over-cleaning is fatal.

---

### Pattern: A physical constraint on the data is a better detector than a threshold

**Context**: Finding unadjusted corporate actions in vendor price data.

C5 used a 45% close-to-close threshold and missed TRENT's 1:1.5 bonus (only −33.0%).
But NSE enforces a **±20% daily circuit limit**, so an overnight gap beyond that is
arithmetically impossible as a market move. The bound is derived from the exchange, not
from the data, so it does not need tuning.

**Rule**: prefer a bound justified by mechanism (exchange rules, circuit limits, lot
sizes) over one justified by a histogram of what the data happens to contain.

---

### Pattern: Mask selection, never prices

**Context**: Point-in-time universes.

NaN-ing non-members out of the price panel poisoned the equity curve: a name dropped
from the index on 1 June is still held by an annual-rebalance book until January, so
`q * NaN` produced 206 NaN bars and MaxDD reported a nonsense −100%.

```python
# Membership gates SELECTION only. Prices are always observed.
live = px.notna() & (px > 0) & tradable.reindex(index=px.index, columns=px.columns)
# A held name with no fresh quote is carried at its last price, never fabricated.
p = last_px.get(sym)
```

**Corollary**: an *annual* rebalance makes this unavoidable. Any longer holding period
widens the window in which a held name can leave the universe.

---

### Pattern: Point-in-time membership must be lagged

**Context**: Any point-in-time index membership.

The first implementation used the **current** month's month-end membership for every
date in that month — a look-ahead letting a name enter up to a month before it joined.
GOAL.md §6 forbids this class of error outright.

```python
prior = px.index[px.index < rows[0]]        # membership published at END of M-1
keep = _pit_members(m, prior[-1])
```

**Rule**: the membership in force during month M is the one published at the end of M−1.

---

### Pattern: Report a bias as a floor when the correction is incomplete

**Context**: Any survivorship or coverage correction.

Only 68.8% of point-in-time members have price history (23/50 in 2009 → 47/50 in 2026).
The unpriceable ones are disproportionately the collapsed and delisted names, so the
corrected universe is biased *optimistically*. The measured 8.9 pp/yr is therefore a
**floor**, not an estimate.

**Rule**: state the coverage fraction next to the correction, and label the direction of
the residual bias.

---

### Pattern: A mandate conflict is not an engineering problem

**Context**: When a measured strategy cannot satisfy the constitution.

`risk/limits.py` hard-codes `max_drawdown_halt = -15%`. The money-making book has
MaxDD −33.8%. The equal-weight universe spends **28% of its time below −10%** and has a
−67.9% worst drawdown. Simulating the switch: flattening at −15% and re-entering at −10%
gives up **7.4 pp/yr** and *still* leaves −34.4% drawdown. There is no exposure level
that satisfies −15% while holding this asset.

**Rule**: when the constitution and the asset class are incompatible, that is a decision
for the human, not something to engineer around. Do not quietly widen a hard-coded
limit — `verify_limits()` exists precisely to make that impossible.

---

## 3. Best practices applied

1. **Re-derive, don't trust.** Every headline number was recomputed from first
   principles at least once. All three major bugs were found this way, never by
   inspection. *When*: any number that will be quoted or shipped.
2. **One-sided repair rules.** Modify only what is provable; disclose the rest. *When*:
   any data-cleaning rule that could delete real market history.
3. **Bounds from mechanism over thresholds from data.** Circuit limits, lot sizes,
   exchange rules. *When*: writing a detector for data defects.
4. **Derive shared constants by import.** Never restate a number in two modules. *When*:
   two harnesses must agree (engine vs research).
5. **Test the guardrail, not just the happy path.** The C10 crash-survival test and the
   "exclusions must match the production loader" test both caught real divergence.
   *When*: any rule that can silently disagree with another.
6. **Null-matched comparison.** Signal-scrambled null preserves the score distribution
   while destroying symbol↔score association — not a time-shift, which smuggles real
   lagged information back in. *When*: judging whether a signal carries information.
7. **Report the family, not the winner.** Percentiles across all cells before the best
   cell's p-value. *When*: any grid evaluated on a holdout.
8. **Walk-forward as the final arbiter.** Params re-selected once on the first fold
   only; later folds reuse them. Re-picking per fold turns a walk-forward into N
   independent in-sample searches. *When*: validating a selected configuration.
9. **Cost the benchmark identically.** A cost-free benchmark flatters the strategy.
   *When*: comparing against "do nothing".
10. **Look for the mandate conflict early.** Checking the kill-switch limit against the
    strategy's drawdown would have saved two phases. *When*: a measured result must
    satisfy hard-coded risk limits.

---

## 4. Mistakes to avoid

1. **Restating a unit-bearing constant.**
   *What went wrong*: `STATUTORY_BPS` documented as bps-of-turnover, consumed as
   bps-of-notional → 1.469× understatement of all costs.
   *Prevent*: import and derive. Add a test asserting the two harnesses agree.

2. **A repair rule that deletes on ambiguity.**
   *What went wrong*: C10 truncated at any ambiguous event → would have deleted the real
   2008 crash and duplicated C9's nestleind fix.
   *Prevent*: repair only provable cases; flag the rest. Ask "what real history could
   this rule destroy?" and test exactly that.

3. **Running a detector after the rules it would react to.**
   *What went wrong*: C10 fired on gaps created by C5/C9 deletions.
   *Prevent*: detection before mutation; document the ordering constraint in-code.

4. **Masking prices instead of selection.**
   *What went wrong*: PIT NaN mask → 206 NaN equity bars, MaxDD −100%.
   *Prevent*: mask the *universe*, never the *price*; carry last-known price.

5. **Look-ahead in point-in-time series.**
   *What went wrong*: current month's membership applied to every date in that month.
   *Prevent*: lag to the prior period's publication.

6. **Quoting a post-selected p-value.**
   *What went wrong*: "43/44 configs beat the null, p=2.6e-12" — 44 configs on one
   window. Walk-forward: 6/13, p=0.778.
   *Prevent*: report the family distribution; walk-forward before claiming anything.

7. **Testing a hypothesis with a confounded comparison.**
   *What went wrong*: `corr(turnover, alpha)` across pairs with *different* signal
   liveness conflated "holding pays" with "this strategy is dead".
   *Prevent*: fix the signal, vary one thing.

8. **Blaming your own changes for pre-existing failures.**
   *What went wrong*: three crypto tests failed in a full run; they pass in isolation and
   fail *differently* at stashed HEAD.
   *Prevent*: reproduce in isolation and compare against HEAD before attributing.

9. **Unit typos in verification scripts.**
   *What went wrong*: wrote `stt = 0.100 + 0.100` meaning "0.1% + 0.1%" — that is 10%,
   producing a 101× error in the "independent" check. The script's whole purpose was
   independent verification.
   *Prevent*: in a verification script, use unmistakable literals (`0.001` for 0.1%) and
   print the derived total before comparing.

10. **Believing a p-value from a family you didn't compute.**
    *What went wrong*: 74.5% positive in the best cell looked like p=0.0005, but the
    96-cell family's 95th percentile was 60% and the median 36%.
    *Prevent*: compute the family before quoting any cell.

11. **Assuming a "risk control" helps before measuring it.**
    *What went wrong*: the market regime filter looked like it should cut 2008 — it
    went flat in **January 2008**, six months early, and sat in cash for 626 days of a
    losing market. It also never changed the result at all.
    *Prevent*: simulate the control and measure it. A filter's benefit is an empirical
    claim.

12. **Writing instinct files in the wrong format.**
    *What went wrong*: recorded the instincts as JSON. The importer only accepts
    `.yaml`/`.yml`/`.md` with `---`-delimited frontmatter, and a hand-written file in
    the wrong place is invisible to `instinct-cli.py status` — it looked installed and
    was not.
    *Prevent*: install instincts with the CLI, then **verify with `status`**. Keep the
    YAML in the repo as source of truth (`research/instincts/`) and re-import from it.
    Use `scope: project` so a trading lesson does not leak into unrelated repos.

13. **Blowing up your own context with a bad groupby.**
    *What went wrong*: episode analysis grouped by a cumsum that incremented per bar,
    producing 762 one-bar "episodes" and flooding the output.
    *Prevent*: assert the group count before printing; sanity-check the first few groups.

---

## 5. Reusable snippets

### Derive a shared constant and pin the two harnesses

```python
# research/optimize/config.py
def _delivery_statutory_bps() -> D:
    from nsealgo.costs import CostModel
    model = CostModel(segment="delivery", slippage_bps=D("0"))
    return model.round_trip_bps(CAPITAL_INR) * 2

STATUTORY_BPS = _delivery_statutory_bps()
```

```python
# tests/unit/...
def test_harnesses_agree_on_costs(self):
    from nsealgo.costs import CostModel
    engine = CostModel(segment="delivery", slippage_bps=D("0")).round_trip_bps(D("2100000"))
    assert C.STATUTORY_BPS == engine * 2      # turnover-bps -> notional-bps
```

### Scrambled-cross-section null (the correct null for ranking signals)

```python
def _scrambled(px: pd.DataFrame) -> pd.DataFrame:
    """Permute each date's cross-section independently.

    Preserves each date's score distribution while destroying any relationship
    between a symbol and its score. NOT a time-shift -- shifting in time smuggles
    real lagged information back in, so it is not a null.
    """
    base = np.array(_composite(px).to_numpy(), copy=True)
    rng = np.random.default_rng(20260101)
    for i in range(base.shape[0]):
        base[i] = rng.permutation(base[i])
    return pd.DataFrame(base, index=px.index, columns=px.columns)
```

### Walk-forward with params selected once

```python
def rolling_wf(px, score, signal, n_hold, buffer, years=3):
    """Re-fit each year, trade the next year. Params are NOT re-selected.

    Selection happens once, on the first fold. Later folds reuse those params
    deliberately: re-picking per fold would let each year choose its own winner
    and turn the walk-forward into 11 independent in-sample searches.
    """
    rows = []
    y = pd.Timestamp("2010-01-01", tz=px.index.tz)
    while y + pd.DateOffset(years=years + 1) <= px.index[-1]:
        tr0, tr1 = y, y + pd.DateOffset(years=years)
        te0, te1 = tr1, tr1 + pd.DateOffset(years=1)
        for label, sc in (("real", score), ("null", null_score)):
            r = _one(px, sc, signal, n_hold, buffer,
                     str(te0.date()), str(te1.date()), tradable=pit_mask)
            if r:
                r.tag = f"{r.tag}_{label}"
                rows.append(r)
        y = y + pd.DateOffset(years=1)
    return rows
```

### Point-in-time membership, lagged

```python
# Membership in force during month M is the one published at the END of M-1.
prior = px.index[px.index < rows[0]]
if len(prior) == 0:
    continue
keep = _pit_members(m, prior[-1])
```

### Corporate-action repair that cannot delete real history

```python
C10_MIN_GAP = 0.30          # far above the 20% circuit limit, not at it
C10_RESCALE_TOLERANCE = 0.02
C10_SPLIT_RATIOS = (1.0, 2/3, 0.5, 2/5, 1/3, 0.25, 0.2, 0.1)

# Only rescale a provable 1:x ratio. Everything else is disclosed, not modified.
nearest = min(C10_SPLIT_RATIOS, key=lambda r: abs(r - ratio))
if abs(nearest - ratio) <= C10_RESCALE_TOLERANCE * nearest:
    df.loc[df.index < event, ["open", "high", "low", "close"]] *= nearest
    rep.rescaled_actions.append((symbol, str(event.date()), float(nearest)))
else:
    rep.unresolved_actions.append((symbol, str(event.date()), float(ratio), spread))
```

### Guardrail test: two harnesses must not drift

```python
def test_exclusions_match_the_production_loader(self, production_universe):
    _, symbols, report = production_universe
    assert set(report.excluded_symbols) == set(S.EXCLUDED_SYMBOLS), (
        "the two harnesses would silently disagree"
    )
```

---

## 6. Instincts — installed, not just described

The instincts for this session are **installed and live** in the continuous-learning-v2
store, scoped to this project so they do not contaminate unrelated work:

```
Scope     : project
Project   : trade (e691ea49feb8)
Count     : 14 instincts, 10 in domain `quant-research`, 3 in `python`, 1 in `testing`
Installed : ~/.local/share/ecc-homunculus/projects/e691ea49feb8/instincts/inherited/
Source of truth (version controlled): research/instincts/trade-instincts.yaml
```

**The real format is `---`-delimited YAML frontmatter, not JSON.** An earlier draft of
this document recorded them as JSON, which the importer silently does not accept
(`ALLOWED_INSTINCT_EXTENSIONS = (".yaml", ".yml", ".md")`). Install them with the CLI,
not by writing files by hand:

```bash
python3 <skill>/scripts/instinct-cli.py import research/instincts/trade-instincts.yaml --dry-run --force
python3 <skill>/scripts/instinct-cli.py import research/instincts/trade-instincts.yaml --force
python3 <skill>/scripts/instinct-cli.py status      # verify they are readable
```

Each entry needs at minimum `id`, `trigger`, `action`, `confidence`, `scope`, `domain`.
`scope: project` is what keeps a trading-research lesson from leaking into an unrelated
repo; `scope: global` is only for genuinely universal lessons.

### The fourteen

| id | confidence | domain |
|---|---|---|
| `shared-constant-unit-mismatch` | 0.95 | python |
| `charge-selection-to-the-hypothesis` | 0.95 | quant-research |
| `repair-only-what-is-provable` | 0.90 | quant-research |
| `detector-before-deletion` | 0.90 | quant-research |
| `mask-selection-not-prices` | 0.90 | quant-research |
| `benchmark-against-doing-nothing` | 0.90 | quant-research |
| `mandate-conflict-is-a-human-decision` | 0.90 | quant-research |
| `exposure-is-the-first-order-driver` | 0.85 | quant-research |
| `incomplete-correction-is-a-floor` | 0.85 | quant-research |
| `deliver-the-thing-not-the-research-program` | 0.85 | quant-research |
| `measure-the-risk-control-before-trusting-it` | 0.80 | quant-research |
| `units-typo-in-the-verification-script` | 0.80 | python |
| `reproduce-in-isolation-before-attributing` | 0.80 | testing |
| `sanity-check-grouping-before-printing` | 0.75 | python |

The JSON form below is retained only for reading by tools that do not speak YAML.
It is **not** the installed format.

```json
[
  {
    "trigger": "A constant appears in both a production module and a research harness, and one side documents a different unit than the other consumes",
    "action": "Import and derive the constant from the canonical source instead of restating it, and add a test asserting the two harnesses agree",
    "confidence": 0.95,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A signal or strategy result looks strong on a holdout window",
    "action": "Before quoting it, compute the family distribution across all tested cells and run walk-forward with params selected once; a p-value after post-hoc selection is not a p-value",
    "confidence": 0.95,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A data-cleaning rule could delete rows, and ambiguity is possible (crash vs corporate action vs demerger)",
    "action": "Repair only what is provable; record everything else as flagged-but-unmodified, and test explicitly that a real drawdown survives the rule",
    "confidence": 0.9,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A detector inspects adjacency between rows (gaps, runs, jumps) while other cleaning rules also remove rows",
    "action": "Run the detector before any row deletion and document the ordering constraint; otherwise it fires on gaps created by deletions",
    "confidence": 0.9,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A point-in-time membership or universe file is used to restrict a backtest",
    "action": "Lag membership to the prior period's publication, mask selection rather than prices, and carry last-known price for held names",
    "confidence": 0.9,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A strategy is being evaluated for whether it is worth running",
    "action": "Benchmark it against the do-nothing alternative with an identical cost stack; beating a scrambled null is necessary but not sufficient",
    "confidence": 0.9,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A long-only equity book's measured median return is near zero or negative",
    "action": "Bucket every result by exposure before optimising anything; the >60% exposure bucket is typically the only profitable one, and turnover cuts are usually the wrong lever",
    "confidence": 0.85,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A measured strategy's drawdown exceeds a hard-coded risk limit that the code cannot widen",
    "action": "Stop and report it as a mandate conflict for a human decision; quantify whether any exposure level satisfies the limit, and never quietly widen the limit",
    "confidence": 0.9,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A survivorship or coverage correction is applied but the corrected data is incomplete",
    "action": "State the coverage fraction next to the correction and label the result a floor or ceiling, not an estimate",
    "confidence": 0.85,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  },
  {
    "trigger": "A risk control (regime filter, stop, overlay) is proposed to improve a strategy",
    "action": "Simulate the control end to end and measure it; a filter that engages early and stays engaged can make results worse while appearing to help",
    "confidence": 0.8,
    "source": "session-extraction",
    "timestamp": "2026-10-19T00:00:00Z"
  }
]
```

## 7. Suggested skill updates

### `rules/python/coding-style.md` — add a "shared constants" section

```markdown
## Shared constants are imported, never restated

If a value is used in more than one module, exactly one module owns it and the
others import it. This applies especially to values with a unit (bps, seconds,
basis points of turnover vs of notional).

**Why**: a restated constant drifts silently, and a unit mismatch between
document and consumer is invisible until a result is wrong. In the 2026-10-19
session, `STATUTORY_BPS` documented as bps-of-turnover but consumed as
bps-of-notional understated every cost by 1.469× for the life of the project.

**How**: define in the owning module; import elsewhere. Where the unit is
ambiguous, the import is what disambiguates it. Add a test asserting the
consumers agree.
```

### `rules/testing.md` — add "guardrail tests" and "negative-path tests"

```markdown
## Test the guardrail, not just the happy path

Any rule that can silently disagree with another needs a test that fails when
they diverge. Any rule that can delete data needs a test proving real data
survives it.

**Why**: in the 2026-10-19 session, the "exclusions must match the production
loader" guardrail correctly caught a real divergence the moment a new symbol was
excluded, and a crash-survival test caught a corporate-action rule that would
have deleted the 2008 crash.

**How**: write the assertion against the *shared source of truth* rather than a
restated expectation, so it stays true as the code changes.
```

### `skills/quant-research/SKILL.md` (new) — or extend an existing research skill

```markdown
## Validating a trading hypothesis (order matters)

1. Fix the signal, vary one thing at a time. Never infer from a correlation
   across configs with different signal liveness.
2. Use a **signal-scrambled null** (per-date cross-section permuted), not a
   time-shift null.
3. Report the **family distribution** across all tested cells, then the best
   cell. A p-value after post-hoc selection is not a p-value.
4. **Walk-forward** with params selected once, on the first fold only.
5. Benchmark against the **do-nothing** alternative with an identical cost
   stack. Beating a scrambled null is necessary, not sufficient.
6. Report **exposure** alongside return. For long-only equity, exposure is
   usually the first-order driver.
7. Correct **point-in-time** membership (lagged), and correct survivorship
   before interpreting any level.
8. Check the result against the **hard-coded risk limits** before proposing it.
   A mandate conflict is a human decision.
```

### `rules/python/security.md` — no change needed

Nothing in this session touched secrets, auth, or input validation. The
lessons are about measurement and units, not security.

---

## 8. Standing conclusions to carry forward

- **No edge**: the price-only technical signal is indistinguishable from a
  scrambled null (p=0.386) and from holding the universe (p=0.240).
- **What works**: being invested, cheaply — ~100% exposure, 1–3 round trips/yr,
  32.32 bp. ~17%/yr net. That is capital efficiency, not alpha, and must never
  be reported as alpha.
- **Blocker**: the hard-coded −15% kill switch is incompatible with Indian
  largecaps (28% of time below −10%, worst −67.9%). A human decision.
- **Next**: fundamentals data (value/quality/earnings revisions) is the only
  genuinely new information available; the short side is the only untested
  quadrant; live paper fills validate the largest remaining assumption.
- **Never**: quote any number produced before the cost fix, the C10 repair, or
  the survivorship correction. All stored results are stale.
