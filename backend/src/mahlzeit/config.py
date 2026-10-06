"""Settings, read from environment variables only."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://mahlzeit:mahlzeit@localhost:5433/mahlzeit"
    base_url: str = "http://localhost"
    # Comma-separated extra origins allowed for unsafe requests (e.g. the Vite dev server).
    extra_origins: str = ""

    # 32 bytes, base64url. Encrypts secrets at rest (push keys now, API keys later).
    encryption_key: str = ""

    session_days: int = 30
    invite_days: int = 7
    reset_token_minutes: int = 60

    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_subject: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"

    files_dir: str = "/data/files"
    worker_poll_seconds: float = Field(default=2.0, gt=0)

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def allowed_origins(self) -> set[str]:
        parts = urlsplit(self.base_url)
        origins = {f"{parts.scheme}://{parts.netloc}"}
        origins |= {o.strip().rstrip("/") for o in self.extra_origins.split(",") if o.strip()}
        return origins

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def push_enabled(self) -> bool:
        return bool(self.vapid_private_key and self.vapid_public_key and self.vapid_subject)


@lru_cache
def get_settings() -> Settings:
    return Settings()
