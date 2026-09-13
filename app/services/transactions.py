"""Операции: создание, изменение, выборка с фильтрами."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionKind
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services.accounts import get_account
from app.services.categories import get_category
from app.services.errors import BusinessRuleError, NotFoundError

MAX_PAGE_SIZE = 200


@dataclass(slots=True)
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    account_id: int | None = None
    category_id: int | None = None
    kind: TransactionKind | None = None
    search: str | None = None


def _apply_filters[SelectT: Select[Any]](stmt: SelectT, filters: TransactionFilters) -> SelectT:
    """Один и тот же набор фильтров нужен и для выборки строк, и для COUNT(*).

    Обобщённый параметр сохраняет конкретный тип запроса: иначе COUNT
    возвращал бы «что-то из Transaction» вместо числа.
    """
    if filters.date_from is not None:
        stmt = stmt.where(Transaction.occurred_on >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Transaction.occurred_on <= filters.date_to)
    if filters.account_id is not None:
        # Счёт участвует в операции и как источник, и как получатель перевода —
        # иначе входящие переводы пропали бы из выписки по счёту.
        stmt = stmt.where(
            or_(
                Transaction.account_id == filters.account_id,
                Transaction.counter_account_id == filters.account_id,
            )
        )
    if filters.category_id is not None:
        stmt = stmt.where(Transaction.category_id == filters.category_id)
    if filters.kind is not None:
        stmt = stmt.where(Transaction.kind == filters.kind)
    if filters.search:
        stmt = stmt.where(Transaction.note.ilike(f"%{filters.search.strip()}%"))
    return stmt


def list_transactions(
    session: Session,
    user_id: int,
    filters: TransactionFilters,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Transaction], int]:
    """Страница операций и общее количество, подходящее под фильтры."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)

    base = select(Transaction).where(Transaction.user_id == user_id)
    base = _apply_filters(base, filters)

    total = session.scalar(
        _apply_filters(
            select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id),
            filters,
        )
    )

    items = session.scalars(
        base.order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return items, int(total or 0)


def get_transaction(session: Session, user_id: int, transaction_id: int) -> Transaction:
    transaction = session.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    if transaction is None:
        raise NotFoundError(f"Операция {transaction_id} не найдена")
    return transaction


def _validate_category(
    session: Session, user_id: int, category_id: int | None, kind: TransactionKind
) -> Category | None:
    if category_id is None:
        return None
    category = get_category(session, user_id, category_id)
    if category.kind.value != kind.value:
        raise BusinessRuleError(
            f"Категория «{category.name}» относится к типу «{category.kind.value}», "
            f"её нельзя использовать для операции типа «{kind.value}»"
        )
    return category


def create_transaction(session: Session, user_id: int, data: TransactionCreate) -> Transaction:
    # get_account бросит NotFoundError, если счёт чужой — это и есть проверка прав.
    get_account(session, user_id, data.account_id)
    if data.counter_account_id is not None:
        get_account(session, user_id, data.counter_account_id)
    _validate_category(session, user_id, data.category_id, data.kind)

    transaction = Transaction(
        user_id=user_id,
        kind=data.kind,
        amount=data.amount,
        account_id=data.account_id,
        counter_account_id=data.counter_account_id,
        category_id=data.category_id,
        occurred_on=data.occurred_on,
        note=data.note.strip() if data.note else None,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def update_transaction(
    session: Session, user_id: int, transaction_id: int, data: TransactionUpdate
) -> Transaction:
    """Изменить операцию.

    Тип операции (доход/расход/перевод) менять нельзя: у перевода другой набор
    обязательных полей, и «превращение» расхода в перевод на месте — верный
    способ получить строку, нарушающую CHECK-констрейнт. Нужен другой тип —
    удали операцию и создай новую.
    """
    transaction = get_transaction(session, user_id, transaction_id)
    payload = data.model_dump(exclude_unset=True)

    if "account_id" in payload:
        get_account(session, user_id, payload["account_id"])
        if transaction.counter_account_id == payload["account_id"]:
            raise BusinessRuleError("Счёт списания и счёт зачисления должны различаться")

    if "category_id" in payload:
        if transaction.kind is TransactionKind.transfer and payload["category_id"] is not None:
            raise BusinessRuleError("У перевода не бывает категории")
        _validate_category(session, user_id, payload["category_id"], transaction.kind)

    for field, value in payload.items():
        setattr(transaction, field, value.strip() if field == "note" and value else value)

    session.commit()
    session.refresh(transaction)
    return transaction


def delete_transaction(session: Session, user_id: int, transaction_id: int) -> None:
    transaction = get_transaction(session, user_id, transaction_id)
    session.delete(transaction)
    session.commit()
