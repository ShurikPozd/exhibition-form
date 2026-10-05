"""Сохранение и выборка заявок — здесь вся работа с SQL.

Ответ «201» сам по себе не доказывает, что запись легла в базу: соединение может
оборваться на commit, а SQLite — вернуть конфликт блокировок. Поэтому create_submission()
после сохранения перечитывает строку обратно (read-back) и поднимает ошибку, если её нет.
"""

import logging
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from config.consent_text import CONSENT_VERSION
from models import Submission, utcnow
from schemas import SubmissionIn
from utils.masking import mask_email, mask_phone

logger = logging.getLogger(__name__)

LIST_LIMIT = 1000
ERROR_MAX_LENGTH = 300


def build_payload(data: SubmissionIn) -> dict:
    """Собирает payload заявки: группы чекбоксов и свободный текст."""
    return {
        "role": list(data.role),
        "role_other": data.role_other,
        "stall": list(data.stall),
        "directions": list(data.directions),
        "interest": list(data.interest),
        "after_show": data.after_show,
    }


def count_checkboxes(payload: dict) -> int:
    """Считает, сколько всего чекбоксов отмечено в заявке."""
    return sum(len(value) for value in payload.values() if isinstance(value, list))


def create_submission(
    session: Session, data: SubmissionIn, user_agent: str = ""
) -> Submission:
    """Сохраняет заявку в SQLite и подтверждает запись чтением обратно.

    Args:
        session: сессия SQLAlchemy.
        data: провалидированные данные формы.
        user_agent: строка User-Agent для контекста (что за устройство заполняло).

    Returns:
        Submission: запись, прочитанная из базы после сохранения.

    Raises:
        RuntimeError: если после commit запись не читается обратно.
    """
    submission = Submission(
        name=data.name,
        company=data.company,
        phone=data.phone,
        email=data.email,
        payload=build_payload(data),
        consent_version=CONSENT_VERSION,
        user_agent=(user_agent or "")[:ERROR_MAX_LENGTH],
    )
    session.add(submission)
    session.commit()

    saved = session.get(Submission, submission.id)
    if saved is None:
        session.rollback()
        logger.error("Заявка #%s не читается после сохранения", submission.id)
        raise RuntimeError("не удалось подтвердить запись заявки")

    logger.info(
        "Сохранена заявка #%s (телефон: %s, email: %s, отмечено пунктов: %d)",
        saved.id,
        mask_phone(saved.phone) if saved.phone else "—",
        mask_email(saved.email) if saved.email else "—",
        count_checkboxes(saved.payload),
    )
    return saved


def get_submission(session: Session, submission_id: int) -> Submission | None:
    """Возвращает заявку по id или None."""
    return session.get(Submission, submission_id)


def list_submissions(
    session: Session,
    *,
    query: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = LIST_LIMIT,
) -> list[Submission]:
    """Возвращает заявки, свежие сверху, с фильтрами по поиску и дате."""
    stmt = select(Submission).order_by(Submission.id.desc()).limit(limit)

    pattern = f"%{(query or '').strip()}%"
    if pattern != "%%":
        stmt = stmt.where(
            or_(
                Submission.name.ilike(pattern),
                Submission.company.ilike(pattern),
                Submission.phone.ilike(pattern),
                Submission.email.ilike(pattern),
            )
        )

    if date_from is not None:
        stmt = stmt.where(Submission.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Submission.created_at <= date_to)

    return list(session.scalars(stmt))


def count_submissions(session: Session) -> int:
    """Возвращает общее количество заявок."""
    return int(session.scalar(select(func.count()).select_from(Submission)) or 0)


def unsynced_submissions(session: Session) -> list[Submission]:
    """Возвращает заявки, которые ещё не уехали в Google Sheets."""
    stmt = (
        select(Submission)
        .where(Submission.google_synced_at.is_(None))
        .order_by(Submission.id.asc())
    )
    return list(session.scalars(stmt))


def mark_google_result(
    session: Session, submission: Submission, *, ok: bool, error: str = ""
) -> None:
    """Фиксирует результат синхронизации заявки с Google Sheets."""
    submission.google_synced_at = utcnow() if ok else None
    submission.google_error = "" if ok else error[:ERROR_MAX_LENGTH]
    session.commit()
