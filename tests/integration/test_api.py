import pytest
from httpx import AsyncClient

from tests.conftest import null_broker, register_and_login


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_route(client: AsyncClient, token: str) -> dict:
    resp = await client.post(
        "/api/v1/routes",
        json={
            "origin": "Москва",
            "destination": "Махачкала",
            "departure_at": "01-01-2026",
            "arrival_at": "05-01-2026",
            "total_seats": 5,
            "price": "1500.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Auth ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "strongpass",
            "first_name": "Aziev",
            "last_name": "Kadir",
            "username": "Some",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@example.com"
    assert resp.json()["role"] == "user"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "first_name": "Aziev",
        "last_name": "Kadir",
        "username": "Some",
    }
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "password123",
            "first_name": "Aziev",
            "last_name": "Kadir",
            "username": "Some",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "password123", "full_name": "User"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "x@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Routes & seats ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_route(client: AsyncClient):
    token = await register_and_login(client, make_admin=True)
    route = await _create_route(client, token)
    assert route["origin"] == "Москва"
    assert route["id"] == 1


@pytest.mark.asyncio
async def test_list_routes(client: AsyncClient):
    token = await register_and_login(client, make_admin=True)
    await _create_route(client, token)
    resp = await client.get("/api/v1/routes")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_seats(client: AsyncClient):
    token = await register_and_login(client, make_admin=True)
    route = await _create_route(client, token)
    resp = await client.get(f"/api/v1/routes/{route['id']}/seats")
    assert resp.status_code == 200
    seats = resp.json()
    assert len(seats) == 5
    assert all(not s["is_booked"] for s in seats)


# ── Bookings ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_booking_publishes_event(client: AsyncClient):
    """Booking confirmed → FastStream publishes BookingConfirmedEvent."""
    null_broker.published.clear()
    token = await register_and_login(client, make_admin=True)
    route = await _create_route(client, token)
    seats = (await client.get(f"/api/v1/routes/{route['id']}/seats")).json()

    resp = await client.post(
        "/api/v1/bookings",
        json={"route_id": route["id"], "seat_id": seats[0]["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "confirmed"

    # exactly one event published
    assert len(null_broker.published) == 1
    event, queue, _ = null_broker.published[0]
    assert event["booking_id"] == resp.json()["id"]
    assert event["user_email"] == "user@test.com"


@pytest.mark.asyncio
async def test_double_booking_same_seat(client: AsyncClient):
    token = await register_and_login(client, make_admin=True)
    route = await _create_route(client, token)
    seats = (await client.get(f"/api/v1/routes/{route['id']}/seats")).json()
    seat_id = seats[0]["id"]

    await client.post(
        "/api/v1/bookings",
        json={"route_id": route["id"], "seat_id": seat_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.post(
        "/api/v1/bookings",
        json={"route_id": route["id"], "seat_id": seat_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_my_bookings(client: AsyncClient):
    token = await register_and_login(client, make_admin=True)
    route = await _create_route(client, token)
    seats = (await client.get(f"/api/v1/routes/{route['id']}/seats")).json()

    await client.post(
        "/api/v1/bookings",
        json={"route_id": route["id"], "seat_id": seats[0]["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/v1/bookings/my", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_cancel_booking_publishes_event(client: AsyncClient):
    """Booking cancelled → FastStream publishes BookingCancelledEvent."""
    null_broker.published.clear()
    token = await register_and_login(client, make_admin=True)
    route = await _create_route(client, token)
    seats = (await client.get(f"/api/v1/routes/{route['id']}/seats")).json()

    booking_id = (
        await client.post(
            "/api/v1/bookings",
            json={"route_id": route["id"], "seat_id": seats[0]["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()["id"]

    null_broker.published.clear()  # reset — only care about cancel event

    resp = await client.delete(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    assert len(null_broker.published) == 1
    event, _, _ = null_broker.published[0]
    assert event.booking_id == booking_id


@pytest.mark.asyncio
async def test_cancel_other_users_booking(client: AsyncClient):
    token1 = await register_and_login(client, "user1@test.com", make_admin=True)
    token2 = await register_and_login(client, "user2@test.com", make_admin=True)

    route = await _create_route(client, token1)
    seats = (await client.get(f"/api/v1/routes/{route['id']}/seats")).json()

    booking_id = (
        await client.post(
            "/api/v1/bookings",
            json={"route_id": route["id"], "seat_id": seats[0]["id"]},
            headers={"Authorization": f"Bearer {token1}"},
        )
    ).json()["id"]

    resp = await client.delete(
        f"/api/v1/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_booking_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/bookings", json={"route_id": 1, "seat_id": 1})
    assert resp.status_code == 401
