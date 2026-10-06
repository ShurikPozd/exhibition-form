"""Админка: список заявок, правка, скрытие и выгрузка в Excel/CSV.

Способы попасть внутрь (все fail-closed, utils/security.py):
- сессия после входа по ADMIN_PASSWORD — обычный путь человека через браузер;
- EXPORT_TOKEN в заголовке X-Export-Token или в ?token= — для curl и скриптов.

Просмотр и выгрузка открыты обоими способами, а правка и скрытие заявок — только сессией:
токен выгрузки выдаётся скриптам, и скрипту незачем уметь менять данные.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from database import get_session
from handlers.auth import LOGIN_PATH
from schemas import SubmissionEditIn
from services import exporters
from services import submissions as submissions_service
from templating import templates
from utils.security import (
    has_session,
    require_export_access,
    require_session,
    token_matches,
)
from utils.session import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_PATH = "/admin"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


def _rows_response(items: list) -> JSONResponse:
    """Отдаёт заявки таблицей: заголовки колонок и строки."""
    return JSONResponse(
        {
            "count": len(items),
            "headers": exporters.headers(),
            "rows": exporters.rows(items),
        }
    )


def _admin_redirect() -> RedirectResponse:
    """Отправляет гостя на форму входа: 303, чтобы дальше шёл GET."""
    return RedirectResponse(LOGIN_PATH, status_code=303)


def _not_found() -> HTTPException:
    """Единая ошибка «заявки нет» для всех операций с записью."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="заявка не найдена"
    )


@router.get("/admin", response_class=HTMLResponse, response_model=None)
def admin_page(
    request: Request,
    show_deleted: bool = False,
    token: str = "",
    x_export_token: str = Header(default=""),
    session: Session = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    """Показывает страницу со списком заявок и кнопками выгрузки.

    Без сессии и без верного токена — не 403, а переход на форму входа: ссылку на
    /admin можно открывать прямо из закладок, не дописывая к ней токен руками.
    Токен принимается и в заголовке, и в адресе: скриптам удобнее заголовок,
    человеку — ссылка.
    """
    if not has_session(request.cookies.get(SESSION_COOKIE_NAME)) and not token_matches(
        x_export_token or token
    ):
        return _admin_redirect()

    items = submissions_service.list_submissions(session, deleted=show_deleted)
    context = {
        "headers": exporters.headers(),
        "rows": exporters.rows(items),
        "total": submissions_service.count_submissions(session),
        "deleted_total": submissions_service.count_submissions(session, deleted=True),
        "show_deleted": show_deleted,
        "generated_at": datetime.now().strftime(exporters.DATE_FORMAT),
    }
    return templates.TemplateResponse(
        request=request, name="admin.html", context=context
    )


@router.get("/api/submissions")
def list_submissions(
    session: Session = Depends(get_session),
    _: None = Depends(require_export_access),
) -> JSONResponse:
    """Отдаёт все заявки JSON-таблицей (те же колонки, что и в Excel)."""
    return _rows_response(submissions_service.list_submissions(session))


@router.get("/api/submissions.xlsx")
def export_xlsx(
    session: Session = Depends(get_session),
    _: None = Depends(require_export_access),
) -> Response:
    """Выгружает заявки в .xlsx: листы «Заявки» и «Подробно»."""
    items = submissions_service.list_submissions(session)
    content = exporters.to_xlsx(items)
    logger.info("Выгружен .xlsx: заявок %d", len(items))
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{exporters.download_name("xlsx")}"'
            )
        },
    )


@router.get("/api/submissions.csv")
def export_csv(
    session: Session = Depends(get_session),
    _: None = Depends(require_export_access),
) -> Response:
    """Выгружает заявки в CSV (UTF-8 с BOM, разделитель «;»)."""
    items = submissions_service.list_submissions(session)
    content = exporters.to_csv(items)
    logger.info("Выгружен .csv: заявок %d", len(items))
    return Response(
        content=content,
        media_type=CSV_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{exporters.download_name("csv")}"'
            )
        },
    )


@router.get("/admin/submissions/{submission_id}/edit", response_class=HTMLResponse)
def edit_page(
    request: Request,
    submission_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_session),
) -> HTMLResponse:
    """Форма правки заявки: контакты и заметка."""
    submission = submissions_service.get_submission(session, submission_id)
    if submission is None:
        raise _not_found()

    return templates.TemplateResponse(
        request=request,
        name="edit.html",
        context={
            "submission": submission,
            "form": {},
            "error": "",
            "back_to_deleted": submission.deleted_at is not None,
        },
    )


@router.post("/admin/submissions/{submission_id}/edit", response_model=None)
def edit_submit(
    request: Request,
    submission_id: int,
    name: str = Form(...),
    company: str = Form(default=""),
    phone: str = Form(default=""),
    email: str = Form(default=""),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
    _: None = Depends(require_session),
) -> HTMLResponse | RedirectResponse:
    """Сохраняет правку и возвращает в админку.

    Returns:
        RedirectResponse: 303 в админку с сохранёнными данными.
        HTMLResponse: та же форма с текстом ошибки, если данные не прошли проверку.
    """
    form = {
        "name": name,
        "company": company,
        "phone": phone,
        "email": email,
        "note": note,
    }
    submission = submissions_service.get_submission(session, submission_id)
    if submission is None:
        raise _not_found()

    try:
        data = SubmissionEditIn(**form)
    except ValidationError as error:
        return templates.TemplateResponse(
            request=request,
            name="edit.html",
            context={
                "submission": submission,
                "form": form,
                "error": "; ".join(str(item["msg"]) for item in error.errors()),
                "back_to_deleted": submission.deleted_at is not None,
            },
        )

    updated = submissions_service.update_contacts(session, submission_id, data)
    if updated is None:
        raise _not_found()

    return RedirectResponse(ADMIN_PATH, status_code=303)


@router.post("/admin/submissions/{submission_id}/delete")
def delete_submission(
    submission_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_session),
) -> RedirectResponse:
    """Прячет заявку из админки и выгрузок."""
    if submissions_service.soft_delete(session, submission_id) is None:
        raise _not_found()
    return RedirectResponse(ADMIN_PATH, status_code=303)


@router.post("/admin/submissions/{submission_id}/restore")
def restore_submission(
    submission_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(require_session),
) -> RedirectResponse:
    """Возвращает скрытую заявку в админку и выгрузки."""
    if submissions_service.restore(session, submission_id) is None:
        raise _not_found()
    return RedirectResponse(f"{ADMIN_PATH}?show_deleted=true", status_code=303)
