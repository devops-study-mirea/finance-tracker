"""Проверка веб-интерфейса: страницы открываются, формы работают.

Это дымовые тесты. Их задача — поймать сломанный шаблон, битую ссылку или
разъехавшийся контекст: такие поломки не видит ни один тест API, а
пользователь упирается в них сразу.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

PAGES = ("/", "/transactions", "/reports", "/budgets", "/accounts", "/categories")


def _register_via_web(client: TestClient, email: str = "web@example.com") -> None:
    response = client.post(
        "/register", data={"email": email, "password": "password123"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "access_token" in response.cookies


def test_anonymous_is_redirected_to_login(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_login_page_renders(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Вход" in response.text


def test_register_then_every_page_renders(client: TestClient):
    _register_via_web(client)
    for page in PAGES:
        response = client.get(page)
        assert response.status_code == 200, f"{page} → {response.status_code}"
        assert "Финансы" in response.text


def test_auth_cookie_is_httponly(client: TestClient):
    response = client.post(
        "/register",
        data={"email": "cookie@example.com", "password": "password123"},
        follow_redirects=False,
    )
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header


def test_open_redirect_is_blocked(client: TestClient):
    _register_via_web(client)
    client.get("/logout")
    response = client.post(
        "/login",
        data={"email": "web@example.com", "password": "password123", "next": "https://evil.test"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"


def test_wrong_password_shows_message_not_crash(client: TestClient):
    _register_via_web(client)
    client.get("/logout")
    response = client.post("/login", data={"email": "web@example.com", "password": "nope12345"})
    assert response.status_code == 200
    assert "Неверный email или пароль" in response.text


def test_add_transaction_through_the_form(client: TestClient):
    _register_via_web(client)
    account_id = client.get("/api/v1/accounts").json()[0]["id"]
    category_id = next(
        item["id"] for item in client.get("/api/v1/categories").json() if item["name"] == "Продукты"
    )

    response = client.post(
        "/transactions",
        data={
            "kind": "expense",
            "amount": "1 234,56",  # запятая и пробел — как пишет человек
            "account_id": str(account_id),
            "category_id": str(category_id),
            "occurred_on": "2026-09-02",
            "note": "тест",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/transactions")
    assert "1 234,56" in page.text.replace(" ", " ").replace("\xa0", " ")
    assert client.get("/api/v1/transactions").json()["total"] == 1


def test_form_error_is_shown_to_the_user(client: TestClient):
    _register_via_web(client)
    account_id = client.get("/api/v1/accounts").json()[0]["id"]

    response = client.post(
        "/transactions",
        data={
            "kind": "transfer",
            "amount": "100",
            "account_id": str(account_id),
            "counter_account_id": str(account_id),  # перевод сам себе
            "occurred_on": "2026-09-02",
        },
    )
    assert "тот же самый счёт" in response.text


def test_dashboard_shows_budget_progress(client: TestClient):
    _register_via_web(client)
    category_id = next(
        item["id"] for item in client.get("/api/v1/categories").json() if item["name"] == "Продукты"
    )
    client.post("/budgets", data={"category_id": str(category_id), "limit_amount": "10000"})

    page = client.get("/")
    assert "Продукты" in page.text
    assert re.search(r"budget-fill", page.text)


def test_health_and_ready(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready").json()
    assert ready["checks"]["database"] is True
