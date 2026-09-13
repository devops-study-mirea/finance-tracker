"""Наполнение базы демонстрационными данными.

Запуск:  make demo
Логин:   demo@local / demo12345

Скрипт удаляет и пересоздаёт демо-пользователя целиком, поэтому его можно
запускать сколько угодно раз с одинаковым результатом. Реальные аккаунты
он не трогает: работает строго по email demo@local.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Account,
    Budget,
    Category,
    CategoryKind,
    Transaction,
    TransactionKind,
    User,
)
from app.services import users

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"
MONTHS_OF_HISTORY = 6

# (категория, минимум, максимум, сколько раз в месяц)
EXPENSE_PROFILE: list[tuple[str, int, int, int]] = [
    ("Продукты", 800, 4500, 12),
    ("Кафе и рестораны", 400, 2500, 6),
    ("Транспорт", 60, 900, 14),
    ("Жильё и коммуналка", 28000, 32000, 1),
    ("Связь и интернет", 700, 1400, 2),
    ("Здоровье", 500, 6000, 1),
    ("Одежда", 1500, 9000, 1),
    ("Развлечения", 500, 4000, 3),
    ("Подписки", 200, 900, 4),
    ("Образование", 2000, 12000, 1),
]

INCOME_PROFILE: list[tuple[str, int, int, int]] = [
    ("Зарплата", 145000, 145000, 1),
    ("Подработка", 8000, 45000, 1),
]

# Наличными платят за повседневные мелочи, а не за аренду и учёбу.
# Без этого ограничения демо-кошелёк уходит в глубокий минус и выглядит
# как ошибка расчёта, хотя арифметика верна.
CASH_CATEGORIES = {"Продукты", "Кафе и рестораны", "Транспорт", "Развлечения"}
CASH_SHARE = 0.35

BUDGETS = {
    "Продукты": Decimal("45000"),
    "Кафе и рестораны": Decimal("12000"),
    "Транспорт": Decimal("8000"),
    "Развлечения": Decimal("10000"),
    "Подписки": Decimal("2500"),
}


def main() -> int:
    random.seed(20260902)  # одинаковые данные при каждом запуске

    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing is not None:
            session.delete(existing)  # каскадом уходят счета, категории и операции
            session.commit()
            print(f"Прежний {DEMO_EMAIL} удалён")

        user = users.register(session, DEMO_EMAIL, DEMO_PASSWORD)

        accounts = {
            account.name: account
            for account in session.scalars(select(Account).where(Account.user_id == user.id))
        }
        categories = {
            (category.kind, category.name): category
            for category in session.scalars(select(Category).where(Category.user_id == user.id))
        }

        card = accounts["Карта"]
        cash = accounts["Наличные"]
        card.initial_balance = Decimal("35000")

        today = date.today()  # noqa: DTZ011 — демо-данные, часовой пояс неважен
        first_month = (today.replace(day=1) - timedelta(days=31 * (MONTHS_OF_HISTORY - 1))).replace(
            day=1
        )

        created = 0
        month_start = first_month
        while month_start <= today:
            days_in_month = (
                month_start.replace(
                    year=month_start.year + month_start.month // 12,
                    month=month_start.month % 12 + 1,
                    day=1,
                )
                - timedelta(days=1)
            ).day

            # В текущем (незакончившемся) месяце даты берём только из уже
            # прошедших дней. Иначе почти все операции месяца выпадают на
            # будущее, отбрасываются, и дашборд выглядит пустым.
            is_current_month = (month_start.year, month_start.month) == (today.year, today.month)
            last_day = today.day if is_current_month else min(28, days_in_month)

            for name, low, high, times in INCOME_PROFILE:
                category = categories[(CategoryKind.income, name)]
                for _ in range(times):
                    occurred = month_start.replace(day=random.randint(1, last_day))
                    session.add(
                        Transaction(
                            user_id=user.id,
                            kind=TransactionKind.income,
                            amount=Decimal(random.randint(low, high)),
                            account_id=card.id,
                            category_id=category.id,
                            occurred_on=occurred,
                            note=None,
                        )
                    )
                    created += 1

            for name, low, high, times in EXPENSE_PROFILE:
                category = categories[(CategoryKind.expense, name)]
                for _ in range(times):
                    occurred = month_start.replace(day=random.randint(1, last_day))
                    session.add(
                        Transaction(
                            user_id=user.id,
                            kind=TransactionKind.expense,
                            amount=Decimal(random.randint(low, high)),
                            account_id=(
                                cash.id
                                if name in CASH_CATEGORIES and random.random() < CASH_SHARE
                                else card.id
                            ),
                            category_id=category.id,
                            occurred_on=occurred,
                            note=None,
                        )
                    )
                    created += 1

            # Раз в месяц снимаем наличные — это перевод, а не расход.
            withdrawal_day = min(20, last_day)
            if month_start.replace(day=withdrawal_day) <= today:
                session.add(
                    Transaction(
                        user_id=user.id,
                        kind=TransactionKind.transfer,
                        amount=Decimal(random.choice([20000, 25000, 30000])),
                        account_id=card.id,
                        counter_account_id=cash.id,
                        occurred_on=month_start.replace(day=withdrawal_day),
                        note="Снятие в банкомате",
                    )
                )
                created += 1

            month_start = (month_start + timedelta(days=32)).replace(day=1)

        for name, limit in BUDGETS.items():
            session.add(
                Budget(
                    user_id=user.id,
                    category_id=categories[(CategoryKind.expense, name)].id,
                    limit_amount=limit,
                )
            )

        session.commit()

    print(f"Готово: создано {created} операций за {MONTHS_OF_HISTORY} месяцев")
    print(f"Вход: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
