"""
Typed Application Settings Schema using Pydantic Settings.
Adheres strictly to:
1. No .env parsed directly in code. Loads automatically via Pydantic Settings env_file provider.
2. Mandatory rule: JWT_SECRET_KEY length must be at least 32 characters.
3. Telegram MTProto Protocol (Telethon) configuration: api_id, api_hash, session_string, chat_id.
4. Optional TELEGRAM_BOT_TOKEN for Telegram Login Widget HMAC validation.
5. Fail-fast if STORAGE_BACKEND is 'mtproto' but credentials are missing.
"""

from typing import List, Literal
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    # Core Django
    DJANGO_SECRET_KEY: str = "django-insecure-prod-key-must-be-long-and-secure-change-in-prod"
    DEBUG: bool = True
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"

    # Database (PostgreSQL / Neon URL)
    DATABASE_URL: str = ""
    DB_NAME: str = "telegram_drive"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "secret"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

    # JWT Configuration (Access 15 mins, Refresh 7 days)
    JWT_SECRET_KEY: str = "a-very-secure-jwt-secret-key-that-is-at-least-32-chars-long"
    JWT_ACCESS_TTL_MINUTES: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7

    # Telegram MTProto & Storage Configuration
    STORAGE_BACKEND: Literal["mock", "mtproto"] = "mock"
    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_SESSION_STRING: str = ""
    TELEGRAM_STORAGE_CHAT_ID: str = ""
    TELEGRAM_BOT_TOKEN: str = ""

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""

    # CORS
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Upload Chunk Size Configuration (in Megabytes)
    # Telegram MTProto Policy: Min 1 MB (prevents FloodWait), Max 2000 MB (standard MTProto limit)
    DEFAULT_CHUNK_SIZE_MB: int = 8
    MIN_CHUNK_SIZE_MB: int = 4
    MAX_CHUNK_SIZE_MB: int = 32

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(f"JWT_SECRET_KEY must be at least 32 characters long. Provided length: {len(v)}")
        return v

    @model_validator(mode="after")
    def validate_storage_backend(self):
        if self.STORAGE_BACKEND == "mtproto":
            if not self.TELEGRAM_API_ID or not self.TELEGRAM_API_HASH:
                raise ValueError("STORAGE_BACKEND is set to 'mtproto', but TELEGRAM_API_ID or TELEGRAM_API_HASH is missing!")
        return self

    @model_validator(mode="after")
    def validate_chunk_sizes(self):
        TELEGRAM_HARD_MIN_MB = 1
        TELEGRAM_HARD_MAX_MB = 2000

        if self.MIN_CHUNK_SIZE_MB < TELEGRAM_HARD_MIN_MB:
            raise ValueError(f"MIN_CHUNK_SIZE_MB ({self.MIN_CHUNK_SIZE_MB} MB) cannot be less than Telegram limit ({TELEGRAM_HARD_MIN_MB} MB).")
        if self.MAX_CHUNK_SIZE_MB > TELEGRAM_HARD_MAX_MB:
            raise ValueError(f"MAX_CHUNK_SIZE_MB ({self.MAX_CHUNK_SIZE_MB} MB) cannot exceed Telegram limit ({TELEGRAM_HARD_MAX_MB} MB).")
        if self.MIN_CHUNK_SIZE_MB > self.MAX_CHUNK_SIZE_MB:
            raise ValueError(f"MIN_CHUNK_SIZE_MB ({self.MIN_CHUNK_SIZE_MB}) cannot exceed MAX_CHUNK_SIZE_MB ({self.MAX_CHUNK_SIZE_MB}).")
        if not (self.MIN_CHUNK_SIZE_MB <= self.DEFAULT_CHUNK_SIZE_MB <= self.MAX_CHUNK_SIZE_MB):
            raise ValueError(
                f"DEFAULT_CHUNK_SIZE_MB ({self.DEFAULT_CHUNK_SIZE_MB}) must be between "
                f"MIN_CHUNK_SIZE_MB ({self.MIN_CHUNK_SIZE_MB}) and MAX_CHUNK_SIZE_MB ({self.MAX_CHUNK_SIZE_MB})."
            )
        return self

    @property
    def allowed_hosts_list(self) -> List[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]


config = AppConfig()
