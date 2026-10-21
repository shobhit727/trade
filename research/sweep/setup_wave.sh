#!/usr/bin/env bash
# Set up one wave: 40 git worktrees, one per agent, each fully runnable.
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

# Untracked-but-required paths that a fresh worktree will not have.
# The panel lives in /data (gitignored) and PIT membership needs tools/.
link_path() {
  local wt="$1" rel="$2"
  if [ -e "${ROOT}/${rel}" ] && [ ! -e "${wt}/${rel}" ]; then
    mkdir -p "$(dirname "${wt}/${rel}")"
    ln -sfn "${ROOT}/${rel}" "${wt}/${rel}"
  fi
}

echo "wave ${WAVE}: ${N} worktrees from ${BASE:0:12}"
for i in $(seq 0 $((N - 1))); do
  BR="wave${WAVE}/agent${i}"
  git -C "${ROOT}" worktree remove --force "${WT}/a${i}" 2>/dev/null || true
  git -C "${ROOT}" branch -D "${BR}" 2>/dev/null || true
  git -C "${ROOT}" worktree add -q -f "${WT}/a${i}" -b "${BR}" "${BASE}"

  A="${WT}/a${i}"
  # The venv and the data panel are not in git; link them so the agent's
  # commands work verbatim.
  ln -sfn "${ROOT}/.venv" "${A}/.venv"
  link_path "${A}" "data"
  link_path "${A}" "tools/pit_membership.py"
  link_path "${A}" "tools/build_pit_membership.py"
  link_path "${A}" "data/nse_membership"
  # The agent's assignment, generated so every agent gets the same contract.
  PYTHONPATH="${ROOT}/src:${ROOT}" "${ROOT}/.venv/bin/python" \
    -m research.sweep.agent_task --wave "${WAVE}" --agent "${i}" \
    --out "${A}/AGENT_TASK.md" >/dev/null
done
echo "ready: ${WT}/a0 .. ${WT}/a$((N-1))   results -> ${RESULTS}"
echo "each worktree has: AGENT_TASK.md (your assignment), .venv, data/, tools/pit_membership.py"
