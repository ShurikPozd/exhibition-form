"""Маскирование персональных данных и секретов для логов.

Заявки содержат имя, телефон и почту — в логи их писать нельзя. Для диагностики
(«какая заявка сохранилась») достаточно первых и последних символов.

Отдельно закрыт токен доступа к админке: uvicorn пишет в access-лог полный путь запроса
вместе с query-строкой, из-за чего ?token=... попадал в логи открытым текстом. Логи
читают, копируют и показывают при разборе поломок чаще, чем .env, а секрет, попавший
в лог, уже не секрет.
"""

import logging
import re

# Значение параметра token=... в строке: после ? или &, до следующего разделителя.
QUERY_TOKEN_PATTERN = re.compile(r"(?i)([?&](?:token|access_token)=)([^&\s\"']+)")
TOKEN_MASK = "***"


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


def mask_query_token(text: str) -> str:
    """Заменяет значение token=... в URL на ***, сохраняя путь и остальные параметры.

    Маскируется только значение после token=, и только когда параметр стоит в
    query-строке: иначе можно было бы испортить, например, путь, в котором
    встретилось слово «token».

    Args:
        text: строка запроса целиком, как её пишет access-лог.

    Returns:
        str: та же строка без значения токена.
    """
    return QUERY_TOKEN_PATTERN.sub(rf"\1{TOKEN_MASK}", text)


class AccessLogTokenFilter(logging.Filter):
    """Маскирует токен доступа в записях логгера uvicorn.access.

    Uvicorn передаёт путь запроса позиционным аргументом logging (record.args),
    поэтому фильтр правит и args, и msg: при обновлении uvicorn формат записи может
    измениться, а утечка токена — остаться.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Маскирует токен в записи лога.

        Args:
            record: запись, которую предстоит отформатировать и передать обработчикам.

        Returns:
            bool: всегда True — запись не должна теряться из-за маскирования.
        """
        if isinstance(record.msg, str):
            record.msg = mask_query_token(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                mask_query_token(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: mask_query_token(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


def install_access_log_mask() -> logging.Logger:
    """Устанавливает фильтр маскирования на логгер uvicorn.access.

    Вызывается при настройке логов (logger_config), до первого запроса: uvicorn
    применяет собственную конфигурацию логирования при старте, а фильтр добавляется
    позже, поэтому переживает её. Повторный вызов ничего не дублирует.

    Returns:
        logging.Logger: логгер uvicorn.access с установленным фильтром.
    """
    access_logger = logging.getLogger("uvicorn.access")
    if not any(
        isinstance(item, AccessLogTokenFilter) for item in access_logger.filters
    ):
        access_logger.addFilter(AccessLogTokenFilter())
    return access_logger
