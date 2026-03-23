"""
Rate limiter — алгоритм sliding window на Redis.

Принцип работы:
  Для каждой пары (IP, endpoint) храним sorted set, где каждый элемент —
  timestamp запроса. При каждом запросе:
    1. Удаляем записи старше окна (ZREMRANGEBYSCORE).
    2. Добавляем текущий timestamp (ZADD).
    3. Считаем количество записей (ZCARD).
    4. Если превышен лимит — возвращаем (False, retry_after).

Всё выполняется атомарно через Lua-скрипт, поэтому нет гонки между
ZCARD и ZADD при параллельных запросах.
"""

import logging
import time

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Lua-скрипт выполняется атомарно на стороне Redis.
# Аргументы: KEYS[1]=ключ, ARGV[1]=now_ms, ARGV[2]=window_ms, ARGV[3]=limit, ARGV[4]=ttl_sec
# Member = "now_ms:random" — уникален даже при одинаковом timestamp (параллельные запросы).
_SLIDING_WINDOW_SCRIPT = """
local key        = KEYS[1]
local now        = tonumber(ARGV[1])
local window     = tonumber(ARGV[2])
local limit      = tonumber(ARGV[3])
local ttl        = tonumber(ARGV[4])
local window_start = now - window

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local member = now .. ':' .. math.random(1, 1000000)
redis.call('ZADD', key, now, member)
local count = redis.call('ZCARD', key)
redis.call('EXPIRE', key, ttl)
return count
"""


class RateLimiter:
    """Sliding-window rate limiter поверх Redis"""

    def __init__(self, redis: Redis):
        self._redis = redis
        # Регистрируем скрипт один раз - Redis вернет SHA
        # при повторных вызовах передаем SHA вместо полного скрипта(экономим трафик)
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        """Загружает Lua-скрипт в Redis при первом вызове, далее использует SHA"""
        if self._script_sha is None:
            self._script_sha = await self._redis.script_load(_SLIDING_WINDOW_SCRIPT)
        return self._script_sha

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Проверяет, не превышен ли лимит для данного ключа.

        Args:
            key:            Уникальный идентификатор (например "rl:127.0.0.1:/auth/login").
            limit:          Максимальное число запросов в окне.
            window_seconds: Ширина скользящего окна в секундах.

        Returns:
            (allowed, retry_after_seconds)
            allowed=False → запрос нужно отклонить,
            retry_after   → сколько секунд ждать (для заголовка Retry-After).
        """
        now_ms = int(time.time() * 1000)
        window_ms = window_seconds * 1000

        try:
            sha = await self._ensure_script()
            count = await self._redis.evalsha(
                sha,
                1,  # количество ключей
                key,  # KEYS[1]
                now_ms,  # ARGV[1]
                window_ms,  # ARGV[2]
                limit,  # ARGV[3]
                window_seconds + 1,  # ARGV[4] — TTL чуть больше окна
            )
            allowed = int(count) <= limit
            retry_after = window_seconds if not allowed else 0
            return allowed, retry_after
        except Exception:
            # Если Redis недоступен — пропускаем запрос (fail open).
            # В продакшене здесь стоит алертить, но не роняем сервис.
            logger.warning("Rate limiter Redis error for key=%s, failing open", key)
            return True, 0
