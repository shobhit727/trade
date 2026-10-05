# Cryptobot Runbook

> How to run this trading bot with Docker Compose. Keep this file next to `docker-compose.yml`.

## 1. Prerequisites

You need only three things on your machine:

| Tool | Version | Why |
|------|---------|-----|
| Docker Engine | 24.0+ | Builds and runs containers |
| Docker Compose v2 | 2.20+ | `docker compose` (not `docker-compose`) |
| Bash or PowerShell | n/a | Running the commands below |

Optional:

- Git (only if you clone from GitHub)
- A Binance Testnet account: https://testnet.binance.vision (live trading keys, if you ever turn `EXECUTION_MODE=live` on)

Verify:

```bash
docker --version
docker compose version
```

Both must print non-error output.

> **Apple Silicon note.** Compose profiles use `linux/amd64` images. Apple Silicon will work via emulation but is slower. The multi-arch `Dockerfile` can also publish `linux/arm64` images; see §6.

## 2. Clone the repo

```bash
git clone git@github.com:shobhit727/trade.git cryptobot
cd cryptobot
```

If you only have HTTPS access:

```bash
git clone https://github.com/shobhit727/trade.git cryptobot
```

## 3. File layout that matters for Compose

| File | What it is |
|------|-----------|
| `docker-compose.yml` | Root compose file. Profiles: `paper`, `backtest`, `test`, `tracing`. |
| `Dockerfile` | Multi-stage (`base`, `test`, `production`). Uses `python:3.14-slim`. |
| `.dockerignore` | Keeps the build context small. |
| `configs/base.yaml` | Default configuration (Pydantic settings). |
| `requirements/prod.txt` | Runtime deps. |
| `requirements/test.txt` | Test deps (pytest, pytest-asyncio, etc.). |
| `.env.example` (optional) | If you want to set env vars; see §4. |
| `compose/docker-compose.yml` | ⚠️ Legacy second compose file — currently broken (nonexistent Dockerfile path, invalid CLI flag, wrong migrations path; #23). The root file is the source of truth. |

## 4. Environment variables

Compose reads secrets from your shell environment. Set them inline or in a `.env` file next to `docker-compose.yml`:

```bash
# Required only if you actually trade / connect to Binance
export BINANCE_API_KEY="your-testnet-key"
export BINANCE_API_SECRET="your-testnet-secret"

# Optional alerting (Telegram / Discord / email)
export MONITORING_TELEGRAM_BOT_TOKEN=""
export MONITORING_TELEGRAM_CHAT_ID=""
export MONITORING_DISCORD_WEBHOOK=""
# NOTE (2026-08-22): email alerting is NOT configurable yet — MonitoringSettings lacks the
# email_* fields (#29). The vars below are placeholders until that lands; use the
# MONITORING_EMAIL_* prefix if you experiment.
export EMAIL_SMTP_HOST=""
export EMAIL_SMTP_PORT=""
export EMAIL_USERNAME=""
export EMAIL_PASSWORD=""
export EMAIL_FROM=""
export EMAIL_TO=""

# Database (only used when running the full stack)
export DB_PASSWORD="cryptobot"
```

The compose file uses `:-` defaults so missing vars are not errors. The full stack logs warnings when `BINANCE_API_KEY` is unset; that's expected for paper-only runs.

## 5. Profiles

| Profile | What it brings up | Use it when |
|---------|-------------------|-------------|
| (default) | TimescaleDB + Redis + Prometheus + Alertmanager + Grafana + Loki + Promtail + nginx + `cryptobot` paper | Running the full observability stack locally |
| `test` | just `cryptobot-test` | Running the smoke tests in an isolated container |
| `backtest` | TimescaleDB + Redis + `cryptobot-backtest` | Heavy compute for a long historical run |
| `paper` | TimescaleDB + Redis + `cryptobot-paper` (debug log level) | Trading in paper mode with logging on |
| `tracing` (in `compose/docker-compose.yml`) | Jaeger all-in-one | Adding distributed tracing |

Profiles are combined with `--profile`. Default services always run unless excluded.

Validate before starting:

```bash
docker compose config --quiet
docker compose --profile test config --quiet
docker compose --profile backtest config --quiet
```

Both must exit 0 with no output.

## 6. Common commands

### Run the test suite (recommended first step)

```bash
docker compose --profile test build cryptobot-test
docker compose --profile test run --rm cryptobot-test
```

Equivalent one-shot:

```bash
docker compose --profile test run --rm --build cryptobot-test
```

You should see pytest pass (700+ tests as of 2026-08-22) and exit 0.

### Start the full stack (paper trading + observability)

```bash
docker compose up -d cryptobot-paper
```

This brings up:
- `cryptobot-paper` on `http://localhost:8080` (health endpoint — read §10).
- Prometheus on `http://localhost:9090`.
- Grafana on `http://localhost:3000` (default `admin/admin`).
- Alertmanager on `http://localhost:9093`.
- Loki on `http://localhost:3100`.

Tail logs:

```bash
docker compose logs -f cryptobot-paper
```

Stop:

```bash
docker compose down
```

Reset state:

```bash
docker compose down -v
```

### Run a backtest from the CLI

After running the test profile once (so the test image is built locally), you can also run the same image as a CLI:

```bash
docker compose --profile test run --rm cryptobot-test \
  python -m cryptobot.cli.main backtest \
  --strategy trend_following --bars 200 --json
```

The CLI sources stay `synthetic` by default. To plug in real data:

```bash
docker compose --profile test run --rm \
  -v "$PWD/data:/app/data" \
  cryptobot-test \
  python -m cryptobot.cli.main backtest \
  --strategy mean_reversion --source csv --path /app/data/ohlcv.csv
```

### Multi-arch build (linux/amd64, linux/arm64)

```bash
docker buildx create --name cryptobot --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --target production \
  --tag ghcr.io/<you>/trade:latest \
  --build-arg REQUIREMENTS=requirements/prod.txt \
  --push .
```

Or use the helper:

```bash
REGISTRY=ghcr.io/<you>/trade TAG=dev ./scripts/build_multiarch.sh
```

Requires `setup-qemu-action` registration on Linux runners, or Docker Desktop with `docker-container` driver on macOS.

## 7. Outputs and ports

| Service | Host port | Container port | Notes |
|---------|-----------|----------------|-------|
| cryptobot-paper / cryptobot | 8080 | 8080 | Health/metrics endpoint |
| prometheus | 9090 | 9090 | `/metrics` scrape target |
| alertmanager | 9093 | 9093 | |
| grafana | 3000 | 3000 | Login `admin/admin` |
| loki | 3100 | 3100 | |
| timescaledb | 5432 | 5432 | Postgres-compatible |
| redis | 6379 | 6379 | |
| nginx | 80, 443 | 80, 443 | Reverse proxy for grafana/prometheus |

`cryptobot-test` and `cryptobot-backtest` expose **no host ports** by design — they run, finish, and exit.

## 8. Logs

```bash
# All services, follow
docker compose logs -f

# One service
docker compose logs -f cryptobot-paper

# Last 200 lines
docker compose logs --tail=200 cryptobot-paper

# Since a timestamp
docker compose logs --since="2024-01-01T00:00:00" cryptobot-paper
```

`cryptobot-paper` is configured with `APP_LOG_LEVEL=DEBUG` for easier inspection. Production builds (the `production` image target) default to `INFO`.

## 9. Configuration knobs

The bot reads `configs/base.yaml`. Override anything via env (prefixes: `APP_`, `RISK_`, `EXECUTION_`, `BINANCE_`, `MARKET_DATA_`, `MONITORING_`, `DB_`, `ML_`, `BACKTEST_`, `EXTERNAL_`, `TIMEOUT_`, `SERVER_`).

> Note (2026-08-31): The configuration system was extended with three new sections:
> - `EXTERNAL_*`: External service URLs (Kite, Yahoo Finance, Binance prod/futures, Telegram, PagerDuty, WhatsApp)
> - `TIMEOUT_*`: HTTP timeouts (default=20s, long=30s, short=10s, strategy=0.5s, stop=30s, SMTP=30s)
> - `SERVER_*`: Bind host/ports (127.0.0.1:8080, NSE basket=8084, NSE powerhour=8085)

> Note (2026-08-22): large blocks of base.yaml (`strategies.*`, `ml.models.*`) are parsed but never
> read by `Settings` — strategy/model params come from code defaults. See issue #52.

Examples:

```bash
# Tighter risk
RISK_MAX_DAILY_LOSS_PCT=0.02 RISK_KILL_SWITCH_DAILY_LOSS_PCT=0.05 \
  docker compose up -d cryptobot-paper

# Live mode (DANGER — only after Binance adapter is wired and tested)
EXECUTION_MODE=binance BINANCE_TESTNET=false \
  BINANCE_API_KEY=$BINANCE_API_KEY BINANCE_API_SECRET=$BINANCE_API_SECRET \
  docker compose up -d cryptobot

# Custom timeouts
TIMEOUT_HTTP_DEFAULT_TIMEOUT=30 TIMEOUT_SMTP_TIMEOUT=60 \
  docker compose up -d cryptobot-paper
```

The YAML structure (`exchanges.binance`, `monitoring.alerts.*`) is flattened into the Settings namespace by `Settings.from_yaml_safe` in `src/cryptobot/config.py`.

### 9.1 WhatsApp alerting (new in v0.3.0)

```yaml
# configs/base.yaml
alerts:
  whatsapp_enabled: false
  whatsapp_token: "${WHATSAPP_TOKEN}"
  whatsapp_phone_id: "${WHATSAPP_PHONE_ID}"
  whatsapp_to: []
```

```bash
export MONITORING_WHATSAPP_ENABLED=true
export WHATSAPP_TOKEN="your-token"
export WHATSAPP_PHONE_ID="your-phone-id"
export WHATSAPP_TO="+919999999999,+918888888888"
```

## 10. Health checks and `/health` endpoint

The Dockerfile configures:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"
```

The endpoint is served by `src/cryptobot/utils/health_server.py` (stdlib ThreadingHTTPServer,
`/health` + `/metrics` + `/dashboard`). `cryptobot bot` starts it; `cryptobot serve` runs it standalone.

> ✅ **2026-08-31**: Production image starts correctly (issue #22 fixed in `Dockerfile`).

### 10.1 Dashboard (v0.3.0+)

The `/dashboard` endpoint renders a read-only family dashboard with:

- **Equity card** — current equity, today's P&L, peak equity, max drawdown
- **Price & trades chart** — inline SVG with BUY/SELL markers
- **Equity curve** — sparkline of historical equity
- **Trading stats** — bars seen/fed, orders, fills, rejects, open positions
- **Paper gate progress** — dynamic bar (blue→amber→green) with 60-day target
- **Global fund** — balance + frozen state pill
- **Circuit breaker** — TRIPPED/armed status with reason
- **India VDA tax** — tax breakdown table
- **Live trade tape** — auto-refreshes every 5s
- **Strategy sweep** — backtest all registered strategies, drill into trades

Auto-refreshes every 30s via meta tag; live trades poll every 5s.

When the container runs:

```bash
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/metrics | head
open http://localhost:8080/dashboard  # browser
```

If you override the entrypoint, keep the healthcheck in mind:

```bash
# Check the process manually if needed
docker compose exec cryptobot-paper ps -ef | grep cryptobot
```

## 11. Troubleshooting

### "Cannot connect to the Docker daemon"

```bash
# macOS / Windows: start Docker Desktop
# Linux:
sudo systemctl start docker
sudo usermod -aG docker $USER    # log out, log in
```

### `qemu: process terminated unexpectedly` or similar host crash

Known intermittent issue with Docker Desktop on certain Apple Silicon builds. Restart Docker Desktop. CI workflows use buildx + QEMU explicitly to avoid this:

```bash
docker buildx create --use
```

### `cryptobot-paper` is `Restarting` or unhealthy

```bash
docker compose logs cryptobot-paper | tail -100
docker compose exec cryptobot-paper python -c "from cryptobot.config import settings; print(settings.exchange.symbols)"
```

Most common root causes:
- Missing `_sqlite3` (will log a warning; persistence silently disabled — see `PROJECT_MEMORY/13_Bug_Tracker.md` `B024`).
- `configs/base.yaml` mismatch — fixed in `Settings.from_yaml_safe` (`08_Config_Reference.md`).
- Risk rejection — `cryptobot kill switch` style logs from `risk.manager.RiskManager.check_order`.

### Tests pass locally, fail in Docker

The test target installs `requirements/test.txt` plus an extra `pip install numpy pandas` step in CI. Locally that's your dev install. In Docker it's pulled fresh. If a test fails, rebuild:

```bash
docker compose --profile test build --no-cache cryptobot-test
```

### "Port already in use"

Stop the conflicting process or change `ports:` mapping in `docker-compose.yml`. 5432, 6379, 9090, 9093, 3000, 3100, 8080 are the common offenders.

### "Network cryptobot-network not found"

Compose creates the network on first `up`. If you see this error, run any service first:

```bash
docker compose up -d timescaledb redis
docker compose up -d cryptobot-paper
```

### `BinanceVenue` rejects orders

Expected when `BINANCE_API_KEY` is empty. Either set real testnet keys or set `EXECUTION_MODE=paper` to use `SimulatedVenue`:

```bash
EXECUTION_MODE=paper docker compose up -d cryptobot-paper
```

### "Ledger corrupt" on startup (NSE basket / tax engine)

**Symptom:** `ERROR: sell X SYMBOL without open lots — ledger corrupt` on container restart.

**Root cause:** State file restored positions but tax ledger lots were missing (version mismatch or corruption).

**Fixed in v0.3.0:** `BasketState.from_dict()` now reconciles missing tax lots from trade history on load.

```bash
# Verify fix
docker compose restart nse-basket
docker logs cryptobot-nse-basket | grep -i "ledger corrupt"
# Should show no errors; rebalance should complete
```

If you see the error on an older image, rebuild:

```bash
docker compose build nse-basket
docker compose up -d nse-basket
```

### Wipe persistent state

```bash
docker compose down -v
```

Removes named volumes (timescaledb_data, redis_data, prometheus_data, etc.).

## 12. Kubernetes

`deploy/k8s/` has manifests: namespace, configmap, secret, pvc, deployment, service, hpa, kustomization overlay.

> ⚠️ **2026-08-22**: the manifests do not deploy cleanly as shipped — the Deployment runs a one-shot
> `paper` command so probes never pass, Service/HPA are duplicated (kustomize fails), and a mount
> uses Compose-style `:ro`. See issue #28 before using.

Apply:

```bash
kubectl apply -k deploy/k8s/
```

Inspect:

```bash
kubectl -n cryptobot get pods
kubectl -n cryptobot logs -f deploy/cryptobot
```

The `cryptobot` service exposes port 8080 via ClusterIP; add an Ingress to expose publicly.

Secrets live in `deploy/k8s/02-secret.yaml` with `REPLACE_ME` placeholders. Replace them with `kubectl -n cryptobot create secret` or sealed-secrets.

The deployment needs an image registry (default: `ghcr.io/shobhit727/trade:latest`). Push your build first:

```bash
docker push ghcr.io/shobhit727/trade:latest
kubectl -n cryptobot set image deploy/cryptobot cryptobot=ghcr.io/<you>/trade:$GIT_SHA
```

## 13. CI

`.github/workflows/ci.yml` runs on every push/PR:
- ruff + pyflakes lint
- pytest with coverage
- docker build of `test` target
- docker compose config validation (default + `test` profiles)
- docker buildx multi-arch matrix (linux/amd64 + linux/arm64) on `main`

`.github/workflows/release.yml` runs on `v*.*.*` tags:
- Multi-arch publish (linux/amd64 + linux/arm64) to GHCR
- SBOM + provenance
- Manifest list at `ghcr.io/<you>/trade:latest`

To cut a release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## 14. Where to look next

- `PROJECT_MEMORY/12_Feature_Status.md` — module-by-module status.
- `PROJECT_MEMORY/13_Bug_Tracker.md` — known issues, indexed against GitHub #20–#53 (2026-08-22 audit).
- `PROJECT_MEMORY/08_Config_Reference.md` — Settings field reference.
- `plan.md` — phases and remaining work.
- `src/cryptobot/backtest/runner.py` + `runner.run_backtest` — backtest API.
- `src/cryptobot/execution/router.py` — SOR.

---

## 12. Seed Phase operations (2026-08-22)

Full plan: `PROJECT_MEMORY/28_Seed_Phase_Plan.md`.

### 12.1 Paper trading (owner's PC)

```bash
# start the bot (paper is the default and the gate phase)
python3 -m cryptobot.cli.main bot --strategy dual_ma --symbol BTCUSDT \
    --timeframe 1d --mode paper --warmup 300 --profile realistic

# what to watch
curl -s localhost:8080/health     | jq .          # machine-readable state
open http://localhost:8080/dashboard              # read-only family view
```

The process automatically: harvests 10% of realized PnL into the global fund
every 8h, records fills into the VDA tax ledger, snapshots equity daily into
the 60-day paper gate, and places exchange-native protective stops on live venues.

### 12.2 State files (back these up)

| file | contents |
|---|---|
| `state/global_fund.json` | fund balance, freeze flag, full history |
| `state/paper_gate.json` | daily equity snapshots, gate status/extensions |
| `state/tax_engine.json` | FIFO lots + disposals (restart-safe) |
| `state/breaker.json` | breaker trip state (persists across restarts) |
| `state/audit_log.jsonl` | every owner action |

### 12.3 Breaker

Trips at −25% from peak equity: entries halt, positions close profit-first,
the fund freezes. It stays tripped across restarts until:

```bash
python3 -m cryptobot.cli.main breaker-reset   # logged to audit_log
```

### 12.4 Gate → live

```bash
python3 -m cryptobot.cli.main bot --help      # see --mode live
```
`--mode live` refuses with a reason until the gate passes (60 days net-positive,
Sharpe ≥ 1, rejects ≤ 5%, zero breaker trips; failure auto-extends ×30d, max 2).

### 12.5 Taxes & reporting

```bash
python3 -m cryptobot.cli.main tax --export-csv schedule_vda_fy26.csv
```

Monthly family PDF:
```python
from cryptobot.monitoring.monthly_report import build_monthly_report
build_monthly_report("reports/2026-08.pdf", "August 2026", stats, history, tax)
```
(`stats` = `/health` snapshot; `history` = gate snapshots.)

### 12.6 Alerts env vars

```bash
# email digest (Gmail app-password)
EMAIL_SMTP_USER=you@gmail.com EMAIL_SMTP_PASS=xxxx EMAIL_TO=family@gmail.com

# WhatsApp (Meta Business Cloud API, dedicated number)
WHATSAPP_TOKEN=xxx WHATSAPP_PHONE_ID=123 WHATSAPP_TO=919999999999
```

### 12.7 Live phase on a VPS (~₹500/mo)

```bash
# on the box
git clone git@github.com:shobhit727/trade.git && cd trade
docker build --target production --build-arg PYTHON_TAG=3.14-slim \
    -t cryptobot:seed .
docker run -d --name cryptobot --restart unless-stopped \
    -v $(pwd)/state:/app/state \
    --env-file .env \
    cryptobot:seed cryptobot.cli.main bot \
        --strategy dual_ma --symbol BTCUSDT --timeframe 1d --mode live
```

- `-v state:/app/state` keeps fund/gate/tax/breaker state outside the container.
- `--restart unless-stopped` survives reboots; protective stops cover the gap.
- NOTE: the image ENTRYPOINT is `python -m`, so container args start at the
  module path (`cryptobot.cli.main ...`) — do NOT prefix `python3 -m`.
- If the port is taken the bot now fails fast with a clear message:
  "health server cannot bind ... use --port". Pick a free port and remap.
- Backup cron: `tar czf backup_$(date +%F).tgz state/` off-box weekly.

### 12.8 The 60-day gate run (started 2026-08-23)

Two processes, one per validated assignment:

| service | container | strategy | dashboard |
|---|---|---|---|
| `cryptobot` | cryptobot-app | dual_ma(5,50) BTCUSDT 1d | http://localhost:8081/dashboard |
| `cryptobot-eth` | cryptobot-eth | time_series(60, 0.05) ETHUSDT 1d | http://localhost:8082/dashboard |

Both seed equity 10k, paper mode, gate collecting (x/60). State lives in
`./state/` (BTC) and `./state-eth/` (ETH). Daily snapshots land at first bar
after UTC midnight; the gate auto-evaluates at day 60.

Operations:
```bash
docker compose ps                      # both healthy?
docker compose logs -f cryptobot       # BTC trades: grep TRADE
docker compose restart cryptobot-eth   # single-process restart
```

Gate pass criteria (auto): net-positive, Sharpe >= 1, rejects <= 5%, zero
breaker trips. Fail -> auto-extend 30d (max 2), then review.

### 12.8b Multi-algo mode (one process, N strategies)

```bash
BOT_ALGOS='[
  {"name":"dual_ma","params":{"fast":5,"slow":50},"weight":0.6},
  {"name":"time_series","params":{"period":60,"threshold":0.05},"weight":0.4}
]' docker compose up -d --no-deps cryptobot
```

Each algo trades its own equity slice; fills are tagged per algo on the tape.
Per-algo weights normalize to 1.0.

## 12.9 Strategy sweep from the dashboard

The dashboard has a **Strategy sweep** panel: pick symbol/timeframe/capital,
click *Run all N algorithms*. It backtests every registered strategy on
`data/{symbol}_{timeframe}.csv` (synthetic fallback if missing) and streams a
Sharpe-ranked table.

API equivalents:

```bash
curl -X POST "localhost:8081/api/backtest/start?symbol=BTCUSDT&timeframe=1d&capital=10000"
curl localhost:8081/api/backtest/status | jq '.results[:5]'
```

One sweep at a time; per-algorithm errors are captured in the note column.
