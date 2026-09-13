"""Правила формы операции проверяются до похода в базу."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import TransactionKind
from app.schemas.transaction import TransactionCreate


def _payload(**overrides):
    base = {
        "kind": TransactionKind.expense,
        "amount": Decimal("100"),
        "account_id": 1,
        "occurred_on": date(2026, 9, 1),
    }
    base.update(overrides)
    return base


def test_expense_is_valid():
    transaction = TransactionCreate(**_payload(category_id=5))
    assert transaction.amount == Decimal("100")


def test_amount_must_be_positive():
    with pytest.raises(ValidationError):
        TransactionCreate(**_payload(amount=Decimal("0")))
    with pytest.raises(ValidationError):
        TransactionCreate(**_payload(amount=Decimal("-10")))


def test_transfer_requires_counter_account():
    with pytest.raises(ValidationError, match="счёт-получатель"):
        TransactionCreate(**_payload(kind=TransactionKind.transfer))


def test_transfer_to_same_account_is_rejected():
    with pytest.raises(ValidationError, match="тот же самый счёт"):
        TransactionCreate(**_payload(kind=TransactionKind.transfer, counter_account_id=1))


def test_transfer_cannot_have_category():
    with pytest.raises(ValidationError, match="категории"):
        TransactionCreate(
            **_payload(kind=TransactionKind.transfer, counter_account_id=2, category_id=3)
        )


def test_non_transfer_cannot_have_counter_account():
    with pytest.raises(ValidationError, match="только для перевода"):
        TransactionCreate(**_payload(counter_account_id=2))


def test_date_defaults_to_today():
    payload = _payload()
    del payload["occurred_on"]
    assert TransactionCreate(**payload).occurred_on is not None
