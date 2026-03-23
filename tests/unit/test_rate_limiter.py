"""
Тесты для rate limiter.

Два уровня:
1. Unit-тест RateLimiter с fake Redis — проверяем алгоритм sliding window изолированно.
2. Integration-тест через HTTP-клиент — проверяем что HTTP 429 возвращается
   при превышении лимита и что заголовки Retry-After присутствуют.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.rate_limiter import RateLimiter
from app.services.cache import cache
from app.core.config import settings


# ── Unit-тесты RateLimiter ────────────────────────────────────────────────────


class FakeRedis:
    """Минимальная in-memory реализация Redis-команд нужных для rate limiter."""

    def __init__(self):
        self._data: dict[str, dict[str, float]] = {}  # key → {member: score}
        self._counter = 0  # уникальный счётчик для member, чтобы избежать коллизий

    async def script_load(self, _script: str) -> str:
        return "fake_sha"

    async def evalsha(self, sha, numkeys, key, now_ms, window_ms, limit, ttl):
        store = self._data.setdefault(key, {})
        window_start = int(now_ms) - int(window_ms)
        # ZREMRANGEBYSCORE: удалить записи старше окна
        to_remove = [m for m, s in store.items() if s <= window_start]
        for m in to_remove:
            del store[m]
        # ZADD: добавить запись с уникальным member и timestamp как score
        self._counter += 1
        store[str(self._counter)] = int(now_ms)
        # ZCARD: вернуть количество
        return len(store)

    async def expire(self, key, ttl):
        pass


@pytest.mark.asyncio
async def test_rate_limiter_allows_requests_within_limit():
    """Запросы в пределах лимита должны быть разрешены."""
    redis = FakeRedis()
    limiter = RateLimiter(redis)

    for _ in range(5):
        allowed, retry_after = await limiter.is_allowed(
            "test:key", limit=5, window_seconds=60
        )
        assert allowed is True
        assert retry_after == 0


@pytest.mark.asyncio
async def test_rate_limiter_blocks_on_limit_exceeded():
    """6-й запрос при лимите 5 должен быть заблокирован."""
    redis = FakeRedis()
    limiter = RateLimiter(redis)

    for _ in range(5):
        allowed, _ = await limiter.is_allowed("test:key", limit=5, window_seconds=60)
        assert allowed is True

    # 6ой запрос
    allowed, retry_after = await limiter.is_allowed(
        "test:key", limit=5, window_seconds=60
    )
    assert allowed is False
    assert retry_after == 60


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window_resets_old_requests():
    """После истечения окна старые запросы не учитываются."""
    redis = FakeRedis()
    limiter = RateLimiter(redis)

    # Добавляем 5 "старых" запросов вручную — с timestamp в прошлом
    key = "test:sliding"
    old_ms = int((time.time() - 120) * 1000)  # 2 минуты назад
    for i in range(5):
        redis._data.setdefault(key, {})[str(old_ms + i)] = old_ms + i

    # Принудительно сбрасываем кешированный SHA чтобы evalsha пересчитал
    limiter._script_sha = "fake_sha"

    # Новый запрос — окно 60 сек, старые записи должны быть вычищены
    allowed, _ = await limiter.is_allowed(key, limit=5, window_seconds=60)
    assert allowed is True  # старые записи вне окна — лимит не превышен


@pytest.mark.asyncio
async def test_rate_limiter_fails_open_on_redis_error():
    """При недоступном Redis лимитер пропускает запрос (fail open)."""
    broken_redis = AsyncMock()
    broken_redis.script_load.side_effect = ConnectionError("Redis down")

    limiter = RateLimiter(broken_redis)
    allowed, retry_after = await limiter.is_allowed(
        "test:key", limit=5, window_seconds=60
    )

    assert allowed is True  # не блокируем при ошибке инфраструктуры
    assert retry_after == 0


# ── Integration-тесты через HTTP-клиент ───────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_429_on_auth_exceeded(client: AsyncClient):
    """При превышении лимита login возвращает 429 с нужными заголовками."""

    fake_redis = FakeRedis()

    # Патчим cache._client чтобы зависимость увидела "живой" Redis
    with patch.object(cache, "_client", fake_redis):
        payload = {"username": "brute@test.com", "password": "wrongpass"}

        # Первые RATE_LIMIT_AUTH запросов — проходят (401 Unauthorized, но не 429)
        limit = settings.RATE_LIMIT_AUTH

        for _ in range(limit):
            resp = await client.post("/api/v1/auth/login", data=payload)
            assert resp.status_code != 429, "Неожиданный 429 до исчерпания лимита"

        # Следующий запрос — должен получить 429
        resp = await client.post("/api/v1/auth/login", data=payload)
        assert resp.status_code == 429

        body = resp.json()
        assert body["error"] == "Too Many Requests"
        assert "detail" in body

        # Заголовки должны присутствовать
        assert "retry-after" in resp.headers
        assert resp.headers["x-ratelimit-limit"] == str(limit)


@pytest.mark.asyncio
async def test_rate_limit_different_ips_independent(client: AsyncClient):
    """Лимиты для разных IP независимы друг от друга."""

    fake_redis = FakeRedis()

    with patch.object(cache, "_client", fake_redis):
        limit = settings.RATE_LIMIT_AUTH
        payload = {"username": "x@test.com", "password": "pass"}

        # Исчерпываем лимит для IP 1
        for _ in range(limit + 1):
            await client.post(
                "/api/v1/auth/login",
                data=payload,
                headers={"X-Forwarded-For": "10.0.0.1"},
            )

        # IP 1 заблокирован
        resp = await client.post(
            "/api/v1/auth/login",
            data=payload,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp.status_code == 429

        # IP 2 — не заблокирован
        resp = await client.post(
            "/api/v1/auth/login",
            data=payload,
            headers={"X-Forwarded-For": "10.0.0.2"},
        )
        assert resp.status_code != 429
