import pytest_asyncio

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.db.database import Base, get_db
from app.main import app
from app.services.broker import get_broker
from app.services.cache import get_cache
from app.models.booking import UserStatus, User


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def register_and_login(
    client: AsyncClient,
    email="user@test.com",
    password="password123",
    make_admin: bool = False,
) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Aziev",
            "last_name": "Kadir",
            "username": "Some",
        },
    )

    if make_admin:
        async with TestSessionLocal() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if user:
                user.role = UserStatus.ADMIN
                await session.commit()
                await session.refresh(user)

    resp = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    return resp.json()["access_token"]


# ── Stubs for infra ────────────────────────────────────────────────────────────


class _NullBroker:
    """Drop-in stub for FastStream RabbitBroker — records published messages."""

    def __init__(self):
        self.published: list[tuple] = []

    async def publish(self, message, *, queue=None, exchange=None, **_):
        self.published.append((message, queue, exchange))


class _NullCache:
    async def get(self, _):
        return None

    async def set(self, *_, **__):
        pass

    async def delete(self, _):
        pass

    async def delete_pattern(self, _):
        pass


null_broker = _NullBroker()
null_cache = _NullCache()

app.dependency_overrides[get_db] = _override_db
app.dependency_overrides[get_broker] = lambda: null_broker
app.dependency_overrides[get_cache] = lambda: null_cache
