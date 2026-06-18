"""Runtime settings, loaded once from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    default_model: str = "kokoro"
    model_cache_dir: str | None = None
    kokoro_device: str = "cpu"


settings = Settings()
