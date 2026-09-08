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

RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
