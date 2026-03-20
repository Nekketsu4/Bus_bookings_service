from pydantic import BaseModel


class SeatOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    seat_number: int
    is_booked: bool
