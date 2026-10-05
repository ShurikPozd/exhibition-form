"""Языки анкеты: переводы отделены от описания полей.

Ключевое решение: в базу, в выгрузку и в проверку сервера уходит русское значение
варианта, а перевод — только подпись на экране. Поэтому словарь значений один на все
языки, а i18n трогает исключительно текст. Иначе пришлось бы держать в базе две версии
одного и того же ответа и разбираться, какая из них «правильная».

Модуль ничего не знает про FastAPI и шаблоны: он переводит словари и строки.
"""

from typing import Any

from config.consent_text import consent_text as ru_consent_text
from config.translations import en, ru

LANG_RU = "ru"
LANG_EN = "en"

DEFAULT_LANG = LANG_RU
SUPPORTED_LANGS = (LANG_RU, LANG_EN)

TRANSLATIONS: dict[str, Any] = {LANG_RU: ru.TRANSLATION, LANG_EN: en.TRANSLATION}

# Название языка в переключателе пишется на своём же языке: «Русский» и «English»
# узнают и те, кто этой версией не владеет.
LANG_NAMES = {LANG_RU: "Русский", LANG_EN: "English"}


def languages() -> list[dict[str, str]]:
    """Список языков для переключателя: код и название на своём же языке."""
    return [{"code": code, "name": LANG_NAMES[code]} for code in SUPPORTED_LANGS]


def normalize_lang(value: str | None) -> str:
    """Приводит код языка к поддерживаемому или возвращает язык по умолчанию.

    Args:
        value: код из query-параметра или заголовка Accept-Language (may be None).

    Returns:
        str: код из SUPPORTED_LANGS.
    """
    if not value:
        return DEFAULT_LANG
    code = value.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


def _bundle(lang: str) -> dict[str, Any]:
    """Возвращает словарь переводов языка (пустой для языка по умолчанию)."""
    return TRANSLATIONS.get(lang) or {}


def field_text(field: dict[str, Any], lang: str) -> dict[str, str]:
    """Переводит текстовые подписи одного поля.

    Args:
        field: описание поля из config/form_fields.py.
        lang: код языка.

    Returns:
        dict: ключи label, placeholder, hint и required_note — с переводом там,
            где он есть, и с исходным текстом там, где перевода нет.
    """
    bundle = _bundle(lang)
    key = field["key"]
    return {
        "label": bundle.get("labels", {}).get(key, field.get("label", "")),
        "placeholder": bundle.get("placeholders", {}).get(
            key, field.get("placeholder", "")
        ),
        "hint": bundle.get("hints", {}).get(key, field.get("hint", "")),
        "required_note": bundle.get("notes", {}).get(
            key, field.get("required_note", "")
        ),
    }


def option_label(value: str, lang: str) -> str:
    """Переводит подпись варианта, оставляя значение как есть.

    Args:
        value: значение варианта из анкеты (например, «дизайнер, архитектор»).
        lang: код языка.

    Returns:
        str: подпись для показа; при отсутствии перевода — исходное значение.
    """
    return _bundle(lang).get("options", {}).get(value, value)


def other_text(field: dict[str, Any], lang: str) -> dict[str, str]:
    """Переводит подпись и плейсхолдер поля уточнения рядом с «другое»."""
    other = field.get("other_key")
    bundle = _bundle(lang)
    if not other:
        return {}
    translated = bundle.get("other", {}).get(other, {})
    return {
        "label": translated.get("label", field.get("other_label", "")),
        "placeholder": translated.get(
            "placeholder", field.get("other_placeholder", "")
        ),
    }


def ui(lang: str, key: str) -> str:
    """Отдаёт строку интерфейса перевода или пустую строку."""
    return _bundle(lang).get("ui", {}).get(key, "")


def js_messages(lang: str) -> dict[str, str]:
    """Отдаёт словарь подсказок и статусов для клиентского скрипта."""
    return _bundle(lang).get("js", {})


def server_messages(lang: str) -> dict[str, str]:
    """Отдаёт переводы сообщений сервера по ключу поля.

    Пустой словарь означает «показывай ответ сервера как есть»: так работает русская
    версия, где ответ сервера уже на нужном посетителю языке.
    """
    return _bundle(lang).get("server", {})


def consent_text(
    lang: str,
    operator_name: str,
    operator_email: str = "",
    operator_address: str = "",
) -> str:
    """Собирает текст согласия на нужном языке."""
    translated = _bundle(lang).get("consent")
    if callable(translated):
        return translated(operator_name, operator_email, operator_address)
    return ru_consent_text(operator_name, operator_email, operator_address)
