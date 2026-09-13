from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.category import CategoryKind


class PeriodSummary(BaseModel):
    """Сводка «сколько пришло, сколько ушло» за период."""

    date_from: date
    date_to: date
    income: Decimal
    expense: Decimal
    net: Decimal = Field(description="Доходы минус расходы: сколько отложилось за период")
    transactions_count: int


class CategoryBreakdownItem(BaseModel):
    category_id: int | None = Field(description="None — операции без категории")
    category_name: str
    color_slot: int | None
    total: Decimal
    share: float = Field(description="Доля в процентах от общей суммы за период")


class CategoryBreakdown(BaseModel):
    kind: CategoryKind
    date_from: date
    date_to: date
    total: Decimal
    items: list[CategoryBreakdownItem]


class TimelinePoint(BaseModel):
    period_start: date
    income: Decimal
    expense: Decimal
    net: Decimal


class Timeline(BaseModel):
    granularity: str
    points: list[TimelinePoint]


class BudgetStatusItem(BaseModel):
    category_id: int
    category_name: str
    color_slot: int
    limit_amount: Decimal
    spent: Decimal
    remaining: Decimal = Field(description="Отрицательное значение = перерасход")
    usage_pct: float
    is_over: bool


class BudgetStatus(BaseModel):
    month: date = Field(description="Первое число месяца, за который считался статус")
    items: list[BudgetStatusItem]
    total_limit: Decimal
    total_spent: Decimal
