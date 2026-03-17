from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus


class BookingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, booking_id: int) -> Booking | None:
        result = await self.db.execute(select(Booking).where(Booking.id == booking_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int) -> list[Booking]:
        result = await self.db.execute(
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(Booking.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        route_id: int,
        seat_id: int,
        total_price: Decimal,
    ) -> Booking:
        booking = Booking(
            user_id=user_id,
            route_id=route_id,
            seat_id=seat_id,
            total_price=total_price,
            status=BookingStatus.PENDING,
        )
        self.db.add(booking)
        await self.db.flush()
        await self.db.refresh(booking)
        return booking

    async def update_status(
        self, booking_id: int, status: BookingStatus
    ) -> Booking | None:
        booking = await self.get_by_id(booking_id)
        if booking:
            booking.status = status
            await self.db.flush()
            await self.db.refresh(booking)
        return booking
