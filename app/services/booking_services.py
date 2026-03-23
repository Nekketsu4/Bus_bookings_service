import logging

from fastapi import HTTPException, status
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.repositories.booking_repo import BookingRepository
from app.repositories.route_repo import RouteRepository, SeatRepository
from app.repositories.user_repo import UserRepository
from app.schemas.events import BookingCancelledEvent, BookingConfirmedEvent
from app.services.broker import EXCHANGE, QUEUE_CANCELLED, QUEUE_CONFIRMED
from app.services.cache import CacheService


logger = logging.getLogger(__name__)


class BookingService:
    def __init__(
        self,
        db: AsyncSession,
        broker: RabbitBroker,
        cache: CacheService,
    ) -> None:
        self._booking = BookingRepository(db)
        self._route = RouteRepository(db)
        self._seat = SeatRepository(db)
        self._user = UserRepository(db)
        self._broker = broker
        self._cache = cache

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_booking(
        self, user_id: int, route_id: int, seat_id: int
    ) -> Booking:
        logger.info(
            "Creating booking: user_id=%d route_id=%d seat_id=%d",
            user_id,
            route_id,
            seat_id,
        )
        # 1. Validate route
        route = await self._route.get_by_id(route_id)
        if not route or not route.is_active:
            logger.warning(
                "Booking rejected — route not found or inactive: route_id=%d", route_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Route not found or is inactive",
            )

        # 2. Validate seat
        seat = await self._seat.get_by_id(seat_id)
        if not seat or seat.route_id != route_id:
            logger.warning(
                "Booking rejected — seat not found on route: seat_id=%d route_id=%d",
                seat_id,
                route_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Seat not found on this route",
            )
        if seat.is_booked:
            logger.warning(
                "Booking rejected — seat already booked: seat_id=%d", seat_id
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seat is already booked",
            )

        # 3. Create booking PENDING → CONFIRMED (in prod: after payment callback)
        booking = await self._booking.create(
            user_id=user_id,
            route_id=route_id,
            seat_id=seat_id,
            total_price=route.price,
        )
        await self._seat.mark_booked(seat_id)
        booking = await self._booking.update_status(booking.id, BookingStatus.CONFIRMED)

        logger.info("Booking confirmed: booking_id=%d user_id=%d", booking.id, user_id)

        # 4. Invalidate seats cache for this route
        await self._cache.delete_pattern(f"seats:{route_id}:*")

        # 5. Publish domain event via FastStream
        user = await self._user.get_by_id(user_id)
        route_info = f"{route.origin} → {route.destination} ({route.departure_at:%d.%m.%Y %H:%M})"

        event = BookingConfirmedEvent(
            booking_id=booking.id,
            user_email=user.email if user else "unknown",
            route=route_info,
        )

        await self._broker.publish(
            event.model_dump(),
            queue=QUEUE_CONFIRMED,
            exchange=EXCHANGE,
        )

        return booking

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel_booking(self, booking_id: int, user_id: int) -> Booking:
        logger.info(
            "Cancelling booking: booking_id=%d requested_by_user_id=%d",
            booking_id,
            user_id,
        )
        booking = await self._booking.get_by_id(booking_id)
        if not booking:
            logger.warning(
                "Cancel rejected — booking not found: booking_id=%d", booking_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
            )
        if booking.user_id != user_id:
            logger.warning(
                "Cancel rejected — ownership mismatch: booking_id=%d owner_id=%d requester_id=%d",
                booking_id,
                booking.user_id,
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This booking belongs to another user",
            )
        if booking.status == BookingStatus.CANCELLED:
            logger.warning(
                "Cancel rejected — already cancelled: booking_id=%d", booking_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is already cancelled",
            )

        booking = await self._booking.update_status(booking_id, BookingStatus.CANCELLED)
        await self._seat.mark_free(booking.seat_id)
        await self._cache.delete_pattern(f"seats:{booking.route_id}:*")

        logger.info("Booking cancelled: booking_id=%d user_id=%d", booking_id, user_id)

        # 5. Publish domain event via FastStream
        user = await self._user.get_by_id(user_id)

        await self._broker.publish(
            BookingCancelledEvent(
                booking_id=booking_id,
                user_email=user.email if user else "unknown",
            ),
            queue=QUEUE_CANCELLED,
            exchange=EXCHANGE,
        )

        return booking
