from functools import lru_cache
import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "University Lab Equipment API"
    environment: str = "development"
    database_url: str = "mysql+pymysql://root:root@localhost:3306/lab_equipment?charset=utf8mb4"
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    overdue_check_interval_seconds: int = 300
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_jwks_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
