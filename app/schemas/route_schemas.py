from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class RouteCreate(BaseModel):
    origin: str = Field(min_length=2, max_length=100, examples=["Москва"])
    destination: str = Field(min_length=2, max_length=100, examples=["Махачкала"])
    departure_at: str = Field(examples=["15-03-2026"])
    arrival_at: str = Field(examples=["19-03-2026"])
    total_seats: int = Field(gt=0, le=60)
    price: Decimal = Field(gt=0, decimal_places=2, examples=["1500.00"])

    @field_validator("arrival_at")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Проверяем, что дата приходит в нужном формате"""
        try:
            # Пробуем распарсить - если ошибка, значит формат неверный
            datetime.strptime(v, "%d-%m-%Y")
            return v
        except ValueError:
            raise ValueError(
                'Дата должна быть в формате ДД-ММ-ГГГГ, например "01-01-2026"'
            )

    @model_validator(mode="after")
    def validate_dates_order(self):
        """Проверяем, что arrival_at позже departure_at"""
        # Преобразуем строки в datetime для сравнения
        dep = datetime.strptime(self.departure_at, "%d-%m-%Y")
        arr = datetime.strptime(self.arrival_at, "%d-%m-%Y")

        if arr <= dep:
            raise ValueError("arrival_at must be after departure_at")

        return self


class RouteOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    origin: str
