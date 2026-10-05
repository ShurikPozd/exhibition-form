"""Проверки API формы: рендер страницы, приём заявки, чтение из базы и отказы валидации."""

import pytest

from config.consent_text import CONSENT_VERSION
from models import Submission

ENDPOINT = "/api/submissions"


def test_healthz(client):
    """Healthcheck отвечает без ошибок — на него завязан Docker."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_form_page_renders(client):
    """Главная отдаёт анкету со всеми блоками и подписями."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    page = response.text
    for label in (
        "Анкета участника выставки",
        "Имя",
        "Кто вы?",
        "Что интересует на стенде",
        "Интересующие направления",
        "Что интересует",
        "Согласие на обработку персональных данных",
    ):
        assert label in page, label


def test_form_contains_all_checkbox_options(client):
    """Каждый вариант из описания анкеты попал в HTML."""
    from config.form_fields import checkbox_fields, checkbox_options

    page = client.get("/").text
    for field in checkbox_fields():
        for option in checkbox_options(field):
            assert f'value="{option}"' in page, option


def test_submission_is_saved_and_read_back(client, session, valid_payload):
    """Главный сценарий: 201, а запись действительно лежит в базе."""
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 201

    body = response.json()
    assert body["id"] > 0
    assert "created_at" in body

    saved = session.get(Submission, body["id"])
    assert saved is not None
    assert saved.name == "Иван Петров"
    assert saved.company == "ООО Ромашка"
    assert saved.phone == "+7 999 123-45-67"
    assert saved.email == "ivan@example.com"
    assert saved.payload["directions"] == ["SmartHome", "МКД"]
    assert saved.payload["stall"] == ["материалы о продуктах", "обучающие курсы"]
    assert saved.payload["after_show"] == "Прислать прайс"
    assert saved.consent_version == CONSENT_VERSION


def test_response_has_no_personal_data(client, valid_payload):
    """В ответе нет персональных данных — только подтверждение."""
    response = client.post(ENDPOINT, json=valid_payload)
    body = response.json()
    assert set(body) == {"id", "created_at"}
    assert "Иван Петров" not in response.text


def test_empty_name_rejected(client, valid_payload):
    """Пустое имя — 422."""
    valid_payload["name"] = "   "
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


def test_contact_is_required(client, valid_payload):
    """Ни телефона, ни email — 422: ответить посетителю будет нечем."""
    valid_payload["phone"] = ""
    valid_payload["email"] = ""
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


def test_broken_email_rejected(client, valid_payload):
    """Неполный адрес почты — 422."""
    valid_payload["email"] = "ivan@"
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


def test_short_phone_rejected(client, valid_payload):
    """Телефон из трёх цифр — 422."""
    valid_payload["phone"] = "123"
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "phone",
    ["+375 29 123-45-67", "+49 151 12345678", "+1 202 555 0143", "0037 812 345 678"],
)
def test_international_phone_is_stored_as_typed(client, session, valid_payload, phone):
    """Номер из другой страны принимается и сохраняется ровно как введён.

    Проверяется только количество цифр (10–15 — длина номера по E.164): определить
    страну без базы стран нельзя, а отклонять номер посетителя нельзя тем более.
    """
    valid_payload["phone"] = phone
    valid_payload["email"] = ""
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 201

    saved = session.get(Submission, response.json()["id"])
    assert saved.phone == phone


def test_consent_is_required(client, valid_payload):
    """Без согласия на ПДн заявка не принимается."""
    valid_payload["consent"] = False
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


def test_other_option_requires_text(client, valid_payload):
    """Отметили «другое» в блоке «Кто вы?» — нужно уточнение."""
    valid_payload["role"] = ["другое"]
    valid_payload["role_other"] = ""
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422

    valid_payload["role_other"] = "журналист"
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 201


def test_unknown_checkbox_rejected(client, valid_payload):
    """Варианта нет в анкете — 422, а не «тихо сохраним мусор»."""
    valid_payload["directions"] = ["SmartHome", "Квантовые компьютеры"]
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


def test_unknown_field_rejected(client, valid_payload):
    """Лишнее поле в запросе — 422."""
    valid_payload["promo_code"] = "SALE"
    response = client.post(ENDPOINT, json=valid_payload)
    assert response.status_code == 422


def test_rejected_submission_is_not_stored(client, session, valid_payload):
    """Отклонённая заявка не появляется в базе."""
    before = session.query(Submission).count()
    valid_payload["consent"] = False

    response = client.post(ENDPOINT, json=valid_payload)

    assert response.status_code == 422
    assert session.query(Submission).count() == before
