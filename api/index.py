"""App entrypoint: FastAPI construction, middleware, lifespan, router wiring.

Route handlers live in api/routes/*.py (one module per domain, mirroring the
src/services/ layout); optional/app-specific imports live in api/bootstrap.py
so a broken import can't crash the whole app at boot.
"""
from contextlib import asynccontextmanager
import asyncio
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(override=False)

from api.bootstrap import (
    AdminAuditMiddleware,
    AlertConsumer,
    CorrelationIdMiddleware,
    OrderService,
    R2Service,
    RateLimitMiddleware,
    db,
    logger,
    redis_client,
    register_exception_handlers,
    settings,
)


def _cors_middleware_kwargs():
    from src.security.cors_policy import build_cors_middleware_kwargs

    origins = settings.cors_origins_list if settings else ["http://localhost:5173"]
    return build_cors_middleware_kwargs(origins)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database, Redis, and background-task lifecycle."""
    try:
        if db:
            await db.connect()
            if OrderService is not None:
                try:
                    await OrderService().ensure_indexes()
                except Exception as idx_err:
                    if logger:
                        logger.warning(f"Order index setup skipped: {idx_err}")
        if redis_client:
            await redis_client.connect()
        # Ensure the R2 media bucket exists for dynamic asset hosting
        if R2Service is not None:
            try:
                R2Service().ensure_bucket()
            except Exception as r2_err:
                if logger:
                    logger.warning(f"R2 bucket check skipped: {r2_err}")
    except Exception as e:
        if logger:
            logger.error(f"Startup connection error: {e}")
        print(f"Startup connection error: {e}", file=sys.stderr)

    alert_consumer_task = None
    if AlertConsumer is not None and settings is not None and settings.telegram_enabled:
        alert_consumer_task = asyncio.create_task(AlertConsumer().run())

    yield

    if alert_consumer_task is not None:
        alert_consumer_task.cancel()
        try:
            await alert_consumer_task
        except asyncio.CancelledError:
            pass

    try:
        if db:
            await db.close()
        if redis_client:
            await redis_client.close()
    except Exception as e:
        if logger:
            logger.error(f"Shutdown connection error: {e}")
        print(f"Shutdown connection error: {e}", file=sys.stderr)


# Export THIS ONLY
app = FastAPI(lifespan=lifespan)

if logger is not None:
    register_exception_handlers(app, logger)

if RateLimitMiddleware:
    app.add_middleware(RateLimitMiddleware)

if AdminAuditMiddleware:
    app.add_middleware(AdminAuditMiddleware)

app.add_middleware(CORSMiddleware, **_cors_middleware_kwargs())

if CorrelationIdMiddleware:
    app.add_middleware(CorrelationIdMiddleware)


from api.routes import (
    admin_auth,
    admin_catalog,
    admin_content,
    admin_fraud,
    admin_inbox,
    admin_orders,
    admin_upload,
    contact,
    cqrs,
    cron,
    health,
    orders,
    storefront,
)

app.include_router(health.router)
app.include_router(storefront.router)
app.include_router(contact.router)
app.include_router(orders.router)
app.include_router(admin_auth.router)
app.include_router(admin_upload.router)
app.include_router(admin_orders.router)
app.include_router(admin_catalog.router)
app.include_router(admin_content.router)
app.include_router(admin_inbox.router)
app.include_router(admin_fraud.router)
app.include_router(cron.router)
app.include_router(cqrs.router)
