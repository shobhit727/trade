# BUG — `CostModel.all_in_round_trip_bps` crashes on a float `slippage_bps`

**File:** `src/nsealgo/costs.py:230`
**Severity:** medium (blocks a whole class of legitimate analysis; no live-path impact today)
**Status:** reported only — **not fixed**, per brief §9 ("do not modify `src/nsealgo/**`")

## The defect

```python
# src/nsealgo/costs.py:198-217
def round_trip_bps(self, notional: Decimal) -> Decimal:
    ...
    return ((buy.total + sell.total) / total_turnover * D("10000")).quantize(D("0.01"))
    # -> returns a Decimal

# src/nsealgo/costs.py:219-230
def all_in_round_trip_bps(self, notional: Decimal) -> Decimal:
    return self.round_trip_bps(notional) + self.slippage_bps * 2
    #                    Decimal       +  float            -> TypeError
```

`round_trip_bps` returns a `Decimal`, but `slippage_bps` is stored **uncoerced**.
A Python `int` or `Decimal` happens to interoperate with `Decimal`; a `float` does not.

## Reproduction

```
$ .venv/bin/python -c "... CostModel(segment='delivery', slippage_bps=X).all_in_round_trip_bps(100_000) ..."

slippage_bps=5     (int)     -> 21.92           OK
slippage_bps=5.0   (float)   -> TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'
slippage_bps=0     (int)     -> 11.92           OK
slippage_bps=0.0   (float)   -> TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'
slippage_bps=Decimal('5')    -> 21.92           OK
slippage_bps='5'             -> TypeError in the constructor (unrelated: str slips past validation)
slippage_bps=None            -> TypeError in the constructor (same)
```

## Why it matters

**1. You cannot measure gross-of-cost performance through `run_backtest`.**
The obvious way to separate "the signal is bad" from "the costs ate it" is to rerun
the same backtest at zero slippage. `CostModel(segment="delivery", slippage_bps=0.0)`
is the natural spelling and it raises. The engine calls `all_in_round_trip_bps`
unconditionally at `engine.py:503`, so *every* `run_backtest` call dies.

I hit this immediately in `research/agent_ma_cross/controls.py` section B
(cost decomposition). This is not a contrived path — it is the first thing any
agent asked to report cost drag (§6.4 of `AGENT_BRIEF.md`) will try.

**2. It fails late, not at construction.**
`CostModel.__init__` does not validate or coerce `slippage_bps`, so a bad type
survives construction and explodes on first use. A one-line coercion in
`__post_init__` (`self.slippage_bps = D(str(slippage_bps))`) would turn a
`TypeError` deep inside the backtest into a validated, deterministic value.

**3. It is latent in production only by luck.**
`STRESS_MODELS` at `costs.py:238-239` uses `slippage_bps=D("5")` (a `Decimal`), and
the brief's canonical example `CostModel(segment="delivery", slippage_bps=5)` passes
an `int`. Both work. Nothing inside the package ever passes a float — so no
in-repo test covers this. It is reachable only from caller code, which is exactly
where agents and researchers live.

## Suggested fix (not applied)

In `CostModel.__init__` / `__post_init__`:

```python
self.slippage_bps = D(str(slippage_bps))
```

`costs.py` already has a `D()` helper in use, so this is consistent with the file's
own convention, and it also fixes the `'5'` / `None` constructor cases by forcing
them through the same validated conversion.

## Workaround used in my run

`CostModel(segment="delivery", slippage_bps=0)` — **int `0`, not float `0.0`**.
Gives the 11.92 bps statutory-only round trip, which is the correct gross baseline.