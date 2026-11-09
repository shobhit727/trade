"""Authoritative final run — pins the engine hash before and after.

`src/nsealgo/backtest/engine.py` is being edited concurrently by another agent, so
a result is only meaningful together with the engine revision it was produced on.
This retries until the revision is stable across the run, and prints the hash.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time

ENGINE = "src/nsealgo/backtest/engine.py"


def engine_hash() -> str:
    return hashlib.md5(open(ENGINE, "rb").read()).hexdigest()


for attempt in range(1, 6):
    before = engine_hash()
    p = subprocess.run(
        [".venv/bin/python", "research/agent_multifactor/eval_test.py"],
        capture_output=True,
        text=True,
    )
    after = engine_hash()
    if before == after:
        print(f"engine md5 {before}  (stable, attempt {attempt}, rc={p.returncode})")
        print("=" * 100)
        print(p.stdout)
        if p.stderr.strip():
            print("STDERR:", p.stderr, file=sys.stderr)
        sys.exit(p.returncode)
    print(f"attempt {attempt}: engine changed mid-run "
          f"({before[:8]} -> {after[:8]}), retrying", file=sys.stderr)
    time.sleep(3)

print("engine never held still across 5 attempts — do not trust these numbers",
      file=sys.stderr)
sys.exit(1)
