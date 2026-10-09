# Bugs found while validating `ensemble_signals` on NSE

Found by agent `agent_ensemble`. Both are **harness/data** bugs, not bugs in the
catalog strategy. Neither is a one-line fix in `src/nsealgo` — both need a decision
about policy, so they are reported rather than worked around silently.

---

## BUG 1 (HIGH) — `load_universe` returns internal NaNs, which silently poisons any
## rolling or recursive indicator built on the panel

**Where:** `src/nsealgo/data/loader.py:250-252`

```python
panel = pd.DataFrame(series).sort_index()
# C4 again at panel level: a symbol can be NaN on dates others are not.
panel = panel.dropna(how="all")
```

`load_symbol` asserts **no NaN close within a symbol's own frame** (C6,
`loader.py:112-113`), and rule C4 says "never forward-fill" (`loader.py:144`). But
`pd.DataFrame(series)` pivots the per-symbol frames onto their **union** index, so a
symbol that lacks a trading day that other symbols have becomes NaN in the panel.
Nothing then repairs or flags it.

**Evidence (2026-10-08):**

```
panel (4629, 48)   13,966 NaN cells
symbols with exactly one interior hole : 39  (nastily uniform)
the hole                                : 2010-02-06  — a SATURDAY
```

`2010-02-06` is missing from the raw `*_1d.csv` of 39 of 48 symbols. It is not a market
holiday — every other symbol's file also has no bar that day, but 9 files do carry one,
so the union index creates the hole for the other 39. Two further interior holes exist:
`nestleind` (2), `bajajfinsv` (3), `indigo` (1, at 2026-05-01). Everything else is
leading/pre-listing NaN (`eternal` 3340, `maxhealth` 3111, `hdfclife` 2433,
`sbilife` 2401, `indigo` 1936, `coalindia` 701) — those are benign and must **not** be
filled.

**Why it is HIGH.** Any strategy that computes an indicator on the raw panel is silently
corrupted from the first hole onward. In my run the vectorised replica of
`ensemble_signals` disagreed with the real `EnsembleSignalsStrategy.signal()` on
**44–116 bars per variant** (of ~19,000 checked), every one of them inside the
`period`-bar window following 2010-02-06. It did not blow up loudly — the aggregate long
fraction moved by only 0.006pp — because the hole is a single bar 6 years before TRAIN
starts. That is exactly what makes it dangerous: **an agent that does not verify its
replica against the catalog strategy will not notice, and a hole inside TRAIN or TEST
would corrupt the result silently.**

`run_backtest` itself survives (it uses `pct_change(fill_method=None).fillna(0.0)` and
`vol` with `min_periods=20`), and `trailing_return` survives (NaN for one bar only). But
`rolling` and `ewm` over a long window do not.

**Suggested fix (not applied — brief forbids editing `src/nsealgo`):** in `load_universe`,
detect interior holes and either (a) drop the offending *date* panel-wide if it is not a
real trading day, or (b) emit `interior_holes` in `CleaningReport` and document that
callers must `panel.ffill()` — forward-fill from the past only, which preserves
pre-listing NaNs because `ffill` never backfills. Option (b) is what I did in my harness
and it makes the replica bit-faithful.

---

## BUG 2 (LOW, cosmetic) — dead code in `ensemble_signals_strategy.py`

`src/cryptobot/strategies/catalog/ensemble_signals_strategy.py:31-32`

```python
if sma(closes, self.config.period) != sma(closes, self.config.period):
    votes += 0
```

A NaN guard that adds 0. It is harmless but calls `sma` twice per bar for nothing, and it
reads as if the author intended to `return 0` on NaN. It also *masks* the real NaN
behaviour: during warmup `closes[-1] > sma(...)` is `False`, so the leg votes **−1**, not
0. Harmless here (the RSI NaN check on line 42 returns 0 anyway) but a trap for anyone
refactoring the vote arithmetic.