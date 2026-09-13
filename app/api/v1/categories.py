from __future__ import annotations

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DbSession
from app.models import CategoryKind
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services import categories

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    user: CurrentUser,
    session: DbSession,
    kind: CategoryKind | None = None,
    include_archived: bool = False,
) -> list[CategoryResponse]:
    rows = categories.list_categories(
        session, user.id, kind=kind, include_archived=include_archived
    )
    return [CategoryResponse.model_validate(row) for row in rows]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate, user: CurrentUser, session: DbSession
) -> CategoryResponse:
    return CategoryResponse.model_validate(categories.create_category(session, user.id, data))


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int, data: CategoryUpdate, user: CurrentUser, session: DbSession
) -> CategoryResponse:
    return CategoryResponse.model_validate(
        categories.update_category(session, user.id, category_id, data)
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, user: CurrentUser, session: DbSession) -> None:
    """Удалить категорию. Операции по ней сохранятся как «Без категории»."""
    categories.delete_category(session, user.id, category_id)
