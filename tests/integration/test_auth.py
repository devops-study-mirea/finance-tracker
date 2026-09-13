from __future__ import annotations

from fastapi.testclient import TestClient


def test_register_returns_token_and_seeds_account(client: TestClient):
    response = client.post(
        "/api/v1/auth/register", json={"email": "new@example.com", "password": "password123"}
    )
    assert response.status_code == 201
    token = response.json()["access_token"]

    # Новый пользователь сразу может работать: счета и категории созданы.
    headers = {"Authorization": f"Bearer {token}"}
    assert len(client.get("/api/v1/accounts", headers=headers).json()) == 2
    assert len(client.get("/api/v1/categories", headers=headers).json()) > 10


def test_email_is_case_insensitive(client: TestClient):
    client.post(
        "/api/v1/auth/register", json={"email": "Mixed@Example.com", "password": "password123"}
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": "mixed@example.com", "password": "password123"}
    )
    assert response.status_code == 200


def test_duplicate_registration_conflicts(client: TestClient):
    payload = {"email": "dup@example.com", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_short_password_rejected(client: TestClient):
    response = client.post(
        "/api/v1/auth/register", json={"email": "short@example.com", "password": "1234"}
    )
    assert response.status_code == 422


def test_login_with_wrong_password(client: TestClient):
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "password123"})
    response = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_with_unknown_email_gives_same_error(client: TestClient):
    """Ответ не должен подсказывать, зарегистрирован ли такой email."""
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "password123"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный email или пароль"


def test_protected_endpoint_requires_token(client: TestClient):
    assert client.get("/api/v1/accounts").status_code == 401


def test_me_returns_current_user(auth_client: TestClient):
    response = auth_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
