"""Пароли и токены."""

from __future__ import annotations

import time

import pytest

from app.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_reversible_and_verifies():
    password = "correct horse battery staple"
    hashed = hash_password(password)

    assert password not in hashed
    assert verify_password(password, hashed)
    assert not verify_password("wrong password", hashed)


def test_same_password_produces_different_hashes():
    """У bcrypt своя соль на каждый хеш.

    Одинаковые хеши означали бы, что по утечке базы видно, у каких
    пользователей совпадают пароли.
    """
    assert hash_password("same") != hash_password("same")


def test_password_over_bcrypt_limit_is_rejected():
    with pytest.raises(ValueError):
        hash_password("x" * 73)


def test_token_roundtrip():
    token = create_access_token(42)
    assert decode_access_token(token) == 42


def test_tampered_token_is_rejected():
    token = create_access_token(1)
    # Меняем последний символ подписи.
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_garbage_token_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("не токен вовсе")


def test_expired_token_is_rejected(monkeypatch):
    from app import security

    monkeypatch.setattr(security.settings, "jwt_expire_minutes", -1)
    token = create_access_token(1)
    time.sleep(0.01)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
