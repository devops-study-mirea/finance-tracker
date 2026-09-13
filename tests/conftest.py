"""Общая обвязка тестов.

Тесты работают с НАСТОЯЩИМ PostgreSQL, а не с SQLite-заглушкой. Причина
практическая: половина логики этого приложения — SQL (date_trunc, CHECK-
констрейнты, ON DELETE, оконные агрегаты). На SQLite эти тесты были бы
зелёными и ничего бы не проверяли.

Схема накатывается миграциями Alembic, а не metadata.create_all(). Так каждый
прогон заодно проверяет, что миграции действительно дают ту схему, которую
ожидает код — рассинхрон между моделями и миграциями обнаруживается сразу.
"""

from __future__ import annotations

import os

# Переменные окружения должны быть выставлены ДО импорта app.config:
# настройки читаются один раз и кэшируются.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://finance:finance@localhost:5433/finance_test"
    ),
)
os.environ.setdefault("ENVIRONMENT", "ci")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-anywhere-else")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from collections.abc import Iterator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from app.db import SessionLocal, engine
from app.main import app

TABLES = ("transactions", "budgets", "categories", "accounts", "users")


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> Iterator[None]:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """Каждый тест начинается с пустой базы.

    TRUNCATE ... CASCADE вместо удаления и пересоздания схемы: на порядок
    быстрее, а RESTART IDENTITY возвращает счётчики id, чтобы тесты
    не зависели от порядка запуска.
    """
    yield
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as db_session:
        yield db_session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """Клиент с зарегистрированным пользователем и токеном в заголовке."""
    response = client.post(
        "/api/v1/auth/register", json={"email": "user@example.com", "password": "password123"}
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def other_client() -> Iterator[TestClient]:
    """Второй, независимый пользователь — для проверки изоляции данных."""
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/auth/register",
            json={"email": "other@example.com", "password": "password123"},
        )
        assert response.status_code == 201, response.text
        test_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield test_client


@pytest.fixture
def accounts(auth_client: TestClient) -> dict[str, int]:
    """Счета, создаваемые при регистрации: {'Наличные': id, 'Карта': id}."""
    response = auth_client.get("/api/v1/accounts")
    return {item["name"]: item["id"] for item in response.json()}


@pytest.fixture
def categories(auth_client: TestClient) -> dict[str, int]:
    """Категории по умолчанию, ключ вида «expense:Продукты».

    Ключ с типом нужен потому, что «Прочее» и «Подарки» существуют
    и среди расходов, и среди доходов.
    """
    response = auth_client.get("/api/v1/categories")
    return {f"{item['kind']}:{item['name']}": item["id"] for item in response.json()}
