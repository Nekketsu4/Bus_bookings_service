from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Route, Seat


class RouteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, route_id: int) -> Route | None:
        result = await self.db.execute(select(Route).where(Route.id == route_id))
        return result.scalar_one_or_none()

    async def list_active(
        self,
        origin: str | None = None,
        destination: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Route], int]:
        q = select(Route).where(Route.is_active.is_(True))
        if origin:
            q = q.where(Route.origin.ilike(f"%{origin}%"))
        if destination:
            q = q.where(Route.destination.ilike(f"%{destination}%"))

        total_q = select(func.count()).select_from(q.subquery())
        total: int = (await self.db.execute(total_q)).scalar_one()

        q = q.order_by(Route.departure_at).offset((page - 1) * size).limit(size)
        rows = (await self.db.execute(q)).scalars().all()
        return list(rows), total

    async def create(self, **kwargs) -> Route:
        route = Route(**kwargs)
        self.db.add(route)
        await self.db.flush()
        await self.db.refresh(route)
        # auto-generate seats
        seats = [
            Seat(route_id=route.id, seat_number=n)
            for n in range(1, route.total_seats + 1)
        ]
        self.db.add_all(seats)
        await self.db.flush()
        return route


class SeatRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, seat_id: int) -> Seat | None:
        result = await self.db.execute(select(Seat).where(Seat.id == seat_id))
        return result.scalar_one_or_none()

    async def list_by_route(self, route_id: int) -> list[Seat]:
        result = await self.db.execute(
            select(Seat)
            .where(Seat.route_id == route_id)
            .order_by(Seat.seat_number)
        )
        return list(result.scalars().all())

    async def mark_booked(self, seat_id: int) -> None:
        seat = await self.get_by_id(seat_id)
        if seat:
            seat.is_booked = True

    async def mark_free(self, seat_id: int) -> None:
        seat = await self.get_by_id(seat_id)
        if seat:
            seat.is_booked = False