"""Конфигурация приложения: читает переменные окружения из .env и проверяет их.

Экспортирует пути (DATA_DIR, DATABASE_URL), параметры запуска (HOST, PORT), настройки
доступа к админке (ADMIN_PASSWORD, EXPORT_TOKEN) и реквизиты оператора персональных данных.

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


HOST = os.getenv("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

DATA_DIR = os.getenv("DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "submissions.db")
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}"

EXPORT_TOKEN = os.getenv("EXPORT_TOKEN") or None

# Пароль для входа в админку через форму. В отличие от EXPORT_TOKEN его вводит
# человек, поэтому задаётся читаемой строкой в .env, а подпись сессии делается на нём же.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or None
SESSION_TTL_HOURS = _env_int("SESSION_TTL_HOURS", 8)
# Secure-флаг cookie обязателен на HTTPS, но на http://127.0.0.1 он запрещает cookie,
# поэтому по умолчанию выключен и включается в .env при публикации наружу.
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)

# --- Резервные копии базы ---
# Дампы всегда пишутся в BACKUP_DIR; выгрузка в репозиторий GitHub включается только
# когда заданы BACKUP_REPO и BACKUP_TOKEN. Токен — fine-grained PAT с правом
# Contents: Read and write на репозиторий с копиями.
BACKUP_DIR = os.getenv("BACKUP_DIR") or os.path.join(DATA_DIR, "backup")
BACKUP_KEEP = _env_int("BACKUP_KEEP", 14)
BACKUP_ON_SUBMIT = _env_bool("BACKUP_ON_SUBMIT", True)
BACKUP_INTERVAL_HOURS = _env_int("BACKUP_INTERVAL_HOURS", 6)
BACKUP_REPO = os.getenv("BACKUP_REPO") or None
BACKUP_TOKEN = os.getenv("BACKUP_TOKEN") or None
BACKUP_PATH = os.getenv("BACKUP_PATH") or "backups/submissions.db.gz"
BACKUP_BRANCH = os.getenv("BACKUP_BRANCH", "main")

CONSENT_OPERATOR_NAME = os.getenv("CONSENT_OPERATOR_NAME", "организатор выставки")
CONSENT_OPERATOR_EMAIL = os.getenv("CONSENT_OPERATOR_EMAIL", "")
CONSENT_OPERATOR_ADDRESS = os.getenv("CONSENT_OPERATOR_ADDRESS", "")

if not EXPORT_TOKEN:
    logger.warning(
        "EXPORT_TOKEN не задан — /admin и выгрузка будут отдавать 403 (fail-closed)."
    )
else:
    logger.debug("EXPORT_TOKEN загружен")

if not ADMIN_PASSWORD:
    logger.warning(
        "ADMIN_PASSWORD не задан — форма входа /admin/login объяснит, что его нужно задать."
    )
else:
    logger.debug("ADMIN_PASSWORD загружен")

if not CONSENT_OPERATOR_NAME:
    logger.warning("CONSENT_OPERATOR_NAME не задан — в тексте согласия будет заглушка.")
