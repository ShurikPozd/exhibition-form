"""Доступ к админке и выгрузке: сессия после входа по паролю либо токен для скриптов.

Два способа попасть внутрь, и оба закрыты по умолчанию (fail-closed):

1. Сессия — человек вводит ADMIN_PASSWORD в форме /admin/login и дальше работает с
   подписанной cookie. Читается из cookie на любой защищённой ручке.
2. EXPORT_TOKEN — машинный доступ: заголовок X-Export-Token или параметр ?token=. Так
   работают curl и скрипты; пароль в такие сценарии не вставляют.

Если в .env не задано ни то, ни другое, защищённые ручки отдают 403 с понятным текстом,
а не пускают «на авось»: заявки содержат персональные данные.
"""

import hmac
import logging

from fastapi import Cookie, Header, HTTPException, Query, status

import settings
from utils.session import SESSION_COOKIE_NAME, verify_session

logger = logging.getLogger(__name__)

TOKEN_REQUIRED_DETAIL = (
    "Доступ закрыт: не заданы ADMIN_PASSWORD и EXPORT_TOKEN в .env. "
    "Задайте переменные и перезапустите приложение."
)
TOKEN_INVALID_DETAIL = "Неверный токен доступа к выгрузке."
SESSION_REQUIRED_DETAIL = "Войдите в админку: /admin/login"


def token_matches(provided: str | None) -> bool:
    """Сверяет переданный токен с EXPORT_TOKEN за постоянное время.

    Сравниваются байты UTF-8: compare_digest не принимает не-ASCII строки, и токен,
    введённый с русской раскладкой, ронял проверку с TypeError и 500.
    """
    if not provided or not settings.EXPORT_TOKEN:
        return False

    return hmac.compare_digest(provided.encode(), settings.EXPORT_TOKEN.encode())


def has_session(session_cookie: str | None) -> bool:
    """Сообщает, есть ли действующая сессия админки."""
    return verify_session(session_cookie)


def require_export_access(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    x_export_token: str | None = Header(default=None, alias="X-Export-Token"),
    token: str | None = Query(default=None),
) -> None:
    """Пропускает запрос по сессии или по токену выгрузки."""
    if has_session(session_cookie) or token_matches(x_export_token or token):
        return

    logger.warning("Отказ в доступе к выгрузке: нет ни сессии, ни верного токена")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            TOKEN_REQUIRED_DETAIL if not settings.EXPORT_TOKEN else TOKEN_INVALID_DETAIL
        ),
    )


def require_session(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    """Пропускает только пользователя, вошедшего по паролю (правки и удаления)."""
    if has_session(session_cookie):
        return

    logger.warning("Отказ в операции с заявкой: нет действующей сессии")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=SESSION_REQUIRED_DETAIL
    )
