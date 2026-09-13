"""Хеширование паролей и выпуск/проверка JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings

# bcrypt работает с байтами и молча обрезает вход длиннее 72 байт.
# Явно ограничиваем, чтобы «пароль из 200 символов» не превращался
# незаметно для пользователя в «первые 72 символа».
MAX_PASSWORD_BYTES = 72


class InvalidTokenError(Exception):
    """Токен просрочен, подделан или имеет неверную структуру."""


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Пароль длиннее {MAX_PASSWORD_BYTES} байт не поддерживается")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Битый хеш в базе — считаем, что пароль не подошёл.
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Вернуть user_id из токена или бросить InvalidTokenError."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc
