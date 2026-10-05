"""Проверка и нормализация пользовательского ввода.

Модуль намеренно без внешних зависимостей: pydantic-типа EmailStr требует отдельного
пакета email-validator, а здесь достаточно понятных регулярных выражений. Правила
намеренно мягкие — это выставочная анкета, а не платёжная форма: лучше принять странный
телефон, чем потерять заявку посетителя стенда.
"""

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
PHONE_DIGITS_MIN = 10
PHONE_DIGITS_MAX = 15


def clean_text(value: str) -> str:
    """Убирает лишние пробелы и невидимые символы, обрезает по краям."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def validate_name(value: str) -> str:
    """Проверяет имя: после очистки должен остаться хотя бы один символ.

    Raises:
        ValueError: если имя пустое.
    """
    cleaned = clean_text(value)
    if not cleaned:
        raise ValueError("введите имя")
    return cleaned


def validate_phone(value: str) -> str:
    """Проверяет телефон по количеству цифр, возвращает введённый формат.

    Формат не нормализуется: менеджеру привычнее видеть то, что человек набрал.

    Raises:
        ValueError: если цифр меньше 10 или больше 15.
    """
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < PHONE_DIGITS_MIN:
        raise ValueError("в телефоне слишком мало цифр")
    if len(digits) > PHONE_DIGITS_MAX:
        raise ValueError("в телефоне слишком много цифр")
    return cleaned


def validate_email(value: str) -> str:
    """Проверяет адрес электронной почты; пустое значение допустимо.

    Raises:
        ValueError: если адрес не похож на почту.
    """
    cleaned = clean_text(value).lower()
    if not cleaned:
        return ""
    if not EMAIL_RE.match(cleaned):
        raise ValueError("похоже, что адрес почты заполнен не полностью")
    return cleaned
