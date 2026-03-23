"""
FastAPI-зависимости для rate limiting.

Паттерн: фабричная функция возвращает зависимость с нужными лимитами.
Использование на эндпоинте:

    @router.post("/login", dependencies=[Depends(rate_limit_auth)])
    async def login(...): ...

При превышении лимита зависимость бросает HTTP 429 с заголовками:
    Retry-After: <секунды>
    X-RateLimit-Limit: <лимит>
    X-RateLimit-Window: <окно в секундах>
"""

import logging
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.cache import cache
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    """Извлекает реальный IP клиента.

    За reverse-proxy (nginx, Traefik) реальный IP приходит в X-Forwarded-For.
    Напрямую — в request.client.host.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Заголовок может содержать цепочку: "client, proxy1, proxy2"
        # Берём первый элемент — это IP оригинального клиента.
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def make_rate_limit_dependency(limit: int, window: int) -> Callable:
    """Фабрика: создаёт зависимость с конкретным лимитом и окном.

    Args:
        limit:  Максимальное число запросов.
        window: Ширина скользящего окна в секундах.

    Returns:
        Async-функция, пригодная для Depends().
    """

    async def _dependency(request: Request) -> None:
        # Получаем клиент Redis из уже инициализированного cache-синглтона.
        # CacheService хранит _client — используем его напрямую.
        redis_client = cache._client
        if redis_client is None:
            # Redis не подключён (например, в тестах без Redis) — пропускаем.
            return

        limiter = RateLimiter(redis_client)

        # Ключ включает IP и путь эндпоинта — лимиты независимы для каждого маршрута.
        ip = _get_client_ip(request)
        key = f"rl:{ip}:{request.url.path}"

        allowed, retry_after = await limiter.is_allowed(
            key=key,
            limit=limit,
            window_seconds=window,
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded: ip=%s path=%s limit=%d window=%ds",
                ip,
                request.url.path,
                limit,
                window,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please wait {retry_after} seconds.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Window": str(window),
                },
            )

    return _dependency


# ── Готовые зависимости для каждой группы эндпоинтов ──────────────────────────
# Значения лимитов берутся из settings, чтобы их можно было переопределить
# через .env (например, поставить высокие значения в тестовом окружении).

rate_limit_auth = make_rate_limit_dependency(
    limit=settings.RATE_LIMIT_AUTH,
    window=settings.RATE_LIMIT_WINDOW_SECONDS,
)

rate_limit_bookings = make_rate_limit_dependency(
    limit=settings.RATE_LIMIT_BOOKINGS,
    window=settings.RATE_LIMIT_WINDOW_SECONDS,
)

rate_limit_default = make_rate_limit_dependency(
    limit=settings.RATE_LIMIT_DEFAULT,
    window=settings.RATE_LIMIT_WINDOW_SECONDS,
)
