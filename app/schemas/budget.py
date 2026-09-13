from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import MoneyAmount


class BudgetCreate(BaseModel):
    category_id: int
    limit_amount: MoneyAmount


class BudgetUpdate(BaseModel):
    limit_amount: MoneyAmount


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    category_name: str
    limit_amount: Decimal
