# Quick Start

This repo has two real execution layers, and the docs should reflect both of them:

- the generic `cryptobot` CLI for the trading framework
- the active `nsealgo` NSE research workflow

## 1. Set up the environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
make install-test
```

## 2. Run the checks

```bash
# unit tests
.venv/bin/python -m pytest tests/unit -q

# lint
.venv/bin/ruff check src tests
```

## 3. Shared framework command

```bash
python -m cryptobot.cli.main backtest --strategy trend_following --source synthetic --bars 200 --json
```

## 4. NSE validation flow

```bash
# audit the data source
.venv/bin/python research/audit_data.py

# run the real validation entrypoint used by the NSE work
.venv/bin/python -m nsealgo.cli validate --folds 6
```

This is the main evidence path for the current research mission.

## 5. Paper path for the active NSE mission

```bash
docker compose -f docker-compose.nse.yml up -d --build
docker compose -f docker-compose.nse.yml run --rm nsealgo paper --duration 1w
```

## 6. Key references

- `GOAL.md` — hard constraints and current validation rules
- `AGENTS.md` — repo operating standards
- `src/cryptobot/cli/main.py` — generic CLI implementation
- `src/nsealgo/cli.py` — NSE CLI implementation
- `reports/VALIDATION_v1.md` — current validation evidence and caveats

> The default policy remains research-only. No capital deployment should occur until the mission gates in `GOAL.md` are met.
