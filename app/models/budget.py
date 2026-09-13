from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.category import Category


class Budget(Base):
    """Месячный лимит трат по категории.

    Лимит один на категорию и действует каждый месяц. Помесячные
    переопределения («в декабре на подарки больше») — осознанно вынесены
    за скобки первой версии: они требуют отдельной таблицы периодов,
    а пользы дают мало, пока нет истории.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", name="uq_budgets_user_id_category_id"),
        CheckConstraint("limit_amount > 0", name="limit_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="CASCADE")
    )
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<Budget id={self.id} category_id={self.category_id} limit={self.limit_amount}>"
