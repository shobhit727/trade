"""Provenance hashes for the code and data that produce a backtest result.

Why this exists
---------------
Multiple research agents, working in parallel on one repo, produced *irreproducible*
results twice, for two different reasons:

1. ``backtest/engine.py`` was rewritten mid-experiment. Identical scripts returned
   different numbers because ``apply_turnover_budget`` had changed.
2. ``data/loader.py`` gained a cleaning rule mid-experiment. ``engine_sha`` did not
   change -- it only ever hashed the engine -- so the panel silently changed under a
   study with no provenance marker at all. One agent caught this only because its
   numbers happened to move.

Both files change results. Both must be fingerprinted.

Design notes
------------
* **Docstrings are stripped** before hashing so that editing prose in a docstring does
  not invalidate the fingerprint. Code changes still do, which is the point.
* **The hash lives outside the hashed files.** If ``provenance.py`` hashed itself,
  every change here would invalidate every result, and the fingerprint would churn
  for no reason. It hashes ``engine.py``, ``loader.py`` and ``costs.py`` only.
* Hashing never raises. Provenance is bookkeeping; it must not be able to fail a
  backtest.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

__all__ = ["ENGINE_SHA", "LOADER_SHA", "COSTS_SHA", "PANEL_SHA", "provenance"]

#: Files whose contents can change a backtest result. Order is fixed so the digest is
#: stable. ``costs.py`` is included because it sets the charge applied to every fill.
_TRACKED = (
    ("engine", "backtest/engine.py"),
    ("loader", "data/loader.py"),
    ("costs", "costs.py"),
)


def _sha(path: Path) -> str:
    """Content hash of one source file, ignoring docstrings.

    Falls back to the literal ``"unknown"`` rather than raising -- see module docstring.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(
                node,
                ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Module,
            ):
                body = getattr(node, "body", None)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body.pop(0)
        payload = ast.dump(tree)
    except Exception:  # noqa: BLE001 - provenance must never break a backtest
        return "unknown"
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


_ROOT = Path(__file__).resolve().parent


def _build() -> dict[str, str]:
    out = {name: _sha(_ROOT / rel) for name, rel in _TRACKED}
    out["panel"] = _panel_sha()
    return out


def _panel_sha() -> str:
    """Fingerprint the loaded market data.

    The panel is reconstructed from ``data/nse/*.csv`` by ``loader.load_universe``.
    Hashing those files catches the case where data was re-fetched or edited without
    any code change -- for example when ``tools/recover_nse_data.py`` recovers more
    timeframes and a study is re-run against a longer history.
    """
    try:
        digest = hashlib.sha256()
        data_dir = _ROOT.parent.parent / "data" / "nse"
        for csv in sorted(data_dir.rglob("*.csv")):
            digest.update(csv.relative_to(data_dir).as_posix().encode())
            digest.update(csv.read_bytes())
        return digest.hexdigest()[:12]
    except Exception:  # noqa: BLE001 - provenance must never break a backtest
        return "unknown"


_HASHES = _build()

ENGINE_SHA: str = _HASHES["engine"]
LOADER_SHA: str = _HASHES["loader"]
COSTS_SHA: str = _HASHES["costs"]
PANEL_SHA: str = _HASHES["panel"]


def provenance() -> dict[str, str]:
    """All provenance fingerprints, for stamping into a report or a result."""
    return dict(_HASHES)
