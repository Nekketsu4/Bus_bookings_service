"""
RabbitMQ broker via FastStream.

Topology:
    Exchange : booking.events  (topic, durable)
    Queues   : booking.confirmed.queue  → routing key "booking.confirmed"
               booking.cancelled.queue  → routing key "booking.cancelled"
               booking.dlq              ← dead-letter queue для провальных сообщений

    Dead Letter Flow:
    Если хендлер бросает исключение → FastStream делает nack → RabbitMQ
    перекладывает сообщение в booking.dlq для ручного разбора.

Publisher : FastStream RabbitBroker (used by BookingService)
Consumer  : see app/services/worker.py  (runs inside the same process)
"""

import logging

from faststream.rabbit import (
    ExchangeType,
    RabbitBroker,
    RabbitExchange,
    RabbitQueue,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Topology declarations ──────────────────────────────────────────────────────

EXCHANGE = RabbitExchange(
    name="booking.events", type=ExchangeType.TOPIC, durable=True, declare=True
)

# Dead Letter Queue — принимает сообщения, которые не удалось обработать.
# Отдельный exchange нужен потому что RabbitMQ требует явный DLX.
DEAD_LETTER_EXCHANGE = RabbitExchange(
    name="booking.dlx", type=ExchangeType.DIRECT, durable=True, declare=True
)

QUEUE_DLQ = RabbitQueue(
    name="booking.dlq",
    routing_key="booking.dead",
    durable=True,
    arguments={},
)

QUEUE_CONFIRMED = RabbitQueue(
    name="booking.confirmed.queue",
    routing_key="booking.confirmed",
    durable=True,
    arguments={
        # Если сообщение отклонено — переложить в DLX
        "x-dead-letter-exchange": "booking.dlx",
        "x-dead-letter-routing-key": "booking.dead",
    },
)

QUEUE_CANCELLED = RabbitQueue(
    name="booking.cancelled.queue",
    routing_key="booking.cancelled",
    durable=True,
    arguments={
        # Если сообщение отклонено — переложить в DLX
        "x-dead-letter-exchange": "booking.dlx",
        "x-dead-letter-routing-key": "booking.dead",
    },
)

# ── Broker singleton ───────────────────────────────────────────────────────────

rabbit_broker = RabbitBroker(
    url=settings.RABBITMQ_URL,
    logger=logger,
)


# ── FastAPI dependency ─────────────────────────────────────────────────────────


async def get_broker() -> RabbitBroker:
    return rabbit_broker
