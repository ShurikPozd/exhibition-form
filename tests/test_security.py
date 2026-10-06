"""Защита выгрузки: /admin открывается по сессии или токену, файлы — по тому же правилу.

Проверки fail-closed сохранены: если в .env не задано ни ADMIN_PASSWORD, ни EXPORT_TOKEN,
доступ закрыт, а не открыт «на авось» — заявки содержат персональные данные.
"""

import settings
from conftest import TEST_ADMIN_PASSWORD, TEST_TOKEN


def test_admin_redirects_to_login_without_access(client):
    """Без сессии и токена страница админки отправляет на форму входа."""
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_redirects_with_wrong_token(client):
    """Неверный токен не подходит (значение латиницей: заголовок HTTP — latin-1)."""
    response = client.get(
        "/admin", headers={"X-Export-Token": "wrong-token"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_redirects_with_non_ascii_token(client):
    """Токен с не-ASCII символом даёт редирект, а не падение на hmac.compare_digest.

    Сравнение строк в compare_digest поддерживает только ASCII: без сравнения байтов
    русскоязычный токен ронял проверку с TypeError, и посетитель видел 500.
    """
    response = client.get(
        "/admin", params={"token": "неправильный"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.status_code != 500


def test_admin_opens_with_header(client):
    """Верный токен в заголовке открывает список заявок."""
    response = client.get("/admin", headers={"X-Export-Token": TEST_TOKEN})

    assert response.status_code == 200
    assert "Заявки с выставки" in response.text


def test_admin_opens_with_query(client):
    """Верный токен в адресе открывает список — так скачивание работает ссылкой."""
    response = client.get(f"/admin?token={TEST_TOKEN}")

    assert response.status_code == 200


def test_export_closed_when_nothing_configured(client, monkeypatch):
    """Если не заданы ни пароль, ни токен, выгрузка закрыта и объясняет, что делать."""
    monkeypatch.setattr(settings, "EXPORT_TOKEN", None)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", None)

    response = client.get("/api/submissions.xlsx")

    assert response.status_code == 403
    assert "EXPORT_TOKEN" in response.json()["detail"]


def test_json_list_requires_access(client):
    """Список заявок в JSON открыт по токену и по сессии, а без них — нет."""
    assert client.get("/api/submissions").status_code == 403
    assert (
        client.get(
            "/api/submissions", headers={"X-Export-Token": TEST_TOKEN}
        ).status_code
        == 200
    )

    client.cookies.clear()
    assert (
        client.post(
            "/admin/login",
            data={"password": TEST_ADMIN_PASSWORD},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert client.get("/api/submissions").status_code == 200


def test_xlsx_requires_access(client):
    """Файл Excel не отдаётся без сессии или токена."""
    assert client.get("/api/submissions.xlsx").status_code == 403

    response = client.get(
        "/api/submissions.xlsx", headers={"X-Export-Token": TEST_TOKEN}
    )

    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # xlsx — это zip-архив


def test_csv_requires_access(client):
    """CSV тоже под сессией или токеном."""
    assert client.get("/api/submissions.csv").status_code == 403

    response = client.get(
        "/api/submissions.csv", headers={"X-Export-Token": TEST_TOKEN}
    )

    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["content-type"]


def test_wrong_token_denied_with_non_ascii_value(client):
    """Регрессия compare_digest на защищённой ручке: не-ASCII токен даёт 403, не 500."""
    response = client.get("/api/submissions", params={"token": "неправильный"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Неверный токен доступа к выгрузке."
