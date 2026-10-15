"""Discover the catalog and derive a bounded search space for each strategy's Config.

The catalog exposes 84 strategies, each with a dataclass ``Config``. Annotations drive
the search space: ``int`` fields become an integer range, ``float`` fields a float range,
``bool`` fields a boolean, and ``Literal`` fields a fixed choice list.

Two guards keep this honest:

1. **Unknown types are skipped, never guessed.** A field we cannot type-safely sample is
   dropped from the space and recorded, so the report can say "N fields held fixed" rather
   than silently claiming full coverage.
2. **The shipped default is always evaluated.** Every pair reports ``default`` alongside
   ``optimised``, so the value added by searching is measured rather than assumed.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import logging
import pathlib
import typing
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

CATALOG_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "cryptobot" / "strategies" / "catalog"

#: Sampling bounds by field name, where a generic range would be absurd. Keys are matched
#: case-insensitively as substrings. Anything unmatched falls through to the type defaults.
NAME_BOUNDS: dict[str, tuple[float, float]] = {
    "period": (2, 250),
    "lookback": (2, 250),
    "window": (2, 250),
    "length": (2, 250),
    "fast": (2, 100),
    "slow": (3, 250),
    "signal": (2, 100),
    "smooth": (2, 50),
    "atr": (2, 100),
    "std": (2, 100),
    "threshold": (0.01, 4.0),
    "entry": (0.01, 4.0),
    "exit": (0.01, 4.0),
    "zscore": (0.1, 4.0),
    "profit_target": (0.01, 0.5),
    "stop_loss": (0.01, 0.5),
    "trail": (0.01, 0.5),
    "multiplier": (0.5, 5.0),
    "quantity": (1, 10),
}

#: Floats outside this range are almost certainly nonsense for a lookback-style knob.
INT_DEFAULT_BOUNDS = (2, 250)


@dataclass
class ParamSpec:
    """One searchable field of a strategy Config."""

    name: str
    kind: str  # "int" | "float" | "bool" | "choice"
    low: float | None = None
    high: float | None = None
    choices: tuple[object, ...] = ()

    def sample(self, rng):
        if self.kind == "int":
            return int(rng.integers(int(self.low), int(self.high) + 1))
        if self.kind == "float":
            return round(float(rng.uniform(self.low, self.high)), 6)
        if self.kind == "bool":
            return bool(rng.integers(0, 2))
        return self.choices[int(rng.integers(0, len(self.choices)))]

    def to_dict(self) -> dict:
        d = {"name": self.name, "kind": self.kind}
        if self.kind in ("int", "float"):
            d["low"], d["high"] = self.low, self.high
        if self.kind == "choice":
            d["choices"] = list(self.choices)
        return d


@dataclass
class StrategySpec:
    """A catalog strategy plus its search space."""

    name: str
    module: str
    config_cls: type
    strategy_cls: type
    params: list[ParamSpec] = field(default_factory=list)
    held_fixed: list[str] = field(default_factory=list)
    default: dict = field(default_factory=dict)

    def sample(self, rng) -> dict:
        return {p.name: p.sample(rng) for p in self.params}

    def build(self, values: dict):
        """Instantiate the strategy with a Config built from ``values``.

        Only fields present in ``values`` are overridden; the rest keep their defaults.
        That is deliberate -- the caller may pass a partial dict (e.g. the shipped
        default) and get the shipped behaviour.

        Values are coerced back to their annotated type. This matters for reproducibility:
        the results JSONL serialises ``Decimal`` as a JSON string, so re-running a saved
        result handed the config ``quantity='1'`` (a str) instead of ``Decimal('1')``.
        The catalog's own ``SignalStrategy.feed`` then evaluates ``'1' * Decimal(2)`` and
        raises ``TypeError: can't multiply sequence by non-int``. Every saved pair was
        therefore unreproducible. Coercion here fixes it for all callers at once.
        """
        cfg_cls = self.config_cls
        kwargs = {
            f.name: _coerce(f, v)
            for f in dataclasses.fields(cfg_cls)
            if (v := values.get(f.name)) is not None
        }
        try:
            cfg = cfg_cls(**kwargs)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{self.name}: rejected config {kwargs!r}: {exc}") from exc
        return self.strategy_cls(cfg)


def _coerce(f, value):
    """Restore a JSON round-tripped value to the type its dataclass field declares."""
    if not isinstance(value, str):
        return value
    return _coerce_str(value, f.type)


def _coerce_str(value: str, annotation):
    import decimal

    text = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
    if "Decimal" in text:
        try:
            return decimal.Decimal(value)
        except decimal.InvalidOperation:
            return value
    return value


def _pick_class(mod, suffix: str):
    """Find a class DEFINED in ``mod`` whose name ends with ``suffix``.

    The ``__module__`` check is essential, not defensive tidiness. Every catalog module
    does ``from ..signal_base import SignalStrategy``, so ``vars(mod)`` contains the base
    class -- and because the import happens before the local class definition, a naive
    name-suffix scan returns ``SignalStrategy`` for **all 84 modules**. ``SignalStrategy.
    signal()`` returns 0 unconditionally, so the whole 4,200-pair sweep would have
    reported 0.00% CAGR for every strategy, with no error anywhere.

    That failure was caught by a smoke test asserting non-zero trades, which is why
    ``run_single_stock`` is paired with the liveness checks in the test suite.
    """
    for _n, obj in vars(mod).items():
        if (
            inspect.isclass(obj)
            and obj.__module__ == mod.__name__
            and obj.__name__.lower().endswith(suffix.lower())
        ):
            return obj
    return None


def _literal_choices(annotation) -> tuple[object, ...] | None:
    origin = typing.get_origin(annotation)
    if origin is not typing.Literal and origin is not getattr(__import__("typing_extensions"), "Literal", ()):
        return None
    args = typing.get_args(annotation)
    return tuple(args) if args else None


def _spec_for(name: str, annotation) -> ParamSpec | None:
    if _literal_choices(annotation):
        return ParamSpec(name=name, kind="choice", choices=_literal_choices(annotation))

    # Unwrap Optional[X] / X | None.
    origin = typing.get_origin(annotation)
    if origin is typing.Union or str(origin) == "<class 'types.UnionType'>" or origin is getattr(
        __import__("types"), "UnionType", None
    ):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _spec_for(name, args[0])
        return None

    if annotation is bool:
        return ParamSpec(name=name, kind="bool")
    if annotation is int:
        lo, hi = NAME_BOUNDS.get(name.lower(), INT_DEFAULT_BOUNDS)
        return ParamSpec(name=name, kind="int", low=lo, high=hi)
    if annotation is float:
        lo, hi = NAME_BOUNDS.get(name.lower(), (0.01, 5.0))
        return ParamSpec(name=name, kind="float", low=lo, high=hi)
    return None


def load_strategy(module_name: str) -> StrategySpec:
    """Import one catalog module and derive its search space."""
    mod = importlib.import_module(f"cryptobot.strategies.catalog.{module_name}")

    cfg_cls = _pick_class(mod, "Config")
    if cfg_cls is None or not dataclasses.is_dataclass(cfg_cls):
        raise ValueError(f"{module_name}: no *Config dataclass found")

    strategy_cls = _pick_class(mod, "Strategy")
    if strategy_cls is None:
        raise ValueError(f"{module_name}: no *Strategy class defined in this module")
    if strategy_cls.__name__ == "SignalStrategy":
        raise ValueError(
            f"{module_name}: resolved to the BASE SignalStrategy, not a concrete "
            f"subclass -- the sweep would silently trade nothing"
        )

    params, held = [], []
    for f in dataclasses.fields(cfg_cls):
        spec = _spec_for(f.name, f.type if not isinstance(f.type, str) else _resolve(f, cfg_cls))
        if spec is None:
            held.append(f.name)
        else:
            params.append(spec)

    default = {}
    try:
        inst = cfg_cls()
        for f in dataclasses.fields(cfg_cls):
            default[f.name] = getattr(inst, f.name)
    except TypeError:
        log.warning("%s: Config has no zero-arg constructor; default baseline unavailable",
                    module_name)

    return StrategySpec(
        name=module_name,
        module=mod.__name__,
        config_cls=cfg_cls,
        strategy_cls=strategy_cls,
        params=params,
        held_fixed=held,
        default=default,
    )


def _resolve(f, cls):
    """Best-effort resolution of a possibly-stringified annotation."""
    try:
        return typing.get_type_hints(cls)[f.name]
    except Exception:
        return f.type


def discover(include: tuple[str, ...] = ()) -> list[StrategySpec]:
    """Load every catalog strategy, or just the named subset."""
    names = sorted(p.stem for p in CATALOG_DIR.glob("*.py") if p.stem != "__init__")
    if include:
        wanted = set(include)
        names = [n for n in names if n in wanted]

    specs, failed = [], []
    for n in names:
        try:
            specs.append(load_strategy(n))
        except Exception as exc:  # noqa: BLE001 - one bad module must not kill the sweep
            log.warning("SKIP %s: %s", n, exc)
            failed.append((n, str(exc)))
    if failed:
        log.warning("discover(): %d/%d strategies failed to load", len(failed), len(names))
    return specs
