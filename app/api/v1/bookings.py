from fastapi import APIRouter, Depends
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.database import get_db
from app.repositories.booking_repo import BookingRepository
from app.schemas.booking_schemas import BookingOut
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


@router.get("/my", response_model=list[BookingOut], summary="My bookings history")
async def my_bookings(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    repo = BookingRepository(db)
    return await repo.list_by_user(user_id)