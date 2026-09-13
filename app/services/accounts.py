"""Счета и расчёт остатков."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Account, Transaction, TransactionKind
from app.schemas.account import AccountCreate, AccountUpdate
from app.services.errors import BusinessRuleError, ConflictError, NotFoundError

ZERO = Decimal("0.00")


def list_accounts(
    session: Session, user_id: int, *, include_archived: bool = False
) -> Sequence[Account]:
    stmt = select(Account).where(Account.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    return session.scalars(stmt.order_by(Account.is_archived, Account.id)).all()


def get_account(session: Session, user_id: int, account_id: int) -> Account:
    account = session.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    if account is None:
        raise NotFoundError(f"Счёт {account_id} не найден")
    return account


def create_account(session: Session, user_id: int, data: AccountCreate) -> Account:
    account = Account(
        user_id=user_id,
        name=data.name.strip(),
        kind=data.kind,
        currency=data.currency.upper(),
        initial_balance=data.initial_balance,
    )
    session.add(account)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"Счёт с названием «{data.name}» уже существует") from exc
    session.refresh(account)
    return account


def update_account(session: Session, user_id: int, account_id: int, data: AccountUpdate) -> Account:
    account = get_account(session, user_id, account_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value.strip() if field == "name" else value)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("Счёт с таким названием уже существует") from exc
    session.refresh(account)
    return account


def delete_account(session: Session, user_id: int, account_id: int) -> None:
    """Удалить счёт. Счёт с историей операций удалить нельзя — только архивировать."""
    account = get_account(session, user_id, account_id)
    used = session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            or_(
                Transaction.account_id == account_id,
                Transaction.counter_account_id == account_id,
            )
        )
    )
    if used:
        raise BusinessRuleError(
            f"По счёту есть операции ({used} шт.). Удаление стёрло бы их из отчётов — "
            f"архивируй счёт вместо удаления."
        )
    session.delete(account)
    session.commit()


def compute_balances(session: Session, user_id: int) -> dict[int, Decimal]:
    """Остатки по всем счетам пользователя: {account_id: баланс}.

    Считается двумя агрегатами вместо запроса на каждый счёт — иначе на 20 счетах
    получаем 20 запросов (классическая проблема N+1), и дашборд начинает тормозить
    ровно тогда, когда данных стало достаточно, чтобы он был полезен.
    """
    balances: dict[int, Decimal] = {
        account.id: Decimal(account.initial_balance)
        for account in session.scalars(select(Account).where(Account.user_id == user_id))
    }

    # Движение по счёту-источнику: доход прибавляет, расход и перевод вычитают.
    own_movement = session.execute(
        select(
            Transaction.account_id,
            func.sum(
                case(
                    (Transaction.kind == TransactionKind.income, Transaction.amount),
                    else_=-Transaction.amount,
                )
            ),
        )
        .where(Transaction.user_id == user_id)
        .group_by(Transaction.account_id)
    ).all()

    # Приход на счёт-получатель перевода.
    incoming_transfers = session.execute(
        select(Transaction.counter_account_id, func.sum(Transaction.amount))
        .where(
            Transaction.user_id == user_id,
            Transaction.kind == TransactionKind.transfer,
        )
        .group_by(Transaction.counter_account_id)
    ).all()

    for account_id, delta in own_movement:
        if account_id in balances and delta is not None:
            balances[account_id] += Decimal(delta)

    for account_id, delta in incoming_transfers:
        if account_id in balances and delta is not None:
            balances[account_id] += Decimal(delta)

    return {account_id: balance.quantize(ZERO) for account_id, balance in balances.items()}


def total_balance(balances: dict[int, Decimal]) -> Decimal:
    """Сумма по всем счетам.

    Корректно только пока все счета в одной валюте. Мультивалютность требует
    курсов на дату операции — сознательно отложено, см. docs/ROADMAP.md.
    """
    return sum(balances.values(), ZERO)
