"""Постраничный список заявок в админке: размер страницы, номера страниц, возврат.

Задача разбивки: список не должен расти одной длинной страницей. Размер страницы
выбирается человеком и запоминается в cookie, чтобы не тянуть его в каждой ссылке,
а после правки или скрытия заявки нужно вернуться на ту же страницу, а не в начало.
"""

from handlers.admin import PER_PAGE_COOKIE_NAME
from models import Submission


def _fill(client, payload: dict, count: int) -> list[int]:
    """Создаёт count заявок и возвращает их id в порядке создания."""
    ids: list[int] = []
    for number in range(count):
        response = client.post(
            "/api/submissions",
            json={**payload, "name": f"Заявка {number:02d}", "company": ""},
        )
        assert response.status_code == 201, response.text
        ids.append(int(response.json()["id"]))
    return ids


def _card_ids(text: str) -> list[int]:
    """Достаёт номера заявок из карточек страницы по подписи «№»."""
    parts = text.split(">№")
    found = []
    for part in parts[1:]:
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        found.append(int(digits))
    return found


def test_first_page_holds_ten_cards(auth_client, client, valid_payload):
    """Без настройки на странице десять карточек, свежие сверху."""
    _fill(client, valid_payload, 25)

    listing = auth_client.get("/admin")

    assert _card_ids(listing.text) == list(range(25, 15, -1))
    assert "Показано 1–10 из 25" in listing.text
    assert "Страница 1 из 3" in listing.text


def test_second_and_third_pages(auth_client, client, valid_payload):
    """Вторая и третья страницы отдают следующие порции, свежие сверху."""
    _fill(client, valid_payload, 25)

    second = auth_client.get("/admin?page=2")
    assert _card_ids(second.text) == list(range(15, 5, -1))
    assert "Показано 11–20 из 25" in second.text
    assert "Страница 2 из 3" in second.text

    third = auth_client.get("/admin?page=3")
    assert _card_ids(third.text) == list(range(5, 0, -1))
    assert "Показано 21–25 из 25" in third.text


def test_page_beyond_last_shows_last_page(auth_client, client, valid_payload):
    """Ссылка из истории браузера не должна вести в пустоту."""
    _fill(client, valid_payload, 25)

    listing = auth_client.get("/admin?page=999")

    assert _card_ids(listing.text) == list(range(5, 0, -1))
    assert "Страница 3 из 3" in listing.text


def test_broken_page_and_size_do_not_break_page(auth_client, client, valid_payload):
    """Мусор в адресе не превращается в ошибку 422: показывается первая страница."""
    _fill(client, valid_payload, 25)

    assert auth_client.get("/admin?page=abc").status_code == 200
    assert auth_client.get("/admin?page=-3").status_code == 200
    assert auth_client.get("/admin?per_page=13").status_code == 200

    first_page = list(range(25, 15, -1))
    assert _card_ids(auth_client.get("/admin?page=abc").text) == first_page
    assert _card_ids(auth_client.get("/admin?per_page=13").text) == first_page


def test_page_size_choice_saved_in_cookie(auth_client, client, valid_payload):
    """Выбранный размер страницы запоминается и действует дальше сам."""
    _fill(client, valid_payload, 25)

    response = auth_client.get("/admin?per_page=20", follow_redirects=False)

    assert response.status_code == 303
    assert PER_PAGE_COOKIE_NAME in auth_client.cookies
    assert auth_client.cookies[PER_PAGE_COOKIE_NAME] == "20"

    listing = auth_client.get("/admin")
    assert len(_card_ids(listing.text)) == 20
    assert "Показано 1–20 из 25" in listing.text
    assert "Страница 1 из 2" in listing.text


def test_page_size_survives_paging(auth_client, client, valid_payload):
    """Размер страницы не сбрасывается при переходе на следующую страницу."""
    _fill(client, valid_payload, 25)
    auth_client.get("/admin?per_page=20", follow_redirects=False)

    second = auth_client.get("/admin?page=2")

    assert _card_ids(second.text) == list(range(5, 0, -1))
    assert "Страница 2 из 2" in second.text


def test_hidden_list_paginated_too(auth_client, client, valid_payload):
    """Список скрытых листается тем же размером страницы."""
    ids = _fill(client, valid_payload, 12)
    for submission_id in ids[:11]:
        assert (
            auth_client.post(
                f"/admin/submissions/{submission_id}/delete", follow_redirects=False
            ).status_code
            == 303
        )

    listing = auth_client.get("/admin?show_deleted=true")

    assert len(_card_ids(listing.text)) == 10
    assert "Показано 1–10 из 11" in listing.text
    assert "Страница 1 из 2" in listing.text

    second = auth_client.get("/admin?show_deleted=true&page=2")
    assert _card_ids(second.text) == [ids[0]]


def test_delete_keeps_current_page(auth_client, client, valid_payload):
    """После скрытия заявки остаёмся на той же странице, а не в начале."""
    ids = _fill(client, valid_payload, 25)

    response = auth_client.post(
        f"/admin/submissions/{ids[5]}/delete",
        data={"next": "/admin?page=2"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?page=2"


def test_restore_keeps_current_page(auth_client, client, valid_payload):
    """Восстановление из списка скрытых тоже возвращает на ту же страницу."""
    ids = _fill(client, valid_payload, 12)
    auth_client.post(f"/admin/submissions/{ids[0]}/delete", follow_redirects=False)

    response = auth_client.post(
        f"/admin/submissions/{ids[0]}/restore",
        data={"next": "/admin?show_deleted=true&page=2"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?show_deleted=true&page=2"


def test_restore_without_next_goes_to_hidden_list(auth_client, created_id):
    """Без адреса возврата восстановление ведёт в список скрытых, как раньше."""
    auth_client.post(f"/admin/submissions/{created_id}/delete", follow_redirects=False)

    response = auth_client.post(
        f"/admin/submissions/{created_id}/restore", follow_redirects=False
    )

    assert response.headers["location"] == "/admin?show_deleted=true"


def test_edit_keeps_current_page(auth_client, client, valid_payload):
    """Правка со страницы 2 возвращает на страницу 2."""
    ids = _fill(client, valid_payload, 25)

    form = auth_client.get(f"/admin/submissions/{ids[5]}/edit?next=/admin%3Fpage%3D2")
    assert 'name="next" value="/admin?page=2"' in form.text

    response = auth_client.post(
        f"/admin/submissions/{ids[5]}/edit",
        data={
            "name": "Правка со страницы",
            "phone": "+7 999 000-11-22",
            "next": "/admin?page=2",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?page=2"


def test_next_outside_admin_is_ignored(auth_client, session, created_id):
    """Адрес возврата из формы принимается только из самой админки."""
    for hostile in ("https://example.com/", "//example.com/", "/evil?page=2"):
        response = auth_client.post(
            f"/admin/submissions/{created_id}/delete",
            data={"next": hostile},
            follow_redirects=False,
        )

        assert response.headers["location"] == "/admin"
        assert session.get(Submission, created_id).deleted_at is not None

        auth_client.post(
            f"/admin/submissions/{created_id}/restore", follow_redirects=False
        )


def test_html_escaped_in_card(auth_client, client, valid_payload):
    """Имя с разметкой показывается текстом, а не разметкой."""
    client.post(
        "/api/submissions",
        json={**valid_payload, "name": "<script>alert(1)</script>", "company": ""},
    )

    listing = auth_client.get("/admin")

    assert "<script>alert(1)</script>" not in listing.text
    assert "&lt;script&gt;" in listing.text
