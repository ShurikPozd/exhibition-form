"""Вход в админку по паролю и выход из неё.

Пароль вводится в форме, а не пишется в адрес: пароль в URL остаётся в истории браузера,
закладках и скриншотах. После проверки выдаётся подписанная cookie (utils/session.py), и
дальше ручки админки узнают пользователя по ней, а не по токену в строке запроса.

Проверка пароля идёт за постоянное время, как и проверка токена выгрузки, а неудачные
попытки пишутся в лог без самого пароля.
"""

import hmac
import logging
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import settings
from templating import templates
from utils import session
from utils.security import has_session

logger = logging.getLogger(__name__)

router = APIRouter()

LOGIN_PATH = "/admin/login"
ADMIN_PATH = "/admin"

PASSWORD_REQUIRED_DETAIL = (
    "Вход закрыт: не задан ADMIN_PASSWORD в .env. "
    "Задайте переменную и перезапустите приложение."
)
PASSWORD_INVALID_DETAIL = "Неверный пароль."
PASSWORD_EMPTY_DETAIL = "Введите пароль."


def _back_to_login(error: str) -> RedirectResponse:
    """Возвращает на форму входа с текстом ошибки в query."""
    return RedirectResponse(f"{LOGIN_PATH}?error={quote(error)}", status_code=303)


@router.get("/admin/login", response_model=None)
def login_page(request: Request, error: str = "") -> HTMLResponse | RedirectResponse:
    """Показывает форму входа. Если сессия уже есть — сразу возвращает в админку."""
    if has_session(request.cookies.get(session.SESSION_COOKIE_NAME)):
        return RedirectResponse(ADMIN_PATH, status_code=303)

    if not settings.ADMIN_PASSWORD and not error:
        error = PASSWORD_REQUIRED_DETAIL

    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": error}
    )


@router.post("/admin/login")
def login_submit(password: str = Form(default="")) -> RedirectResponse:
    """Проверяет пароль и ставит сессионную cookie.

    Args:
        password: значение из поля формы.

    Returns:
        RedirectResponse: 303 на /admin с cookie либо назад на форму с ошибкой.
    """
    if not settings.ADMIN_PASSWORD:
        logger.warning("Попытка входа при незаданном ADMIN_PASSWORD")
        return _back_to_login(PASSWORD_REQUIRED_DETAIL)

    if not password:
        return _back_to_login(PASSWORD_EMPTY_DETAIL)

    if not hmac.compare_digest(password.encode(), settings.ADMIN_PASSWORD.encode()):
        logger.warning("Попытка входа с неверным паролем")
        return _back_to_login(PASSWORD_INVALID_DETAIL)

    response = RedirectResponse(ADMIN_PATH, status_code=303)
    params = session.cookie_params()
    response.set_cookie(
        value=session.issue_session(),
        key=params["key"],
        max_age=params["max_age"],
        httponly=params["httponly"],
        samesite=params["samesite"],
        secure=params["secure"],
        path=params["path"],
    )
    logger.info("Администратор вошёл в админку")
    return response


@router.get("/admin/logout")
def logout() -> RedirectResponse:
    """Сбрасывает сессионную cookie и возвращает на форму входа."""
    response = RedirectResponse(LOGIN_PATH, status_code=303)
    response.delete_cookie(
        key=session.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )
    logger.info("Администратор вышел из админки")
    return response
