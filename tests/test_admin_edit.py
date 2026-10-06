"""Правка заявок и мягкое удаление: контакты, заметка, скрытие и восстановление.

Всё это доступно только человеку, вошедшему по паролю: токен выгрузки предназначен для
curl и скриптов и не должен уметь менять данные.
"""

import io

from openpyxl import load_workbook

from database import SessionLocal
from models import Submission
from utils.session import SESSION_COOKIE_NAME


def _get(submission_id: int):
    """Читает заявку из БД отдельной сессией, чтобы увидеть неотдачу коммита."""
    db = SessionLocal()
    try:
        return db.get(Submission, submission_id)
    finally:
        db.close()


def test_edit_page_prefills_contacts(auth_client, created_id):
    """Форма правки показывает текущие контакты."""
    response = auth_client.get(f"/admin/submissions/{created_id}/edit")

    assert response.status_code == 200
    assert "Иван Петров" in response.text


def test_edit_saves_contacts_and_note(auth_client, created_id):
    """Правка сохраняет контакты и заметку, проставляет updated_at."""
    response = auth_client.post(
        f"/admin/submissions/{created_id}/edit",
        data={
            "name": "Пётр Иванов",
            "company": "ООО Ромашка-2",
            "phone": "+7 999 000-11-22",
            "email": "petr@example.com",
            "note": "Перезвонить в пятницу",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    submission = _get(created_id)
    assert submission.name == "Пётр Иванов"
    assert submission.company == "ООО Ромашка-2"
    assert submission.phone == "+7 999 000-11-22"
    assert submission.email == "petr@example.com"
    assert submission.note == "Перезвонить в пятницу"
    assert submission.updated_at is not None


def test_edit_keeps_visitor_answers(auth_client, created_id, valid_payload):
    """Ответы посетителя не меняются: согласие давалось под тем составом анкеты."""
    auth_client.post(
        f"/admin/submissions/{created_id}/edit",
        data={
            "name": "Пётр Иванов",
            "company": "",
            "phone": "+7 999 000-11-22",
            "email": "",
            "note": "",
        },
        follow_redirects=False,
    )

    submission = _get(created_id)
    assert submission.payload["role"] == valid_payload["role"]
    assert submission.payload["stall"] == valid_payload["stall"]
    assert submission.consent_version


def test_edit_without_name_shows_form_with_error(auth_client, created_id):
    """Пустое имя не сохраняется: форма возвращается с текстом ошибки."""
    response = auth_client.post(
        f"/admin/submissions/{created_id}/edit",
        data={"name": "   ", "phone": "+7 999 000-11-22", "email": ""},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Имя" in response.text
    assert _get(created_id).name == "Иван Петров"


def test_edit_without_any_contact_shows_form_with_error(auth_client, created_id):
    """Как и на анкете, без телефона и почты заявку не с кем связать."""
    response = auth_client.post(
        f"/admin/submissions/{created_id}/edit",
        data={"name": "Пётр Иванов", "phone": "", "email": ""},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "телефон" in response.text.lower()
    assert _get(created_id).phone == "+7 999 123-45-67"


def test_edit_missing_submission_returns_404(auth_client):
    """Правка несуществующей заявки — 404, а не 500."""
    response = auth_client.get("/admin/submissions/999999/edit")

    assert response.status_code == 404


def test_edit_requires_session(client, created_id):
    """Без сессии правка закрыта (303 на форму входа для страницы, 403 для POST)."""
    assert client.get(f"/admin/submissions/{created_id}/edit").status_code == 403
    assert (
        client.post(
            f"/admin/submissions/{created_id}/edit",
            data={"name": "Взлом", "phone": "+7 999 000-11-22"},
            follow_redirects=False,
        ).status_code
        == 403
    )
    assert _get(created_id).name == "Иван Петров"


def test_edit_rejects_export_token(client, created_id):
    """Токен выгрузки не даёт править заявки: он для скриптов, а не для правки."""
    response = client.post(
        f"/admin/submissions/{created_id}/edit",
        data={"name": "Взлом", "phone": "+7 999 000-11-22"},
        headers={"X-Export-Token": "test-export-token"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert _get(created_id).name == "Иван Петров"


def test_delete_hides_submission_from_list_and_export(auth_client, created_id):
    """Скрытая заявка пропадает из админки и выгрузок, но остаётся в базе."""
    response = auth_client.post(
        f"/admin/submissions/{created_id}/delete", follow_redirects=False
    )

    assert response.status_code == 303
    assert _get(created_id).deleted_at is not None
    assert "Иван Петров" not in auth_client.get("/admin").text

    xlsx = auth_client.get("/api/submissions.xlsx")
    workbook = load_workbook(io.BytesIO(xlsx.content))
    assert "Иван Петров" not in "".join(
        str(cell.value or "") for row in workbook["Заявки"].iter_rows() for cell in row
    )


def test_deleted_submission_visible_with_flag(auth_client, created_id):
    """С переключателем скрытая заявка видна и её можно вернуть."""
    auth_client.post(f"/admin/submissions/{created_id}/delete", follow_redirects=False)

    listing = auth_client.get("/admin?show_deleted=true")

    assert "Иван Петров" in listing.text
    assert "Вернуть" in listing.text


def test_hidden_flag_shows_only_deleted(auth_client, created_id, client, valid_payload):
    """Список скрытых не должен содержать видимые заявки.

    Регрессия: под надписью «Показать скрытые» показывались все записи разом, и у каждой
    была кнопка «Вернуть», которой нечего было вернуть.
    """
    other_id = _create_another(client, valid_payload, name="Вторая заявка")

    auth_client.post(f"/admin/submissions/{created_id}/delete", follow_redirects=False)

    listing = auth_client.get("/admin?show_deleted=true")

    assert "Иван Петров" in listing.text
    assert "Вторая заявка" not in listing.text
    assert listing.text.count("Вернуть") == 1
    assert f"/admin/submissions/{other_id}/restore" not in listing.text


def test_hidden_count_shows_only_deleted(
    auth_client, client, created_id, valid_payload
):
    """Счётчик «скрытых» считает именно скрытые записи, а не все."""
    _create_another(client, valid_payload, name="Вторая заявка")

    listing = auth_client.get("/admin")

    assert "скрытых: 0" in listing.text
    assert "Скрытых заявок нет" in listing.text

    auth_client.post(f"/admin/submissions/{created_id}/delete", follow_redirects=False)

    listing = auth_client.get("/admin")

    assert "скрытых: 1" in listing.text
    assert "Показать скрытые (1)" in listing.text


def _create_another(client, payload: dict, *, name: str) -> int:
    """Отправляет вторую валидную заявку и возвращает её id."""
    response = client.post("/api/submissions", json={**payload, "name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_restore_brings_submission_back(auth_client, created_id):
    """Восстановление возвращает запись в список и выгрузки."""
    auth_client.post(f"/admin/submissions/{created_id}/delete", follow_redirects=False)

    response = auth_client.post(
        f"/admin/submissions/{created_id}/restore", follow_redirects=False
    )

    assert response.status_code == 303
    assert _get(created_id).deleted_at is None
    assert "Иван Петров" in auth_client.get("/admin").text


def test_delete_and_restore_require_session(client, created_id):
    """Скрытие и восстановление доступны только по сессии."""
    assert client.post(f"/admin/submissions/{created_id}/delete").status_code == 403
    assert client.post(f"/admin/submissions/{created_id}/restore").status_code == 403
    assert _get(created_id).deleted_at is None


def test_delete_missing_submission_returns_404(auth_client):
    """Скрытие несуществующей заявки — 404."""
    response = auth_client.post("/admin/submissions/999999/delete")

    assert response.status_code == 404


def test_logout_removes_admin_button_access(auth_client):
    """После выхода страница правки снова закрыта."""
    auth_client.get("/admin/logout", follow_redirects=False)

    assert auth_client.get("/admin", follow_redirects=False).status_code == 303
    assert SESSION_COOKIE_NAME not in auth_client.cookies


def test_note_is_last_export_column(auth_client, created_id):
    """Заметка идёт последней колонкой листа «Заявки» и не попадает в «Подробно»."""
    auth_client.post(
        f"/admin/submissions/{created_id}/edit",
        data={
            "name": "Иван Петров",
            "company": "ООО Ромашка",
            "phone": "+7 999 123-45-67",
            "email": "ivan@example.com",
            "note": "Лучший клиент",
        },
        follow_redirects=False,
    )

    workbook = load_workbook(
        io.BytesIO(auth_client.get("/api/submissions.xlsx").content)
    )

    sheet = workbook["Заявки"]
    assert sheet.cell(row=1, column=sheet.max_column).value == "Заметка"
    assert sheet.cell(row=2, column=sheet.max_column).value == "Лучший клиент"

    details = "".join(
        str(cell.value or "")
        for row in workbook["Подробно"].iter_rows()
        for cell in row
    )
    assert "Лучший клиент" not in details
