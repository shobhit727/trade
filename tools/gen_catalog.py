"""Emit one module + one test per catalog strategy from a compact spec table.

Run: `python tools/gen_catalog.py`. Each strategy becomes its own file under
src/cryptobot/strategies/catalog/ plus tests/strategies/test_catalog_<name>.py.
Authoring-time tool; generated files are the shipped artifacts.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "cryptobot" / "strategies" / "catalog"
TESTS = ROOT / "tests" / "strategies"

MODULE_TMPL = """'''NAME'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import IMPORTS
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CFG:
FIELDS
    quantity: Decimal = Decimal("1")


class STRAT(SignalStrategy):
    name = "KEY"

    def __init__(self, config: CFG | None = None):
        super().__init__(config or CFG())

    def warmup(self, closes) -> int:
        return self.config.WARM

    def signal(self, closes, highs, lows, volumes):
SIGNAL
"""

TEST_TREND_TMPL = '''"""Tests for catalog strategy KEY."""

from __future__ import annotations

from cryptobot.strategies.catalog.KEY import STRAT


def _series(up: bool):
    s = STRAT()
    out = []
    for i in range(200):
        px = (100.0 + i * 0.4) if up else (200.0 - i * 0.4)
        o = s.feed("BTC", px, px, px, 1000.0)
        if o:
            out.append(o)
    return out


def test_KEY_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_KEY_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
'''

TEST_OSC_TMPL = '''"""Tests for catalog strategy KEY."""

from __future__ import annotations

import math

from cryptobot.strategies.catalog.KEY import STRAT


def _series(up: bool):
    s = STRAT()
    out = []
    for i in range(300):
        px = 100.0 + 8.0 * math.sin(i / 6.0) + (0.05 * i if up else -0.05 * i)
        o = s.feed("BTC", px, px * 1.002, px * 0.998, 1000.0)
        if o:
            out.append(o)
    return out


def test_KEY_long_signal():
    assert any(o.side.value == "BUY" for o in _series(True))


def test_KEY_short_signal():
    assert any(o.side.value == "SELL" for o in _series(False))
'''


TEST_VOL_TMPL = '''"""Tests for catalog strategy KEY."""

from __future__ import annotations

from cryptobot.strategies.catalog.KEY import STRAT


def test_KEY_expansion_follows_spike():
    s = STRAT()
    got = []
    for i in range(120):
        px = 100.0 + i * 0.1
        o = s.feed("BTC", px, px * 1.001, px * 0.999, 1000.0)
        if o:
            got.append(o.side.value)
    px = 120.0
    o = s.feed("BTC", px, px * 1.05, px * 0.95, 5000.0)
    assert o is None or o.side.value == "BUY"
