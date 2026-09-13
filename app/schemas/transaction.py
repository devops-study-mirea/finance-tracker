from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.transaction import Transaction, TransactionKind
from app.schemas.common import MoneyAmount


def _today() -> date:
    return datetime.now(UTC).date()


class TransactionCreate(BaseModel):
    kind: TransactionKind
    amount: MoneyAmount
    account_id: int
    counter_account_id: int | None = None
    category_id: int | None = None
    occurred_on: date = Field(default_factory=_today)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_shape(self) -> TransactionCreate:
        """Те же правила, что и CHECK-констрейнт в базе.

        Дублирование намеренное: Pydantic даёт пользователю понятную ошибку 422,
        а констрейнт в базе гарантирует, что мусор не попадёт туда никаким
        другим путём — через psql, миграцию или будущий воркер.
        """
        if self.kind is TransactionKind.transfer:
            if self.counter_account_id is None:
                raise ValueError("Для перевода нужно указать счёт-получатель (counter_account_id)")
            if self.counter_account_id == self.account_id:
                raise ValueError("Нельзя перевести деньги на тот же самый счёт")
            if self.category_id is not None:
                raise ValueError("У перевода не бывает категории: деньги не покидают твой бюджет")
        elif self.counter_account_id is not None:
            raise ValueError("counter_account_id допустим только для перевода")
        return self


class TransactionUpdate(BaseModel):
    amount: MoneyAmount | None = None
    account_id: int | None = None
    category_id: int | None = None
    occurred_on: date | None = None
    note: str | None = Field(default=None, max_length=500)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: TransactionKind
    amount: Decimal
    occurred_on: date
    note: str | None

    account_id: int
    account_name: str
    counter_account_id: int | None
    counter_account_name: str | None
    category_id: int | None
    category_name: str | None
    category_slot: int | None

    @classmethod
    def from_model(cls, transaction: Transaction) -> TransactionResponse:
        return cls(
            id=transaction.id,
            kind=transaction.kind,
            amount=transaction.amount,
            occurred_on=transaction.occurred_on,
            note=transaction.note,
            account_id=transaction.account_id,
            account_name=transaction.account.name,
            counter_account_id=transaction.counter_account_id,
            counter_account_name=(
                transaction.counter_account.name if transaction.counter_account else None
            ),
            category_id=transaction.category_id,
            category_name=transaction.category.name if transaction.category else None,
            category_slot=transaction.category.color_slot if transaction.category else None,
        )


class TransactionPage(BaseModel):
    """Страница результатов. total нужен, чтобы UI мог нарисовать пагинацию."""

    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int
