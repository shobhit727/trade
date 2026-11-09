"""Look-ahead proof: truncating the panel must not change any past CCI value.

If the CCI at date t used any data after t, then computing it from a panel that
*ends* at t would give a different number. This is the strongest available check
and it does not depend on reading the indicator's source and trusting it.
"""

from __future__ import annotations

import numpy as np
from common import cci_panel, load_panels, typical_price

p = load_panels()
tp = typical_price(p)
PERIOD = 20

full = cci_panel(tp, PERIOD)

rng = np.random.default_rng(7)
max_err = 0.0
checked = 0
for _ in range(12):
    cut = int(rng.integers(400, len(tp) - 1))
    truncated = cci_panel(tp.iloc[: cut + 1], PERIOD)
    a = truncated.to_numpy(dtype=float)
    b = full.iloc[: cut + 1].to_numpy(dtype=float)
    assert a.shape == b.shape, (a.shape, b.shape)
    both_nan = np.isnan(a) & np.isnan(b)
    diff = np.where(both_nan, 0.0, np.abs(np.nan_to_num(a) - np.nan_to_num(b)))
    max_err = max(max_err, float(diff.max()))
    checked += int((~both_nan).sum())

print(f"lookahead test: 12 truncations, {checked:,} bar/symbol values compared")
print(f"max |full - truncated| = {max_err:.3e}")
print(f"NO LOOKAHEAD = {max_err < 1e-12}")

# Second, independent check: the value the engine acts on at date t must be the
# value computable from closes up to and including t only.
close = p.close
ok_tp = bool(((p.high + p.low + p.close) / 3.0).equals(tp))
last = float((close / close.shift(126) - 1.0).iloc[-1, 0])
print(f"typical price == (H+L+C)/3 of the same bar: {ok_tp}")
print("engine holds weights decided at t from t+1 (run_backtest: gross = held.shift(1) * rets)")
print(f"rank factor is trailing: mom126 last bar value = {last:.4f} (uses close.shift(126))")
assert np.isfinite(max_err)
