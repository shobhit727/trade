---
name: nse-wave-orchestration
description: Run a wave of parallel agents testing NSE trading signals, using git worktrees for isolation and the shared sweep harness for identical measurement. Use when orchestrating a multi-agent research wave, dividing a hypothesis space across agents, or collecting and aggregating wave results.
---

# Orchestrating a research wave

A wave = 40 agents testing a slice of the hypothesis space, each in its own git
worktree, all measured by one shared harness.

## Why worktrees

40 agents editing one repo will collide. Each agent gets a worktree branched
from the wave's base commit, so:

- agents never block each other
- a failing agent's half-written factor cannot corrupt the shared harness
- a wave can be abandoned without leaving the main branch dirty
- results are merged back as **new files only** (`factors_<id>.py`), so there
  are no merge conflicts

## Why one harness

A result is only comparable across 1,400 cells if the measurement is
*identical*. Identical measurement is only possible if there is exactly one
implementation of it. Every agent calls `research/sweep/harness.py`. Agents
never edit it.

## The wave lifecycle

```bash
# 1. Base commit -- the harness plus any factors already merged
BASE=$(git rev-parse HEAD)

# 2. One worktree per agent
for i in $(seq 0 39); do
  git worktree add -f .worktrees/w$N/a$i -b wave$N/a$i "$BASE"
done

# 3. Agents work in their own worktree (see nse-factor skill)

# 4. Collect results -- results live OUTSIDE the worktree, in tem/
#    so a worktree can be discarded without losing the data
mkdir -p tem/waves/wave$N
# each agent writes tem/waves/wave$N/agent<NN>.jsonl  (append, resumable)

# 5. Merge the factor files back
for i in $(seq 0 39); do
  git -C .worktrees/w$N/a$i add research/sweep/factors_*.py
  git -C .worktrees/w$N/a$i commit -m "wave$N: factors from agent $i"
  git -C .worktrees/w$N/a$i format-patch -1 --stdout >> /tmp/wave$N.patch
done
git am /tmp/wave$N.patch

# 6. Clean up
for i in $(seq 0 39); do git worktree remove --force .worktrees/w$N/a$i; done
```

## Wave design — the wave number picks a REGIME

Not a random slice. Each wave is a coherent experiment, and the 35 waves
together cover the space systematically. `research/sweep/run.py:wave_cells`
implements this:

| waves | regime | what it varies |
|---|---|---|
| 1–7 | factor family sweep | one family per wave, all clocks/buffers |
| 8–14 | parameter grid | wide (n_hold, buffer) grids on the best families |
| 15–20 | instrument + short side | delivery / ETF / futures cost stacks |
| 21–26 | composites and blends | multi-factor weights, N and buffer |
| 27–31 | universe robustness | PIT vs fixed-50, weight scaling |
| 32–35 | validation | walk-forward of the survivors |

## Running the cells

```bash
# One agent's slice (deterministic sharding by --agent)
PYTHONPATH=src:. .venv/bin/python -m research.sweep.run \
    --wave 1 --agent 7 --agents 40 --out tem/waves/wave1

# Parallel across agents, 6 workers each (8 cores total)
for i in $(seq 0 39); do
  PYTHONPATH=src:. .venv/bin/python -m research.sweep.run \
      --wave 1 --agent $i --agents 40 --out tem/waves/wave1 \
      > tem/waves/wave1/agent$i.log 2>&1 &
done
wait
```

## Performance

The harness caches the do-nothing benchmark and the scrambled score, so a cell
costs ~3.7s after the first. At 40 agents × ~1,500 cells per wave, a wave is
minutes of wall-clock, not hours.

If a cell costs 20s+, the cache is cold — that is the first-call cost, and it
happens once per process.

## Aggregating

```bash
PYTHONPATH=src:. .venv/bin/python -m research.sweep.aggregate --wave 1
```

Always aggregate with **FDR across the whole family**, not per-wave. A factor
that looks good in wave 3 has been tested against every other cell in waves
1–34, and the multiple-comparison burden is cumulative.

## Traps

- **Do not let agents edit `harness.py`.** One file per agent. A 40-way merge
  conflict on a shared file is the whole reason for worktrees.
- **Results must live in `tem/`, not in the worktree.** Otherwise cleaning up a
  worktree destroys the wave's data.
- **Never `git reset --hard` or bulk-stage.** This repo has ~791 unrelated
  in-flight changes in the working tree that are not ours.
- **Do not skip the null.** A cell measured only against a benchmark will
  produce confident nonsense at 1,400 trials.
