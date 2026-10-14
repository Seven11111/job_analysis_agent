"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.router import router as v1_router
from src.config import get_settings


def create_app(*, enable_subscription_scheduler: bool = False) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        scheduler_task = None
        if enable_subscription_scheduler:
            from api.v1.endpoints.subscriptions import service as subscription_service
            from src.services.subscription_scheduler import JobSubscriptionScheduler

            scheduler = JobSubscriptionScheduler(subscription_service)
            scheduler_task = asyncio.create_task(scheduler.run_forever())
            app.state.job_subscription_scheduler = scheduler
        try:
            yield
        finally:
            if scheduler_task is not None:
                scheduler_task.cancel()
                try:
                    await scheduler_task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title="Job Analysis Agent API",
        version="0.2.0",
        description="个人单用户岗位研究 Agent API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(v1_router, prefix="/api/v1")
    return app
