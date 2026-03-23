"""
Unit-тесты для глобальных обработчиков ошибок.
Проверяют что все ошибки возвращаются в едином формате ErrorResponse.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login
from tests.integration.test_api import _create_route


# ── HTTP-ошибки → единый формат ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_404_returns_unified_format(client: AsyncClient):
    """Несуществующий маршрут API → 404 в формате ErrorResponse."""
    resp = await client.get("/api/v1/routes/99999/seats")
    # seats возвращает пустой список, но бронирование несуществующего маршрута → 404
    token = await register_and_login(client, "u@test.com")
    resp = await client.post(
        "/api/v1/bookings",
        json={"route_id": 99999, "seat_id": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "Not Found"
    assert "detail" in body


@pytest.mark.asyncio
async def test_401_returns_unified_format(client: AsyncClient):
    """Запрос без токена → 401 в формате ErrorResponse."""
    resp = await client.post("/api/v1/bookings", json={"route_id": 1, "seat_id": 1})
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "Unauthorized"
    assert "detail" in body


@pytest.mark.asyncio
async def test_403_returns_unified_format(client: AsyncClient):
    """Обычный пользователь создаёт маршрут → 403 в формате ErrorResponse."""
    token = await register_and_login(client, "user@test.com")
    resp = await client.post(
        "/api/v1/routes",
        json={
            "origin": "A",
            "destination": "B",
            "departure_at": "01-01-2026",
            "arrival_at": "05-01-2026",
            "total_seats": 5,
            "price": "100.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"] == "Forbidden"
    assert body["detail"] == "Admin access required"


@pytest.mark.asyncio
async def test_409_returns_unified_format(client: AsyncClient):
    """Дублирующая бронь → 409 в формате ErrorResponse."""

    admin_token = await register_and_login(client, "admin@test.com", make_admin=True)
    user_token = await register_and_login(client, "user@test.com")
    route = await _create_route(client, admin_token)
    seats = (await client.get(f"/api/v1/routes/{route['id']}/seats")).json()
    seat_id = seats[0]["id"]

    await client.post(
        "/api/v1/bookings",
        json={"route_id": route["id"], "seat_id": seat_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    resp = await client.post(
        "/api/v1/bookings",
        json={"route_id": route["id"], "seat_id": seat_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "Conflict"
    assert "detail" in body


# ── Ошибки валидации Pydantic → единый формат ─────────────────────────────────


@pytest.mark.asyncio
async def test_validation_error_returns_unified_format(client: AsyncClient):
    """Невалидный email при регистрации → 422 с полем field."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "password123",
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "Unprocessable Entity"
    assert "detail" in body
    assert body["field"] == "email"


@pytest.mark.asyncio
async def test_validation_error_short_password(client: AsyncClient):
    """Короткий пароль → 422 с полем field=password."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@test.com",
            "password": "123",
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "Unprocessable Entity"
    assert body["field"] == "password"
