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

    # ----- CORS -----
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])

    # ----- Rate limiting -----
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_ENABLED: bool = True

    # ----- Flower -----
    FLOWER_BASIC_AUTH: str = "admin:ChangeMe!2024"

    # ----- Derived helpers -----
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        """Allow ``CORS_ORIGINS`` to be supplied as a comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
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
