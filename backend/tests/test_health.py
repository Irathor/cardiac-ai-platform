"""Liveness must never require infrastructure; readiness must genuinely check the DB."""
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app

client = TestClient(app)


def test_liveness_ok():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_fails_without_database():
    # Force the DB dependency to fail regardless of whether a real Postgres
    # happens to be reachable from wherever this test runs (e.g. inside the
    # docker-compose backend container, where one deliberately is) — readiness
    # must surface that as a failure instead of silently reporting healthy.
    # TestClient defaults to re-raising unhandled server exceptions (useful for
    # catching bugs), but here the unhandled DB error *is* the expected
    # behavior a real client would see as a 500 — so it must become a response.
    def broken_get_db():
        raise ConnectionError("simulated database outage")
        yield  # pragma: no cover - never reached, makes this a generator

    app.dependency_overrides[get_db] = broken_get_db
    try:
        failing_client = TestClient(app, raise_server_exceptions=False)
        response = failing_client.get("/api/v1/health/ready")
        assert response.status_code == 500
    finally:
        del app.dependency_overrides[get_db]
