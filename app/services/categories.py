"""Категории доходов и расходов."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, CategoryKind
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services.errors import BusinessRuleError, ConflictError, NotFoundError


def list_categories(
    session: Session,
    user_id: int,
    *,
    kind: CategoryKind | None = None,
    include_archived: bool = False,
) -> Sequence[Category]:
    stmt = select(Category).where(Category.user_id == user_id)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    if not include_archived:
        stmt = stmt.where(Category.is_archived.is_(False))
    return session.scalars(stmt.order_by(Category.kind, Category.name)).all()


def get_category(session: Session, user_id: int, category_id: int) -> Category:
    category = session.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        raise NotFoundError(f"Категория {category_id} не найдена")
    return category


def create_category(session: Session, user_id: int, data: CategoryCreate) -> Category:
    if data.parent_id is not None:
        parent = get_category(session, user_id, data.parent_id)
        if parent.kind is not data.kind:
            raise BusinessRuleError("Родительская категория должна быть того же типа")

    category = Category(
        user_id=user_id,
        name=data.name.strip(),
        kind=data.kind,
        parent_id=data.parent_id,
        color_slot=data.color_slot,
    )
    session.add(category)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"Категория «{data.name}» уже существует") from exc
    session.refresh(category)
    return category


def update_category(
    session: Session, user_id: int, category_id: int, data: CategoryUpdate
) -> Category:
    category = get_category(session, user_id, category_id)
    payload = data.model_dump(exclude_unset=True)

    if payload.get("parent_id") == category_id:
        raise BusinessRuleError("Категория не может быть родителем сама себе")

    for field, value in payload.items():
        setattr(category, field, value.strip() if field == "name" else value)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("Категория с таким названием уже существует") from exc
    session.refresh(category)
    return category


def delete_category(session: Session, user_id: int, category_id: int) -> None:
    """Удалить категорию.

    Операции по ней не удаляются — они становятся «Без категории»
    (ON DELETE SET NULL). Связанный бюджет удаляется каскадом.
    """
    category = get_category(session, user_id, category_id)
    session.delete(category)
    session.commit()
