"""Подписанная сессия админки: пароль входит один раз, дальше работает cookie.

Зачем это вместо токена в адресе: токен в URL попадает в историю браузера, закладки и
скриншоты, а пароль, введённый в форму, не остаётся в адресе нигде. В cookie кладётся не
сам пароль и не токен, а подписанный штамп времени: подпись делается тем же паролем
(ADMIN_PASSWORD), поэтому смена пароля в .env обесценивает все ранее выданные cookie.

Формат cookie — «время.подпись», где подпись это hex от HMAC-SHA256. Проверка подписи
сравнением байт за постоянное время, как при проверке токена выгрузки.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "admin_session"
# Соли для подписи и для хранения времени в разных форматах не нужны: значение и так
# проверяется подписью, формат фиксирован.
_SEPARATOR = "."
_TTL_FALLBACK = timedelta(hours=8)


def _secret() -> bytes:
    """Отдаёт секрет подписи; пустой означает «сессии работать не могут»."""
    return (settings.ADMIN_PASSWORD or "").encode("utf-8")


def _sign(stamp: str) -> str:
    """Считает подпись для строки времени входа."""
    return hmac.new(_secret(), stamp.encode("utf-8"), hashlib.sha256).hexdigest()


def _ttl() -> timedelta:
    """Отдаёт срок жизни сессии из настроек."""
    hours = settings.SESSION_TTL_HOURS
    return timedelta(hours=hours) if hours and hours > 0 else _TTL_FALLBACK


def issue_session(now: datetime | None = None) -> str | None:
    """Выпускает значение cookie на текущий момент.

    Returns:
        str | None: строка «время.подпись» либо None, если пароль не задан и подписать
        нечем (тогда вход закрыт, а не открыт).
    """
    if not settings.ADMIN_PASSWORD:
        return None

    moment = now or datetime.now(timezone.utc)
    stamp = f"{int(moment.timestamp())}"
    return f"{stamp}{_SEPARATOR}{_sign(stamp)}"


def verify_session(value: str | None) -> bool:
    """Проверяет cookie: подпись верна и срок не истёк.

    Returns:
        bool: True только при корректной и не просроченной сессии.
    """
    if not value or not settings.ADMIN_PASSWORD:
        return False

    stamp, _, signature = value.partition(_SEPARATOR)
    if not stamp or not signature:
        return False

    if not hmac.compare_digest(signature.encode("utf-8"), _sign(stamp).encode("utf-8")):
        logger.info("Отклонена сессия с неверной подписью")
        return False

    try:
        issued_at = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        logger.info("Отклонена сессия с некорректным временем входа")
        return False

    if datetime.now(timezone.utc) - issued_at > _ttl():
        logger.info("Отклонена сессия: срок действия истёк")
        return False

    return True


def cookie_params() -> dict:
    """Параметры cookie для ответа: путь, время жизни и флаги защиты.

    httpOnly скрывает значение от JavaScript, SameSite=Lax не даёт cookie уйти на
    сторонние сайты и закрывает CSRF на POST-формах, Secure включается в .env при HTTPS.
    """
    return {
        "key": SESSION_COOKIE_NAME,
        "max_age": int(_ttl().total_seconds()),
        "httponly": True,
        "samesite": "lax",
        "secure": settings.SESSION_COOKIE_SECURE,
        "path": "/",
    }
