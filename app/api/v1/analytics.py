from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUser, DbSession
from app.models import CategoryKind
from app.schemas.analytics import BudgetStatus, CategoryBreakdown, PeriodSummary, Timeline
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _resolve_period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """По умолчанию — текущий месяц: самый частый вопрос «сколько я потратил в этом месяце»."""
    if date_from is None or date_to is None:
        default_from, default_to = analytics.month_bounds(analytics.today())
        return date_from or default_from, date_to or default_to
    return date_from, date_to


@router.get("/summary", response_model=PeriodSummary)
def summary(
    user: CurrentUser,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> PeriodSummary:
    start, end = _resolve_period(date_from, date_to)
    return analytics.period_summary(session, user.id, start, end)


@router.get("/breakdown", response_model=CategoryBreakdown)
def breakdown(
    user: CurrentUser,
    session: DbSession,
    kind: CategoryKind = CategoryKind.expense,
    date_from: date | None = None,
    date_to: date | None = None,
) -> CategoryBreakdown:
    """Разрез по категориям. Категории сверх восьмой сворачиваются в «Остальное»."""
    start, end = _resolve_period(date_from, date_to)
    return analytics.category_breakdown(session, user.id, kind, start, end)


@router.get("/timeline", response_model=Timeline)
def timeline(
    user: CurrentUser,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = Query(default="month", pattern="^(day|week|month|year)$"),
) -> Timeline:
    start, end = _resolve_period(date_from, date_to)
    return analytics.timeline(session, user.id, start, end, granularity)


@router.get("/budget-status", response_model=BudgetStatus)
def budget_status(user: CurrentUser, session: DbSession, month: date | None = None) -> BudgetStatus:
    """Статус лимитов за месяц, в который попадает переданная дата."""
    return analytics.budget_status(session, user.id, month)
