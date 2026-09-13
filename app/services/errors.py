"""Ошибки предметной области.

Слой сервисов ничего не знает про HTTP: он бросает эти исключения, а слой API
превращает их в коды ответа (app/api/exception_handlers.py). Благодаря этому
бизнес-логику можно вызвать откуда угодно — из воркера, из скрипта, из тестов —
и она не потянет за собой FastAPI.
"""

from __future__ import annotations


class DomainError(Exception):
    """Базовая ошибка бизнес-логики."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """Объект не найден или принадлежит другому пользователю.

    Эти два случая намеренно неразличимы снаружи: иначе по разнице между
    404 и 403 можно перебором узнать, какие id существуют у чужих аккаунтов.
    """


class ConflictError(DomainError):
    """Нарушение уникальности: такой email/счёт/категория уже есть."""


class BusinessRuleError(DomainError):
    """Операция технически возможна, но запрещена правилами."""


class AuthError(DomainError):
    """Неверные учётные данные или недействительный токен."""
