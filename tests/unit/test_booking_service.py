"""
Unit tests for BookingService.
No real DB, broker, or cache — everything is mocked.
FastStream RabbitBroker is replaced with a simple AsyncMock.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from fastapi import HTTPException

from app.models.booking import Booking, BookingStatus, Route, Seat, User
from app.services.booking_services import BookingService

# ── Object factories ───────────────────────────────────────────────────────────


def _make_route(active=True) -> Route:
    route = Route()
    route.id = 1
    route.origin = "Москва"
    route.destination = "Махачкала"
    route.price = 1500.00
    route.is_active = active
    route.departure_at = datetime(2030, 6, 1, tzinfo=timezone.utc)
    route.arrival_at = datetime(2030, 6, 1, tzinfo=timezone.utc)
    return route


def _make_seat(is_booked=False, route_id=1) -> Seat:
    seat = Seat()
    seat.id = 10
    seat.route_id = route_id
    seat.seat_number = 5
    seat.is_booked = is_booked
    return seat


def _make_user() -> User:
    user = User()
    user.id = 42
    user.email = "kadir@example.com"
    user.full_name = "Kadyr Aziev"
    return user


def _make_booking(status=BookingStatus.CONFIRMED) -> Booking:
    b = Booking()
    b.id = 99
    b.user_id = 42
    b.route_id = 1
    b.seat_id = 10
    b.total_price = 1500.00
    b.status = status
    return b


def _make_service(route, seat, user, booking) -> BookingService:
    """BookingService with all repos and infra mocked."""
    db = AsyncMock()
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.delete_pattern = AsyncMock()

    # FastStream RabbitBroker stub — only .publish() is called
    broker = AsyncMock()
    broker.publish = AsyncMock()

    service = BookingService(db=db, broker=broker, cache=cache)

    service._route = AsyncMock()
    service._route.get_by_id = AsyncMock(return_value=route)

    service._seat = AsyncMock()
    service._seat.get_by_id = AsyncMock(return_value=seat)
    service._seat.mark_booked = AsyncMock()
    service._seat.mark_free = AsyncMock()

    service._user = AsyncMock()
    service._user.get_by_id = AsyncMock(return_value=user)

    service._booking = AsyncMock()
    service._booking.create = AsyncMock(return_value=booking)
    service._booking.get_by_id = AsyncMock(return_value=booking)
    service._booking.update_status = AsyncMock(return_value=booking)

    return service


# ── create_booking ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_booking_success():
    """Тест на успешную бронь места определенного рейса"""
    service = _make_service(_make_route(), _make_seat(), _make_user(), _make_booking())
    result = await service.create_booking(user_id=42, route_id=1, seat_id=10)

    assert result.status == BookingStatus.CONFIRMED
    service._seat.mark_booked.assert_awaited_once_with(10)

    # FastStream broker.publish called with BookingConfirmedEvent
    service._broker.publish.assert_awaited_once()
    event = service._broker.publish.call_args.args[0]
    assert event["booking_id"] == 99
    assert event["user_email"] == "kadir@example.com"


@pytest.mark.asyncio
async def test_create_booking_seat_already_booked():
    """Проверка что забронированное место нельзя занять повторно"""
    service = _make_service(
        _make_route(), _make_seat(is_booked=True), _make_user(), _make_booking()
    )
    with pytest.raises(HTTPException) as exc:
        await service.create_booking(user_id=42, route_id=1, seat_id=10)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_booking_route_inactive():
    """Проверка что нельзя сделать бронь на удаленый рейс"""
    service = _make_service(
        _make_route(active=False), _make_seat(), _make_user(), _make_booking()
    )
    with pytest.raises(HTTPException) as exc:
        await service.create_booking(user_id=42, route_id=1, seat_id=10)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_booking_seat_wrong_route():
    """Проверка что нельзя сделать бронь на не корректно введеный рейс"""
    service = _make_service(
        _make_route(), _make_seat(route_id=999), _make_user(), _make_booking()
    )
    with pytest.raises(HTTPException) as exc:
        await service.create_booking(user_id=42, route_id=1, seat_id=10)
    assert exc.value.status_code == 404


# ── cancel_booking ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_booking_success():
    """Тест успешной отмены брони"""
    booking = _make_booking(BookingStatus.CONFIRMED)
    cancelled = _make_booking(BookingStatus.CANCELLED)
    service = _make_service(_make_route(), _make_seat(), _make_user(), booking)
    service._booking.update_status = AsyncMock(return_value=cancelled)

    result = await service.cancel_booking(booking_id=99, user_id=42)

    assert result.status == BookingStatus.CANCELLED
    service._seat.mark_free.assert_awaited_once_with(booking.seat_id)

    # FastStream broker.publish called with BookingCancelledEvent
    service._broker.publish.assert_awaited_once()
    event = service._broker.publish.call_args.args[0]
    assert event.booking_id == 99


@pytest.mark.asyncio
async def test_cancel_booking_wrong_user():
    """
    Проверка вызова исключения при попытке отменить бронь
    другим юзером,
    """
    booking = _make_booking()
    booking.user_id = 999
    service = _make_service(_make_route(), _make_seat(), _make_user(), booking)
    with pytest.raises(HTTPException) as exc:
        await service.cancel_booking(booking_id=99, user_id=42)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_already_cancelled():
    """
    Проверка вызова исключения при попытке отменить уже отмененную бронь
    """
    service = _make_service(
        _make_route(),
        _make_seat(),
        _make_user(),
        _make_booking(BookingStatus.CANCELLED),
    )
    with pytest.raises(HTTPException) as exc:
        await service.cancel_booking(booking_id=99, user_id=42)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_cancel_booking_not_found():
    """
    Проверказ вызова исключения при попытке отменить не существующую бронь
    """
    service = _make_service(_make_route(), _make_seat(), _make_user(), _make_booking())
    service._booking.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await service.cancel_booking(booking_id=999, user_id=42)
    assert exc.value.status_code == 404
