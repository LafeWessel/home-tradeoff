from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parent.parent.parent / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Backend
    backend_host: str = "127.0.0.1"
    backend_port: int = 8765
    database_url: str = "sqlite:///./data.db"

    # External API keys (all optional; missing keys disable specific metrics)
    census_api_key: str | None = None
    bls_api_key: str | None = None
    fbi_api_key: str | None = None
    noaa_api_token: str | None = None

    # HTTP cache TTL in seconds (default 30 days)
    http_cache_ttl: int = 60 * 60 * 24 * 30


settings = Settings()
