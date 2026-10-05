"""Настройка логирования: консоль + файл с ротацией.

Создаёт папку logs/, настраивает корневой логгер. Файловый handler — RotatingFileHandler
(10 МБ × 5). StreamHandler добавляется только если доступен sys.stderr, чтобы приложение
не падало в окружениях без консоли.

Здесь же ставится маскирование токена в access-логе uvicorn: этот логгер настраивается
самим uvicorn, но фильтр добавляется позже и переживает его конфигурацию.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from settings import LOG_LEVEL
from utils.masking import install_access_log_mask

LOG_DIR = Path(__file__).parent / "logs"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_root_logger(level: str = LOG_LEVEL) -> logging.Logger:
    """Настраивает корневой логгер: консоль + файл с ротацией.

    Args:
        level: уровень логирования (INFO, DEBUG, WARNING...).

    Returns:
        logging.Logger: Настроенный корневой логгер.
    """
    LOG_DIR.mkdir(exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    if root_logger.handlers:
        return root_logger

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    if sys.stderr:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return root_logger


setup_root_logger()
install_access_log_mask()
logging.getLogger(__name__).debug("Система логирования инициализирована")
