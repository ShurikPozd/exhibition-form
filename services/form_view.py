"""Подготовка данных для шаблона анкеты.

Шаблон ничего не знает про конкретные поля: он рисует то, что пришло из
config/form_fields.py. Поэтому изменение анкеты (новый пункт, другая раскладка) не
требует правок HTML.
"""

from typing import Any

import settings
from config.consent_text import CONSENT_VERSION, consent_text
from config.form_fields import (
    CHECKBOX_GROUP,
    CONSENT,
    FORM_FIELDS,
    LAYOUT_COLUMNS,
    checkbox_options,
    max_length,
    other_field,
)


def build_form_context() -> dict[str, Any]:
    """Собирает контекст для form.html: поля, текст согласия, версию согласия."""
    fields: list[dict[str, Any]] = []

    for field in FORM_FIELDS:
        item: dict[str, Any] = dict(field)
        item["max_length"] = max_length(field)

        if field["type"] == CHECKBOX_GROUP:
            item["options"] = checkbox_options(field)
            item["is_columns"] = field.get("layout") == LAYOUT_COLUMNS
            # Колонки приводим к общему виду, чтобы шаблон не знал про две раскладки
            item["columns"] = (
                [list(column) for column in field["columns"]]
                if item["is_columns"]
                else [list(field.get("options", []))]
            )
            item["other"] = other_field(field)

        if field["type"] == CONSENT:
            item["consent_text"] = consent_text(
                settings.CONSENT_OPERATOR_NAME,
                settings.CONSENT_OPERATOR_EMAIL,
                settings.CONSENT_OPERATOR_ADDRESS,
            )

        fields.append(item)

    return {
        "fields": fields,
        "consent_version": CONSENT_VERSION,
        "operator_name": settings.CONSENT_OPERATOR_NAME,
    }
