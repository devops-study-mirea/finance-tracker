"""Аналитика: сводки, разрезы по категориям, динамика, контроль бюджетов.

Общее правило всех отчётов: ПЕРЕВОДЫ НЕ УЧИТЫВАЮТСЯ.
Переложить деньги с карты на наличные — не расход и не доход, суммарное
состояние не изменилось. Если их считать, то каждое снятие в банкомате
удваивает «траты» месяца, и отчёт врёт. Поэтому везде фильтр по kind.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, case, func, select
from sqlalchemy.orm import Session

from app.models import Budget, Category, CategoryKind, Transaction, TransactionKind
from app.schemas.analytics import (
    BudgetStatus,
    BudgetStatusItem,
    CategoryBreakdown,
    CategoryBreakdownItem,
    PeriodSummary,
    Timeline,
    TimelinePoint,
)

ZERO = Decimal("0.00")

# Столько категорий показываем в разрезе поимённо, остальные сворачиваем
# в «Остальное». Ограничение не косметическое: палитра гарантирует
# различимость цветов только на восьми слотах (см. app/palette.py).
MAX_BREAKDOWN_ITEMS = 8

GRANULARITIES = ("day", "week", "month", "year")

UNCATEGORIZED_LABEL = "Без категории"
OTHER_LABEL = "Остальное"


def today() -> date:
    return datetime.now(UTC).date()


def month_bounds(reference: date) -> tuple[date, date]:
    """Первый и последний день месяца, в который попадает reference."""
    last_day = calendar.monthrange(reference.year, reference.month)[1]
    return reference.replace(day=1), reference.replace(day=last_day)


def _quantize(value: Decimal | int | float | None) -> Decimal:
    return Decimal(value or 0).quantize(ZERO)


def period_summary(session: Session, user_id: int, date_from: date, date_to: date) -> PeriodSummary:
    """Сколько пришло, сколько ушло и что осталось за период."""
    row = session.execute(
        select(
            func.coalesce(
                func.sum(
                    case((Transaction.kind == TransactionKind.income, Transaction.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Transaction.kind == TransactionKind.expense, Transaction.amount), else_=0)
                ),
                0,
            ),
            func.count(),
        ).where(
            Transaction.user_id == user_id,
            Transaction.occurred_on >= date_from,
            Transaction.occurred_on <= date_to,
            Transaction.kind != TransactionKind.transfer,
        )
    ).one()

    income, expense, count = _quantize(row[0]), _quantize(row[1]), int(row[2])
    return PeriodSummary(
        date_from=date_from,
        date_to=date_to,
        income=income,
        expense=expense,
        net=income - expense,
        transactions_count=count,
    )


def category_breakdown(
    session: Session,
    user_id: int,
    kind: CategoryKind,
    date_from: date,
    date_to: date,
    *,
    max_items: int = MAX_BREAKDOWN_ITEMS,
) -> CategoryBreakdown:
    """Разрез сумм по категориям за период, от большей к меньшей."""
    transaction_kind = (
        TransactionKind.income if kind is CategoryKind.income else TransactionKind.expense
    )

    rows = session.execute(
        select(
            Transaction.category_id,
            Category.name,
            Category.color_slot,
            func.sum(Transaction.amount),
        )
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.kind == transaction_kind,
            Transaction.occurred_on >= date_from,
            Transaction.occurred_on <= date_to,
        )
        .group_by(Transaction.category_id, Category.name, Category.color_slot)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    total = sum((_quantize(row[3]) for row in rows), ZERO)

    items: list[CategoryBreakdownItem] = []
    folded = ZERO
    for index, (category_id, name, color_slot, amount) in enumerate(rows):
        value = _quantize(amount)
        if index < max_items:
            items.append(
                CategoryBreakdownItem(
                    category_id=category_id,
                    category_name=name or UNCATEGORIZED_LABEL,
                    color_slot=color_slot,
                    total=value,
                    share=_share(value, total),
                )
            )
        else:
            folded += value

    if folded > ZERO:
        items.append(
            CategoryBreakdownItem(
                category_id=None,
                category_name=OTHER_LABEL,
                color_slot=None,
                total=folded,
                share=_share(folded, total),
            )
        )

    return CategoryBreakdown(
        kind=kind, date_from=date_from, date_to=date_to, total=total, items=items
    )


def _share(value: Decimal, total: Decimal) -> float:
    if total == 0:
        return 0.0
    return round(float(value / total) * 100, 1)


def timeline(
    session: Session,
    user_id: int,
    date_from: date,
    date_to: date,
    granularity: str = "month",
) -> Timeline:
    """Доходы и расходы по периодам — видно тренд, а не одну точку."""
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity должен быть одним из {GRANULARITIES}")

    bucket = func.date_trunc(granularity, Transaction.occurred_on).cast(Date).label("bucket")

    rows = session.execute(
        select(
            bucket,
            func.coalesce(
                func.sum(
                    case((Transaction.kind == TransactionKind.income, Transaction.amount), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Transaction.kind == TransactionKind.expense, Transaction.amount), else_=0)
                ),
                0,
            ),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_on >= date_from,
            Transaction.occurred_on <= date_to,
            Transaction.kind != TransactionKind.transfer,
        )
        .group_by(bucket)
        .order_by(bucket)
    ).all()

    points = [
        TimelinePoint(
            period_start=row[0],
            income=_quantize(row[1]),
            expense=_quantize(row[2]),
            net=_quantize(row[1]) - _quantize(row[2]),
        )
        for row in rows
    ]
    return Timeline(granularity=granularity, points=points)


def budget_status(session: Session, user_id: int, month: date | None = None) -> BudgetStatus:
    """Насколько израсходован лимит по каждой категории за месяц."""
    period_start, period_end = month_bounds(month or today())

    spent_subquery = (
        select(Transaction.category_id, func.sum(Transaction.amount).label("spent"))
        .where(
            Transaction.user_id == user_id,
            Transaction.kind == TransactionKind.expense,
            Transaction.occurred_on >= period_start,
            Transaction.occurred_on <= period_end,
        )
        .group_by(Transaction.category_id)
        .subquery()
    )

    rows = session.execute(
        select(Budget, Category, func.coalesce(spent_subquery.c.spent, 0))
        .join(Category, Category.id == Budget.category_id)
        .outerjoin(spent_subquery, spent_subquery.c.category_id == Budget.category_id)
        .where(Budget.user_id == user_id)
        .order_by(Category.name)
    ).all()

    items: list[BudgetStatusItem] = []
    for budget, category, spent_raw in rows:
        limit_amount = _quantize(budget.limit_amount)
        spent = _quantize(spent_raw)
        usage = round(float(spent / limit_amount) * 100, 1) if limit_amount else 0.0
        items.append(
            BudgetStatusItem(
                category_id=category.id,
                category_name=category.name,
                color_slot=category.color_slot,
                limit_amount=limit_amount,
                spent=spent,
                remaining=limit_amount - spent,
                usage_pct=usage,
                is_over=spent > limit_amount,
            )
        )

    return BudgetStatus(
        month=period_start,
        items=items,
        total_limit=sum((item.limit_amount for item in items), ZERO),
        total_spent=sum((item.spent for item in items), ZERO),
    )
