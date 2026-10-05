"""Ручки формы для посетителя: показать анкету и принять заявку."""

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_session
from schemas import SubmissionIn, SubmissionOut
from services import google_sheet
from services import submissions
from services.form_view import build_form_context
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def show_form(request: Request) -> HTMLResponse:
    """Отдаёт анкету, собранную по описанию полей.

    Raises:
        HTTPException: 500, если нет шаблона (отловлено глобальным обработчиком).
    """
    return templates.TemplateResponse(
        request=request, name="form.html", context=build_form_context()
    )


@router.post(
    "/api/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_submission(
    data: SubmissionIn,
    request: Request,
    session: Session = Depends(get_session),
) -> SubmissionOut:
    """Принимает заявку, сохраняет в SQLite и подтверждает запись чтением обратно.

    Ошибки валидации Pydantic превращаются в 422 автоматически: посетитель увидит
    текст problem, а в базу ничего не попадёт.
    """
    submission = submissions.create_submission(
        session, data, user_agent=request.headers.get("user-agent", "")
    )
    google_sheet.sync_submission(session, submission)

    return SubmissionOut(
        id=submission.id,
        created_at=submission.created_at,
        google_synced=submission.google_synced_at is not None,
    )
