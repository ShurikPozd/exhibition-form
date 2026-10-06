"""Ручки формы для посетителя: показать анкету и принять заявку."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import settings
from database import get_session
from config.i18n import normalize_lang
from schemas import SubmissionIn, SubmissionOut
from services import backup, submissions
from services.form_view import build_form_context
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def show_form(request: Request) -> HTMLResponse:
    """Отдаёт анкету, собранную по описанию полей.

    Язык приходит в ?lang=ru|en; неизвестный код молча превращается в язык по
    умолчанию, чтобы ссылка с опечаткой не показывала 500.

    Raises:
        HTTPException: 500, если нет шаблона (отловлено глобальным обработчиком).
    """
    lang = normalize_lang(request.query_params.get("lang"))
    return templates.TemplateResponse(
        request=request, name="form.html", context=build_form_context(lang)
    )


@router.post(
    "/api/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_submission(
    data: SubmissionIn,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> SubmissionOut:
    """Принимает заявку, сохраняет в SQLite и подтверждает запись чтением обратно.

    Ошибки валидации Pydantic превращаются в 422 автоматически: посетитель увидит
    текст problem, а в базу ничего не попадёт.

    После ответа посетителю в фоне снимается дамп базы: на Render контейнер может быть
    пересоздан в любой момент, и копия должна появиться раньше, чем её попросит
    следующая заявка.
    """
    submission = submissions.create_submission(
        session, data, user_agent=request.headers.get("user-agent", "")
    )

    if settings.BACKUP_ON_SUBMIT:
        background_tasks.add_task(backup.run_backup, "после заявки")

    return SubmissionOut(id=submission.id, created_at=submission.created_at)
