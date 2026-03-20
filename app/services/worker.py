"""
FastStream consumers (subscribers) for booking domain events.

Both handlers are registered on the shared `rabbit_broker` singleton
and start automatically when the broker connects in app lifespan.

In a larger project these would live in a separate worker process
launched with:  faststream run app.services.worker:fs_app
For now they run in-process alongside the FastAPI app so the repo
stays self-contained and easy to demo.
"""

import logging

from faststream import FastStream

from app.schemas.events import BookingCancelledEvent, BookingConfirmedEvent
from app.services.broker import (
    EXCHANGE,
    QUEUE_CANCELLED,
    QUEUE_CONFIRMED,
    rabbit_broker,
)

logger = logging.getLogger(__name__)

# ── Subscribers ────────────────────────────────────────────────────────────────


@rabbit_broker.subscriber(QUEUE_CONFIRMED, EXCHANGE)
async def on_booking_confirmed(event: BookingConfirmedEvent) -> None:
    """
    Handle booking.confirmed events.
    In production: send confirmation email, push notification, etc.
    """
    logger.info(
        "[WORKER] Booking #%d confirmed for %s — route: %s",
        event.booking_id,
        event.user_email,
        event.route,
    )
    # TODO: integrate with email/SMS service


@rabbit_broker.subscriber(QUEUE_CANCELLED, EXCHANGE)
async def on_booking_cancelled(event: BookingCancelledEvent) -> None:
    """
    Handle booking.cancelled events.
    In production: send cancellation email, trigger refund, etc.
    """
    logger.info(
        "[WORKER] Booking #%d cancelled for %s",
        event.booking_id,
        event.user_email,
    )
    # TODO: trigger refund flow


# ── Standalone FastStream app (for `faststream run`) ──────────────────────────

fs_app = FastStream(rabbit_broker)
