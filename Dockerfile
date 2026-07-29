FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ARG REQUIREMENTS=requirements/prod.txt
COPY requirements /app/requirements
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/${REQUIREMENTS}

COPY . /app

FROM base AS test
ARG REQUIREMENTS=requirements/test.txt
CMD ["pytest", "-q", "tests/unit/test_core_foundation.py"]

FROM base AS production
CMD ["python", "-m", "cryptobot.cli.main", "paper"]
