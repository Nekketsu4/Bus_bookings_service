from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    route_id: int
    seat_id: int


class BookingOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    route_id: int
    seat_id: int
    status: BookingStatus
    total_price: Decimal
    created_at: datetime
    updated_at: datetime