from fastapi import APIRouter, Depends
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.database import get_db
from app.repositories.booking_repo import BookingRepository
from app.schemas.booking_schemas import BookingOut, BookingCreate
from app.services.booking_services import BookingService
from app.services.broker import get_broker
from app.services.cache import CacheService, get_cache

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def _service(
    db: AsyncSession = Depends(get_db),
    broker: RabbitBroker = Depends(get_broker),
    cache: CacheService = Depends(get_cache),
) -> BookingService:
    return BookingService(db=db, broker=broker, cache=cache)


@router.post("", response_model=BookingOut, status_code=201, summary="Book a seat")
async def create_booking(
    payload: BookingCreate,
    user_id: int = Depends(get_current_user_id),
    service: BookingService = Depends(_service),
):
    booking_seat = payload.model_dump(exclude={"user_id"})
    booking_seat["user_id"] = user_id
    return await service.create_booking(**booking_seat)


@router.get("/my", response_model=list[BookingOut], summary="My bookings history")
async def my_bookings(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    repo = BookingRepository(db)
    return await repo.list_by_user(user_id)


@router.delete("/{booking_id}", response_model=BookingOut, summary="Cancel a booking")
async def cancel_booking(
    booking_id: int,
    user_id: int = Depends(get_current_user_id),
    service: BookingService = Depends(_service),
):
    return await service.cancel_booking(booking_id=booking_id, user_id=user_id)
