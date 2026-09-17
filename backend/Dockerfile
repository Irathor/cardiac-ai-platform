FROM python:3.12-slim

WORKDIR /srv

# libpq-dev/gcc needed to build psycopg's C extension if no wheel matches the arch.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY ml /ml

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# The ml/ package (biomarker math, see docs/architecture.md) is installed
# first from its sibling path so backend's own install can be satisfied by
# the -e ".[dev]" step below without needing a private package index.
RUN pip install --no-cache-dir -e /ml \
    && pip install --no-cache-dir -e ".[dev]"

# EPIC-6: also pre-creates the prometheus_client multiprocess mode
# directory owned by appuser before it becomes a named-volume mount point
# (docker-compose.yml's `prometheus_multiproc` volume) — Docker seeds a
# fresh named volume from whatever already exists at that path in the
# image on first mount, permissions included, so this avoids the
# container's non-root `appuser` hitting a PermissionError writing its
# mmap .db files into a directory Docker would otherwise auto-create as
# root:root.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /tmp/prometheus_multiproc \
    && chown appuser:appuser /tmp/prometheus_multiproc
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
