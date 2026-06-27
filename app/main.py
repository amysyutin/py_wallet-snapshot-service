import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.debug import router as debug_router
from app.api.health import router as health_router
from app.api.internal_jobs import router as internal_jobs_router
from app.api.metrics import router as metrics_router
from app.config import get_settings
from app.logging_config import configure_logging
from app.scheduler.loop import run_scheduler_forever
from app.worker.loop import run_worker_forever


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    tasks: list[asyncio.Task] = []
    if settings.snapshot_worker_enabled:
        tasks.append(asyncio.create_task(run_worker_forever()))
    if settings.snapshot_scheduler_enabled:
        tasks.append(asyncio.create_task(run_scheduler_forever()))
    app.state.background_tasks = tasks
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(debug_router)
    app.include_router(internal_jobs_router)
    return app


app = create_app()
