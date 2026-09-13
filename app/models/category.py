from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CategoryKind(StrEnum):
    income = "income"
    expense = "expense"


class Category(Base):
    """Категория дохода или расхода.

    parent_id позволяет строить двухуровневую структуру («Транспорт» →
    «Такси»), но вся аналитика на этапе 2 работает по плоскому списку.
    Иерархическая свёртка — задел на будущее.
    """

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "name", name="uq_categories_user_id_kind_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[CategoryKind] = mapped_column(Enum(CategoryKind, name="category_kind"))
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # Номер слота палитры, а не hex: см. app/palette.py.
    color_slot: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} kind={self.kind.value}>"
