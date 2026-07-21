"""Application settings, sourced entirely from the environment (§6, §11).

Platform-level configuration only. Tenant-specific configuration never lives
here — it lives in the database (business_settings, workflow definitions).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Core
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Security
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30

    # Data stores
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lead_recovery"
    redis_url: str = "redis://localhost:6379/0"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    public_api_base_url: str = "http://localhost:8000"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
