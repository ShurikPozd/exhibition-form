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

# Размеры страницы в админке: не список произвольных чисел, а несколько предсказуемых
# вариантов. Человек сразу видит, сколько карточек влезет на экран, и не может случайно
# выбрать 3000 и получить длинную страницу.
PER_PAGE_OPTIONS = (10, 20, 50, 100)
PER_PAGE_DEFAULT = 10


def _deleted_filter(deleted: bool):
    """Условие «видимые» или «скрытые»: списки в админке не должны смешиваться.

    Список скрытых показывает только скрытые записи, а обычный — только видимые: иначе
    под надписью «Показать скрытые» оказывались бы все заявки сразу, а у каждой ещё и
    кнопка «Вернуть», которой нечего вернуть.
    """
    if deleted:
        return Submission.deleted_at.is_not(None)
    return Submission.deleted_at.is_(None)


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
    session: Session, *, limit: int = LIST_LIMIT, deleted: bool = False
) -> list[Submission]:
    """Возвращает заявки, свежие сверху.

    Args:
        session: сессия SQLAlchemy.
        limit: сколько записей отдать, свежие приходят первыми.
        deleted: брать только скрытые записи (список для восстановления).

    Returns:
        list[Submission]: либо видимые заявки, либо только скрытые — по флагу deleted.
    """
    stmt = select(Submission).where(_deleted_filter(deleted))
    stmt = stmt.order_by(Submission.id.desc()).limit(limit)
    return list(session.scalars(stmt))


def count_submissions(session: Session, *, deleted: bool = False) -> int:
    """Возвращает количество видимых заявок или, при deleted=True, скрытых."""
    stmt = select(func.count()).select_from(Submission).where(_deleted_filter(deleted))
    return int(session.scalar(stmt) or 0)


def normalize_per_page(value: object) -> int:
    """Приводит значение из адреса или cookie к размеру страницы.

    Args:
        value: что пришло из query-параметра или cookie — строка, число или None.

    Returns:
        int: одно из PER_PAGE_OPTIONS; всё остальное (мусор, «0», «13») — размер
        по умолчанию, чтобы испорченная ссылка не ломала страницу.
    """
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return PER_PAGE_DEFAULT
    return number if number in PER_PAGE_OPTIONS else PER_PAGE_DEFAULT


def normalize_page(value: object) -> int:
    """Приводит значение из адреса к номеру страницы, начиная с 1."""
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 1
    return number if number > 0 else 1


def paginate_submissions(
    session: Session,
    *,
    page: object = 1,
    per_page: object = PER_PAGE_DEFAULT,
    deleted: bool = False,
) -> dict:
    """Отдаёт одну страницу заявок вместе со счётчиками для пейджера.

    Страница за пределами диапазона не считается ошибкой: показывается ближайшая
    существующая, чтобы ссылка из истории браузера не приводила к пустому экрану.

    Args:
        session: сессия SQLAlchemy.
        page: номер страницы, начиная с 1.
        per_page: сколько заявок на странице (нормализуется внутри).
        deleted: брать только скрытые записи (список для восстановления).

    Returns:
        dict: items — заявки страницы, total — сколько их всего, page, per_page,
        pages — сколько страниц, shown_from и shown_to — номера показанных записей.
    """
    per_page = normalize_per_page(per_page)
    total = count_submissions(session, deleted=deleted)
    pages = max(1, -(-total // per_page))
    page = min(normalize_page(page), pages)

    stmt = select(Submission).where(_deleted_filter(deleted))
    stmt = stmt.order_by(Submission.id.desc())
    stmt = stmt.limit(per_page).offset((page - 1) * per_page)
    items = list(session.scalars(stmt))

    shown_from = (page - 1) * per_page + 1 if items else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "shown_from": shown_from,
        "shown_to": shown_from + len(items) - 1 if items else 0,
    }


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
