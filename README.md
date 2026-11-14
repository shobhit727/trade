# trade

This repository contains both the shared quantitative trading backbone and the current NSE research mission.

## Repo shape

- `src/cryptobot/` — the generic trading system: CLI, backtests, execution, risk, monitoring, and shared Python/Rust framework code.
- `src/nsealgo/` — the active NSE NIFTY-50 systematic research package with walk-forward validation and live/paper simulation logic.

The current active mission is the NSE work under `GOAL.md`. That mission is still research-only; no deployment is allowed until the gating rules are satisfied.

## Actual CLI entrypoints in code

The code exposes two real command surfaces:

1. `cryptobot` CLI from `pyproject.toml` and `src/cryptobot/cli/main.py`
2. `nsealgo` CLI from `src/nsealgo/cli.py`

Examples from the code:

```bash
# installed script
cryptobot --help
cryptobot backtest --strategy trend_following --source synthetic --bars 200 --json

# module entrypoint
python -m cryptobot.cli.main --help
python -m nsealgo.cli --help
python -m nsealgo.cli validate --folds 6
python -m nsealgo.cli paper --cycles 5
python -m nsealgo.cli limits
```

## Working setup

Use the host venv for Python work and Docker only for the app/runtime path.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
make install-test

# unit tests
.venv/bin/python -m pytest tests/unit -q

# lint
.venv/bin/ruff check src tests
```

## Core commands

```bash
# shared crypto stack
python -m cryptobot.cli.main backtest --strategy trend_following --source synthetic --bars 200 --json

# active NSE strategy workflow
python -m nsealgo.cli audit
python -m nsealgo.cli costs --json
python -m nsealgo.cli limits
python -m nsealgo.cli backtest --positions 22
python -m nsealgo.cli validate --folds 6
python -m nsealgo.cli paper --cycles 5
```

## NSE mission status

The governing document is `GOAL.md`. The current state is intentionally conservative:

- daily-bar research only
- full Indian cost stack required
- walk-forward validation as the evidence standard
- no capital deployment until the §5 gates pass
- current recorded result is research-only band D, not a deployable strategy

## Docker and research workflow

```bash
# start the NSE stack
docker compose -f docker-compose.nse.yml up -d --build

# run a short paper session
docker compose -f docker-compose.nse.yml run --rm nsealgo paper --duration 1w

# audit the data source used by the NSE research pipeline
.venv/bin/python research/audit_data.py
```

## Important references

| File | Purpose |
|------|---------|
| `GOAL.md` | Binding mission, risk limits, and no-go gates |
| `AGENTS.md` | Repo working rules |
| `src/cryptobot/cli/main.py` | Shared crypto CLI implementation |
| `src/nsealgo/cli.py` | NSE research CLI implementation |
| `reports/VALIDATION_v1.md` | Current validation narrative and evidence |
| `docs/RUNBOOK.md` | Local operating guide |

## Current caution

This is not a single “bot is ready” repo narrative. It is a combined system: a reusable trading framework and an active NSE research programme. The safer and more accurate description is that the repo contains both a production-like framework and a research-only deployment gate.
