"""Точка входа: собирает FastAPI-приложение, статику и роутеры.

Запуск локально: python -m uvicorn app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import logger_config  # noqa: F401  (настройка логов происходит при импорте)
import settings
from database import init_db
from handlers import admin, auth, form
from services import backup

logger = logging.getLogger(__name__)


async def _backup_loop(interval_seconds: float) -> None:
    """Делает бэкап каждые interval_seconds, пока приложение живо.

    Сон между срабатываниями, а не расписание по часам: сервис на Render может уснуть
    и проснуться в любой момент, и такой цикл переживает перезапуск, а часы в контейнере
    могли бы ехать.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(backup.run_backup, "по расписанию")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Готовит схему БД при старте, восстанавливает базу из копии и пишет в лог адреса.

    Порядок важен: восстановление идёт до init_db(), потому что оно подменяет файл базы
    целиком, и уже настоящий файл проверяется на готовность схемы.
    """
    with suppress(Exception):
        backup.restore_if_empty()
    init_db()

    backup_task = None
    if settings.BACKUP_INTERVAL_HOURS > 0:
        backup_task = asyncio.create_task(
            _backup_loop(settings.BACKUP_INTERVAL_HOURS * 3600)
        )
    app.state.backup_task = backup_task

    logger.info("Приложение запущено: http://%s:%s", settings.HOST, settings.PORT)
    logger.info("Анкета: /   Админка: /admin (вход по ADMIN_PASSWORD на /admin/login)")
    logger.info(
        "Бэкапы: дампы в %s каждые %s ч, выгрузка в репозиторий — %s",
        settings.BACKUP_DIR,
        settings.BACKUP_INTERVAL_HOURS,
        "включена" if settings.BACKUP_TOKEN else "не настроена",
    )
    try:
        yield
    finally:
        if backup_task is not None:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task
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
app.include_router(auth.router)
app.include_router(admin.router)


@app.api_route("/healthz", methods=["GET", "HEAD"], tags=["service"])
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
