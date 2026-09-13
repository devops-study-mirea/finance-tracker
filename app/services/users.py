"""Регистрация, аутентификация и стартовое наполнение аккаунта."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Account, AccountKind, Category, CategoryKind, User
from app.security import hash_password, verify_password
from app.services.errors import AuthError, ConflictError

# (название, слот палитры)
DEFAULT_EXPENSE_CATEGORIES: tuple[tuple[str, int], ...] = (
    ("Продукты", 5),
    ("Кафе и рестораны", 1),
    ("Транспорт", 0),
    ("Жильё и коммуналка", 6),
    ("Связь и интернет", 2),
    ("Здоровье", 7),
    ("Одежда", 4),
    ("Развлечения", 3),
    ("Подписки", 6),
    ("Образование", 0),
    ("Прочее", 0),
)

DEFAULT_INCOME_CATEGORIES: tuple[tuple[str, int], ...] = (
    ("Зарплата", 5),
    ("Подработка", 0),
    ("Проценты и вклады", 2),
    ("Подарки", 4),
    ("Прочее", 3),
)


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.lower()))


def register(session: Session, email: str, password: str) -> User:
    """Создать пользователя вместе со стартовыми счетами и категориями.

    Всё делается в одной транзакции: либо пользователь получает готовый к работе
    аккаунт, либо не создаётся вовсе. Полурегистрация без категорий — состояние,
    из которого приложение потом не умеет выбираться.
    """
    normalized = email.lower().strip()
    if get_by_email(session, normalized) is not None:
        raise ConflictError("Пользователь с таким email уже зарегистрирован")

    user = User(email=normalized, password_hash=hash_password(password))
    session.add(user)
    session.flush()  # нужен user.id для связанных объектов

    seed_defaults(session, user)
    session.commit()
    session.refresh(user)
    return user


def seed_defaults(session: Session, user: User) -> None:
    """Стартовые счета и категории, чтобы приложение было пригодно с первой минуты."""
    session.add_all(
        [
            Account(
                user_id=user.id,
                name="Наличные",
                kind=AccountKind.cash,
                currency=settings.default_currency,
                initial_balance=Decimal("0"),
            ),
            Account(
                user_id=user.id,
                name="Карта",
                kind=AccountKind.card,
                currency=settings.default_currency,
                initial_balance=Decimal("0"),
            ),
        ]
    )
    session.add_all(
        [
            Category(user_id=user.id, name=name, kind=CategoryKind.expense, color_slot=slot)
            for name, slot in DEFAULT_EXPENSE_CATEGORIES
        ]
    )
    session.add_all(
        [
            Category(user_id=user.id, name=name, kind=CategoryKind.income, color_slot=slot)
            for name, slot in DEFAULT_INCOME_CATEGORIES
        ]
    )


def authenticate(session: Session, email: str, password: str) -> User:
    user = get_by_email(session, email)

    # Пароль проверяем даже если пользователя нет: иначе ответ на несуществующий
    # email приходит заметно быстрее, и по времени ответа можно перебрать,
    # какие адреса зарегистрированы.
    password_hash = user.password_hash if user else _DUMMY_HASH
    password_ok = verify_password(password, password_hash)

    if user is None or not password_ok:
        raise AuthError("Неверный email или пароль")
    if not user.is_active:
        raise AuthError("Учётная запись отключена")
    return user


# Хеш от заведомо непригодного пароля — только для выравнивания времени ответа.
_DUMMY_HASH = hash_password("dummy-password-for-timing-equalization")