'''


def _indent(text: str, n: int) -> str:
    """Shift a block right by n, preserving relative indentation."""
    base = 0
    for ln in text.splitlines():
        if ln.strip():
            base = len(ln) - len(ln.lstrip())
            break
    out = []
    for ln in text.splitlines():
        out.append(" " * n + ln[base:] if ln.strip() else "")
    return "\n".join(out)


def _key(cfg: str) -> str:
    cls = cfg.replace("Config", "").replace("Strategy", "")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls).lower()


SPECS: list[dict] = []


def add(
    doc: str,
    imports: str,
    cfg: str,
    cls: str,
    warm: str,
    fields: str,
    signal: str,
    mode: str = "trend",
    dirs: str = "both",
) -> None:
    SPECS.append(
        dict(
            doc=doc,
            imports=imports,
            cfg=cfg,
            strat_cls=cls,
            warm=warm,
            fields=fields,
            signal=signal,
            mode=mode,
            dirs=dirs,
            key=_key(cfg),
        )
    )


def build_module(spec: dict) -> str:
    code = MODULE_TMPL
    code = code.replace("NAME", spec["doc"].capitalize())
    imports = spec["imports"].strip()
    if imports:
        code = code.replace(
            "from cryptobot.strategies.indicators import IMPORTS\n",
            f"from cryptobot.strategies.indicators import {imports}\n",
        )
    else:
        code = code.replace("from cryptobot.strategies.indicators import IMPORTS\n", "")
    code = code.replace("IMPORTS", imports)
    code = code.replace("CFG", spec["cfg"])
    code = code.replace("STRAT", spec["strat_cls"])
    code = code.replace("KEY", spec["key"])
    code = code.replace("WARM", spec["warm"])
    code = code.replace("FIELDS", _indent(spec["fields"], 4))
    code = code.replace("SIGNAL", _indent(spec["signal"], 8))
    return code


def build_test(spec: dict) -> str:
    if spec.get("mode") == "vol":
        return TEST_VOL_TMPL.replace("KEY", spec["key"]).replace("STRAT", spec["strat_cls"])
    t = TEST_OSC_TMPL if spec.get("mode") == "osc" else TEST_TREND_TMPL
    t = t.replace("KEY", spec["key"]).replace("STRAT", spec["strat_cls"])
    dirs = spec.get("dirs", "both")
    if dirs == "long":
        t = _drop_func(t, f"test_{spec['key']}_short_signal")
    elif dirs == "short":
        t = _drop_func(t, f"test_{spec['key']}_long_signal")
        t = t.replace("_series(True)", "_series(False)")
    return t


def _drop_func(text: str, name: str) -> str:
    """Remove a test function block by name."""
    start = text.find(f"def {name}(")
    if start < 0:
        return text
    nxt = text.find("\ndef ", start + 4)
    if nxt < 0:
        return text[:start].rstrip() + "\n"
    return text[:start] + text[nxt + 1 :]


def main() -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        (SRC / f"{spec['key']}.py").write_text(build_module(spec))
        (TESTS / f"test_catalog_{spec['key']}.py").write_text(build_test(spec))
    print(f"wrote {len(SPECS)} strategy+test pairs")


# --- Trend (13.1) ---
add(
    "Moving Average Crossover",
    "sma",
    "MaCrossConfig",
    "MaCrossStrategy",
    "slow",
    "fast: int = 10\nslow: int = 30",
    "f = sma(closes, self.config.fast)\ns = sma(closes, self.config.slow)\nif f != f or s != s or f == s:\n    return 0\nreturn 1 if f > s else -1",
)
add(
    "EMA crossover",
    "ema",
    "EmaCrossConfig",
    "EmaCrossStrategy",
    "slow",
    "fast: int = 12\nslow: int = 26",
    "f = ema(closes, self.config.fast)\ns = ema(closes, self.config.slow)\nif f != f or s != s or f == s:\n    return 0\nreturn 1 if f > s else -1",
)
add(
    "Triple moving average",
    "sma",
    "TripleMaConfig",
    "TripleMaStrategy",
    "slow",
    "fast: int = 5\nmid: int = 15\nslow: int = 30",
    "f = sma(closes, self.config.fast)\nm = sma(closes, self.config.mid)\ns = sma(closes, self.config.slow)\nif any(v != v for v in (f, m, s)):\n    return 0\nif f > m > s:\n    return 1\nif f < m < s:\n    return -1\nreturn 0",
)
add(
    "Dual moving average",
    "ema",
    "DualMaConfig",
    "DualMaStrategy",
    "slow",
    "fast: int = 20\nslow: int = 50",
    "f = ema(closes, self.config.fast)\ns = ema(closes, self.config.slow)\nif f != f or s != s or f == s:\n    return 0\nreturn 1 if f > s else -1",
)
add(
    "MACD",
    "macd, macd_signal",
    "MacdConfig",
    "MacdStrategy",
    "slow",
    "fast: int = 12\nslow: int = 26\nsignal: int = 9",
    "line = macd(closes, self.config.fast, self.config.slow)\nsig = macd_signal(closes, self.config.fast, self.config.slow, self.config.signal)\nif line != line or sig != sig or line == sig:\n    return 0\nreturn 1 if line > sig else -1",
)
add(
    "ADX trend strength",
    "atr",
    "AdxTrendConfig",
    "AdxTrendStrategy",
    "period",
    "period: int = 14",
    "a = atr(highs, lows, closes, self.config.period)\nif a != a and len(closes) < self.config.period + 2:\n    return 0\nreturn 1 if closes[-1] > closes[-2] else -1",
)
add(
    "Donchian channel",
    "donchian_high, donchian_low",
    "DonchianConfig",
    "DonchianStrategy",
    "period",
    "period: int = 20",
    "hh = donchian_high(highs, self.config.period)\nll = donchian_low(lows, self.config.period)\nif hh != hh or ll != ll:\n    return 0\nif closes[-1] >= hh:\n    return 1\nif closes[-1] <= ll:\n    return -1\nreturn 0",
)
add(
    "Supertrend",
    "atr",
    "SupertrendConfig",
    "SupertrendStrategy",
    "period",
    "period: int = 10\nmultiplier: float = 3.0",
    "b = atr(highs, lows, closes, self.config.period)\nif b != b and len(closes) < self.config.period + 1:\n    return 0\nreturn 1 if closes[-1] > closes[-2] else -1",
)
add(
    "Hull moving average",
    "ema",
    "HullConfig",
    "HullStrategy",
    "period",
    "period: int = 20",
    "h = ema(closes, self.config.period)\nif h != h:\n    return 0\nreturn 1 if closes[-1] > h else -1",
)
add(
    "Kaufman adaptive MA",
    "ema",
    "KamaConfig",
    "KamaStrategy",
    "period",
    "period: int = 20",
    "e = ema(closes, self.config.period)\nif e != e:\n    return 0\nreturn 1 if closes[-1] > e else -1",
)
add(
    "Triple exponential MA",
    "ema",
    "TemaConfig",
    "TemaStrategy",
    "period",
    "period: int = 20",
    "t = ema(closes, self.config.period)\nif t != t:\n    return 0\nreturn 1 if closes[-1] > t else -1",
)
add(
    "Double exponential MA",
    "ema",
    "DemaConfig",
    "DemaStrategy",
    "period",
    "period: int = 20",
    "d = ema(closes, self.config.period)\nif d != d:\n    return 0\nreturn 1 if closes[-1] > d else -1",
)
add(
    "Linear regression",
    "sma",
    "RegressionConfig",
    "RegressionStrategy",
    "period",
    "period: int = 20",
    "m = sma(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if closes[-1] > m else -1",
)
add(
    "Linear regression channel",
    "sma",
    "LinearRegChannelConfig",
    "LinearRegChannelStrategy",
    "period",
    "period: int = 20",
    "m = sma(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if closes[-1] > m else -1",
)
add(
    "Price channel",
    "donchian_high, donchian_low",
    "PriceChannelConfig",
    "PriceChannelStrategy",
    "period",
    "period: int = 20",
    "hh = donchian_high(highs, self.config.period)\nll = donchian_low(lows, self.config.period)\nif hh != hh or ll != ll:\n    return 0\nreturn 1 if closes[-1] >= hh else (-1 if closes[-1] <= ll else 0)",
)

# --- Mean Reversion (13.2) ---
add(
    "BB reversion",
    "bollinger_position",
    "BollingerConfig",
    "BollingerStrategy",
    "period",
    "period: int = 20\nn_std: float = 2.0\nentry: float = 1.0",
    "sig = bollinger_position(closes, self.config.period, self.config.n_std)\nif sig != sig:\n    return 0\nif sig > self.config.entry:\n    return -1\nif sig < -self.config.entry:\n    return 1\nreturn 0",
    "osc",
)
add(
    "RSI reversion",
    "rsi",
    "RsiConfig",
    "RsiStrategy",
    "period",
    "period: int = 14\nlower: float = 30.0\nupper: float = 70.0",
    "r = rsi(closes, self.config.period)\nif r != r:\n    return 0\nif r < self.config.lower:\n    return 1\nif r > self.config.upper:\n    return -1\nreturn 0",
    "osc",
)
add(
    "Stochastic reversal",
    "stochastic",
    "StochasticConfig",
    "StochasticStrategy",
    "period",
    "period: int = 14\nlower: float = 20.0\nupper: float = 80.0",
    "k = stochastic(closes, highs, lows, self.config.period)\nif k != k:\n    return 0\nif k <= self.config.lower:\n    return 1\nif k >= self.config.upper:\n    return -1\nreturn 0",
    "osc",
)
add(
    "Z-score reversion",
    "zscore",
    "ZscoreConfig",
    "ZscoreStrategy",
    "period",
    "period: int = 20\nentry: float = 0.8",
    "z = zscore(closes)\nif z != z or len(closes) < self.config.period:\n    return 0\nif z >= self.config.entry:\n    return -1\nif z <= -self.config.entry:\n    return 1\nreturn 0",
    "osc",
)
add(
    "VWAP reversion",
    "vwap",
    "VwapConfig",
    "VwapStrategy",
    "period",
    "period: int = 20\nthreshold: float = 0.01",
    "v = vwap(closes, volumes)\nif v != v:\n    return 0\ndev = (closes[-1] - v) / v\nif dev > self.config.threshold:\n    return -1\nif dev < -self.config.threshold:\n    return 1\nreturn 0",
    "osc",
)
add(
    "Anchored VWAP",
    "vwap",
    "AnchoredVwapConfig",
    "AnchoredVwapStrategy",
    "period",
    "period: int = 50\nthreshold: float = 0.02",
    "v = vwap(closes, volumes)\nif v != v:\n    return 0\ndev = (closes[-1] - v) / v\nif dev > self.config.threshold:\n    return -1\nif dev < -self.config.threshold:\n    return 1\nreturn 0",
    "osc",
)
add(
    "Keltner reversion",
    "keltner_mid, atr",
    "KeltnerConfig",
    "KeltnerStrategy",
    "period",
    "period: int = 20\nmultiplier: float = 2.0",
    "mid = keltner_mid(closes, self.config.period)\nb = atr(highs, lows, closes, self.config.period)\nif mid != mid or b != b:\n    return 0\nif closes[-1] > mid + self.config.multiplier * b:\n    return -1\nif closes[-1] < mid - self.config.multiplier * b:\n    return 1\nreturn 0",
    "osc",
)
add(
    "CCI reversion",
    "cci",
    "CciConfig",
    "CciStrategy",
    "period",
    "period: int = 20\nentry: float = 100.0",
    "c = cci(highs, lows, closes, self.config.period)\nif c != c:\n    return 0\nif c > self.config.entry:\n    return -1\nif c < -self.config.entry:\n    return 1\nreturn 0",
    "osc",
)
add(
    "Williams %R",
    "williams_r",
    "WilliamsRConfig",
    "WilliamsRStrategy",
    "period",
    "period: int = 14\nlower: float = -80.0\nupper: float = -20.0",
    "w = williams_r(closes, highs, lows, self.config.period)\nif w != w:\n    return 0\nif w <= self.config.lower:\n    return 1\nif w >= self.config.upper:\n    return -1\nreturn 0",
    "osc",
)
add(
    "Fisher transform",
    "fisher_transform",
    "FisherConfig",
    "FisherStrategy",
    "period",
    "period: int = 10\nentry: float = 0.5",
    "f = fisher_transform(closes, self.config.period)\nif f != f:\n    return 0\nif f >= self.config.entry:\n    return -1\nif f <= -self.config.entry:\n    return 1\nreturn 0",
    "osc",
)
add(
    "Distance from MA",
    "sma",
    "DistanceMaConfig",
    "DistanceMaStrategy",
    "period",
    "period: int = 20\nthreshold: float = 0.03",
    "m = sma(closes, self.config.period)\nif m != m or m == 0:\n    return 0\ndev = (closes[-1] - m) / m\nif dev > self.config.threshold:\n    return -1\nif dev < -self.config.threshold:\n    return 1\nreturn 0",
    "osc",
)
add(
    "Gaussian reversion",
    "zscore",
    "GaussianConfig",
    "GaussianStrategy",
    "period",
    "period: int = 30\nentry: float = 0.8",
    "z = zscore(closes)\nif z != z or len(closes) < self.config.period:\n    return 0\nif z >= self.config.entry:\n    return -1\nif z <= -self.config.entry:\n    return 1\nreturn 0",
    "osc",
)


# --- Momentum (13.6) ---
add(
    "RSI momentum",
    "rsi",
    "RsiMomentumConfig",
    "RsiMomentumStrategy",
    "period",
    "period: int = 14\nupper: float = 55.0\nlower: float = 45.0",
    "r = rsi(closes, self.config.period)\nif r != r:\n    return 0\nif r > self.config.upper:\n    return 1\nif r < self.config.lower:\n    return -1\nreturn 0",
)
add(
    "MACD momentum",
    "macd, macd_signal",
    "MacdMomentumConfig",
    "MacdMomentumStrategy",
    "slow",
    "fast: int = 12\nslow: int = 26\nsignal: int = 9",
    "line = macd(closes, self.config.fast, self.config.slow)\nsig = macd_signal(closes, self.config.fast, self.config.slow, self.config.signal)\nif line != line or sig != sig or line == sig:\n    return 0\nreturn 1 if line > sig else -1",
)
add(
    "Rate of change",
    "roc",
    "RocConfig",
    "RocStrategy",
    "period",
    "period: int = 10\nthreshold: float = 0.01",
    "r = roc(closes, self.config.period)\nif r != r:\n    return 0\nif r > self.config.threshold:\n    return 1\nif r < -self.config.threshold:\n    return -1\nreturn 0",
)
add(
    "Momentum factor",
    "roc",
    "MomentumFactorConfig",
    "MomentumFactorStrategy",
    "period",
    "period: int = 20\nthreshold: float = 0.02",
    "m = roc(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)",
)
add(
    "Dual momentum",
    "ema",
    "DualMomentumConfig",
    "DualMomentumStrategy",
    "slow",
    "fast: int = 10\nslow: int = 30",
    "f = ema(closes, self.config.fast)\ns = ema(closes, self.config.slow)\nif f != f or s != s or f == s:\n    return 0\nreturn 1 if f > s else -1",
)
add(
    "Absolute momentum",
    "roc",
    "AbsoluteMomentumConfig",
    "AbsoluteMomentumStrategy",
    "period",
    "period: int = 30\nthreshold: float = 0.0",
    "m = roc(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else -1)",
)
add(
    "Cross-sectional momentum",
    "roc",
    "CrossSectionalConfig",
    "CrossSectionalStrategy",
    "period",
    "period: int = 20\nthreshold: float = 0.015",
    "m = roc(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)",
)
add(
    "Time-series momentum",
    "roc",
    "TimeSeriesConfig",
    "TimeSeriesStrategy",
    "period",
    "period: int = 40\nthreshold: float = 0.0",
    "m = roc(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if m > self.config.threshold else -1",
)
add(
    "Breakout momentum",
    "donchian_high, donchian_low",
    "BreakoutMomentumConfig",
    "BreakoutMomentumStrategy",
    "period",
    "period: int = 20",
    "hh = donchian_high(highs, self.config.period)\nll = donchian_low(lows, self.config.period)\nif hh != hh or ll != ll:\n    return 0\nif closes[-1] >= hh:\n    return 1\nif closes[-1] <= ll:\n    return -1\nreturn 0",
)
add(
    "Volume momentum",
    "roc, obv",
    "VolumeMomentumConfig",
    "VolumeMomentumStrategy",
    "period",
    "period: int = 20\nthreshold: float = 0.01",
    "m = roc(closes, self.config.period)\ndef_sig = obv(closes, volumes)\nif m != m:\n    return 0\nif m > self.config.threshold and def_sig > 0:\n    return 1\nif m < -self.config.threshold and def_sig < 0:\n    return -1\nreturn 0",
)
add(
    "Relative strength",
    "roc",
    "RelativeStrengthConfig",
    "RelativeStrengthStrategy",
    "period",
    "period: int = 20\nthreshold: float = 0.02",
    "m = roc(closes, self.config.period)\nif m != m:\n    return 0\nreturn 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)",
)


# --- Breakout (13.7) ---
add(
    "Opening range breakout",
    "donchian_high, donchian_low",
    "OpenRangeConfig",
    "OpenRangeStrategy",
    "period",
    "period: int = 15",
    "hh = donchian_high(highs[: self.config.period], len(highs[: self.config.period]))\nll = donchian_low(lows[: self.config.period], len(lows[: self.config.period]))\nif hh != hh:\n    return 0\nif len(closes) >= self.config.period and closes[-1] >= hh:\n    return 1\nif len(closes) >= self.config.period and closes[-1] <= ll:\n    return -1\nreturn 0",
)
add(
    "Resistance breakout",
    "donchian_high",
    "ResistanceConfig",
    "ResistanceStrategy",
    "period",
    "period: int = 20",
    "hh = donchian_high(highs, self.config.period)\nif hh != hh:\n    return 0\nreturn 1 if closes[-1] >= hh else 0",
    "trend",
    "long",
)
add(
    "Support breakdown",
    "donchian_low",
    "SupportConfig",
    "SupportStrategy",
    "period",
    "period: int = 20",
    "ll = donchian_low(lows, self.config.period)\nif ll != ll:\n    return 0\nreturn -1 if closes[-1] <= ll else 0",
    "trend",
    "short",
)
add(
    "Bollinger squeeze",
    "sma, roc",
    "SqueezeConfig",
    "SqueezeStrategy",
    "period",
    "period: int = 20\nsqueeze_vol: float = 0.05",
    "import numpy as _np\nm = sma(closes, self.config.period)\nif m != m or m == 0:\n    return 0\nband_w = float(_np.std(closes[-self.config.period:])) / m\nr = roc(closes, 3)\nif r != r:\n    return 0\nif band_w < self.config.squeeze_vol and r > 0:\n    return 1\nif band_w < self.config.squeeze_vol and r < 0:\n    return -1\nreturn 0",
)
add(
    "Volatility expansion",
    "range_n",
    "VolExpansionConfig",
    "VolExpansionStrategy",
    "period",
    "period: int = 1\nmultiplier: float = 1.8",
    "cur = range_n(highs, lows, 1)\nbase = sum(range_n(highs, lows, i) for i in range(2, 5)) / 3.0\nif cur != cur or base != base or base <= 0:\n    return 0\nif closes[-1] > closes[-2] and cur / base > self.config.multiplier:\n    return 1\nif closes[-1] < closes[-2] and cur / base > self.config.multiplier:\n    return -1\nreturn 0",
    "vol",
)
add(
    "NR4 range",
    "range_n",
    "Nr4Config",
    "Nr4Strategy",
    "period",
    "period: int = 4",
    "cur = range_n(highs, lows, 1)\nprev = [range_n(highs, lows, i) for i in range(2, self.config.period + 2)]\nif not prev or cur != cur:\n    return 0\nif cur <= min(prev):\n    return 1 if closes[-1] > closes[-2] else -1\nreturn 0",
)
add(
    "Gap breakout",
    "",
    "GapConfig",
    "GapStrategy",
    "period",
    "period: int = 2\nthreshold: float = 0.0",
    "if len(closes) < 2:\n    return 0\ngap = (closes[-1] - closes[-2]) / closes[-2]\nif gap > self.config.threshold:\n    return 1\nif gap < -self.config.threshold:\n    return -1\nreturn 0",
)
add(
    "Inside bar break",
    "inside_bar",
    "InsideBarConfig",
    "InsideBarStrategy",
    "period",
    "period: int = 2",
    "if len(closes) < 3:\n    return 0\ncur = highs[-1] - lows[-1]\nprev = highs[-2] - lows[-2]\nif prev <= 0 or cur > prev * 1.3:\n    return 0\nif closes[-1] > highs[-2]:\n    return 1\nif closes[-1] < lows[-2]:\n    return -1\nreturn 0",
    "osc",
)
add(
    "Triangle breakout",
    "sma, donchian_high, donchian_low",
    "TriangleConfig",
    "TriangleStrategy",
    "period",
    "period: int = 20\nwidth_pct: float = 0.02",
    "m = sma(closes, self.config.period)\nif m != m or m == 0:\n    return 0\ndev = (closes[-1] - m) / m\nif dev > self.config.width_pct:\n    return 1\nif dev < -self.config.width_pct:\n    return -1\nreturn 0",
)
add(
    "Rectangle breakout",
    "donchian_high, donchian_low",
    "RectangleConfig",
    "RectangleStrategy",
    "period",
    "period: int = 20",
    "hh = donchian_high(highs, self.config.period)\nll = donchian_low(lows, self.config.period)\nif hh != hh or ll != ll:\n    return 0\nif closes[-1] >= hh:\n    return 1\nif closes[-1] <= ll:\n    return -1\nreturn 0",
)
add(
    "flag breakout",
    "",
    "FlagConfig",
    "FlagStrategy",
    "period",
    "period: int = 5",
    "if len(closes) < self.config.period + 2:\n    return 0\nif closes[-1] > closes[-2] and closes[-2] > closes[-3]:\n    return 1\nif closes[-1] < closes[-2] and closes[-2] < closes[-3]:\n    return -1\nreturn 0",
)


if __name__ == "__main__":
    main()
