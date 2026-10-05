"""Проверки защиты выгрузки: /admin и файлы закрыты токеном (fail-closed)."""

import settings
from conftest import TEST_TOKEN


def test_admin_denied_when_token_not_configured(client, monkeypatch):
    """Если EXPORT_TOKEN не задан, выгрузка закрыта и объясняет, что делать.

    Обратный вариант (пустой токен = открытый доступ) опасен: заявки содержат
    персональные данные, и адрес /admin не должен быть открыт «авось никто не угадает».
    """
    monkeypatch.setattr(settings, "EXPORT_TOKEN", None)

    response = client.get("/admin")

    assert response.status_code == 403
    assert "EXPORT_TOKEN" in response.json()["detail"]


def test_admin_denied_with_wrong_token(client):
    """Неверный токен не подходит (значение латиницей: заголовок HTTP — latin-1)."""
    response = client.get("/admin", headers={"X-Export-Token": "wrong-token"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Неверный токен доступа к выгрузке."


def test_admin_opens_with_header(client):
    """Верный токен в заголовке открывает список заявок."""
    response = client.get("/admin", headers={"X-Export-Token": TEST_TOKEN})
    assert response.status_code == 200
    assert "Заявки с выставки" in response.text


def test_admin_opens_with_query(client):
    """Верный токен в адресе открывает список — так скачивание работает ссылкой."""
    response = client.get(f"/admin?token={TEST_TOKEN}")
    assert response.status_code == 200


def test_json_list_requires_token(client):
    """Список заявок в JSON тоже под токеном."""
    assert client.get("/api/submissions").status_code == 403
    assert (
        client.get(
            "/api/submissions", headers={"X-Export-Token": TEST_TOKEN}
        ).status_code
        == 200
    )


def test_xlsx_requires_token(client):
    """Файл Excel не отдаётся без токена."""
    assert client.get("/api/submissions.xlsx").status_code == 403
    response = client.get(
        "/api/submissions.xlsx", headers={"X-Export-Token": TEST_TOKEN}
    )
    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # xlsx — это zip-архив


def test_csv_requires_token(client):
    """CSV тоже под токеном."""
    assert client.get("/api/submissions.csv").status_code == 403
    assert (
        client.get(
            "/api/submissions.csv", headers={"X-Export-Token": TEST_TOKEN}
        ).status_code
        == 200
    )
