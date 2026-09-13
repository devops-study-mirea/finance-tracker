"""Отчёты. Главное, что здесь проверяется, — переводы не считаются оборотом."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient, accounts: dict[str, int], categories: dict[str, int]) -> None:
    client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "amount": "100000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["income:Зарплата"],
            "occurred_on": "2026-09-01",
        },
    )
    client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "20000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": "2026-09-05",
        },
    )
    client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "5000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Транспорт"],
            "occurred_on": "2026-09-06",
        },
    )
    # Перевод: не доход и не расход, в отчёты попадать не должен.
    client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "amount": "30000.00",
            "account_id": accounts["Карта"],
            "counter_account_id": accounts["Наличные"],
            "occurred_on": "2026-09-07",
        },
    )


def test_summary_excludes_transfers(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    _seed(auth_client, accounts, categories)
    summary = auth_client.get(
        "/api/v1/analytics/summary?date_from=2026-09-01&date_to=2026-09-30"
    ).json()

    assert summary["income"] == "100000.00"
    assert summary["expense"] == "25000.00"  # без 30000 перевода
    assert summary["net"] == "75000.00"
    assert summary["transactions_count"] == 3


def test_breakdown_sorted_and_shares_add_up(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    _seed(auth_client, accounts, categories)
    breakdown = auth_client.get(
        "/api/v1/analytics/breakdown?kind=expense&date_from=2026-09-01&date_to=2026-09-30"
    ).json()

    assert [item["category_name"] for item in breakdown["items"]] == ["Продукты", "Транспорт"]
    assert breakdown["total"] == "25000.00"
    assert breakdown["items"][0]["share"] == 80.0
    assert round(sum(item["share"] for item in breakdown["items"])) == 100


def test_breakdown_groups_uncategorized(auth_client: TestClient, accounts: dict[str, int]):
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "700.00",
            "account_id": accounts["Карта"],
            "occurred_on": "2026-09-09",
        },
    )
    breakdown = auth_client.get(
        "/api/v1/analytics/breakdown?kind=expense&date_from=2026-09-01&date_to=2026-09-30"
    ).json()
    assert breakdown["items"][0]["category_name"] == "Без категории"
    assert breakdown["items"][0]["color_slot"] is None


def test_breakdown_folds_tail_into_other(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    """Категорий больше восьми — хвост сворачивается, палитра не переполняется."""
    expense_ids = [value for key, value in categories.items() if key.startswith("expense:")]
    assert len(expense_ids) > 8

    for index, category_id in enumerate(expense_ids):
        auth_client.post(
            "/api/v1/transactions",
            json={
                "kind": "expense",
                "amount": f"{(len(expense_ids) - index) * 100}.00",
                "account_id": accounts["Карта"],
                "category_id": category_id,
                "occurred_on": "2026-09-10",
            },
        )

    items = auth_client.get(
        "/api/v1/analytics/breakdown?kind=expense&date_from=2026-09-01&date_to=2026-09-30"
    ).json()["items"]

    assert len(items) == 9  # 8 названных + «Остальное»
    assert items[-1]["category_name"] == "Остальное"
    assert items[-1]["color_slot"] is None


def test_timeline_buckets_by_month(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    for day in ("2026-07-10", "2026-08-10", "2026-08-20"):
        auth_client.post(
            "/api/v1/transactions",
            json={
                "kind": "expense",
                "amount": "1000.00",
                "account_id": accounts["Карта"],
                "category_id": categories["expense:Продукты"],
                "occurred_on": day,
            },
        )

    points = auth_client.get(
        "/api/v1/analytics/timeline?date_from=2026-07-01&date_to=2026-08-31&granularity=month"
    ).json()["points"]

    assert [point["period_start"] for point in points] == ["2026-07-01", "2026-08-01"]
    assert points[1]["expense"] == "2000.00"


def test_budget_status_reports_overspend(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    auth_client.post(
        "/api/v1/budgets",
        json={
            "category_id": categories["expense:Продукты"],
            "limit_amount": "10000.00",
        },
    )
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "12000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": today.isoformat(),
        },
    )

    item = auth_client.get("/api/v1/analytics/budget-status").json()["items"][0]
    assert item["spent"] == "12000.00"
    assert item["remaining"] == "-2000.00"
    assert item["usage_pct"] == 120.0
    assert item["is_over"] is True


def test_budget_only_counts_current_month(
    auth_client: TestClient, accounts: dict[str, int], categories: dict[str, int]
):
    auth_client.post(
        "/api/v1/budgets",
        json={
            "category_id": categories["expense:Продукты"],
            "limit_amount": "10000.00",
        },
    )
    auth_client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "amount": "9000.00",
            "account_id": accounts["Карта"],
            "category_id": categories["expense:Продукты"],
            "occurred_on": "2020-01-15",
        },
    )

    item = auth_client.get("/api/v1/analytics/budget-status").json()["items"][0]
    assert item["spent"] == "0.00"
    assert item["is_over"] is False


def test_budget_on_income_category_is_rejected(auth_client: TestClient, categories: dict[str, int]):
    response = auth_client.post(
        "/api/v1/budgets",
        json={
            "category_id": categories["income:Зарплата"],
            "limit_amount": "1000.00",
        },
    )
    assert response.status_code == 422
