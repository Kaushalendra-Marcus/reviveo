"""Application configuration loaded from environment / .env.

Secrets are never hard-coded. The app is fully functional in `synthetic` mode
with no secrets present; `live` mode activates real Razorpay + Claude calls.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunMode(str, Enum):
    synthetic = "synthetic"
    live = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    run_mode: RunMode = RunMode.synthetic
    api_key: str = "reviveo-dev-key"
    database_url: str = "reviveo.db"
    default_merchant_id: str = "codecraft"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    anthropic_api_key: str = ""
    ai_model_fast: str = "claude-haiku-4-5-20251001"
    ai_model_summary: str = "claude-sonnet-4-6"

    frontend_origin: str = "http://localhost:3000"

    @property
    def is_live(self) -> bool:
        return self.run_mode == RunMode.live

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def ai_configured(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
