"""Админка: список заявок, выгрузка в Excel/CSV, повтор синхронизации с Google.

Все ручки закрыты EXPORT_TOKEN (utils/security.py, режим fail-closed): заявки содержат
персональные данные, поэтому /admin не должен быть доступен «кто угадает адрес».
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from database import get_session
from services import exporters, google_sheet
from services import submissions as submissions_service
from templating import templates
from utils.security import verify_export_token

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_export_token)])

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


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    """Показывает страницу со списком заявок и кнопками выгрузки."""
    items = submissions_service.list_submissions(session)
    context = {
        "headers": exporters.headers(),
        "rows": exporters.rows(items),
        "total": submissions_service.count_submissions(session),
        "unsynced": len(submissions_service.unsynced_submissions(session)),
        "google_enabled": google_sheet.is_enabled(),
        "generated_at": datetime.now().strftime(exporters.DATE_FORMAT),
    }
    return templates.TemplateResponse(
        request=request, name="admin.html", context=context
    )


@router.get("/api/submissions")
def list_submissions(session: Session = Depends(get_session)) -> JSONResponse:
    """Отдаёт все заявки JSON-таблицей (те же колонки, что и в Excel)."""
    return _rows_response(submissions_service.list_submissions(session))


@router.get("/api/submissions.xlsx")
def export_xlsx(session: Session = Depends(get_session)) -> Response:
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
def export_csv(session: Session = Depends(get_session)) -> Response:
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


@router.post("/api/google/sync")
def sync_all(session: Session = Depends(get_session)) -> JSONResponse:
    """Повторяет отправку в Google-таблицу для всех неотправленных заявок."""
    result = google_sheet.retry_unsynced(session)
    logger.info("Повторная синхронизация: %s", result)
    return JSONResponse(result)


@router.post("/api/google/sync/{submission_id}")
def sync_one(
    submission_id: int, session: Session = Depends(get_session)
) -> JSONResponse:
    """Повторяет отправку одной заявки по её id."""
    submission = submissions_service.get_submission(session, submission_id)
    if submission is None:
        return JSONResponse({"detail": "заявка не найдена"}, status_code=404)

    ok = google_sheet.sync_submission(session, submission, attempt="повтор")
    return JSONResponse(
        {
            "id": submission_id,
            "google_synced": ok,
            "google_error": submission.google_error,
        }
    )
