"""Wave runner: execute one wave of cells and append rows to a JSONL file.

Every agent in a wave runs this against its own slice of the wave's cell list.
Results are appended (never rewritten) so a wave is resumable and the aggregator
can read a partial wave.

Usage:
    python -m research.sweep.run --wave 1 --agent 7 --out tem/waves/wave1
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from .harness import Cell, Result, evaluate, read_rows, write_rows

REPO = Path(__file__).resolve().parents[2]


def wave_cells(wave: int) -> list[Cell]:
    """Deterministic cell list for a wave.

    The wave number selects a REGIME of the search space, not a random slice --
    so a wave is a coherent experiment and the 35 waves together cover the
    space systematically.

      1- 7  factor family sweep   (one family per wave, all clocks/buffers)
      8-14  parameter grid         (best families, wide grid)
      15-20 instrument + short side
      21-26 composites and blends
      27-31 universe / membership robustness
      32-35 walk-forward validation of the survivors
    """
    from .harness import FACTORS

    names = sorted(FACTORS)
    cells: list[Cell] = []
    clocks = ("M", "Q", "2Q", "A")
    grids = ((20, 0), (20, 20), (15, 10), (25, 15), (30, 20))

    if 1 <= wave <= 7:
        # One factor family per wave, chunked across the factor list.
        chunk = (len(names) + 6) // 7
        fam = names[(wave - 1) * chunk: wave * chunk]
        for f in fam:
            for clock in clocks:
                for n, b in grids[:3]:
                    cells.append(Cell(factor=f, n_hold=n, buffer=b, clock=clock))
    elif 8 <= wave <= 14:
        fam = names[((wave - 8) % 7) * chunk:][:6] if (chunk := (len(names) + 6) // 7) else []
        for f in fam:
            for n in (10, 15, 20, 25, 30, 40):
                for b in (0, 5, 10, 20, 30):
                    cells.append(Cell(factor=f, n_hold=n, buffer=b, clock="Q"))
    elif 15 <= wave <= 20:
        for f in names[:6]:
            for instr in ("delivery", "etf", "futures"):
                for clock in ("M", "Q", "A"):
                    cells.append(Cell(factor=f, n_hold=20, buffer=20, clock=clock,
                                      instrument=instr))
    elif 21 <= wave <= 26:
        for f in names[:8]:
            for n, b in ((15, 20), (20, 30), (25, 25), (30, 20)):
                for uni in ("pit", "fixed50"):
                    cells.append(Cell(factor=f, n_hold=n, buffer=b, clock="A",
                                      universe=uni))
    elif 27 <= wave <= 31:
        for f in names[:10]:
            for clock in ("M", "Q", "2Q", "A"):
                for w in (0.5, 1.0, 1.5, 2.0):
                    cells.append(Cell(factor=f, n_hold=20, buffer=20, clock=clock,
                                      weight=w))
    else:
        for f in names:
            for clock in ("M", "Q", "A"):
                cells.append(Cell(factor=f, n_hold=20, buffer=20, clock=clock))
    return cells


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--agent", type=int, default=0)
    ap.add_argument("--agents", type=int, default=1)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--window", default="TEST")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cells = wave_cells(args.wave)
    if args.limit:
        cells = cells[: args.limit]
    # Deterministic sharding across agents in the wave.
    mine = cells[args.agent::args.agents]
    out = args.out / f"agent{args.agent:02d}.jsonl"

    done = {r["cid"] for r in read_rows(out) if r.get("window") == args.window}
    todo = [c for c in mine if c.cid not in done]

    print(f"[wave {args.wave} agent {args.agent}] {len(todo)} cells to run "
          f"({len(done)} already done)", flush=True)

    t0 = time.time()
    rows: list[Result] = []
    for i, c in enumerate(todo, 1):
        r = evaluate(c, args.window)
        if r is None:
            continue
        rows.append(r)
        if i % 25 == 0:
            write_rows(rows, out)
            rows = []
            print(f"  {i}/{len(todo)}  ({time.time()-t0:.0f}s)", flush=True)
    if rows:
        write_rows(rows, out)
    print(f"[wave {args.wave} agent {args.agent}] done in {time.time()-t0:.0f}s -> {out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
