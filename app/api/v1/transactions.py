from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.models import TransactionKind
from app.schemas.transaction import (
    TransactionCreate,
    TransactionPage,
    TransactionResponse,
    TransactionUpdate,
)
from app.services import transactions
from app.services.transactions import MAX_PAGE_SIZE, TransactionFilters

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage)
def list_transactions(
    user: CurrentUser,
    session: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    kind: TransactionKind | None = None,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> TransactionPage:
    filters = TransactionFilters(
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        category_id=category_id,
        kind=kind,
        search=search,
    )
    items, total = transactions.list_transactions(
        session, user.id, filters, limit=limit, offset=offset
    )
    return TransactionPage(
        items=[TransactionResponse.from_model(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionCreate, user: CurrentUser, session: DbSession
) -> TransactionResponse:
    return TransactionResponse.from_model(transactions.create_transaction(session, user.id, data))


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int, user: CurrentUser, session: DbSession
) -> TransactionResponse:
    return TransactionResponse.from_model(
        transactions.get_transaction(session, user.id, transaction_id)
    )


@router.patch("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int, data: TransactionUpdate, user: CurrentUser, session: DbSession
) -> TransactionResponse:
    return TransactionResponse.from_model(
        transactions.update_transaction(session, user.id, transaction_id, data)
    )


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, user: CurrentUser, session: DbSession) -> None:
    transactions.delete_transaction(session, user.id, transaction_id)
