"""Маскирование персональных данных для логов.

Заявки содержат имя, телефон и почту — в логи их писать нельзя. Для диагностики
(«какая заявка не уехала в Google») достаточно первых и последних символов.
"""


def mask_phone(value: str) -> str:
    """Маскирует телефон, оставляя последние 4 цифры: +7***12**34**56 -> ...3456."""
    digits = [char for char in value if char.isdigit()]
    if len(digits) <= 4:
        return "***"
    return "***" + "".join(digits[-4:])


def mask_email(value: str) -> str:
    """Маскирует почту, оставляя домен и последние 2 символа имени."""
    if "@" not in value:
        return "***"
    name, domain = value.split("@", 1)
    tail = name[-2:] if len(name) > 2 else "*"
    return f"{'*' * max(len(name) - 2, 1)}{tail}@{domain}"


def mask_text(value: str) -> str:
    """Маскирует произвольную строку: первая и последняя буква, длина в скобках."""
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
