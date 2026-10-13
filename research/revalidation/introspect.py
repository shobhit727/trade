"""Introspect each agent's score builder: signature, and the frozen variant parameters.

Run once to build the driver table. Prints a compact summary per agent so the driver in
``run_all.py`` calls the right function with the right arguments.
"""

from __future__ import annotations

import inspect
import sys

sys.path.insert(0, "/home/ph03n1x/trade/research/revalidation")

from agentlib import load  # noqa: E402

AGENTS = [
    "atr_breakout",
    "bollinger_bands",
    "cci",
    "cointegration",
    "dispersion",
    "distance_ma",
    "donchian",
    "dual_ma",
    "ensemble",
    "fisher",
    "flag_pattern",
    "gap",
    "hull_ma",
    "inapplicable",
    "kama",
    "keltner",
    "macd",
    "mfi",
    "momentum_factor",
    "multifactor",
    "obv",
    "regime_switch",
    "regression",
    "relstrength",
    "stochastic",
    "timeseries",
    "tmr",
    "trendmom",
    "triple_ma",
    "voltarget",
    "volscaling",
    "vwm",
    "williamsr",
    "zscore",
]

WANT = ("score", "signal", "variant", "build")


def main() -> None:
    for a in AGENTS:
        print(f"\n########## {a}")
        try:
            m = load(a)
        except Exception as e:  # noqa: BLE001
            print(f"  !! import failed: {type(e).__name__}: {e}")
            continue
        for nm, obj in vars(m).items():
            if nm.startswith("_"):
                continue
            if inspect.isfunction(obj) and any(w in nm.lower() for w in WANT):
                try:
                    sig = str(inspect.signature(obj))
                except (TypeError, ValueError):
                    sig = "(?)"
                print(f"  def {nm}{sig}")
            elif nm.isupper() and any(w in nm.lower() for w in WANT):
                v = getattr(m, nm)
                txt = repr(v)
                print(f"  {nm} = {txt[:400]}")


if __name__ == "__main__":
    main()
