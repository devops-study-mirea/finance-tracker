"""Точка входа приложения.

Запуск локально:   make run
Документация API:  http://localhost:8000/docs
Веб-интерфейс:     http://localhost:8000/
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.router import api_router
from app.config import settings
from app.observability.health import router as health_router
from app.observability.logging import configure_logging
from app.web.routes import router as web_router

STATIC_DIR = Path(__file__).parent / "web" / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info(
        "Запуск %s (environment=%s, debug=%s)",
        settings.app_name,
        settings.environment,
        settings.debug,
    )
    yield
    logger.info("Остановка %s", settings.app_name)


def create_app() -> FastAPI:
    """Фабрика приложения.

    Именно фабрика, а не глобальный объект: тесты могут собрать отдельный
    экземпляр со своими настройками, не трогая продовый.
    """
    application = FastAPI(
        title="Финансовый трекер",
        description="Учёт доходов и расходов, анализ трат, контроль бюджетов",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router)
    application.include_router(web_router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return application


app = create_app()
