"""Операции и арифметика остатков — самая ответственная часть приложения."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _balances(client: TestClient) -> dict[str, str]:
    return {item["name"]: item["balance"] for item in client.get("/api/v1/accounts").json()}


def test_income_increases_balance(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "amount": "80000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["income:Зарплата"],
            "occurred_on": "2026-09-01",
        },
    )
    assert _balances(auth_client)["Карта"] == "80000.00"


def test_expense_decreases_balance(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "1250.50",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": "2026-09-02",
        },
    )
    assert _balances(auth_client)["Карта"] == "-1250.50"


def test_transfer_moves_money_without_changing_total(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "amount": "10000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["income:Зарплата"],
            "occurred_on": "2026-09-01",
        },
    )
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "amount": "3000.00",
            "account_id": accounts["Карта"],
            "counter_account_id": accounts["Наличные"],
            "occurred_on": "2026-09-02",
        },
    )

    balances = _balances(auth_client)
    assert balances["Карта"] == "7000.00"
    assert balances["Наличные"] == "3000.00"
    # Общая сумма не изменилась — деньги не появились и не исчезли.
    assert float(balances["Карта"]) + float(balances["Наличные"]) == 10000.00


def test_initial_balance_is_the_starting_point(auth_client: TestClient, categories: dict[str, int]):
    account_id = auth_client.post(
        "/api/v1/accounts", json={"name": "Вклад", "currency": "RUB", "initial_balance": "5000.00"}
    ).json()["id"]

    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "1000.00",
            "account_id": account_id,
            "category_id": categories["expense:Прочее"],
            "occurred_on": "2026-09-02",
        },
    )
    assert _balances(auth_client)["Вклад"] == "4000.00"


def test_deleting_transaction_restores_balance(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    created = auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "500.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": "2026-09-02",
        },
    ).json()

    auth_client.delete(f"/api/v1/transactions/{created['id']}")
    assert _balances(auth_client)["Карта"] == "0.00"


def test_category_kind_must_match_transaction_kind(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    """Расход нельзя записать в категорию доходов — иначе отчёты становятся бессмыслицей."""
    response = auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "100.00",
            "account_id": accounts["Карта"],
            "category_id": categories["income:Зарплата"],
            "occurred_on": "2026-09-02",
        },
    )
    assert response.status_code == 422


def test_cannot_use_another_users_account(
    auth_client: TestClient, other_client: TestClient, accounts: dict[str, int]
):
    response = other_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "100.00",
            "account_id": accounts["Карта"],
            "occurred_on": "2026-09-02",
        },
    )
    assert response.status_code == 404


def test_transactions_are_isolated_between_users(
    auth_client: TestClient,
    other_client: TestClient,
    accounts: dict[str, int],
    categories: dict[str, int],
):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "100.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": "2026-09-02",
        },
    )
    assert other_client.get("/api/v1/transactions").json()["total"] == 0
    assert auth_client.get("/api/v1/transactions").json()["total"] == 1


def test_filters_narrow_the_result(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    for day, amount in (("2026-08-15", "100.00"), ("2026-09-10", "200.00")):
        auth_client.post(
            "/api/v1/transactions",
            json={
                "kind": "expense",
                "amount": amount,
                "account_id": accounts["Карта"],
                "category_id": categories["expense:Продукты"],
                "occurred_on": day,
            },
        )

    filtered = auth_client.get("/api/v1/transactions?date_from=2026-09-01&date_to=2026-09-30")
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["amount"] == "200.00"


def test_transfer_appears_in_both_account_statements(
    auth_client: TestClient, accounts: dict[str, int]
):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "amount": "500.00",
            "account_id": accounts["Карта"],
            "counter_account_id": accounts["Наличные"],
            "occurred_on": "2026-09-02",
        },
    )
    for account_id in accounts.values():
        response = auth_client.get(f"/api/v1/transactions?account_id={account_id}")
        assert response.json()["total"] == 1
