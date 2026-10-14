"""Tail-slicing fast path for tail-only indicators.

Why this exists
---------------
After the numpy conversion in :mod:`research.optimize.backtest`, profiling showed
``rsi()`` alone at **48%** of total backtest time, with ``feed()`` at 77% cumulative.
The cause is not the arithmetic -- it is the buffer conversion:

    def rsi(closes, period=14):
        a = np.asarray(closes, dtype=float)      # <-- converts the WHOLE 300-element buffer
        d = np.diff(a[-(period + 1):])          # <-- then reads only period+1 elements

``SignalStrategy.feed`` hands every indicator a 300-element deque, so each of ~1,975 bars
per backtest -- times 12 configs, times 4,032 pairs -- converts 300 floats to read 15.

Which indicators are safe
-------------------------
Only those that provably read nothing but the tail. Each is verified here against the
original implementation, and the reason is recorded so a future edit to
``indicators.py`` that breaks the assumption fails loudly instead of silently changing
results.

============================  =======================  ================================
function                      reads                    safe to pre-slice
============================  =======================  ================================
``sma``                       ``values[-period:]``     YES -- to ``period``
``rsi``                       ``a[-(period+1):]``      YES -- to ``period + 1``
``roc``                       ``[-period-1]``, ``[-1]``YES -- to ``period + 1``
``stochastic``                ``[-period:]`` x3        YES -- to ``period``
``ema``                       whole array (recursive)  NO
``zscore``                    whole array             NO
``kama``                      whole array (recursive)  NO
============================  =======================  ================================

Scope
-----
This patches ``cryptobot.strategies.indicators`` **in this process only**, on explicit
``install()``. It never edits that module, because it is shared with the live crypto
engine, which is mid-refactor. :func:`verify` asserts patched and original agree, and
:mod:`research.optimize.run` calls it at start-up so a future refactor that breaks the
tail-only assumption is caught before 161,000 backtests run against it.
"""

from __future__ import annotations

import logging
import sys

import numpy as np

from cryptobot.strategies import indicators as I

log = logging.getLogger(__name__)

_INSTALLED = False
_ORIGINALS: dict[str, object] = {}


def _tail(values, n: int):
    """Last ``n`` elements, preserving the input container type closely enough.

    Indicators index with ``[-n:]`` and pass the result to ``np.asarray`` /
    ``max`` / ``sum``, so a plain list slice is sufficient and cheapest.
    """
    try:
        if len(values) > n:
            return values[-n:]
    except TypeError:
        return values
    return values


def _wrap(fn, need: int, name: str):
    def wrapper(values, *args, **kwargs):
        return fn(_tail(values, need), *args, **kwargs)

    wrapper.__name__ = name
    wrapper.__doc__ = f"Tail-sliced wrapper around indicators.{name} (need={need})."
    wrapper.__wrapped__ = fn
    return wrapper


def install() -> bool:
    """Patch the tail-only indicators. Idempotent. Returns True if it did work."""
    global _INSTALLED
    if _INSTALLED:
        return False

    # Each wrapper derives its slice size from `period`, which varies per config.
    _ORIGINALS["sma"] = I.sma
    _ORIGINALS["rsi"] = I.rsi
    _ORIGINALS["roc"] = I.roc
    _ORIGINALS["stochastic"] = I.stochastic

    I.sma = _dyn(I.sma, lambda p: max(int(p), 1), "sma")
    I.rsi = _dyn(I.rsi, lambda p: int(p) + 1, "rsi")
    I.roc = _dyn(I.roc, lambda p: int(p) + 1, "roc")
    # stochastic reads period elements from each of the three series.
    I.stochastic = _dyn3(I.stochastic, "stochastic")

    rebound = _rebind_all()
    log.info("installed tail-slicing fast path for sma/rsi/roc/stochastic; "
             "rebound %d call sites across %d modules", rebound, len(sys.modules))

    _INSTALLED = True
    return True


def _rebind_all() -> int:
    """Replace direct references to the original functions everywhere they were imported.

    ``patching I.rsi = ...`` is not enough. Every catalog module does
    ``from cryptobot.strategies.indicators import rsi``, which binds the *function object*
    into that module's namespace. Rebinding only the indicators module leaves all 84
    catalog strategies calling the original -- measured at 1.02x, i.e. nothing.

    So walk every loaded module and, wherever an attribute is the same object as one of
    the originals, swap it for the wrapper. Identity comparison (``is``) is what makes
    this safe: it only touches bindings of exactly these four functions.
    """
    wrappers = {id(fn): getattr(I, name) for name, fn in _ORIGINALS.items()}
    n = 0
    for mod in list(sys.modules.values()):
        d = getattr(mod, "__dict__", None)
        if not d:
            continue
        for attr, val in list(d.items()):
            if id(val) in wrappers and val is not getattr(I, attr, None):
                try:
                    setattr(mod, attr, wrappers[id(val)])
                    n += 1
                except Exception:  # noqa: BLE001 - read-only module namespace
                    continue
    return n


def _dyn(fn, need_fn, name: str):
    """Wrapper whose slice size depends on the ``period`` argument."""

    def wrapper(values, period=20, *a, **kw):
        return fn(_tail(values, need_fn(period)), period, *a, **kw)

    wrapper.__name__ = name
    wrapper.__wrapped__ = fn
    return wrapper


def _dyn3(fn, name: str):
    """``stochastic(closes, highs, lows, period)`` -- slice all three series."""

    def wrapper(closes, highs, lows, period=14, *a, **kw):
        n = max(int(period), 1)
        return fn(_tail(closes, n), _tail(highs, n), _tail(lows, n), period, *a, **kw)

    wrapper.__name__ = name
    wrapper.__wrapped__ = fn
    return wrapper


def uninstall() -> None:
    """Restore the originals. Used by the tests."""
    global _INSTALLED
    if not _INSTALLED:
        return
    for name, fn in _ORIGINALS.items():
        setattr(I, name, fn)
    _ORIGINALS.clear()
    _INSTALLED = False


def verify(seed: int = 0, trials: int = 300) -> None:
    """Assert the patched indicators equal the originals on random data.

    Raises ``AssertionError`` on any divergence. Called at run start-up so that a future
    edit to ``indicators.py`` which invalidates the tail-only assumption fails loudly.
    """
    if not _INSTALLED:
        install()
    originals = dict(_ORIGINALS)
    rng = np.random.default_rng(seed)

    for _ in range(trials):
        n = int(rng.integers(40, 300))
        px = np.cumprod(1.0 + rng.normal(0, 0.01, n)) * 100.0
        hi, lo = px * 1.01, px * 0.99
        for period in (2, 5, 14, 20, 50, 100):
            if period >= n:
                continue
            assert I.sma(px, period) == originals["sma"](px, period), f"sma p={period}"
            assert I.rsi(px, period) == originals["rsi"](px, period), f"rsi p={period}"
            assert I.roc(px, period) == originals["roc"](px, period), f"roc p={period}"
            assert I.stochastic(px, hi, lo, period) == originals["stochastic"](
                px, hi, lo, period
            ), f"stochastic p={period}"
    log.info("fast-path verified: sma/rsi/roc/stochastic identical to original on "
             "%d random series", trials)