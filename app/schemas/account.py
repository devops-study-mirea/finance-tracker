from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.models.account import AccountKind
from app.schemas.common import CurrencyCode, MoneyBalance


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: AccountKind = AccountKind.card
    currency: CurrencyCode = settings.default_currency
    initial_balance: MoneyBalance = Decimal("0")


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: AccountKind | None = None
    initial_balance: MoneyBalance | None = None
    is_archived: bool | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: AccountKind
    currency: str
    initial_balance: Decimal
    balance: Decimal = Field(description="Текущий остаток с учётом всех операций")
    is_archived: bool
