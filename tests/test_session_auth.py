"""Вход в админку по паролю: сессионная cookie, выход и подделка cookie."""

import settings
from conftest import TEST_ADMIN_PASSWORD


def test_login_page_opens(client):
    """Форма входа доступна без сессии и просит пароль."""
    response = client.get("/admin/login")

    assert response.status_code == 200
    assert 'name="password"' in response.text


def test_login_sets_session_and_opens_admin(auth_client):
    """Верный пароль выдаёт cookie, после которой /admin открывается без токена."""
    assert auth_client.get("/admin").status_code == 200


def test_login_rejects_wrong_password(client):
    """Неверный пароль не выдаёт cookie: /admin остаётся закрыт."""
    response = client.post(
        "/admin/login", data={"password": "неверный"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert "/admin/login" in response.headers["location"]
    assert "admin_session" not in auth_cookie_names(client)


def test_login_rejects_empty_password(client):
    """Пустой пароль отклоняется до сравнения."""
    response = client.post(
        "/admin/login", data={"password": ""}, follow_redirects=False
    )

    assert response.status_code == 303
    assert "admin_session" not in auth_cookie_names(client)


def test_login_error_visible_on_form(client):
    """Текст ошибки показывается на форме, а не теряется в адресе."""
    response = client.post(
        "/admin/login",
        data={"password": "неверный"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Неверный пароль" in response.text


def test_login_closed_without_password(client, monkeypatch):
    """Если ADMIN_PASSWORD не задан, вход закрыт и объясняет, что настроить."""
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", None)

    response = client.get("/admin/login")

    assert response.status_code == 200
    assert "ADMIN_PASSWORD" in response.text


def test_admin_redirects_to_login(client):
    """Без сессии и токена /admin отправляет на форму входа, а не ругается 403."""
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_forged_cookie_is_rejected(client, auth_client):
    """Подделка cookie в браузере не даёт доступа: подпись проверяется."""
    auth_client.cookies.set("admin_session", "1234567890.deadbeef")

    assert auth_client.get("/admin", follow_redirects=False).status_code == 303


def test_session_invalid_after_password_change(auth_client, monkeypatch):
    """Смена пароля в .env обесценивает ранее выданные cookie."""
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "другой-пароль")

    assert auth_client.get("/admin", follow_redirects=False).status_code == 303


def test_logout_clears_session(auth_client):
    """Выход сбрасывает cookie, и админка снова закрыта."""
    response = auth_client.get("/admin/logout", follow_redirects=False)

    assert response.status_code == 303
    assert auth_client.get("/admin", follow_redirects=False).status_code == 303


def test_login_page_redirects_when_session_already_valid(auth_client):
    """С активной сессией форма входа сразу отправляет в админку."""
    response = auth_client.get("/admin/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_password_never_appears_in_url(auth_client):
    """Пароль не попадает в адрес: его вводят в форму, в cookie — только подпись."""
    auth_client.get("/admin/logout", follow_redirects=False)
    response = auth_client.post(
        "/admin/login",
        data={"password": TEST_ADMIN_PASSWORD},
        follow_redirects=False,
    )

    assert TEST_ADMIN_PASSWORD not in response.headers["location"]
    assert TEST_ADMIN_PASSWORD not in auth_cookie_names(auth_client)


def auth_cookie_names(client) -> str:
    """Возвращает имена cookie клиента одной строкой (для проверок входа)."""
    return " ".join(client.cookies.keys())
