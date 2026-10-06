"""Подключение к SQLite и создание схемы таблиц.

Движок создаётся один раз при импорте, сессии — через фабрику SessionLocal. Для SQLite
включается WAL: заявки пишутся с iPad параллельно с чтением админки, и блокировки не
мешают друг другу.
"""

import json
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


def _casefold(value):
    """Регистронезависимое приведение текста для поиска по заявкам.

    Встроенная функция SQLite lower() работает только с латиницей: «ПЁТР» она не
    превращает в «пётр», и поиск по фамилии молча ничего не находит. Своя функция
    casefold из Python понимает русский язык и оба регистра букв.
    """
    return value.casefold() if isinstance(value, str) else value


def _json_text(value):
    """Собирает весь текст из JSON-значения в одну строку.

    Аргументы:
        value: строка с JSON (как её хранит колонка payload) или None.

    Returns:
        str | None: все строковые значения — ключи и содержимое списков; None, если
        значения нет либо это не JSON.
    """
    if not isinstance(value, str):
        return value
    try:
        data = json.loads(value)
    except ValueError:
        return value
    parts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            parts.extend(str(key) for key in node)
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return " ".join(parts)


def _json_casefold(value):
    """Регистронезависимый текст анкеты — по нему ищутся отмеченные варианты.

    JSON в базе лежит с экранированием не-ASCII: отметка «МКД» хранится как
    «\\u041c\\u041a\\u0414», и ни lower(), ни casefold() этот текст не распознают —
    буква «М» там записана как код 041c. Поэтому значение сначала разбирается на
    настоящие слова, и только потом приводится к нижнему регистру.
    """
    text = _json_text(value)
    return text.casefold() if isinstance(text, str) else text


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
    """Включает WAL и внешние ключи для SQLite-соединения.

    Заодно регистрируются casefold() и json_casefold() для поиска по заявкам — см.
    их описания выше.
    """
    if not _is_sqlite(settings.DATABASE_URL):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    dbapi_connection.create_function("casefold", 1, _casefold)
    dbapi_connection.create_function("json_casefold", 1, _json_casefold)


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
