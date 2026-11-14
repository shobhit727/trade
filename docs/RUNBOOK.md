# Runbook

This repo has two active execution surfaces that must both be understood correctly:

- `src/cryptobot/` is the shared trading framework and generic CLI.
- `src/nsealgo/` is the active NSE NIFTY-50 research package and the current deploy gate.

## 1. Working rules

- Treat `GOAL.md` as the binding specification for the NSE mission.
- Use the host venv for tests and research iteration.
- Use Docker for the app/runtime path, not as the primary test environment.
- Do not deploy capital until the gates in `GOAL.md` pass.

## 2. Local environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
make install-test
```

## 3. Shared crypto CLI

The generic framework is exposed by the `cryptobot` entrypoint from `pyproject.toml` and implemented in `src/cryptobot/cli/main.py`.

```bash
cryptobot --help
cryptobot backtest --strategy trend_following --source synthetic --bars 200 --json
python -m cryptobot.cli.main backtest --strategy mean_reversion --bars 200 --json
```

This path supports synthetic/CSV/Parquet/Timescale backtests and the normal bot/serve lifecycle for the crypto stack.

## 4. NSE research CLI

The active mission is driven by `src/nsealgo/cli.py`.

```bash
python -m nsealgo.cli --help
python -m nsealgo.cli audit
python -m nsealgo.cli costs --json
python -m nsealgo.cli limits
python -m nsealgo.cli backtest --positions 22
python -m nsealgo.cli validate --folds 6
python -m nsealgo.cli paper --cycles 5
```

The `validate` command is the evidence-producing path required by the project.

## 5. NSE validation and audit flow

```bash
# data audit
.venv/bin/python research/audit_data.py

# walk-forward validation
.venv/bin/python -m nsealgo.cli validate --folds 6

# factor sweep
.venv/bin/python research/sweep.py --factor momentum
```

Results must be reported with the end date, the full Indian cost stack, and the engine provenance attached.

## 6. Docker workflow

```bash
# build and start the NSE stack
docker compose -f docker-compose.nse.yml up -d --build

# short paper session
docker compose -f docker-compose.nse.yml run --rm nsealgo paper --duration 1w
```

This is a dry-run/paper path, not a deployment path.

## 7. Repository map

```text
src/
├── cryptobot/    # shared backend and generic CLI
├── nsealgo/      # active NSE research CLI and validation engine
research/         # audits, sweeps, and analysis scripts
reports/          # validation reports and evidence
configs/          # config files
```

## 8. Key references

- `GOAL.md` — binding NSS mission and no-go rules
- `AGENTS.md` — repo-level working conventions
- `src/cryptobot/cli/main.py` — generic bot CLI
- `src/nsealgo/cli.py` — NSE CLI implementation
- `reports/VALIDATION_v1.md` — current validation status and caveats

## 9. Troubleshooting

```bash
# print current provenance if you need to validate the environment
.venv/bin/python -c 'from nsealgo.provenance import provenance; print(provenance())'

# confirm repo state before changing strategy
git status --short
```

If the issue is in the research pipeline, start from the audit script and the latest validation report before changing factor logic or risk assumptions.
