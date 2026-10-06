"""Общие фикстуры тестов: временная БД, клиент FastAPI и заведомо валидная заявка.

Переменные окружения выставляются до импорта приложения: движок SQLite создаётся в
database.py на импорте, поэтому подменить путь к базе позже уже нельзя. Тесты работают с
отдельным файлом БД во временном каталоге и не трогают рабочую data/submissions.db.
"""

import os
import tempfile
from pathlib import Path

TEST_TOKEN = "test-export-token"
TEST_ADMIN_PASSWORD = "тестовый-пароль-админки"

_TMP_DIR = Path(tempfile.mkdtemp(prefix="exhibition-form-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR / 'test_submissions.db'}"
os.environ["EXPORT_TOKEN"] = TEST_TOKEN
os.environ["ADMIN_PASSWORD"] = TEST_ADMIN_PASSWORD
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402  (импорт после подмены переменных окружения)
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from database import SessionLocal, init_db  # noqa: E402
from models import Submission  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    """Создаёт схему тестовой БД один раз до всех тестов."""
    init_db()


@pytest.fixture()
def client():
    """Клиент TestClient на каждый тест: при входе в контекст lifespan создаёт схему БД.

    Область именно функциональная: cookie сессии админки не должна попадать из одного
    теста в другой, иначе проверки «без доступа» начнут проходить по чужой сессии.
    """
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


@pytest.fixture(autouse=True)
def clean_submissions(session):
    """Перед каждым тестом очищает таблицу заявок: тесты не зависят от порядка."""
    session.query(Submission).delete()
    session.commit()


@pytest.fixture()
def auth_client(client):
    """Клиент, вошедший в админку по ADMIN_PASSWORD: cookie сессии уже в браузере."""
    response = client.post(
        "/admin/login", data={"password": TEST_ADMIN_PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303, "вход по паролю должен выдать 303"
    return client


@pytest.fixture()
def created_id(client, valid_payload) -> int:
    """Отправляет валидную анкету и возвращает id созданной заявки."""
    response = client.post("/api/submissions", json=valid_payload)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


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
