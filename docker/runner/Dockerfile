# Runs saved Pytest suites on an app's Docker network (FR-06, NFR-05). It has no AI key.
FROM python:3.11-slim

# psql restores seed data from inside the network.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /apiguard
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . "pytest>=8,<9"

WORKDIR /work
ENV PYTHONUNBUFFERED=1
