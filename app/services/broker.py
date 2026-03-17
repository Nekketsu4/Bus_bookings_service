"""
RabbitMQ broker via FastStream.

Topology:
  Exchange : booking.events  (topic, durable)
  Queues   : booking.confirmed.queue  → routing key "booking.confirmed"
             booking.cancelled.queue  → routing key "booking.cancelled"

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
    name="booking.events",
    type=ExchangeType.TOPIC,
    durable=True,
)

QUEUE_CONFIRMED = RabbitQueue(
    name="booking.confirmed.queue",
    routing_key="booking.confirmed",
    durable=True,
)

QUEUE_CANCELLED = RabbitQueue(
    name="booking.cancelled.queue",
    routing_key="booking.cancelled",
    durable=True,
)

# ── Broker singleton ───────────────────────────────────────────────────────────

rabbit_broker = RabbitBroker(
    url=settings.RABBITMQ_URL,
    logger=logger,
)


# ── FastAPI dependency ─────────────────────────────────────────────────────────


async def get_broker() -> RabbitBroker:
    return rabbit_broker
