import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="user")


class Route(Base):
    """Рейс: Москва → Махачкала, 20 мест, цена, время."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    destination: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    departure_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    arrival_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    seats: Mapped[list["Seat"]] = relationship(
        "Seat", back_populates="route", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="route")


class Seat(Base):
    """Места в автобуса Уникально для каждого маршрута."""

    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("route_id", "seat_number", name="uq_route_seat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id"), nullable=False, index=True
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)

    route: Mapped["Route"] = relationship("Route", back_populates="seats")
    booking: Mapped["Booking | None"] = relationship("Booking", back_populates="seat")


class Booking(Base):
    """Бронь мест"""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id"), nullable=False, index=True
    )
    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id"), unique=True, nullable=False
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False
    )
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="bookings")
    route: Mapped["Route"] = relationship("Route", back_populates="bookings")
    seat: Mapped["Seat"] = relationship("Seat", back_populates="booking")
