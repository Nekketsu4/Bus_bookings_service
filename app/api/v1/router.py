from fastapi import APIRouter

from app.api.v1 import health, auth, bookings

api_router = APIRouter()


api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(bookings.router)
