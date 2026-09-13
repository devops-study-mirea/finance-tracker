"""Конфигурация приложения.

Единственный источник настроек — переменные окружения (принцип 12-factor).
В коде нигде нет захардкоженных паролей и хостов: локально значения приезжают
из .env, в Docker — из environment, в Kubernetes — из ConfigMap и Secret.
Приложение об этом не знает и знать не должно.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "staging", "production"]

INSECURE_SECRETS = {"dev-only-secret-change-me", "change-me", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "finance-tracker"
    environment: Environment = "local"
    debug: bool = False
    log_level: str = "INFO"

    # База данных
    database_url: str = "postgresql+psycopg://finance:finance@localhost:5433/finance"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # Аутентификация
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60 * 24 * 7, gt=0)

    # Домен
    default_currency: str = Field(default="RUB", min_length=3, max_length=3)

    @field_validator("default_currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _forbid_insecure_secret_outside_local(self) -> Settings:
        """Не даём случайно уехать в прод с дефолтным ключом подписи токенов.

        Такая проверка — дешёвый способ превратить потенциальный инцидент
        в падение пода на старте, которое видно сразу.
        """
        if self.environment in ("staging", "production") and self.jwt_secret in INSECURE_SECRETS:
            raise ValueError(
                f"JWT_SECRET имеет небезопасное значение по умолчанию при ENVIRONMENT="
                f"{self.environment}. Сгенерируй ключ: openssl rand -hex 32"
            )
        return self

    @property
    def is_local(self) -> bool:
        return self.environment in ("local", "ci")


@lru_cache
def get_settings() -> Settings:
    """Настройки читаются один раз за процесс и кэшируются."""
    return Settings()


settings = get_settings()
