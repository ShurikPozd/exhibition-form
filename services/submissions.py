"""Сохранение и выборка заявок — здесь вся работа с SQL.

Ответ «201» сам по себе не доказывает, что запись легла в базу: соединение может
оборваться на commit, а SQLite — вернуть конфликт блокировок. Поэтому create_submission()
после сохранения перечитывает строку обратно (read-back) и поднимает ошибку, если её нет.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.consent_text import CONSENT_VERSION
from models import Submission, utcnow
from schemas import SubmissionEditIn, SubmissionIn
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


def list_submissions(
    session: Session, *, limit: int = LIST_LIMIT, include_deleted: bool = False
) -> list[Submission]:
    """Возвращает заявки, свежие сверху.

    Args:
        session: сессия SQLAlchemy.
        limit: сколько записей отдать, свежие приходят первыми.
        include_deleted: показывать ли скрытые записи (восстановление в админке).

    Returns:
        list[Submission]: заявки по убыванию id.
    """
    stmt = select(Submission)
    if not include_deleted:
        stmt = stmt.where(Submission.deleted_at.is_(None))
    stmt = stmt.order_by(Submission.id.desc()).limit(limit)
    return list(session.scalars(stmt))


def count_submissions(session: Session, *, include_deleted: bool = False) -> int:
    """Возвращает количество заявок (скрытые не считаются, если не сказано иначе)."""
    stmt = select(func.count()).select_from(Submission)
    if not include_deleted:
        stmt = stmt.where(Submission.deleted_at.is_(None))
    return int(session.scalar(stmt) or 0)


def get_submission(session: Session, submission_id: int) -> Submission | None:
    """Возвращает заявку по id или None."""
    return session.get(Submission, submission_id)


def update_contacts(
    session: Session, submission_id: int, data: SubmissionEditIn
) -> Submission | None:
    """Правит контакты и заметку заявки, не трогая ответы посетителя.

    Returns:
        Submission | None: обновлённая запись, перечитанная после commit,
        либо None, если заявки с таким id нет.
    """
    submission = get_submission(session, submission_id)
    if submission is None:
        return None

    submission.name = data.name
    submission.company = data.company
    submission.phone = data.phone
    submission.email = data.email
    submission.note = data.note
    submission.updated_at = utcnow()
    session.commit()

    saved = get_submission(session, submission_id)
    if saved is None:
        session.rollback()
        logger.error("Заявка #%s не читается после правки", submission_id)
        raise RuntimeError("не удалось подтвердить правку заявки")

    logger.info("Изменены контакты и заметка заявки #%s", submission_id)
    return saved


def soft_delete(session: Session, submission_id: int) -> Submission | None:
    """Прячет заявку из админки и выгрузок, оставляя её в базе.

    Returns:
        Submission | None: скрытая запись либо None, если заявки нет.
    """
    submission = get_submission(session, submission_id)
    if submission is None:
        return None

    submission.deleted_at = utcnow()
    session.commit()
    logger.info("Заявка #%s скрыта из админки и выгрузок", submission_id)
    return submission


def restore(session: Session, submission_id: int) -> Submission | None:
    """Возвращает скрытую заявку в админку и выгрузки.

    Returns:
        Submission | None: восстановленная запись либо None, если заявки нет.
    """
    submission = get_submission(session, submission_id)
    if submission is None:
        return None

    submission.deleted_at = None
    session.commit()
    logger.info("Заявка #%s восстановлена", submission_id)
    return submission
