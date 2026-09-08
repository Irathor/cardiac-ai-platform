"""Application configuration, loaded exclusively from environment variables.

No secret ever gets a hardcoded default here — production values must come
from the environment (see .env.example at the repo root).
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "CardiacAI Research Platform"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "cardiac_ai"
    postgres_user: str = "cardiac_ai"
    postgres_password: str = ""

    # Redis / Celery
    redis_host: str = "redis"
    redis_port: int = 6379

    # MinIO (S3-compatible)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_images: str = "cardiac-images"
    minio_secure: bool = False

    # MLflow (training run/model tracking — see docs/architecture.md)
    mlflow_tracking_uri: str = "http://mlflow:5000"

    # DL training runner (see ml/scripts/training_runner_service.py, docs/dl-training-runner.md) —
    # a host-side bridge process the worker reaches for U-Net/CNN3D jobs, since GPU passthrough
    # into the worker container isn't available on this deployment. data_root is the shared
    # ./data bind mount (docker-compose.yml) both sides read/write real training artifacts through.
    training_runner_url: str = "http://host.docker.internal:8800"
    data_root: str = "/data"

    # Auth
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 15

    # CORS
    cors_allowed_origins: str = "http://localhost:5173"

    @field_validator("jwt_secret_key")
    @classmethod
    def _jwt_secret_key_must_be_set(cls, value: str) -> str:
        # An empty secret would let anyone forge a valid access token — the
        # other blank-by-default secrets (postgres_password, minio_*) fail
        # loudly the moment they're actually used against a real service, but
        # jwt.encode()/decode() would happily "succeed" with "" and never
        # surface the mistake, so this needs its own explicit check.
        if not value:
            raise ValueError(
                "JWT_SECRET_KEY must be set — generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return value

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance (one per process)."""
    return Settings()
