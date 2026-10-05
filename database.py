"""Подключение к SQLite и создание схемы таблиц.

Движок создаётся один раз при импорте, сессии — через фабрику SessionLocal. Для SQLite
включается WAL: заявки пишутся с iPad параллельно с чтением админки, и блокировки не
мешают друг другу.
"""

import logging
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для декларативных моделей SQLAlchemy 2.x."""


def _is_sqlite(url: str) -> bool:
    """Сообщает, что DATABASE_URL указывает на SQLite."""
    return url.startswith("sqlite")


def _ensure_data_dir() -> None:
    """Создаёт папку для файла БД, если её ещё нет."""
    if _is_sqlite(settings.DATABASE_URL):
        Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)


_ensure_data_dir()

engine = create_engine(
    settings.DATABASE_URL,
    future=True,
    connect_args=(
        {"check_same_thread": False} if _is_sqlite(settings.DATABASE_URL) else {}
    ),
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Включает WAL и внешние ключи для SQLite-соединения."""
    if not _is_sqlite(settings.DATABASE_URL):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет (идемпотентно)."""
    _ensure_data_dir()
    from models import Submission  # noqa: F401  (нужен для регистрации в метаданных)

    Base.metadata.create_all(bind=engine)
    logger.info("Схема БД готова: %s", settings.DB_PATH)


def get_session() -> Iterator:
    """Зависимость FastAPI: отдаёт сессию на время запроса и закрывает её."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
