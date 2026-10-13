"""Import an agent's *own* harness library so its score panel is reconstructed, not guessed.

Nothing in `research/agent_*` is modified or executed as a script. Only its importable
builder functions are called, so the panel under test is the one that agent actually fed
the engine -- not a reconstruction of it from the report prose.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]


@contextlib.contextmanager
def _quiet():
    """Harness modules print at import time. Silence that, keep real errors."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield


def load(agent: str, module: str | None = None) -> ModuleType:
    """Import `research/agent_<agent>/<module>.py` as a standalone module."""
    d = REPO / "research" / f"agent_{agent}"
    if module is None:
        stem = agent.split("agent_", 1)[-1]
        cands = ["common", "harness", f"{stem}lib", "cmflib", "signal", "coinlib", "dema_lib"]
        for c in cands:
            if (d / f"{c}.py").exists():
                module = c
                break
    path = d / f"{module}.py"
    if not path.exists():
        raise FileNotFoundError(f"{agent}: no importable module (tried {module})")
    name = f"agentlib_{agent}_{module}"
    for sub in (str(REPO / "src"), str(REPO / "research/revalidation")):
        if sub not in sys.path:
            sys.path.insert(0, sub)
    # The agent directory goes in LAST and only when it is not already present: two agents
    # ship a module with the same name (`data_prep.py` in both `mfi` and `obv`), and once
    # one agent's directory is on `sys.path` Python's plain `import data_prep` cache will
    # hand the *other* agent's module back.
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    # Drop any stale bare-name entry so a same-named module from another agent cannot
    # satisfy this file's own intra-package imports.
    sys.modules.pop(module, None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    with _quiet():
        spec.loader.exec_module(mod)
    return mod


def load_json(agent: str, name: str) -> dict:
    import json

    p = REPO / "research" / f"agent_{agent}" / name
    if not p.exists():
        raise FileNotFoundError(p)
    return json.loads(p.read_text())
