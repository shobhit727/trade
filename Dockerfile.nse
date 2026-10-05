# syntax=docker/dockerfile:1.7
# nsealgo — NSE NIFTY-50 systematic trading system.
# Runs the app in Docker; the image is the deployment unit.
ARG PYTHON_TAG=3.14-slim

FROM python:${PYTHON_TAG} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    NSE_DATA=/app/data/nse

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Requirements first so the layer caches across source changes.
# Only requirements/nse.txt — NOT prod.txt, which is the (much heavier) crypto stack.
COPY requirements /app/requirements
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements/nse.txt

# No `pip install -e .`: PYTHONPATH=/app/src is already set, and an editable
# install would drag in pyproject's `readme = "plan.md"` (plus the whole crypto
# dependency set) for no benefit.
COPY src /app/src

# Market data is mounted, not baked: it is large and changes independently.
RUN mkdir -p /app/data/nse /app/state-nse /app/reports \
    && chown -R 1000:1000 /app/data /app/state-nse /app/reports

USER 1000:1000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -m nsealgo.cli limits > /dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "nsealgo.cli"]
CMD ["--help"]