"""Точка входа: собирает FastAPI-приложение, статику и роутеры.

Запуск локально: python -m uvicorn app:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import logger_config  # noqa: F401  (настройка логов происходит при импорте)
import settings
from database import init_db
from handlers import admin, form

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Готовит схему БД при старте и пишет в лог, куда смотреть."""
    init_db()
    logger.info("Приложение запущено: http://%s:%s", settings.HOST, settings.PORT)
    logger.info("Анкета: /   Админка и выгрузка: /admin (нужен EXPORT_TOKEN)")
    yield
    logger.info("Приложение остановлено")


app = FastAPI(
    title="Анкета выставки",
    description="Сбор заявок с планшета и выгрузка в Excel/CSV",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
app.include_router(form.router)
app.include_router(admin.router)


@app.get("/healthz", tags=["service"])
def healthz() -> dict[str, str]:
    """Healthcheck для Docker и внешнего мониторинга."""
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Логирует необработанную ошибку и отдаёт клиенту 500 без деталей.

    Текст исключения может содержать персональные данные или пути, поэтому наружу
    отдаётся только нейтральное сообщение, а подробности — в лог.
    """
    logger.exception(
        "Необработанная ошибка при обработке %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500, content={"detail": "внутренняя ошибка сервера"}
    )
