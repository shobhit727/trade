# Cryptobot — Command Cheat Sheet

## Setup / Install

```bash
# Install project (from repo root)
pip install -e . --break-system-packages

# Install deps (Makefile)
make install            # production deps only
make install-test       # test + dev deps (includes numpy/pandas)

# If pytest/ruff not on PATH (installed to ~/.local/bin):
python -m pytest ...
# or add to PATH: export PATH="$HOME/.local/bin:$PATH"
```

## Backtest — Synthetic Data

```bash
# Basic (default: 200 synthetic bars)
python -m cryptobot.cli.main backtest --strategy trend_following

# More bars, JSON output
python -m cryptobot.cli.main backtest --strategy mean_reversion --bars 500 --json

# Programmatic (2000 bars, custom size)
python - <<'EOF'
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from cryptobot.backtest.runner import generate_synthetic_ohlcv, run_backtest
from cryptobot.strategies.trend_following import TrendFollowingConfig, TrendFollowingStrategy

async def main():
    bars = generate_synthetic_ohlcv(
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        n_bars=2000, freq_minutes=5, start_price=60000.0,
        drift=0.0005, vol=0.01, seed=42,
    )
    strat = TrendFollowingStrategy(TrendFollowingConfig(quantity=Decimal("0.05")))
    r = await run_backtest(bars, strategy=strat, initial_capital=Decimal("10000"))
    print(f"trades={r.n_trades} equity={r.final_equity} return={r.total_return*100:.2f}%")

asyncio.run(main())
EOF
```

> Note: `--bars` > 200 has no effect on synthetic data (hardcoded in `load_bars`).
> Default strategy quantity is 1 BTC; risk limits cap orders at $10k notional — use a small quantity (e.g. 0.05).

## Backtest — Real Historical Data

### Download from Binance (free, no API key)

```bash
mkdir -p data
python - <<'EOF'
import json, urllib.request
import pandas as pd

url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=1000"
rows = json.load(urllib.request.urlopen(url))
df = pd.DataFrame(rows, columns=["ts","open","high","low","close","vol","close_time",
                                 "qv","n","tbb","tbq","ig"])[["ts","open","high","low","close","vol"]]
df.to_csv("data/btcusdt_1h.csv", index=False)
print("saved", len(df), "bars")
EOF
```

- CSV columns required: `timestamp, open, high, low, close, volume`
- Bulk files: `https://data.binance.vision/?prefix=data/spot/monthly/klines/BTCUSDT/1h/`
- Loop with `startTime` param to download more than 1000 bars per request

### Run with CSV / Parquet

```bash
python -m cryptobot.cli.main backtest --strategy trend_following \
  --source csv --path data/btcusdt_1h.csv

python -m cryptobot.cli.main backtest --strategy mean_reversion \
  --source parquet --path data/btcusdt.parquet --json
```

> `timescale` source is documented but not implemented in `load_bars`.

## Backtest — Docker

```bash
# Build + run (starts timescaledb + redis)
docker compose --profile backtest run --rm cryptobot-backtest \
  python -m cryptobot.cli.main backtest --strategy trend_following --bars 500

# Docker build (targets)
docker build --target test --build-arg REQUIREMENTS=requirements/test.txt -t cryptobot:test .
docker build --target production -t ghcr.io/shobhit727/trade:latest .

# Multi-arch
docker buildx build --platform linux/amd64,linux/arm64 --target production --push \
  -t ghcr.io/shobhit727/trade:latest .
```

> If docker gives `permission denied`, you're not in the docker group: `newgrp docker` or re-login.

## Tests & Lint

```bash
python -m pytest tests/unit -q --tb=short        # all unit tests
python -m pytest tests/unit/test_backtest_runner.py -v   # single file
python -m pytest tests/unit -m "not integration" -q

# Lint (ruff)
python -m ruff check src tests                   # if ruff not on PATH
ruff check --fix src tests                       # auto-fix

# Rust workspace
cargo fmt --check && cargo clippy -D warnings && cargo test --workspace

# Makefile shortcuts
make test
make lint
```

## Other CLI Subcommands

```bash
python -m cryptobot.cli.main mm            # market making simulation
python -m cryptobot.cli.main ml            # ML predict
python -m cryptobot.cli.main serve         # run bot server
python -m cryptobot.cli.main bot           # run bot
python -m cryptobot.cli.main validate      # walk-forward validation
python -m cryptobot.cli.main paper         # paper trading
```

## Git

```bash
git status                      # what changed
git diff                        # review changes
git log --oneline -5            # recent commits

git add <files>                 # stage (exclude runtime state like cryptobot.db)
git commit -m "message"
git push origin main            # push

git checkout -- cryptobot.db    # discard runtime DB changes
```

> Don't commit `cryptobot.db` — it's local runtime state.

## Useful Files

| File | Purpose |
|------|---------|
| `BACKTEST_GUIDE.md` | Full backtest docs |
| `AGENTS.md` | Repo conventions, CI order, gotchas |
| `plan.md`, `CODEBASE.md` | Architecture |
| `PROJECT_MEMORY/` | Design decisions, config reference |
| `docs/RUNBOOK.md` | Ops runbook |
