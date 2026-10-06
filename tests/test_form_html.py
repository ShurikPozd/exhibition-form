"""Проверки отрисованной анкеты: уникальность id, подписи, обязательные поля.

Регрессия из ручного прогона: id чекбоксов считались по позиции внутри колонки,
поэтому у блоков в две колонки пятый вариант слева и первый справа имели один id —
и тап по подписи справа отмечал чекбокс слева.
"""

import re

import pytest

from config.form_fields import LAYOUT_COLUMNS, checkbox_fields

ID_PATTERN = re.compile(r'id="([^"]+)"')
FOR_PATTERN = re.compile(r'for="([^"]+)"')
REQUIRED_KEYS = ["name", "phone", "email"]
HINT_KEYS = ["name", "phone", "email", "consent"]


@pytest.fixture()
def page(client):
    """Отрисованная анкета: html одного запроса.

    Область — функциональная, как и у клиента: один TestClient на тест не даёт cookie
    и данным утекать между тестами (иначе проверки «без доступа» проходят по чужой сессии).
    """
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def test_all_ids_are_unique(page):
    """Все id на странице различны — иначе тап по подписи попадает не туда."""
    ids = ID_PATTERN.findall(page)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    assert duplicates == [], f"повторяющиеся id: {duplicates}"


def test_every_label_points_to_existing_id(page):
    """Каждый label for ссылается на существующий контрол."""
    ids = set(ID_PATTERN.findall(page))
    dangling = sorted(
        {target for target in FOR_PATTERN.findall(page) if target not in ids}
    )
    assert dangling == [], f"label ссылается в пустоту: {dangling}"


def test_checkbox_ids_count_columns(page):
    """В id чекбокса есть номер колонки: f-role-c1-0 и f-role-c2-0 — разные варианты."""
    for field in checkbox_fields():
        key = field["key"]
        assert f'id="f-{key}-c1-0"' in page, key
        if field.get("layout") == LAYOUT_COLUMNS:
            assert f'id="f-{key}-c2-0"' in page, key


def test_required_fields_are_marked(page):
    """Звёздочка стоит у обязательных полей: имя и «телефон или email»."""
    for key in REQUIRED_KEYS:
        position = page.index(f'for="f-{key}"')
        window = page[max(0, position - 200) : position + 400]
        assert 'class="req"' in window, f"нет звёздочки у поля {key}"


def test_consent_is_marked(page):
    position = page.index('for="f-consent"')
    window = page[position : position + 400]
    assert 'class="req"' in window, "нет звёздочки у согласия"


def test_phone_and_email_explain_each_other(page):
    """У телефона и email есть пояснение, что достаточно одного из них."""
    assert "или укажите email ниже" in page
    assert "или укажите телефон выше" in page


def test_lead_explains_required_rules(page):
    """Шапка не обещает, что нужны все поля со звёздочкой."""
    assert "Обязательно: имя, телефон или email" in page
    assert "Все поля со звёздочкой обязательны" not in page


def test_hints_exist_for_key_fields(page):
    """Под каждым ключевым полем есть блок для подсказки."""
    for key in HINT_KEYS:
        assert f'id="hint-{key}"' in page, key


def test_other_input_has_id_and_is_outside_label(page):
    """Поле «уточните» доступно скрипту и не лежит внутри label чекбокса."""
    position = page.index('id="f-role_other"')
    label_open = page.rindex("<label", 0, position)
    label_close = page.rindex("</label>", 0, position)
    assert label_close > label_open, "label чекбокса не закрыт до поля «уточните»"


def test_other_input_has_own_label(page):
    """У поля «уточните» своя подпись, клик по ней ведёт в поле."""
    assert 'class="check-other__label" for="f-role_other"' in page


def test_other_input_has_hint(page):
    """Под полем есть место для подсказки — туда попадает ошибка про «другое»."""
    assert 'id="hint-role_other"' in page
