#!/usr/bin/env bash
# Set up one wave: 40 git worktrees, one per agent.
#
# Worktrees exist so 40 agents never collide. Each agent writes ONE factor
# file (research/sweep/factors_<id>.py), so merging a wave back is a set of
# new-file adds with no conflicts.
#
# Results are written OUTSIDE the worktrees (tem/waves/wave<N>/) so a worktree
# can be destroyed without taking the wave's data with it.
set -euo pipefail

WAVE="${1:?usage: setup_wave.sh <wave-number> [n_agents]}"
N="${2:-40}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WT="${ROOT}/.worktrees/w${WAVE}"
RESULTS="${ROOT}/tem/waves/w${WAVE}"

mkdir -p "${WT}" "${RESULTS}"
BASE="$(git -C "${ROOT}" rev-parse HEAD)"

echo "wave ${WAVE}: ${N} worktrees from ${BASE:0:12}"
for i in $(seq 0 $((N - 1))); do
  BR="wave${WAVE}/agent${i}"
  git -C "${ROOT}" worktree remove --force "${WT}/a${i}" 2>/dev/null || true
  git -C "${ROOT}" branch -D "${BR}" 2>/dev/null || true
  git -C "${ROOT}" worktree add -q -f "${WT}/a${i}" -b "${BR}" "${BASE}"
  # .venv and the skill dirs must exist inside the worktree for agents to work.
  ln -sfn "${ROOT}/.venv" "${WT}/a${i}/.venv" 2>/dev/null || true
done
echo "ready: ${WT}/a0 .. ${WT}/a$((N-1))   results -> ${RESULTS}"
