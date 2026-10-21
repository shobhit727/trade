"""Generate an agent's task file for a wave.

One file per agent, written into the agent's worktree. Generating it from code
(rather than hand-writing 40 prompts) guarantees every agent gets the identical
contract, and that the assignment matches the family bank.

Usage:
    python -m research.sweep.agent_task --wave 1 --agent 7 --out <path>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .families import assignment

TEMPLATE = """# Agent {agent} -- Wave {wave}

## Your assignment

**Regime {regime}.** {directive}

You are one of 40 agents in this wave. You own this hypothesis and nobody
else's. Read the assignment carefully: it is a DIRECTIVE with a falsifiable
mechanism, not a topic to free-associate around.

## Read these first

1. `.claude/skills/nse-factor/SKILL.md` -- the factor design rules and the
   four gates. Read this fully.
2. `research/sweep/harness.py` -- the {nfactors} existing factors, the
   measurement, and the house idioms. Scroll the FACTORS dict and pick
   something your assignment does not duplicate.

## Hard rules

- **Stay inside this repository.** Your worktree is `{wt}`. Work there. Do not
  read from or write to any other checkout on this machine.
- **Never edit `research/sweep/harness.py`.** 40 agents run in parallel; a
  shared edit merges into conflicts. You own exactly one file:
  `research/sweep/factors_{tag}.py`.
- **No lookahead.** Only bars up to and including the current one.
- **Commit ONLY your factor file.** Never `git add -A`. Never touch the main
  repo working tree.
- Results go to `{results}/` (outside the worktree) so cleanup cannot destroy
  them.

## Step 1 -- implement

Write `research/sweep/factors_{tag}.py` with 3-5 new factors addressing the
assignment. Use the decorator:

```python
from research.sweep.harness import factor

@factor("your_factor_name")
def _your_factor(px: pd.DataFrame) -> pd.DataFrame:
    \"\"\"One line: what it is. One line: why higher should rank better.\"\"\"
    return px.pct_change(21)
```

Signature is `(px: pd.DataFrame) -> pd.DataFrame`, one column per symbol, higher
= better. The panel is CLOSE PRICES. If you need open/high/low/volume, load
them yourself from `data/nse/<sym>_1d.csv` in a module-level cached loader --
do NOT edit the harness.

**Test the opposite sign too.** If your hypothesis says "higher is better",
also register the negation. If the mechanism is real, one of the two should
win. Which one wins is a finding.

## Step 2 -- measure

```bash
cd {wt}
PYTHONPATH=src:. .venv/bin/python -m research.sweep.run_agent \\
  --factors <comma-separated names> \\
  --n-hold 15 20 25 30 --buffer 0 10 20 --clock M Q A \\
  --windows TEST --out {results} --tag {tag}
```

That is 36 cells per factor. Keep the total to roughly 150-250 cells -- more
if you need a both-ways sign test, but do not run the whole grid blindly.

**Also run TRAIN** (`--windows TRAIN`) for your single best factor. A factor
that works only in the TEST window is not a factor. This is the single most
important check and several agents in wave 1 were disqualified by it.

## Step 3 -- commit

```bash
git add research/sweep/factors_{tag}.py
git -c user.name=agent -c user.email=agent@local commit -m "wave{wave} agent{agent}: <family> factors"
```

## Step 4 -- report

Reply with at most 25 lines:

- Each factor you built and its sign hypothesis, in one line each.
- The best cell: factor, n_hold, buffer, clock, CAGR, null CAGR, bench CAGR,
  `edge_vs_null`, `edge_vs_bench`, Sharpe, MaxDD.
- Family-level: how many of the factor's cells beat the scrambled null, and
  how many beat the equal-weight universe.
- The TRAIN result for your best factor.
- **An honest verdict.** "Nothing found" is a perfectly good result and a
  useful one. A clean negative narrows the space for the other 39 agents.

## The bar

Every cell is measured against a scrambled null AND against holding the
equal-weight universe with the same cost stack. A factor that beats its null
but loses to the universe is **not** a deployable signal -- it means you could
have just held the index and done better.

At 1,400 cells, roughly 70 will look significant by chance. The bar for
"promising" is: beats the null AND beats the universe AND survives TRAIN.
Anything less is a hypothesis for a later wave, not a finding.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--agent", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=None)
    args = ap.parse_args()

    from .harness import FACTORS

    regime, directive = assignment(args.wave, args.agent)
    root = args.root or Path(__file__).resolve().parents[2]
    wt = root / ".worktrees" / f"w{args.wave}" / f"a{args.agent}"
    results = root / "tem" / "waves" / f"w{args.wave}"
    tag = f"a{args.agent:02d}"

    text = TEMPLATE.format(
        wave=args.wave, agent=args.agent, regime=regime, directive=directive,
        wt=wt, results=results, tag=tag, nfactors=len(FACTORS),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
