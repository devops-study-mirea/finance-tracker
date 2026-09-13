"""Форматирование денег и разбор пользовательского ввода."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.palette import NEUTRAL_LIGHT, SLOT_COUNT, slot_hex
from app.services.errors import DomainError
from app.web.routes import NBSP, _decimal, format_money


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0"), f"0,00{NBSP}₽"),
        (Decimal("1500"), f"1{NBSP}500,00{NBSP}₽"),
        (Decimal("1234567.89"), f"1{NBSP}234{NBSP}567,89{NBSP}₽"),
        (Decimal("-250.5"), f"−250,50{NBSP}₽"),
        (None, f"0,00{NBSP}₽"),
    ],
)
def test_format_money(value, expected):
    assert format_money(value) == expected


def test_format_money_uses_currency_symbol():
    assert format_money(Decimal("10"), "USD").endswith("$")
    assert format_money(Decimal("10"), "XYZ").endswith("XYZ")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1500", Decimal("1500")),
        ("1500.50", Decimal("1500.50")),
        ("1500,50", Decimal("1500.50")),  # русская раскладка
        (" 1 500,50 ", Decimal("1500.50")),
    ],
)
def test_decimal_parsing_accepts_human_input(raw, expected):
    assert _decimal(raw) == expected


def test_decimal_parsing_rejects_nonsense():
    with pytest.raises(DomainError):
        _decimal("много денег")


def test_palette_slots_resolve():
    for slot in range(SLOT_COUNT):
        assert slot_hex(slot).startswith("#")
        assert slot_hex(slot, dark=True).startswith("#")


def test_unknown_palette_slot_falls_back_to_neutral():
    assert slot_hex(None) == NEUTRAL_LIGHT
    assert slot_hex(99) == NEUTRAL_LIGHT
