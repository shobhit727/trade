# syntax=docker/dockerfile:1.7
ARG PYTHON_TAG=3.14-slim

FROM python:${PYTHON_TAG} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        gcc \
        g++ \
        libgomp1 \
        tini \
    && rm -rf /var/lib/apt/lists/*

ARG REQUIREMENTS=requirements/prod.txt
COPY requirements /app/requirements
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/${REQUIREMENTS}

COPY . /app

ARG GIT_SHA=dev
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="cryptobot" \
      org.opencontainers.image.description="Elite Quantitative Trading System" \
      org.opencontainers.image.source="https://github.com/shobhit727/trade" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

FROM base AS production
USER 1000:1000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()" || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "cryptobot.cli.main", "paper"]

FROM base AS test
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["pytest", "-q", "tests"]
