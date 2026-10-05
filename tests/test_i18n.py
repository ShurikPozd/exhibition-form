"""Проверки двух языков анкеты.

Главная идея, которую тут защищаем: в базу и в выгрузку уходит русское значение
варианта, а перевод — только подпись на экране. Поэтому тесты проверяют и то, что
английская страница отдаёт русские value, и то, что подписи на ней английские.
"""

import json
import re

import pytest

import settings
from config.form_fields import FORM_FIELDS, checkbox_options
from config.i18n import (
    DEFAULT_LANG,
    LANG_EN,
    LANG_RU,
    SUPPORTED_LANGS,
    TRANSLATIONS,
    field_text,
    languages,
    normalize_lang,
    option_label,
)

PAGE = "/"


@pytest.fixture
def ru_page(client):
    """Ответ страницы на русском (язык по умолчанию)."""
    response = client.get(PAGE)
    assert response.status_code == 200
    return response.text


@pytest.fixture
def en_page(client):
    """Ответ страницы на английском."""
    response = client.get(PAGE + "?lang=en")
    assert response.status_code == 200
    return response.text


@pytest.mark.parametrize("lang", SUPPORTED_LANGS)
def test_page_available(client, lang):
    """Обе версии открываются и объявляют свой язык в <html lang>."""
    response = client.get(PAGE, params={"lang": lang})
    assert response.status_code == 200
    assert f'<html lang="{lang}"' in response.text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("en", LANG_EN),
        ("EN", LANG_EN),
        ("en-US", LANG_EN),
        ("en_US", LANG_EN),
        ("ru", LANG_RU),
        ("ru-RU", LANG_RU),
        ("de", DEFAULT_LANG),
        ("", DEFAULT_LANG),
        (None, DEFAULT_LANG),
        ("../etc/passwd", DEFAULT_LANG),
    ],
)
def test_normalize_lang(raw, expected):
    """Код языка приводится к поддерживаемому, всё остальное — к языку по умолчанию."""
    assert normalize_lang(raw) == expected


def test_default_page_is_russian(ru_page):
    """Без параметра lang открывается русская версия — ссылка на английскую есть."""
    assert "Анкета участника выставки" in ru_page
    assert "Who are you?" not in ru_page
    assert '?lang=en"' in ru_page
    assert '?lang=ru"' in ru_page


def test_english_page_shows_translations(en_page):
    """На английской странице подписи и заголовки английские."""
    assert "Who are you?" in en_page
    assert "Анкета участника выставки" not in en_page
    assert "areas of interest" in en_page.lower()
    assert '?lang=ru"' in en_page


def test_english_page_keeps_russian_values(en_page):
    """Чекбоксы отправляют русские значения: база и выгрузка остаются прежними.

    Это главное правило двуязычности — по нему schemas.py продолжает узнавать
    выбранные варианты и не появляется второй формат данных в базе.
    """
    for value in checkbox_options(next(f for f in FORM_FIELDS if f["key"] == "role")):
        assert f'value="{value}"' in en_page
    assert 'value="дизайнер, архитектор"' in en_page
    assert 'value="интегратор"' in en_page


def test_english_page_translates_labels(en_page):
    """Подписи вариантов переведены, но текст сохранён в атрибуте value."""
    assert "designer / architect" in en_page
    assert "private visitor, just looking" in en_page
    assert ">дизайнер, архитектор<" not in en_page


def test_english_consent_is_translated(client, monkeypatch):
    """Согласие на английском, но реквизиты оператора подставляются те же."""
    monkeypatch.setattr(settings, "CONSENT_OPERATOR_NAME", "ИП Поздняков А.Д.")
    monkeypatch.setattr(settings, "CONSENT_OPERATOR_EMAIL", "test@example.com")

    page = client.get(PAGE, params={"lang": LANG_EN}).text

    assert "consent to the processing" in page.lower()
    assert "ИП Поздняков А.Д." in page
    assert "test@example.com" in page
    assert "Отправляем" not in page


def test_ids_unique_per_language(ru_page, en_page):
    """Идентификаторы полей не должны зависеть от языка: клиент и сервер их знают."""
    pattern = re.compile(r'id="(f-[^"]+)"')
    for page in (ru_page, en_page):
        ids = pattern.findall(page)
        assert ids
        assert len(ids) == len(set(ids))


def test_other_field_keeps_name_in_english(en_page):
    """Поле уточнения сохраняет техническое имя role_other при любом языке."""
    assert 'name="role_other"' in en_page
    assert "Other: tell us who you are" in en_page


def test_i18n_blob_is_valid_json(en_page):
    """Словарь для клиентского скрипта — валидный JSON, вставленный как есть."""
    raw = re.search(
        r'<script id="i18n" type="application/json">(.*?)</script>', en_page, re.S
    )
    assert raw, "блок переводов не найден"
    blob = json.loads(raw.group(1))
    assert blob["js"]["status_sending"] == "Sending…"
    assert blob["server"]["name"] == "please enter your name"
    # Раннее экранирование не должно ломать JSON.parse
    assert "<" not in raw.group(1)


def test_i18n_blob_cannot_break_out_of_script(en_page):
    """Экранирование < и > не даёт переводу закрыть тег script."""
    raw = re.search(
        r'<script id="i18n" type="application/json">(.*?)</script>', en_page, re.S
    )
    body = raw.group(1)
    assert "</script" not in body.lower()


def test_option_label_falls_back_to_value():
    """Без перевода показываем само значение — лучше, чем пустая строка."""
    assert option_label("дизайнер, архитектор", LANG_RU) == "дизайнер, архитектор"
    assert option_label("дизайнер, архитектор", LANG_EN) == "designer / architect"


def test_field_text_falls_back_to_russian():
    """У русского набора нет подписей полей: они родные, из config/form_fields.py."""
    name_field = next(f for f in FORM_FIELDS if f["key"] == "name")
    assert field_text(name_field, LANG_RU)["label"] == name_field["label"]
    assert field_text(name_field, LANG_EN)["label"] == "Name"


def test_translation_bundles_agree_on_keys():
    """Ключи интерфейса и клиентских подсказок должны совпадать во всех языках.

    Иначе на одной из страниц часть текста молча пропадёт: t() вернёт пустую строку.
    """
    reference = TRANSLATIONS[DEFAULT_LANG]
    for lang in SUPPORTED_LANGS:
        bundle = TRANSLATIONS[lang]
        for section in ("ui", "js"):
            assert set(bundle[section]) == set(
                reference[section]
            ), f"секция {section} языка {lang} отличается от {DEFAULT_LANG}"


def test_no_empty_translations():
    """Пустой перевод хуже отсутствующего: проверяем, что все строки непустые."""
    for lang, bundle in TRANSLATIONS.items():
        for section in ("ui", "js"):
            for key, text in bundle[section].items():
                assert text.strip(), f"{lang}.{section}.{key} пусто"


def test_languages_list():
    """Переключатель получает список языков с названиями на своём же языке."""
    assert languages() == [
        {"code": "ru", "name": "Русский"},
        {"code": "en", "name": "English"},
    ]
