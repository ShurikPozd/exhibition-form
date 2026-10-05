"""Конфигурация приложения: читает переменные окружения из .env и проверяет их.

Экспортирует пути (DATA_DIR, DATABASE_URL), параметры запуска (HOST, PORT), настройки
защищённой выгрузки (EXPORT_TOKEN) и синхронизации с Google Sheets.

Отсутствующие значения не роняют импорт модуля, а логируются предупреждением: приложение
должно запуститься даже с пустым .env — тогда защищённые ручки честно отдают 403 с
понятным текстом, а не падают с 500.
"""

import os

from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")


def _env_bool(name: str, default: bool = False) -> bool:
    """Читает булеву переменную окружения (1/true/yes/on)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Читает целочисленную переменную окружения, при ошибке берёт значение по умолчанию."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s не число (%r) — используется %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    """Читает дробную переменную окружения, при ошибке берёт значение по умолчанию."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s не число (%r) — используется %s", name, raw, default)
        return default


def mask_url(url: str) -> str:
    """Маскирует URL вебхука для логов: домен и хвост пути, без идентификатора скрипта."""
    if not url:
        return ""
    if "://" in url:
        scheme, rest = url.split("://", 1)
    else:
        scheme, rest = "https://", url
    host = rest.split("/", 1)[0]
    tail = rest.rstrip("/").rsplit("/", 1)[-1]
    short_tail = tail[-4:] if len(tail) >= 4 else "..."
    return f"{scheme}{host}/.../{short_tail}"


HOST = os.getenv("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

DATA_DIR = os.getenv("DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "submissions.db")
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}"

EXPORT_TOKEN = os.getenv("EXPORT_TOKEN") or None

GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL") or None
GOOGLE_SHEET_SECRET = os.getenv("GOOGLE_SHEET_SECRET") or None
GOOGLE_SHEET_TIMEOUT = _env_float("GOOGLE_SHEET_TIMEOUT", 5.0)
GOOGLE_SYNC_ENABLED = _env_bool("GOOGLE_SYNC_ENABLED", True)

CONSENT_OPERATOR_NAME = os.getenv("CONSENT_OPERATOR_NAME", "организатор выставки")
CONSENT_OPERATOR_EMAIL = os.getenv("CONSENT_OPERATOR_EMAIL", "")
CONSENT_OPERATOR_ADDRESS = os.getenv("CONSENT_OPERATOR_ADDRESS", "")

if not EXPORT_TOKEN:
    logger.warning(
        "EXPORT_TOKEN не задан — /admin и выгрузка будут отдавать 403 (fail-closed)."
    )
else:
    logger.debug("EXPORT_TOKEN загружен")

if not GOOGLE_SHEET_WEBHOOK_URL:
    logger.warning(
        "GOOGLE_SHEET_WEBHOOK_URL не задан — синхронизация с Google Sheets отключена."
    )
elif not GOOGLE_SYNC_ENABLED:
    logger.warning(
        "GOOGLE_SYNC_ENABLED=false — синхронизация с Google Sheets выключена."
    )
elif not GOOGLE_SHEET_SECRET:
    logger.warning(
        "GOOGLE_SHEET_SECRET не задан — вебхук будет принимать записи без проверки секрета."
    )
else:
    logger.debug(
        "Синхронизация с Google Sheets включена, вебхук: %s",
        mask_url(GOOGLE_SHEET_WEBHOOK_URL),
    )

if not CONSENT_OPERATOR_NAME:
    logger.warning("CONSENT_OPERATOR_NAME не задан — в тексте согласия будет заглушка.")
