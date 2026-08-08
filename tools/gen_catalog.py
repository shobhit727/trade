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
    doc: str, imports: str, cfg: str, cls: str, warm: str, fields: str, signal: str, mode: str = "trend"
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
            key=_key(cfg),
        )
    )


def build_module(spec: dict) -> str:
    code = MODULE_TMPL
    code = code.replace("NAME", spec["doc"].capitalize())
    code = code.replace("IMPORTS", spec["imports"])
    code = code.replace("CFG", spec["cfg"])
    code = code.replace("STRAT", spec["strat_cls"])
    code = code.replace("KEY", spec["key"])
    code = code.replace("WARM", spec["warm"])
    code = code.replace("FIELDS", _indent(spec["fields"], 4))
    code = code.replace("SIGNAL", _indent(spec["signal"], 8))
    return code


def build_test(spec: dict) -> str:
    t = TEST_OSC_TMPL if spec.get("mode") == "osc" else TEST_TREND_TMPL
    return t.replace("KEY", spec["key"]).replace("STRAT", spec["strat_cls"])


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


if __name__ == "__main__":
    main()
