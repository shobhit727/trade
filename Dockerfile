# syntax=docker/dockerfile:1.7
ARG PYTHON_TAG=3.13-slim
ARG PYTHON_VER=${PYTHON_TAG%-*}

FROM python:${PYTHON_TAG} AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements /app/requirements
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements/prod.txt

FROM python:${PYTHON_TAG} AS base

ARG PYTHON_TAG=3.13-slim
ARG PYTHON_VER=${PYTHON_TAG%-*}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python${PYTHON_VER}/site-packages /usr/local/lib/python${PYTHON_VER}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ARG REQUIREMENTS=requirements/test.txt
COPY requirements /app/requirements
RUN python -m pip install --no-cache-dir -r /app/${REQUIREMENTS}

COPY . /app
RUN pip install --no-cache-dir -e .

ARG GIT_SHA=dev
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="cryptobot" \
      org.opencontainers.image.description="Elite Quantitative Trading System" \
      org.opencontainers.image.source="https://github.com/shobhit727/trade" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

FROM base AS production
# Runtime-writable dirs for the non-root user (SQLite db + bot state files).
RUN mkdir -p /app/data /app/state && chown -R 1000:1000 /app/data /app/state
USER 1000:1000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()" || exit 1
ENTRYPOINT ["python", "-m", "cryptobot.cli.main"]
CMD ["bot", "--host=0.0.0.0", "--port=8080"]

FROM base AS test
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q", "tests"]
