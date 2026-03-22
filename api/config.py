from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings read from environment variables."""

    DATABASE_URL: str = "postgresql+asyncpg://irt:irt_dev_password@postgres:5432/irt"
    DASHBOARD_API_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:5173"

    @field_validator("DASHBOARD_API_KEY")
    @classmethod
    def _api_key_must_be_set(cls, v: str) -> str:
        if not v or v == "change-me-to-a-secure-key":
            raise ValueError(
                "DASHBOARD_API_KEY is not set or still uses the insecure default. "
                "Set a strong key via environment variable or .env file."
            )
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
