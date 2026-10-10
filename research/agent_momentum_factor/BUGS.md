# Bugs found by the `momentum_factor` agent

Bugs in `src/` are reported, not fixed (the brief forbids modifying `src/**`).
Bugs in **my own** harness are listed too and were fixed before any number was trusted.

---

## BUG-1 — `src/nsealgo/costs.py:230`: `all_in_round_trip_bps` raises `TypeError` for any float `slippage_bps`

**Severity: MEDIUM (latent; blocks a documented diagnostic, no wrong number produced)**

```python
return self.round_trip_bps(notional) + self.slippage_bps * 2
#                                              ^^^^^^^^^^^^^^^^^ float
# round_trip_bps(...) returns a Decimal
```

Reproduced:

| `slippage_bps` | result |
|---|---|
| `5` (int) | 21.92 ✅ |
| `5.0` (float) | **TypeError** |
| `0` (int) | 11.92 ✅ |
| `0.0` (float) | **TypeError** |
| `2.5` (float) | **TypeError** |

`round_trip_bps` returns `Decimal`; `slippage_bps * 2` is `float` when the field was set
from a float. `Decimal + float` is a `TypeError` — Python refuses the mixed operation
rather than silently coercing, which is the *safe* failure mode, but it is still a bug.

**Why it matters.** `GOAL.md` §6.4 requires a Gate 4 stress test that varies cost
assumptions, and the "is this result gross-of-cost?" check the brief's §6.4-cost rule
implies both need a zero-cost or reduced-cost `CostModel`. The only way to construct one
is to pass a float (`slippage_bps=0.0`), which is the most natural spelling and it crashes.
The module's own `STRESS_MODELS` sidesteps this by using `D("5")` strings, so the
production path is unaffected — which is exactly why this has survived.

**Suggested fix (not applied):**
```python
return self.round_trip_bps(notional) + D(str(self.slippage_bps)) * 2
```
or type the dataclass field as `Decimal` and coerce in `__post_init__`.

**Impact on my result: none.** All my reported backtests use the default
`slippage_bps=5` (int) and are unaffected. My zero-cost diagnostic uses
`Decimal("0")` as a workaround.

---

## BUG-2 (mine, fixed) — `research/agent_momentum_factor/common.py`: `benchmark_buy_hold` mangled its first bar

Subtracted the deployment cost from a **return** rather than from **equity**, then assigned
the mangled value to `daily[0]`. Invented a **+99.78 % best day** and inflated
buy-and-hold's TRAIN Sharpe from 0.90 to **20.84**. Caught because the number was
impossible; rewritten to charge the cost against equity and earn returns from the second
bar. Post-fix BH reconciles with the raw gross equal-weight CAGR (22.31 % gross → 21.49 %
net of one deployment).

**Lesson:** a benchmark with a Sharpe an order of magnitude above reality is the cheapest
possible bug detector. Always sanity-check the benchmark before trusting a spread.

---

## BUG-3 (mine, fixed) — `research/agent_momentum_factor/common.py`: `fmt_table` guessed units by magnitude

Used `abs(v) < 20` to decide whether a float was a fraction, so it printed
`avg_names = 19.57` as **1956.51** and Sharpe 0.649 as **64.90**. Replaced with an explicit
set of percent-typed column names. The underlying metrics were always correct — this was
display-only — but it briefly looked like a catastrophic engine bug (`avg_names` > 48 in a
48-name universe) and would have made any reader distrust correct results.

**Lesson:** never infer units from magnitude in financial reporting code.

---

## BUG-4 — structural, in the assigned strategy itself (not a code defect)

`momentum_factor_strategy.py` and `cross_sectional_strategy.py` are **the same 32-line
implementation** with different default constants (`threshold` 0.005 vs 0.015). Neither
contains any cross-sectional logic despite one being named `cross_sectional` and the other
`momentum_factor`. A catalogue reader would reasonably believe these are two different
strategies. They are one strategy with two tunings, and the `momentum` name is a
misnomer for what is empirically a **short-horizon reversal** signal on this panel
(see `REPORT.md` §9.1).

Not fixable without changing strategy semantics, which is out of scope. Flagged so the
catalogue is not over-counted as covering two independent ideas.

---

## BUG-5 (mine, fixed) — `40_diagnose.py`: compounded overlapping-horizon returns

Three defects in one script, all caught before any number reached the report:

1. The TRAIN/TEST loop masked the *leg* but never restricted the forward-return panel, so
   **both windows printed byte-identical numbers** — a silent failure that would have shown
   a "result" for TEST that was actually a duplicate of TRAIN.
2. `(1 + vals).prod()` overflowed to `inf`, and annualising the ~10⁵ name-bars of an
   **overlapping** 21-bar forward-return stream as if they were sequential multiplies each
   bar ~21 times produced nonsense: a leg "annualising" at 732 %/yr. Replaced with the
   standard non-compounding treatment, arithmetic mean scaled by 244/horizon.
3. `df.where(df >= df.quantile(0.8, axis=1), axis=1)` raised
   `ValueError: Operands are not aligned` on this pandas version; the per-row threshold is
   now broadcast row-wise explicitly via `.ge(q80, axis=0)`.

**Lesson:** the first defect is the dangerous one — a duplicated TRAIN block silently
presented as TEST evidence is exactly how a look-ahead audit gets faked. Assert the two
windows differ before trusting either.

---

## BUG-6 (mine, fixed) — `50_sanity.py`: dead code / duplicated full run

A leftover `full = run_backtest(...)` executed the full-history backtest twice. No
numerical impact (both runs are deterministic and identical), removed.
