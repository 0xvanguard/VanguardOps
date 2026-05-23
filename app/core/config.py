"""Typed application settings backed by environment variables.

All configuration flows through this single :class:`Settings` object so the
rest of the codebase never reaches for ``os.getenv`` directly. This makes
configuration:

* discoverable (one place to look),
* validated (Pydantic enforces types and constraints), and
* test-friendly (overridable via env vars in CI).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration.

    Reads from environment variables and (in development) from a ``.env`` file
    located at the repository root. Production deployments should rely on
    real environment variables / secret managers, not on ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ----- Application metadata -----
    PROJECT_NAME: str = "VanguardOps"
    VERSION: str = "2.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"

    # ----- Logging -----
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # ----- Server -----
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 2

    # ----- Security / JWT -----
    SECRET_KEY: str = Field(
        default="dev-only-secret-change-me-in-production-min-32-characters",
        min_length=32,
        description="Secret used to sign JWT tokens. MUST be overridden in production.",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ----- Bootstrap admin (auto-created on first startup) -----
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@vanguardops.local"
    BOOTSTRAP_ADMIN_PASSWORD: str = "ChangeMe!2024"

    # ----- Database -----
    DATABASE_URL: str = "sqlite:///./vanguardops.db"

    # ----- Celery / Redis -----
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # ----- JWT blacklist (Redis DB /2) -----
    # Segregated DB so a routine FLUSHDB on the broker (DB 0) can never
    # destroy active session revocations. See ADR-007.
    REDIS_BLACKLIST_URL: str = "redis://localhost:6379/2"
    JWT_BLACKLIST_ON_REDIS_FAILURE: Literal["closed", "open"] = "closed"

    # ----- CORS -----
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])

    # ----- Rate limiting -----
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_ENABLED: bool = True
    # In-house rate limiter (sliding-window log over Redis DB /3, see ADR-008).
    # Segregated DB keeps abuse-mitigation state immune to FLUSHDB on the
    # broker (/0), result backend (/1), or JWT blacklist (/2).
    RATE_LIMIT_REDIS_URL: str = "redis://localhost:6379/3"
    # Per-IP per-minute caps for high-criticality endpoints.
    RATE_LIMIT_LOGIN_PER_IP: int = 5
    RATE_LIMIT_REFRESH_PER_IP: int = 10
    RATE_LIMIT_REGISTER_PER_IP: int = 3
    RATE_LIMIT_API_DEFAULT_PER_IP: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    # Dynamic banning thresholds.
    RATE_LIMIT_AUTH_FAILURE_THRESHOLD: int = 10
    RATE_LIMIT_AUTH_FAILURE_WINDOW: int = 300  # 5 minutes
    RATE_LIMIT_404_THRESHOLD: int = 20
    RATE_LIMIT_404_WINDOW: int = 60  # 1 minute
    # CIDRs that bypass rate limiting and banning. Comma-separated.
    RATE_LIMIT_WHITELIST_CIDRS: list[str] = Field(default_factory=list)
    # When ``True``, honour the first hop in ``X-Forwarded-For`` as the
    # client IP (only safe behind a trusted reverse proxy / load balancer).
    TRUST_PROXY: bool = False

    # ----- Flower -----
    FLOWER_BASIC_AUTH: str = "admin:ChangeMe!2024"

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_dev_secret_in_production(cls, v: str, info) -> str:
        """Reject the dev-default SECRET_KEY when ``ENVIRONMENT=production``.

        Pydantic feeds us values in declaration order, so by the time this
        validator runs ``ENVIRONMENT`` is already in ``info.data``. If a
        deployment ships the in-repo placeholder, fail fast at import time
        rather than silently sign tokens with a known-public key.
        """
        environment = info.data.get("ENVIRONMENT", "development")
        if environment == "production" and v.startswith("dev-only-secret"):
            raise ValueError(
                "SECRET_KEY must be set to a production-grade value when "
                "ENVIRONMENT=production. Generate one with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(64))'`."
            )
        return v

    # ----- Derived helpers -----
    @field_validator("CORS_ORIGINS", "RATE_LIMIT_WHITELIST_CIDRS", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Allow list-valued env vars to be supplied as comma-separated strings."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT == "test"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Use this in dependencies to avoid re-parsing."""
    return Settings()


# Module-level convenience handle (kept for backward compatibility with
# legacy imports). New code should depend on :func:`get_settings` instead.
settings: Settings = get_settings()
