from __future__ import annotations

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DbSession
from app.models import Budget
from app.schemas.budget import BudgetCreate, BudgetResponse, BudgetUpdate
from app.services import budgets

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _to_response(budget: Budget) -> BudgetResponse:
    return BudgetResponse(
        id=budget.id,
        category_id=budget.category_id,
        category_name=budget.category.name,
        limit_amount=budget.limit_amount,
    )


@router.get("", response_model=list[BudgetResponse])
def list_budgets(user: CurrentUser, session: DbSession) -> list[BudgetResponse]:
    return [_to_response(budget) for budget in budgets.list_budgets(session, user.id)]


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(data: BudgetCreate, user: CurrentUser, session: DbSession) -> BudgetResponse:
    return _to_response(budgets.create_budget(session, user.id, data))


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: int, data: BudgetUpdate, user: CurrentUser, session: DbSession
) -> BudgetResponse:
    return _to_response(budgets.update_budget(session, user.id, budget_id, data))


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: int, user: CurrentUser, session: DbSession) -> None:
    budgets.delete_budget(session, user.id, budget_id)
