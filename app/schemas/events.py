"""
Pydantic schemas for RabbitMQ domain events.
FastStream uses these for automatic serialisation / deserialisation.
"""

from pydantic import BaseModel


class BookingConfirmedEvent(BaseModel):
    booking_id: int
    user_email: str
    route: str  # e.g. "Москва → Махачкала (01.06.2030 08:00)"


class BookingCancelledEvent(BaseModel):
    booking_id: int
    user_email: str
