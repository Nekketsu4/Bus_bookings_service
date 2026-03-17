import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)
DEFAULT_TTL = 60  # seconds


class CacheService:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info("Redis connected url=%s", settings.REDIS_URL)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        if not self._client:
            return None
        raw = await self._client.get(key)
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        if not self._client:
            return
        await self._client.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        if not self._client:
            return
        await self._client.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        if not self._client:
            return
        keys = await self._client.keys(pattern)
        if keys:
            await self._client.delete(*keys)


cache = CacheService()


async def get_cache() -> CacheService:
    return cache
