"""Settings validation — an unset JWT_SECRET_KEY must fail loudly at startup,
not silently sign tokens with an empty secret (see app.core.config)."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_empty_jwt_secret_key_is_rejected():
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key="", postgres_password="x", minio_access_key="x", minio_secret_key="x")


def test_missing_jwt_secret_key_defaults_to_empty_and_is_rejected(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(postgres_password="x", minio_access_key="x", minio_secret_key="x", _env_file=None)


def test_non_empty_jwt_secret_key_is_accepted():
    settings = Settings(
        jwt_secret_key="a-real-secret", postgres_password="x", minio_access_key="x", minio_secret_key="x",
    )
    assert settings.jwt_secret_key == "a-real-secret"
