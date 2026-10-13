"""Batch 5 -- `agent_inapplicable`, whose trial script runs at import.

`trial.py` has no `__main__` guard, so importing it executes the whole experiment. Only
its *function* definitions are extracted here, via `ast`, and called directly.

Two things are worth flagging about this agent before any number is read:

1. Its `load_panel()` reads the raw `*_1d.csv` files and slices `>= 2008-01-01` by hand.
   It does NOT call `load_universe`, so it bypasses cleaning rules C1-C8 and keeps 50
   symbols where every other agent keeps 48. Its panel is not the same substrate, which
   is why this batch probes on the agent's own panel rather than the shared one.
2. Its `random_score` control builds a bare 0/1 mask from `np.random.random(...)` and
   then ranks it -- but `rank(axis=1, pct=True)` makes the values distinct, so this
   particular control was NOT degenerate. Worth stating plainly, because the same
   pattern in other agents WAS, and the difference is the ranking line, not the mask.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json  # noqa: E402

from core import TEST, TRAIN, check_provenance, fmt_pr, probe  # noqa: E402

TRIAL = Path(__file__).resolve().parents[1] / "agent_inapplicable" / "trial.py"


def _defs_only(path: Path) -> dict:
    """Execute only the `def` statements of a top-level script, not its body."""
    tree = ast.parse(path.read_text())
    keep = [
        n
        for n in tree.body
        if isinstance(n, ast.Import | ast.ImportFrom | ast.FunctionDef | ast.Assign)
    ]
    mod = ast.Module(body=keep, type_ignores=[])
    ns: dict = {"__name__": "inapplicable_defs_only", "__file__": str(path)}
    exec(compile(mod, str(path), "exec"), ns)  # noqa: S102
    return ns


ROWS: list[dict] = []


def main() -> None:
    check_provenance()
    ns = _defs_only(TRIAL)
    px = ns["load_panel"]()
    print(f"agent_inapplicable own panel: {px.shape[0]} rows x {px.shape[1]} symbols")
    for kind, label, period, thr in (("basket", "p120_t0.015", 120, 0.015),):
        sig = ns["signal_panel"](px, kind, period, thr)
        sc = ns["cross_sectional_score"](px, sig)
        for wname, w in (("TRAIN", TRAIN), ("TEST", TEST)):
            pr = probe(f"inapplicable::{kind} {label}|{wname}", px, sc, window=w)
            print(fmt_pr(pr))
            ROWS.append(pr.row())

    out = Path(__file__).resolve().parent / "results.json"
    prev = json.loads(out.read_text()) if out.exists() else []
    done = {r["label"] for r in ROWS}
    merged = [r for r in prev if r["label"] not in done] + ROWS
    out.write_text(json.dumps(merged, indent=1))
    print(f"\nwrote {len(merged)} rows -> {out}")


if __name__ == "__main__":
    main()
