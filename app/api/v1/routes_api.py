from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories.route_repo import RouteRepository, SeatRepository
from app.schemas import route_schemas, seat_schemas, pagination
from app.services.cache import CacheService, get_cache

router = APIRouter(prefix="/routes", tags=["Routes"])


# добавить доступ этой ручки только для админа
@router.post(
    "",
    response_model=route_schemas.RouteOut,
    status_code=201,
    summary="Create a new route (admin)",
)
async def create_route(
    payload: route_schemas.RouteCreate,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
):
    repo = RouteRepository(db)
    route_data = payload.model_dump(exclude={"departure_at", "arrival_at"})
    route_data["arrival_at"] = datetime.strptime(payload.arrival_at, "%d-%m-%Y")
    route_data["departure_at"] = datetime.strptime(payload.departure_at, "%d-%m-%Y")
    route = await repo.create(**route_data)
    await cache.delete_pattern("routes:*")
    return route


@router.get(
    "",
    response_model=pagination.Page[route_schemas.RouteOut],
    summary="Search bus routes",
)
async def list_routes(
    origin: str | None = Query(None, description="Filter by origin city"),
    destination: str | None = Query(None, description="Filter by destination city"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
):
    cache_key = f"routes:{origin}:{destination}:{page}:{size}"
    if cached := await cache.get(cache_key):
        return cached

    repo = RouteRepository(db)
    routes, total = await repo.list_active(
        origin=origin, destination=destination, page=page, size=size
    )
    response = pagination.Page[route_schemas.RouteOut](
        total=total,
        page=page,
        size=size,
        items=[route_schemas.RouteOut.model_validate(r) for r in routes],
    )
    await cache.set(cache_key, response.model_dump(), ttl=30)
    return response


@router.get(
    "/{route_id}/seats",
    response_model=list[seat_schemas.SeatOut],
    summary="Get seat availability for a route",
)
async def list_seats(
    route_id: int,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
):
    cache_key = f"seats:{route_id}:all"
    if cached := await cache.get(cache_key):
        return cached

    repo = SeatRepository(db)
    seats = await repo.list_by_route(route_id)
    data = [seat_schemas.SeatOut.model_validate(s).model_dump() for s in seats]
    await cache.set(cache_key, data, ttl=15)
    return data
