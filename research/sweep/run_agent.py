"""Run one agent's own factors across a grid.

An agent's job in a wave is to PROPOSE new signal hypotheses, implement them in
``research/sweep/factors_<id>.py``, and measure them. The grid below is the
measurement plan; the signal content comes from the agent.

Usage (from an agent's worktree):
    PYTHONPATH=src:. python -m research.sweep.run_agent \
        --factors my_f1,my_f2 --n-hold 20 --buffer 20 --clock A \
        --out tem/waves/wave1 --tag agent07
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from .harness import FACTORS, Cell, Result, evaluate, read_rows, write_rows


def grid_cells(factors: list[str], n_holds: list[int], buffers: list[int],
               clocks: list[str], universe: str = "pit",
               instrument: str = "delivery") -> list[Cell]:
    cells: list[Cell] = []
    for f in factors:
        for n in n_holds:
            for b in buffers:
                for c in clocks:
                    cells.append(Cell(factor=f, n_hold=n, buffer=b, clock=c,
                                      universe=universe, instrument=instrument))
    return cells


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--factors", required=True,
                    help="comma-separated factor names you implemented")
    ap.add_argument("--n-hold", type=int, nargs="+", default=[15, 20, 25, 30])
    ap.add_argument("--buffer", type=int, nargs="+", default=[0, 10, 20])
    ap.add_argument("--clock", nargs="+", default=["M", "Q", "A"])
    ap.add_argument("--universe", default="pit")
    ap.add_argument("--instrument", default="delivery")
    ap.add_argument("--windows", nargs="+", default=["TEST"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tag", default="agent")
    args = ap.parse_args()

    names = [f.strip() for f in args.factors.split(",") if f.strip()]
    missing = [f for f in names if f not in FACTORS]
    if missing:
        print(f"ERROR: factor(s) not registered: {missing}")
        print(f"available: {sorted(FACTORS)[:10]} ... ({len(FACTORS)} total)")
        return 2

    out = args.out / f"{args.tag}.jsonl"
    cells = grid_cells(names, args.n_hold, args.buffer, args.clock,
                       args.universe, args.instrument)
    done = {(r["cid"], r["window"]) for r in read_rows(out)}
    total = len(cells) * len(args.windows)
    todo = [(c, w) for c in cells for w in args.windows if (c.cid, w) not in done]

    print(f"[{args.tag}] {len(names)} factors x {len(cells)//len(names)} configs "
          f"x {len(args.windows)} windows = {total} cells; {len(todo)} to run",
          flush=True)

    t0 = time.time()
    buf: list[Result] = []
    for i, (c, w) in enumerate(todo, 1):
        r = evaluate(c, w)
        if r is None:
            continue
        buf.append(r)
        if i % 20 == 0:
            write_rows(buf, out)
            buf = []
            print(f"  {i}/{len(todo)} ({time.time()-t0:.0f}s)", flush=True)
    if buf:
        write_rows(buf, out)
    print(f"[{args.tag}] done {len(todo)} cells in {time.time()-t0:.0f}s -> {out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
