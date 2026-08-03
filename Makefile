.PHONY: help install install-test test lint cargo-lint cargo-test cargo-build compose-build compose-test compose-shell ship ship-multiarch clean

PY ?= python3.13
PIP ?= $(PY) -m pip
DOCKER ?= docker
CARGO ?= cargo

help:
	@echo "cryptobot make targets"
	@echo "  make install      install production deps"
	@echo "  make install-test install test + dev deps"
	@echo "  make test         run pytest"
	@echo "  make lint         run ruff + pyflakes"
	@echo "  make cargo-lint   run cargo fmt + clippy"
	@echo "  make cargo-test   run cargo test"
	@echo "  make cargo-build  build all rust crates"
	@echo "  make compose-test run the test container"
	@echo "  make compose-shell drop into a test container"
	@echo "  make ship         build multi-arch manifest (requires buildx)"
	@echo "  make clean        remove pycache + test artifacts"

install:
	$(PIP) install -e .
	$(PIP) install -r requirements/prod.txt

install-test:
	$(PIP) install -e .
	$(PIP) install -r requirements/test.txt

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

cargo-lint:
	cd crates && $(CARGO) fmt --all -- --check
	cd crates && $(CARGO) clippy --workspace --all-targets -- -D warnings

cargo-test:
	cd crates && $(CARGO) test --workspace

cargo-build:
	cd crates && $(CARGO) build --workspace --release

compose-build:
	$(DOCKER) compose --profile test build cryptobot-test

compose-test:
	$(DOCKER) compose --profile test run --rm cryptobot-test

compose-shell:
	$(DOCKER) compose --profile test run --rm cryptobot-test bash

ship:
	./scripts/build_multiarch.sh

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	rm -rf .ruff_cache .mypy_cache .coverage htmlcov build dist *.egg-info
