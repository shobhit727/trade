# Docker & CI/CD

## Docker

### Dockerfile

```dockerfile
# Multi-stage build
# Base
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PIP_NO_CACHE_DIR=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl gcc g++ libgomp1 tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements /app/requirements
RUN pip install --upgrade pip setuptools wheel && pip install -r /app/requirements/prod.txt

COPY . /app
RUN pip install -e .

# Production
FROM base AS production
USER 1000:1000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()" || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "cryptobot.cli.main", "bot", "--host=0.0.0.0", "--port=8080"]

# Test
FROM base AS test
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["pytest", "-q", "tests"]
```

### Build

```bash
# Build test image
docker build --target test -t cryptobot:test .

# Build production image
docker build --target production -t ghcr.io/shobhit727/trade:latest .
```

### Multi-arch Build

```bash
# Create builder
docker buildx create --name cryptobot --use

# Build multi-arch
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --target production \
  --tag ghcr.io/shobhit727/trade:latest \
  --push .

# Or use script
./scripts/build_multiarch.sh
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: cryptobot
      POSTGRES_USER: cryptobot
      POSTGRES_PASSWORD: cryptobot
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    volumes:
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3000:3000"

  loki:
    image: grafana/loki
    ports:
      - "3100:3100"

  promtail:
    image: grafana/promtail
    volumes:
      - ./logs:/var/log
      - ./monitoring/promtail/config.yml:/etc/promtail/config.yml

  cryptobot:
    build:
      context: .
      target: production
    environment:
      - EXECUTION_MODE=paper
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
    depends_on:
      - timescaledb
      - redis
    ports:
      - "8080:8080"

  cryptobot-paper:
    build:
      context: .
      target: production
    environment:
      - EXECUTION_MODE=paper
    profiles:
      - paper
    depends_on:
      - timescaledb
      - redis

  cryptobot-backtest:
    build:
      context: .
      target: test
    command: pytest -q
    profiles:
      - backtest

profiles:
  paper:
    - cryptobot-paper
  backtest:
    - cryptobot-backtest

volumes:
  timescaledb_data:
```

### Run with Docker Compose

```bash
# Full stack
docker compose up -d

# Paper trading
docker compose --profile paper up -d

# Backtest
docker compose --profile backtest run --rm cryptobot-backtest

# Test only
docker compose run --rm cryptobot-test
```

## GitHub Actions CI

### Workflow Structure

