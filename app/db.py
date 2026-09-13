"""Подключение к базе и выдача сессий."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    # Проверяет живость соединения перед выдачей из пула. Без этого после
    # рестарта Postgres (или разрыва соединения сетью) приложение отдаёт
    # 500 на первый запрос вместо того, чтобы прозрачно переподключиться.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI-зависимость: одна сессия на один HTTP-запрос."""
    with SessionLocal() as session:
        yield session


def check_database() -> bool:
    """Живо ли соединение с базой. Используется в /ready."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
