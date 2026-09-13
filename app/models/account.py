from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AccountKind(StrEnum):
    """Тип счёта. Влияет только на отображение, не на логику расчётов."""

    cash = "cash"
    card = "card"
    savings = "savings"
    credit = "credit"


class Account(Base):
    """Кошелёк, карта, вклад — место, где лежат деньги.

    Текущий баланс намеренно НЕ хранится в колонке. Он всегда считается как
    initial_balance плюс движение по транзакциям (app/services/accounts.py).
    Хранимый баланс — классический источник рассинхрона: любая пропущенная
    или дважды применённая операция расходится с историей навсегда.
    """

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_accounts_user_id_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[AccountKind] = mapped_column(
        Enum(AccountKind, name="account_kind"), default=AccountKind.card
    )
    currency: Mapped[str] = mapped_column(String(3))
    initial_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0")
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r}>"
