"""Доступ к админке и выгрузке по секретному токену (fail-closed).

Если EXPORT_TOKEN не задан в .env, защищённые ручки всегда отдают 403 с понятным
текстом. Обратный вариант (пустой токен = открытый доступ) опасен: заявки содержат
персональные данные, и адрес /admin не должен быть защищён «авось никто не угадает».
"""

import hmac
import logging

from fastapi import Header, HTTPException, Query, status

import settings

logger = logging.getLogger(__name__)

TOKEN_REQUIRED_DETAIL = (
    "Выгрузка закрыта: не задан EXPORT_TOKEN в .env. "
    "Задайте переменную и перезапустите приложение."
)
TOKEN_INVALID_DETAIL = "Неверный токен доступа к выгрузке."


def verify_export_token(
    x_export_token: str | None = Header(default=None, alias="X-Export-Token"),
    token: str | None = Query(default=None),
) -> None:
    """Пропускает запрос только при верном EXPORT_TOKEN.

    Токен можно передать заголовком X-Export-Token (для fetch) или параметром ?token=
    (чтобы скачать файл обычной ссылкой в браузере). Сравнение — constant time.
    """
    if not settings.EXPORT_TOKEN:
        logger.warning("Попытка доступа к выгрузке при незаданном EXPORT_TOKEN")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=TOKEN_REQUIRED_DETAIL
        )

    provided = x_export_token or token or ""
    # compare_digest не принимает не-ASCII строки: токен с кириллицей вызвал бы TypeError
    # и 500 вместо 403. Сравниваем байты UTF-8 — constant time остаётся тем же.
    if not hmac.compare_digest(provided.encode(), settings.EXPORT_TOKEN.encode()):
        logger.warning("Попытка доступа к выгрузке с неверным токеном")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=TOKEN_INVALID_DETAIL
        )
