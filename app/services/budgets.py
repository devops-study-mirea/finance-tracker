"""Месячные лимиты по категориям."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Budget, CategoryKind
from app.schemas.budget import BudgetCreate, BudgetUpdate
from app.services.categories import get_category
from app.services.errors import BusinessRuleError, ConflictError, NotFoundError


def list_budgets(session: Session, user_id: int) -> Sequence[Budget]:
    return session.scalars(
        select(Budget).where(Budget.user_id == user_id).order_by(Budget.id)
    ).all()


def get_budget(session: Session, user_id: int, budget_id: int) -> Budget:
    budget = session.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id))
    if budget is None:
        raise NotFoundError(f"Бюджет {budget_id} не найден")
    return budget


def create_budget(session: Session, user_id: int, data: BudgetCreate) -> Budget:
    category = get_category(session, user_id, data.category_id)
    if category.kind is not CategoryKind.expense:
        raise BusinessRuleError(
            "Лимит можно поставить только на категорию расходов: ограничивать доходы бессмысленно"
        )

    budget = Budget(user_id=user_id, category_id=data.category_id, limit_amount=data.limit_amount)
    session.add(budget)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"Для категории «{category.name}» лимит уже задан") from exc
    session.refresh(budget)
    return budget


def update_budget(session: Session, user_id: int, budget_id: int, data: BudgetUpdate) -> Budget:
    budget = get_budget(session, user_id, budget_id)
    budget.limit_amount = data.limit_amount
    session.commit()
    session.refresh(budget)
    return budget


def delete_budget(session: Session, user_id: int, budget_id: int) -> None:
    budget = get_budget(session, user_id, budget_id)
    session.delete(budget)
    session.commit()
