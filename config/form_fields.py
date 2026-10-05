"""Описание полей анкеты выставки — единственный источник правды.

Из этого описания строятся HTML-форма (templates/form.html), валидация на сервере
(schemas.py) и колонки выгрузки (services/exporters.py). Чтобы добавить, убрать или
переименовать поле, правьте только этот файл.

Раскладка блоков повторяет бумажный макет: чекбоксы либо в две колонки, либо в один ряд.
"""

from typing import Any

TEXT = "text"
TEXTAREA = "textarea"
CHECKBOX_GROUP = "checkbox_group"
CONSENT = "consent"

LAYOUT_COLUMNS = "columns"
LAYOUT_ROW = "row"

CONSENT_TYPE = CONSENT

FORM_FIELDS: list[dict[str, Any]] = [
    {
        "key": "name",
        "number": 1,
        "label": "Имя",
        "type": TEXT,
        "required": True,
        "placeholder": "Как к вам обращаться",
        "autocomplete": "name",
        "max_length": 120,
    },
    {
        "key": "company",
        "number": 2,
        "label": "Компания",
        "type": TEXT,
        "required": False,
        "placeholder": "Не обязательно",
        "autocomplete": "organization",
        "max_length": 200,
    },
    {
        "key": "role",
        "number": 3,
        "label": "Кто вы?",
        "type": CHECKBOX_GROUP,
        "hint": "Можно выбрать несколько вариантов",
        "layout": LAYOUT_COLUMNS,
        "columns": [
            [
                "интегратор",
                "дизайнер, архитектор",
                "электрик, слаботочник",
                "застройщик, девелопер",
                "проектировщик",
            ],
            [
                "частное лицо, смотрю для себя",
                "заказчик от юр. лица",
                "инженер по эксплуатации",
                "продавец УД, ЭУИ, инженерки",
                "другое",
            ],
        ],
        "other_key": "role_other",
        "other_label": "«другое»: уточните, кто вы",
        "other_placeholder": "например: журналист",
        "other_max_length": 120,
    },
    {
        "key": "stall",
        "number": 4,
        "label": "Что интересует на стенде iRidi",
        "export_title": "Что интересует на стенде",
        "type": CHECKBOX_GROUP,
        "hint": "Можно выбрать несколько вариантов",
        "layout": LAYOUT_COLUMNS,
        "columns": [
            [
                "материалы о продуктах",
                "ищу себе инсталлятора",
                "обучающие курсы",
            ],
            [
                "ищу вендора как инсталлятор",
                "хочу стать дистрибьютором",
                "договориться о презентации pre-sale менеджера",
            ],
        ],
    },
    {
        "key": "directions",
        "number": 5,
        "label": "Интересующие направления",
        "type": CHECKBOX_GROUP,
        "hint": "Можно выбрать несколько вариантов",
        "layout": LAYOUT_ROW,
        "options": [
            "SmartHome",
            "Коммерция, AV",
            "МКД",
            "Отели",
            "BMS",
        ],
    },
    {
        "key": "interest",
        "number": 6,
        "label": "Что интересует",
        "type": CHECKBOX_GROUP,
        "hint": "Можно выбрать несколько вариантов",
        "layout": LAYOUT_ROW,
        "options": [
            "Нужно КП, презентация, встреча или партнерство",
            "Будущие планы",
            "Смотрю, что есть на рынке",
        ],
    },
    {
        "key": "phone",
        "number": 7,
        "label": "Телефон",
        "type": TEXT,
        "required": False,
        "required_note": "или укажите email ниже",
        "inputmode": "tel",
        "autocomplete": "tel",
        "placeholder": "+___ ___ ___-__-__",
        "max_length": 40,
    },
    {
        "key": "email",
        "number": 8,
        "label": "Email",
        "type": TEXT,
        "required": False,
        "required_note": "или укажите телефон выше",
        "inputmode": "email",
        "autocomplete": "email",
        "placeholder": "name@example.com",
        "max_length": 120,
    },
    {
        "key": "after_show",
        "number": 9,
        "label": "Выслать/сделать после выставки",
        "type": TEXTAREA,
        "required": False,
        "rows": 3,
        "placeholder": "Что выслать или сделать после выставки",
        "max_length": 1000,
    },
    {
        "key": "consent",
        "number": 10,
        "label": "Согласие на обработку персональных данных",
        "export_title": "Согласие ПДн",
        "type": CONSENT,
        "required": True,
    },
]


def field_by_key(key: str) -> dict[str, Any] | None:
    """Возвращает описание поля по ключу или None, если такого поля нет."""
    for field in FORM_FIELDS:
        if field["key"] == key:
            return field
    return None


def checkbox_fields() -> list[dict[str, Any]]:
    """Возвращает все поля-группы чекбоксов в порядке анкеты."""
    return [field for field in FORM_FIELDS if field["type"] == CHECKBOX_GROUP]


def checkbox_options(field: dict[str, Any]) -> list[str]:
    """Возвращает плоский список вариантов поля-группы чекбоксов.

    Поддерживает обе раскладки: LAYOUT_ROW (options) и LAYOUT_COLUMNS (columns).
    """
    if field.get("layout") == LAYOUT_COLUMNS:
        return [option for column in field["columns"] for option in column]
    return list(field.get("options", []))


def is_required(field: dict[str, Any]) -> bool:
    """Сообщает, обязательно ли поле для заполнения."""
    return bool(field.get("required"))


def max_length(field: dict[str, Any]) -> int | None:
    """Возвращает лимит длины поля (или None, если ограничения нет)."""
    return field.get("max_length")


def other_field(field: dict[str, Any]) -> dict[str, Any] | None:
    """Возвращает описание текстового поля рядом с чекбоксом «другое».

    Поле выводится отдельной строкой под колонками вариантов, поэтому подпись в нём
    обязана быть понятна сама по себе и переводится вместе с остальным текстом.
    """
    other_key = field.get("other_key")
    if not other_key:
        return None
    return {
        "key": other_key,
        "label": field.get("other_label", "Уточните"),
        "placeholder": field.get("other_placeholder", ""),
        "max_length": field.get("other_max_length", 120),
    }
