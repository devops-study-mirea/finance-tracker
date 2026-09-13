from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.account import Account
from app.models.base import Base
from app.models.category import Category


class TransactionKind(StrEnum):
    income = "income"
    expense = "expense"
    transfer = "transfer"


class Transaction(Base):
    """Одна финансовая операция.

    Перевод между своими счетами хранится ОДНОЙ строкой: account_id — откуда,
    counter_account_id — куда. Альтернатива (две строки, расход и доход) требует
    их синхронного создания и удаления и разъезжается при любом сбое на середине.
    Одна строка делает перевод атомарным по построению.

    amount всегда положительный; направление задаёт kind. Знак внутри суммы —
    источник ошибок вида «минус на минус» в отчётах.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # Перевод обязан иметь счёт-получатель, отличный от исходного,
        # и не должен иметь категорию. Обычная операция — наоборот.
        CheckConstraint(
            "(kind = 'transfer' AND counter_account_id IS NOT NULL "
            "AND counter_account_id <> account_id AND category_id IS NULL) "
            "OR (kind <> 'transfer' AND counter_account_id IS NULL)",
            name="transfer_shape",
        ),
        # Главный индекс приложения: почти каждый запрос — «операции
        # пользователя X за период Y», отсортированные по дате убывания.
        Index("ix_transactions_user_id_occurred_on", "user_id", "occurred_on"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[TransactionKind] = mapped_column(Enum(TransactionKind, name="transaction_kind"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    # RESTRICT: счёт с историей операций нельзя удалить молча — иначе исчезнут
    # деньги из отчётов. Приложение предложит архивировать счёт вместо удаления.
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    counter_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    # SET NULL: удаление категории не должно уничтожать саму операцию —
    # она просто становится «Без категории».
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    occurred_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(foreign_keys=[account_id], lazy="joined")
    counter_account: Mapped[Account | None] = relationship(
        foreign_keys=[counter_account_id], lazy="joined"
    )
    category: Mapped[Category | None] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} {self.kind.value} {self.amount}>"
