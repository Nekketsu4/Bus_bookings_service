"""
Тесты для воркера RabbitMQ.

Тестируем:
  - Успешную обработку confirmed/cancelled событий
  - Retry при временной ошибке (успех на 2-й попытке)
  - Исчерпание retry → исключение пробрасывается (→ nack → DLQ)
  - Хендлер DLQ логирует ERROR
"""

import logging

import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.events import BookingCancelledEvent
from app.services.worker import (
    _with_retry,
    MAX_ATTEMPTS,
    on_booking_cancelled,
    on_dead_letter,
)
from app.services.worker import on_booking_confirmed
from app.services.notification import NotificationService


# ── Вспомогательные фикстуры ──────────────────────────────────────────────────


def _make_confirmed_event():
    from app.schemas.events import BookingConfirmedEvent

    return BookingConfirmedEvent(
        booking_id=42,
        user_email="kadir@example.com",
        route="Москва → Махачкала (01.06.2030 08:00)",
    )


def _make_cancelled_event():

    return BookingCancelledEvent(
        booking_id=99,
        user_email="kadir@example.com",
    )


# ── _with_retry ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_with_retry_success_on_first_attempt():
    """Функция вызывается один раз, если нет ошибок."""
    mock_fn = AsyncMock()
    await _with_retry(mock_fn, "arg1", "arg2", event_name="test.event")

    mock_fn.assert_awaited_once_with("arg1", "arg2")


@pytest.mark.asyncio
async def test_with_retry_succeeds_on_second_attempt():
    """Если первая попытка упала — вторая должна пройти успешно."""
    mock_fn = AsyncMock(side_effect=[RuntimeError("временная ошибка"), None])

    # Патчим sleep чтобы тест не ждал реально
    with patch("app.services.worker.asyncio.sleep", new_callable=AsyncMock):
        await _with_retry(mock_fn, event_name="test.event")

    assert mock_fn.await_count == 2


@pytest.mark.asyncio
async def test_with_retry_raises_after_all_attempts_exhausted():
    """После MAX_ATTEMPTS неудачных попыток — исключение пробрасывается."""
    error = ConnectionError("сервис недоступен")
    mock_fn = AsyncMock(side_effect=error)

    with patch("app.services.worker.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ConnectionError, match="сервис недоступен"):
            await _with_retry(mock_fn, event_name="test.event")

    assert mock_fn.await_count == MAX_ATTEMPTS


# ── on_booking_confirmed ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_booking_confirmed_calls_notification():
    """Хендлер вызывает send_booking_confirmed с правильными аргументами."""

    event = _make_confirmed_event()

    with patch(
        "app.services.worker.notification_service.send_booking_confirmed",
        new_callable=AsyncMock,
    ) as mock_notify:
        await on_booking_confirmed(event)

    mock_notify.assert_awaited_once_with(
        event.user_email,
        event.booking_id,
        event.route,
    )


@pytest.mark.asyncio
async def test_on_booking_confirmed_retries_on_error():
    """При временной ошибке NotificationService хендлер делает retry."""

    event = _make_confirmed_event()

    with patch(
        "app.services.worker.notification_service.send_booking_confirmed",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("smtp error"), None],
    ) as mock_notify:
        with patch("app.services.worker.asyncio.sleep", new_callable=AsyncMock):
            await on_booking_confirmed(event)

    assert mock_notify.await_count == 2


@pytest.mark.asyncio
async def test_on_booking_confirmed_raises_after_exhausted_retries():
    """Если все retry провалились — исключение пробрасывается (→ nack → DLQ)."""

    event = _make_confirmed_event()

    with patch(
        "app.services.worker.notification_service.send_booking_confirmed",
        new_callable=AsyncMock,
        side_effect=RuntimeError("постоянная ошибка"),
    ):
        with patch("app.services.worker.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="постоянная ошибка"):
                await on_booking_confirmed(event)


# ── on_booking_cancelled ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_booking_cancelled_calls_notification():
    """Хендлер вызывает send_booking_cancelled с правильными аргументами."""

    event = _make_cancelled_event()

    with patch(
        "app.services.worker.notification_service.send_booking_cancelled",
        new_callable=AsyncMock,
    ) as mock_notify:
        await on_booking_cancelled(event)

    mock_notify.assert_awaited_once_with(
        event.user_email,
        event.booking_id,
    )


@pytest.mark.asyncio
async def test_on_booking_cancelled_raises_after_exhausted_retries():
    """Если все retry провалились — исключение пробрасывается."""

    event = _make_cancelled_event()

    with patch(
        "app.services.worker.notification_service.send_booking_cancelled",
        new_callable=AsyncMock,
        side_effect=RuntimeError("ошибка"),
    ):
        with patch("app.services.worker.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError):
                await on_booking_cancelled(event)


# ── on_dead_letter ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_dead_letter_logs_error(caplog):
    """DLQ-хендлер логирует сообщение с уровнем ERROR."""

    raw = b'{"booking_id": 42, "user_email": "kadir@example.com"}'

    with caplog.at_level(logging.ERROR, logger="app.services.worker"):
        await on_dead_letter(raw)

    assert any("Dead letter" in r.message for r in caplog.records)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


# ── NotificationService ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notification_send_booking_confirmed_logs(caplog):
    """send_booking_confirmed структурированно логирует отправку."""

    svc = NotificationService()

    with caplog.at_level(logging.INFO, logger="app.services.notification"):
        await svc.send_booking_confirmed(
            user_email="test@example.com",
            booking_id=1,
            route="Москва → Сочи",
        )

    assert any("[EMAIL]" in r.message for r in caplog.records)
    assert any("test@example.com" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_notification_send_booking_cancelled_logs(caplog):
    """send_booking_cancelled структурированно логирует отправку."""

    svc = NotificationService()

    with caplog.at_level(logging.INFO, logger="app.services.notification"):
        await svc.send_booking_cancelled(
            user_email="test@example.com",
            booking_id=7,
        )

    assert any("[EMAIL]" in r.message for r in caplog.records)
