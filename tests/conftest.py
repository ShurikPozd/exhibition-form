"""Общие фикстуры тестов: временная БД, клиент FastAPI и заведомо валидная заявка.

Переменные окружения выставляются до импорта приложения: движок SQLite создаётся в
database.py на импорте, поэтому подменить путь к базе позже уже нельзя. Тесты работают с
отдельным файлом БД во временном каталоге и не трогают рабочую data/submissions.db.
"""

import os
import tempfile
from pathlib import Path

TEST_TOKEN = "test-export-token"

_TMP_DIR = Path(tempfile.mkdtemp(prefix="exhibition-form-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR / 'test_submissions.db'}"
os.environ["EXPORT_TOKEN"] = TEST_TOKEN
os.environ["GOOGLE_SYNC_ENABLED"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402  (импорт после подмены переменных окружения)
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from database import SessionLocal  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """Клиент TestClient: при входе в контекст lifespan создаёт схему БД."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def session():
    """Отдельная сессия SQLAlchemy для прямых проверок содержимого базы."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def valid_payload() -> dict:
    """Заявка, которая проходит все проверки сервера."""
    return {
        "name": "Иван Петров",
        "company": "ООО Ромашка",
        "role": ["интегратор"],
        "role_other": "",
        "stall": ["материалы о продуктах", "обучающие курсы"],
        "directions": ["SmartHome", "МКД"],
        "interest": ["Нужно КП, презентация, встреча или партнерство"],
        "phone": "+7 999 123-45-67",
        "email": "ivan@example.com",
        "after_show": "Прислать прайс",
        "consent": True,
    }
