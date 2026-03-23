"""
FastStream consumers (subscribers) for booking domain events.

Both handlers are registered on the shared `rabbit_broker` singleton
and start automatically when the broker connects in app lifespan.

In a larger project these would live in a separate worker process
launched with:  faststream run app.services.worker:fs_app
For now they run in-process alongside the FastAPI app so the repo
stays self-contained and easy to demo.
"""

import asyncio
import logging

from faststream import FastStream

from app.schemas.events import BookingCancelledEvent, BookingConfirmedEvent
from app.services.notification import notification_service
from app.services.broker import (
    EXCHANGE,
    QUEUE_CANCELLED,
    QUEUE_CONFIRMED,
    QUEUE_DLQ,
    rabbit_broker,
)

logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 3  # сколько раз пробуем до отправки в DLQ
RETRY_DELAY_SECONDS = 2  # пауза между попытками


async def _with_retry(coro_func, *args, event_name: str) -> None:
    """Выполняет корутину с повторными попытками при ошибке.

    Args:
        coro_func:  Async-функция для вызова.
        *args:      Аргументы для coro_func.
        event_name: Имя события для логов.

    Raises:
        Exception: Последнее исключение после исчерпания попыток.
                   FastStream перехватит его и сделает nack → DLQ.
    """
    last_exc: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await coro_func(*args)
            return  # успех — выходим
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "[WORKER] %s attempt %d/%d failed: %s",
                event_name,
                attempt,
                MAX_ATTEMPTS,
                exc,
            )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

    # Все попытки исчерпаны — пробрасываем, чтобы FastStream сделал nack
    logger.error(
        "[WORKER] %s exhausted all %d attempts, sending to DLQ",
        event_name,
        MAX_ATTEMPTS,
    )
    raise last_exc


# ── Subscribers ────────────────────────────────────────────────────────────────


@rabbit_broker.subscriber(QUEUE_CONFIRMED, EXCHANGE)
async def on_booking_confirmed(event: BookingConfirmedEvent) -> None:
    """Обрабатывает событие подтверждения бронирования.

    Отправляет email-уведомление пользователю.
    При ошибке — retry MAX_ATTEMPTS раз, затем nack → DLQ.
    """
    logger.info(
        "[WORKER] Processing booking.confirmed: booking_id=%d user=%s",
        event.booking_id,
        event.user_email,
    )

    await _with_retry(
        notification_service.send_booking_confirmed,
        event.user_email,
        event.booking_id,
        event.route,
        event_name=f"booking.confirmed#{event.booking_id}",
    )

    logger.info(
        "[WORKER] booking.confirmed handled: booking_id=%d",
        event.booking_id,
    )


@rabbit_broker.subscriber(QUEUE_CANCELLED, EXCHANGE)
async def on_booking_cancelled(event: BookingCancelledEvent) -> None:
    """Обрабатывает событие отмены бронирования.

    Отправляет email-уведомление и инициирует возврат средств.
    При ошибке — retry MAX_ATTEMPTS раз, затем nack → DLQ.
    """
    logger.info(
        "[WORKER] Processing booking.cancelled: booking_id=%d user=%s",
        event.booking_id,
        event.user_email,
    )

    await _with_retry(
        notification_service.send_booking_cancelled,
        event.user_email,
        event.booking_id,
        event_name=f"booking.cancelled#{event.booking_id}",
    )

    logger.info(
        "[WORKER] booking.cancelled handled: booking_id=%d",
        event.booking_id,
    )


@rabbit_broker.subscriber(QUEUE_DLQ)
async def on_dead_letter(body: bytes) -> None:
    """Хендлер Dead Letter Queue.

    Сообщения сюда попадают только если все retry провалились.
    Логируем как ERROR — это сигнал для систем мониторинга (Sentry, Datadog).

    В продакшене здесь можно:
    - Отправить алерт в Slack/PagerDuty
    - Сохранить в БД для ручного разбора
    - Повторить через длинный интервал (exponential backoff)
    """
    logger.error(
        "[WORKER] Dead letter received: %s",
        body.decode("utf-8", errors="replace"),
    )
    # TODO: отправить алерт в Slack/PagerDuty


# ── Standalone FastStream app (for `faststream run`) ──────────────────────────

fs_app = FastStream(rabbit_broker)
