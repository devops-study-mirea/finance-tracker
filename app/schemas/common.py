"""Общие типы для схем."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

# Денежная сумма: строго положительная, максимум два знака после запятой.
# Decimal, а не float — 0.1 + 0.2 в float даёт 0.30000000000000004,
# и на тысяче транзакций отчёт разъезжается с реальностью.
MoneyAmount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]

# Баланс может быть отрицательным (кредитка, овердрафт).
MoneyBalance = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]

CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")]
ColorHex = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
