"""Подготовка данных для шаблона анкеты.

Шаблон ничего не знает про конкретные поля и про язык: он рисует то, что пришло из
config/form_fields.py и config/i18n.py. Поэтому изменение анкеты (новый пункт, другая
раскладка, другой язык) не требует правок HTML.
"""

import json
from typing import Any

import settings
from config.consent_text import CONSENT_VERSION
from config.form_fields import (
    CHECKBOX_GROUP,
    CONSENT,
    FORM_FIELDS,
    LAYOUT_COLUMNS,
    checkbox_options,
    max_length,
    other_field,
)
from config.i18n import (
    DEFAULT_LANG,
    consent_text,
    field_text,
    js_messages,
    languages,
    option_label,
    other_text,
    server_messages,
    ui,
)

UI_KEYS = (
    "title",
    "lead",
    "lead_note",
    "lang_switch",
    "submit",
    "consent_show",
    "consent_version",
    "done_title",
    "done_text",
    "done_id",
    "done_again",
)


def _option_items(field: dict[str, Any], lang: str) -> list[list[dict[str, str]]]:
    """Раскладывает варианты по колонкам, подставляя подпись нужного языка.

    value — это то, что уйдёт в базу и в выгрузку, label — то, что видит посетитель.
    """
    if field.get("layout") == LAYOUT_COLUMNS:
        source = field["columns"]
    else:
        source = [field.get("options", [])]

    return [
        [{"value": value, "label": option_label(value, lang)} for value in column]
        for column in source
    ]


def i18n_blob(js: dict[str, str], server: dict[str, str]) -> str:
    """Готовит словарь переводов для тега script с типом application/json.

    Символы <, > и & экранируются, чтобы перевод физически не мог закрыть тег script.
    JSON.parse в браузере понимает \\uXXXX и вернёт обычные символы, поэтому текст на
    экране будет ровно таким, как задумано.

    Args:
        js: подсказки и статусы клиентского скрипта.
        server: переводы сообщений сервера по ключу поля.

    Returns:
        str: готовый JSON одной строкой.
    """
    text = json.dumps({"js": js, "server": server}, ensure_ascii=False, sort_keys=True)
    for char, escape in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(char, escape)
    return text


def build_form_context(lang: str = DEFAULT_LANG) -> dict[str, Any]:
    """Собирает контекст для form.html: поля, текст согласия, версию согласия.

    Args:
        lang: код языка из config.i18n.SUPPORTED_LANGS.

    Returns:
        dict: поля с уже переведёнными подписями плюс строки интерфейса.
    """
    fields: list[dict[str, Any]] = []

    for field in FORM_FIELDS:
        item: dict[str, Any] = dict(field)
        item["max_length"] = max_length(field)
        item.update(field_text(field, lang))

        if field["type"] == CHECKBOX_GROUP:
            item["is_columns"] = field.get("layout") == LAYOUT_COLUMNS
            item["options"] = checkbox_options(field)
            item["columns"] = _option_items(field, lang)
            other = other_field(field)
            if other:
                other.update(other_text(field, lang))
            item["other"] = other

        if field["type"] == CONSENT:
            item["consent_text"] = consent_text(
                lang,
                settings.CONSENT_OPERATOR_NAME,
                settings.CONSENT_OPERATOR_EMAIL,
                settings.CONSENT_OPERATOR_ADDRESS,
            )

        fields.append(item)

    return {
        "fields": fields,
        "consent_version": CONSENT_VERSION,
        "operator_name": settings.CONSENT_OPERATOR_NAME,
        "lang": lang,
        "languages": languages(),
        "ui": {key: ui(lang, key) for key in UI_KEYS},
        "i18n_json": i18n_blob(js_messages(lang), server_messages(lang)),
    }
