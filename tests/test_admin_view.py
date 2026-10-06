"""Карточка заявки в админке: что показываем и что молча пропускаем.

Карточка пришла на смену таблице из 13 колонок, ради которой приходилось листать
экран вправо. Проверяем, что в ней остались все данные заявки, совпадают со
значениями выгрузки и не превращаются в пустые строки.
"""

from datetime import datetime

from models import Submission
from services import exporters
from services.admin_view import build_card, build_cards

CREATED_AT = datetime(2026, 10, 5, 21, 37)


def _submission(**overrides) -> Submission:
    """Собирает заявку в памяти: карточке база не нужна."""
    data = {
        "id": 5,
        "created_at": CREATED_AT,
        "name": "Иван Петров",
        "company": "ООО Ромашка",
        "phone": "+7 999 123-45-67",
        "email": "ivan@example.com",
        "payload": {
            "role": ["интегратор"],
            "role_other": "",
            "stall": ["материалы о продуктах"],
            "directions": ["SmartHome"],
            "interest": ["Будущие планы"],
            "after_show": "Прислать прайс",
        },
        "consent_version": "2026-09-01",
        "note": "Лучший клиент",
    }
    data.update(overrides)
    return Submission(**data)


def test_card_shows_contacts_and_note():
    """Контакты склеены в одну строку, заметка на месте."""
    card = build_card(_submission())

    assert card["id"] == 5
    assert card["name"] == "Иван Петров"
    assert card["company"] == "ООО Ромашка"
    assert card["contacts"] == "+7 999 123-45-67 · ivan@example.com"
    assert card["note"] == "Лучший клиент"
    assert card["deleted"] is False


def test_card_date_is_readable():
    """Дата в карточке без года в формате ISO и без секунд."""
    assert build_card(_submission())["date"] == "05.10.2026 21:37"


def test_card_lists_answers_with_labels():
    """Ответы посетителя идут подписанными строками в порядке анкеты."""
    card = build_card(_submission())

    assert card["answers"] == [
        {"label": "Кто вы?", "value": "интегратор"},
        {"label": "Что интересует на стенде", "value": "материалы о продуктах"},
        {"label": "Интересующие направления", "value": "SmartHome"},
        {"label": "Что интересует", "value": "Будущие планы"},
        {"label": "Выслать/сделать после выставки", "value": "Прислать прайс"},
    ]


def test_card_spells_out_other_option():
    """Пункт «другое» показывается с расшифровкой, как в Excel."""
    card = build_card(
        _submission(payload={"role": ["другое"], "role_other": "журналист"})
    )

    assert card["answers"][0]["value"] == "другое: журналист"


def test_card_skips_unanswered_fields():
    """Пустые ответы не занимают место: незаполненных строк в карточке нет."""
    card = build_card(
        _submission(payload={"role": ["интегратор"]}, note="", company="")
    )

    assert card["answers"] == [{"label": "Кто вы?", "value": "интегратор"}]
    assert card["note"] == ""
    assert card["company"] == ""


def test_card_does_not_show_consent():
    """Согласие есть у любой сохранённой заявки — повторять его незачем."""
    card = build_card(_submission())

    assert "Согласие" not in " ".join(answer["label"] for answer in card["answers"])


def test_card_marks_deleted_submission():
    """Скрытая заявка помечена: карточка окрашивается, кнопка меняется."""
    card = build_card(_submission(deleted_at=datetime(2026, 10, 6, 9, 0)))

    assert card["deleted"] is True


def test_card_contacts_without_email():
    """В заявке без почты строка контактов состоит только из телефона."""
    card = build_card(_submission(email=""))

    assert card["contacts"] == "+7 999 123-45-67"


def test_card_answers_match_export_columns():
    """Значения карточки совпадают с колонками выгрузки.

    Регрессия: если админка и Excel начнут считать значения по-разному (например,
    по-разному раскрывать «другое»), разойдутся и проверки заявок, и выгрузка.
    """
    submission = _submission()

    card = build_card(submission)
    header_row = exporters.rows([submission])[0]
    row = dict(zip(exporters.headers(), header_row))

    for answer in card["answers"]:
        assert answer["value"] == row[answer["label"]]
    assert card["note"] == row[exporters.NOTE_HEADER]


def test_build_cards_keeps_order():
    """Список карточек идёт в том же порядке, что и записи: свежие сверху."""
    items = [_submission(id=index) for index in (3, 2, 1)]

    assert [card["id"] for card in build_cards(items)] == [3, 2, 1]
