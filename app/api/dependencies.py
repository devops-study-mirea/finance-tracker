"""Общие зависимости FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.security import InvalidTokenError, decode_access_token
from app.services.errors import AuthError

# Токен принимается двумя способами: заголовком Authorization (для API-клиентов
# и curl) и httpOnly-кукой (для веб-интерфейса). Кука именно httpOnly —
# JavaScript до неё не дотянется, поэтому XSS не сможет её украсть.
COOKIE_NAME = "access_token"

DbSession = Annotated[Session, Depends(get_session)]


def extract_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if header and header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    return request.cookies.get(COOKIE_NAME)


def get_optional_user(request: Request, session: DbSession) -> User | None:
    """Пользователь или None. Для веб-страниц, которые сами решают, куда redirect."""
    token = extract_token(request)
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        return None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(request: Request, session: DbSession) -> User:
    """Пользователь или 401. Для эндпоинтов API."""
    user = get_optional_user(request, session)
    if user is None:
        raise AuthError("Требуется аутентификация")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