```yaml
# .github/workflows/ci.yml
name: ci

"on":
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

env:
  PYTHON_TAG: "3.14-slim"
  CI_PYTHON: "3.13"
  REGISTRY_IMAGE: ghcr.io/${{ github.repository }}

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v5
        with:
          python-version: "${{ env.CI_PYTHON }}"
          cache: "pip"
      - run: |
          python -m pip install --upgrade pip
          pip install ruff pyflakes
      - run: ruff check src tests
      - run: pyflakes src tests

  cargo-lint:
    name: Rust lint (fmt + clippy)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - uses: dtolnay/rust-toolchain@stable
      - uses: Swatinem/rust-cache@v2
      - run: cargo fmt --all -- --check
      - run: cargo clippy --workspace --all-targets -- -D warnings

  cargo-test:
    name: Rust tests
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - uses: dtolnay/rust-toolchain@stable
      - uses: Swatinem/rust-cache@v2
      - run: cargo test --workspace

  unit:
    name: Unit tests (Python 3.13)
    runs-on: ubuntu-latest
    needs: [lint, cargo-lint, cargo-test]
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v5
        with:
          python-version: "${{ env.CI_PYTHON }}"
          cache: "pip"
      - run: |
          python -m pip install --upgrade pip
          pip install -r requirements/test.txt
          pip install -e .
      - run: pytest -q --tb=short --cov=cryptobot --cov-report=term-missing --timeout=60
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage
          path: .coverage
          retention-days: 14

  docker-test:
    name: Docker test image
    runs-on: ubuntu-latest
    needs: lint
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - run: |
          docker build \
            --target test \
            --build-arg PYTHON_TAG=${{ env.PYTHON_TAG }} \
            --build-arg REQUIREMENTS=requirements/test.txt \
            -t cryptobot:test .
      - run: docker run --rm cryptobot:test

  docker-build:
    name: Docker buildx (amd64 + arm64)
    runs-on: ubuntu-latest
    needs: [lint, unit, docker-test]
    if: github.event_name == 'push' || github.event_name == 'pull_request'
    timeout-minutes: 60
    permissions:
      contents: read
      packages: write
    strategy:
      fail-fast: false
      matrix:
        include: ${{ fromJSON(github.event_name == 'pull_request' && '[{"platform":"linux/amd64","tag_platform":"linux-amd64"}]' || '[{"platform":"linux/amd64","tag_platform":"linux-amd64"},{"platform":"linux/arm64","tag_platform":"linux-arm64"}]') }}
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-qemu-action@v3
        if: matrix.platform == 'linux/arm64'
        with:
          platforms: arm64
      - uses: docker/setup-buildx-action@v3
      - name: Login to GHCR
        if: github.event_name == 'push'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          target: production
          platforms: ${{ matrix.platform }}
          tags: |
            ${{ env.REGISTRY_IMAGE }}:${{ github.sha }}-${{ matrix.tag_platform }}
            ${{ env.REGISTRY_IMAGE }}:latest-${{ matrix.tag_platform }}
          build-args: |
            PYTHON_TAG=${{ env.PYTHON_TAG }}
            REQUIREMENTS=requirements/prod.txt
            GIT_SHA=${{ github.sha }}
            BUILD_DATE=${{ github.event.head_commit.timestamp }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          push: ${{ github.event_name == 'push' }}

  docker-manifest:
    name: Docker manifest (create multi-arch manifest)
    runs-on: ubuntu-latest
    needs: docker-build
    if: github.event_name == 'push'
    timeout-minutes: 15
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v6
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Create multi-arch manifest
        run: |
          docker buildx imagetools create \
            -t ${{ env.REGISTRY_IMAGE }}:${{ github.sha }} \
            -t ${{ env.REGISTRY_IMAGE }}:latest \
            ${{ env.REGISTRY_IMAGE }}:${{ github.sha }}-linux-amd64 \
            ${{ env.REGISTRY_IMAGE }}:${{ github.sha }}-linux-arm64

  compose-validate:
    name: Docker Compose config
    runs-on: ubuntu-latest
    needs: lint
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v6
      - run: docker compose config --quiet
      - run: docker compose --profile test config --quiet
```

### Key Fixes

| Issue | Fix |
|-------|-----|
| `replace()` not available in GH Actions | Use matrix `include` with `tag_platform` |
| arm64 image not pushed | `push: true` for all platforms |
| Manifest creation fails | Separate `docker-manifest` job with `needs: docker-build` |
| Rust cache portability | `.cargo/config.toml` must not set `-C target-cpu=native` (proc-macro SIGILL across runner CPUs); opt in via `CARGO_RUSTFLAGS` locally |
| PRs build amd64 only | Dynamic `fromJSON` matrix keyed on `github.event_name` |
| Node.js 20 deprecation | GitHub handles automatically |


## Release Workflow

```yaml
# .github/workflows/release.yml
name: release-multiarch

on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch:

env:
  REGISTRY_IMAGE: ghcr.io/${{ github.repository }}

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read
  packages: write

jobs:
  build:
    name: Build and push multi-arch images
    runs-on: ubuntu-latest
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-qemu-action@v3
        with:
          platforms: arm64
      - uses: docker/setup-buildx-action@v3
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Validate tag and extract version
        id: meta
        run: |
          if [[ ! "${GITHUB_REF}" == refs/tags/v* ]]; then
            echo "Error: This workflow only runs on version tags (refs/tags/v*)."
            exit 1
          fi
          VERSION=${GITHUB_REF#refs/tags/v}
          echo "VERSION=$VERSION" >> $GITHUB_OUTPUT
          echo "DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> $GITHUB_OUTPUT
      - name: Build, push and attest
        uses: docker/build-push-action@v5
        with:
          context: .
          target: production
          platforms: linux/amd64,linux/arm64
          tags: |
            ${{ env.REGISTRY_IMAGE }}:latest
            ${{ env.REGISTRY_IMAGE }}:${{ steps.meta.outputs.VERSION }}
            ${{ env.REGISTRY_IMAGE }}:${{ steps.meta.outputs.VERSION }}-multiarch
          build-args: |
            REQUIREMENTS=requirements/prod.txt
            GIT_SHA=${{ github.sha }}
            BUILD_DATE=${{ steps.meta.outputs.DATE }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          sbom: true
          provenance: true
          push: true
```


### Tagging

```bash
# Create release
git tag v0.1.0
git push origin v0.1.0
```

## Local Development

### Requirements

```bash
# Install dev dependencies
pip install -r requirements/test.txt
pip install -e .

# Or with uv (faster)
uv pip install -r requirements/test.txt
uv pip install -e .
```

### Run Tests

```bash
# All tests
pytest -q --tb=short --cov=cryptobot --cov-report=term-missing

# Specific test
pytest tests/unit/test_strategies_ml.py -v

# With timeout
pytest -q --timeout=60

# Parallel
pytest -n auto
```

### Linting

```bash
# Ruff
ruff check src tests
ruff format src tests

# Pyflakes
pyflakes src tests

# Rust
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

### Pre-commit

```bash
# Install
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

## VS Code

```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "ruff",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": "explicit",
    "source.fixAll.ruff": "explicit"
  },
  "rust-analyzer.enable": true,
  "docker.defaultRegistryPath": "ghcr.io/shobhit727"
}
```

### launch.json

```json
{
  "configurations": [
    {
      "name": "Python: Backtest",
      "type": "python",
      "request": "launch",
      "module": "cryptobot.cli.main",
      "args": ["backtest", "--strategy", "trend_following", "--bars", "500"],
      "console": "integratedTerminal",
      "justMyCode": true
    },
    {
      "name": "Python: Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["-v", "tests/unit/test_core_foundation.py"],
      "console": "integratedTerminal"
    }
  ]
}
```

## Environment Variables

```bash
# Copy example
cp .env.example .env

# Required
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# Optional
EXECUTION_MODE=paper          # paper, live, backtest
EXECUTION_VENUE=simulated     # simulated, binance
APP_LOG_LEVEL=INFO            # DEBUG, INFO, WARNING, ERROR
RISK_MAX_DAILY_LOSS_PCT=0.05
RISK_MAX_POSITION_USD=50000
```

### All Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXECUTION_MODE` | paper | paper, live, backtest |
| `EXECUTION_VENUE` | simulated | simulated, binance |
| `BINANCE_API_KEY` | - | Binance API key |
| `BINANCE_API_SECRET` | - | Binance API secret |
| `BINANCE_TESTNET` | true | Use testnet |
| `APP_LOG_LEVEL` | INFO | DEBUG, INFO, WARNING, ERROR |
| `RISK_MAX_POSITION_USD` | 50000 | Max position size |
| `RISK_MAX_DAILY_LOSS_PCT` | 0.05 | Daily loss limit |
| `RISK_MAX_CORRELATION` | 0.7 | Max correlation |
| `MARKET_DATA_SYMBOLS` | ["BTCUSDT"] | Subscribed symbols |
| `MARKET_DATA_TIMEFRAMES` | ["1m"] | Timeframes |
| `MONITORING_PROMETHEUS_PORT` | 9090 | Prometheus port |
| `DB_HOST` | timescaledb | DB host |
| `DB_PASSWORD` | cryptobot | DB password |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: cryptobot` | Run `pip install -e .` |
| `sqlite3` missing | Install `sqlite3` package |
| `ccxt` not installed | `pip install ccxt` |
| `prometheus_client` missing | `pip install prometheus-client` |
| Docker build fails | Check Dockerfile syntax, try `docker build --no-cache` |
| Tests hang | Increase timeout: `pytest --timeout=120` |
| ImportError | Check `PYTHONPATH=src` or `pip install -e .` |

## Files

- `Dockerfile` - Multi-stage build
- `docker-compose.yml` - Local development stack
- `.github/workflows/ci.yml` - CI pipeline
- `.github/workflows/release.yml` - Release pipeline
- `requirements/prod.txt` - Production dependencies
- `requirements/test.txt` - Test dependencies
- `pyproject.toml` - Package config
- `pyproject.toml` - Ruff config
- `Cargo.toml` - Rust workspace
- `.github/workflows/ci.yml` - CI pipeline
- `.github/workflows/release.yml` - Release pipeline