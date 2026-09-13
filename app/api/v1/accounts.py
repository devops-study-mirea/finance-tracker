from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DbSession
from app.models import Account
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.services import accounts

router = APIRouter(prefix="/accounts", tags=["accounts"])

ZERO = Decimal("0.00")


def _to_response(account: Account, balance: Decimal) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        kind=account.kind,
        currency=account.currency,
        initial_balance=account.initial_balance,
        balance=balance,
        is_archived=account.is_archived,
    )


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    user: CurrentUser, session: DbSession, include_archived: bool = False
) -> list[AccountResponse]:
    balances = accounts.compute_balances(session, user.id)
    return [
        _to_response(account, balances.get(account.id, ZERO))
        for account in accounts.list_accounts(session, user.id, include_archived=include_archived)
    ]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, user: CurrentUser, session: DbSession) -> AccountResponse:
    account = accounts.create_account(session, user.id, data)
    return _to_response(account, Decimal(account.initial_balance))


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, user: CurrentUser, session: DbSession) -> AccountResponse:
    account = accounts.get_account(session, user.id, account_id)
    balances = accounts.compute_balances(session, user.id)
    return _to_response(account, balances.get(account.id, ZERO))


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int, data: AccountUpdate, user: CurrentUser, session: DbSession
) -> AccountResponse:
    account = accounts.update_account(session, user.id, account_id, data)
    balances = accounts.compute_balances(session, user.id)
    return _to_response(account, balances.get(account.id, ZERO))


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, user: CurrentUser, session: DbSession) -> None:
    accounts.delete_account(session, user.id, account_id)
