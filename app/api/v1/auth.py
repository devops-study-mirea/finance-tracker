from __future__ import annotations

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DbSession
from app.config import settings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.security import create_access_token
from app.services import users

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, session: DbSession) -> TokenResponse:
    """Создать пользователя. Сразу возвращает токен — отдельный логин не нужен."""
    user = users.register(session, data.email, data.password)
    return _token_for(user.id)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, session: DbSession) -> TokenResponse:
    user = users.authenticate(session, data.email, data.password)
    return _token_for(user.id)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


def _token_for(user_id: int) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        expires_in=settings.jwt_expire_minutes * 60,
    )
