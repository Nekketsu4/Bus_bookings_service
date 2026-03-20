"""Unit tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas.route_schemas import RouteCreate
from app.schemas.user_schemas import UserRegister


# ── UserRegister ──────────────────────────────────────────────────────────────


def test_user_register_valid():
    """Проверка корректности формата почты"""
    u = UserRegister(
        email="test@example.com",
        password="securepass",
        first_name="Aziev",
        last_name="Kadir",
        username="Some",
    )
    assert u.email == "test@example.com"


def test_user_register_short_password():
    """Проверка вызова исключения если длина названия почты короткая"""
    with pytest.raises(ValidationError):
        UserRegister(
            email="a@b.com",
            password="short",
            first_name="Aziev",
            last_name="Kadir",
            username="Some",
        )


def test_user_register_invalid_email():
    """Проверка вызова исключения если введена некорректная почта"""
    with pytest.raises(ValidationError):
        UserRegister(
            email="not-an-email",
            password="securepass",
            first_name="Aziev",
            last_name="Kadir",
            username="Some",
        )


def test_route_create_arrival_before_departure():
    """
    Проверка что если даты отбытия указать больше чем прибытие
    вызовет исключение
    """
    with pytest.raises(ValidationError, match="arrival_at must be after departure_at"):
        RouteCreate(
            origin="Москва",
            destination="Махачкала",
            departure_at="05-01-2026",
            arrival_at="01-01-2026",  # earlier than departure
            total_seats=40,
            price="1500.00",
        )


def test_route_create_zero_seats():
    """Проверка что нельзя создать рейс с нулевым количеством мест"""
    with pytest.raises(ValidationError):
        RouteCreate(
            origin="Москва",
            destination="Махачкала",
            departure_at="05-01-2026",
            arrival_at="01-01-2026",
            total_seats=0,
            price="1500.00",
        )


def test_route_create_negative_price():
    """Проверяем что нельзя оплатить отрицательную сумму"""
    with pytest.raises(ValidationError):
        RouteCreate(
            origin="Москва",
            destination="Махачкала",
            departure_at="05-01-2026",
            arrival_at="05-01-2026",
            total_seats=10,
            price="-100",
        )
