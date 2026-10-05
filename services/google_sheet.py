"""Синхронизация заявок с Google Sheets через Apps Script-вебхук.

Без OAuth и ключей Google Cloud: заказчик один раз публикует Apps Script-вебхук
(готовый код лежит в docs/google-apps-script.gs) и кладёт его URL в .env.

Синхронизация best-effort. Заявка уже лежит в SQLite, поэтому недоступность Google
(блокировка, лимит, опечатка в URL) не мешает приёму анкет: результат отправки
фиксируется в google_synced_at / google_error, а повторить можно из админки.
"""

import logging

import httpx
from sqlalchemy.orm import Session

import settings
from models import Submission
from services import exporters
from services import submissions as submissions_service

logger = logging.getLogger(__name__)

ERROR_TEXT_MAX_LENGTH = 120


def is_enabled() -> bool:
    """Синхронизация включена, если задан URL вебхука и не выключена флагом."""
    return bool(settings.GOOGLE_SHEET_WEBHOOK_URL) and settings.GOOGLE_SYNC_ENABLED


def _post_row(row: list[str]) -> tuple[bool, str]:
    """Отправляет одну строку в вебхук.

    Returns:
        tuple[bool, str]: (успех, текст ошибки — пустой при успехе).
    """
    payload = {
        "secret": settings.GOOGLE_SHEET_SECRET or "",
        "row": row,
    }
    try:
        response = httpx.post(
            settings.GOOGLE_SHEET_WEBHOOK_URL,
            json=payload,
            timeout=settings.GOOGLE_SHEET_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"[:ERROR_TEXT_MAX_LENGTH]

    if response.status_code >= 400:
        detail = response.text[:ERROR_TEXT_MAX_LENGTH]
        return False, f"HTTP {response.status_code}: {detail}"

    return True, ""


def sync_submission(
    session: Session, submission: Submission, attempt: str = "авто"
) -> bool:
    """Отправляет заявку в Google-таблицу и фиксирует результат.

    Args:
        session: сессия SQLAlchemy.
        submission: заявка для отправки.
        attempt: способ попытки («авто» при отправке формы, «повтор» из админки).

    Returns:
        bool: True, если строка принята вебхуком.
    """
    if not is_enabled():
        logger.debug(
            "Синхронизация с Google выключена — заявка #%s остаётся только в SQLite",
            submission.id,
        )
        return False

    row = exporters.rows([submission])[0]
    ok, error = _post_row(row)
    submissions_service.mark_google_result(session, submission, ok=ok, error=error)

    if ok:
        logger.info(
            "Заявка #%s отправлена в Google Sheets (%s)", submission.id, attempt
        )
    else:
        logger.warning(
            "Заявка #%s не отправлена в Google Sheets (%s): %s",
            submission.id,
            attempt,
            error,
        )
    return ok


def retry_unsynced(session: Session, attempt: str = "повтор") -> dict[str, int]:
    """Повторяет отправку всех заявок, которые ещё не в таблице.

    Returns:
        dict[str, int]: счётчики sent / failed / skipped.
    """
    sent = 0
    failed = 0
    skipped = 0

    for submission in submissions_service.unsynced_submissions(session):
        if not is_enabled():
            skipped += 1
            continue
        if sync_submission(session, submission, attempt=attempt):
            sent += 1
        else:
            failed += 1

    return {"sent": sent, "failed": failed, "skipped": skipped}
