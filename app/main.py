from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.services.broker import (
    EXCHANGE,
    QUEUE_CANCELLED,
    QUEUE_CONFIRMED,
    rabbit_broker,
)
from app.services.cache import cache

# Register subscribers on the broker
import app.services.worker  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect cache
    await cache.connect()

    # 2. Start broker
    await rabbit_broker.start()

    # 3. Explicitly declare exchange + queues via broker's own methods.
    #    This guarantees the topology exists before the first publish,
    #    even if the worker runs in a separate process.
    #    Both calls are idempotent — safe to run on every startup.
    await rabbit_broker.declare_exchange(EXCHANGE)
    await rabbit_broker.declare_queue(QUEUE_CONFIRMED)
    await rabbit_broker.declare_queue(QUEUE_CANCELLED)

    yield

    # shutdown
    await rabbit_broker.close()
    await cache.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "REST API for bus ticket booking.\n\n"
            "Features: JWT auth, seat selection, Redis caching, "
            "async RabbitMQ events via **FastStream**."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_STR)
    return app


app = create_app()
