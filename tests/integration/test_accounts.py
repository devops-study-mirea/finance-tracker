from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_account(auth_client: TestClient):
    response = auth_client.post(
        "/api/v1/accounts",
        json={"name": "Вклад", "kind": "savings", "currency": "RUB", "initial_balance": "50000.00"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["balance"] == "50000.00"


def test_duplicate_account_name_conflicts(auth_client: TestClient):
    payload = {"name": "Копилка", "currency": "RUB"}
    assert auth_client.post("/api/v1/accounts", json=payload).status_code == 201
    assert auth_client.post("/api/v1/accounts", json=payload).status_code == 409


def test_account_of_another_user_is_invisible(
    auth_client: TestClient, other_client: TestClient, accounts: dict[str, int]
):
    """Чужой счёт даёт 404, а не 403: по коду ответа нельзя перебрать чужие id."""
    assert other_client.get(f"/api/v1/accounts/{accounts['Карта']}").status_code == 404


def test_account_with_transactions_cannot_be_deleted(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "100.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": "2026-09-01",
        },
    )
    response = auth_client.delete(f"/api/v1/accounts/{accounts['Карта']}")
    assert response.status_code == 422
    assert "архивируй" in response.json()["detail"].lower()


def test_empty_account_can_be_deleted(auth_client: TestClient, accounts: dict[str, int]):
    assert auth_client.delete(f"/api/v1/accounts/{accounts['Наличные']}").status_code == 204


def test_archived_account_hidden_by_default(auth_client: TestClient, accounts: dict[str, int]):
    auth_client.patch(f"/api/v1/accounts/{accounts['Наличные']}", json={"is_archived": True})
    assert len(auth_client.get("/api/v1/accounts").json()) == 1
    assert len(auth_client.get("/api/v1/accounts?include_archived=true").json()) == 2
