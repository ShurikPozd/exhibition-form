"""Сохранение и выборка заявок — здесь вся работа с SQL.

Ответ «201» сам по себе не доказывает, что запись легла в базу: соединение может
оборваться на commit, а SQLite — вернуть конфликт блокировок. Поэтому create_submission()
после сохранения перечитывает строку обратно (read-back) и поднимает ошибку, если её нет.
"""

import logging

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from config.consent_text import CONSENT_VERSION
from models import Submission, utcnow
from schemas import SubmissionEditIn, SubmissionIn
from utils.masking import mask_email, mask_phone

logger = logging.getLogger(__name__)

LIST_LIMIT = 1000
ERROR_MAX_LENGTH = 300
QUERY_MAX_LENGTH = 120

# Размеры страницы в админке: не список произвольных чисел, а несколько предсказуемых
# вариантов. Человек сразу видит, сколько карточек влезет на экран, и не может случайно
# выбрать 3000 и получить длинную страницу.
PER_PAGE_OPTIONS = (10, 20, 50, 100)
PER_PAGE_DEFAULT = 10

# Колонки, по которым ищет организатор: контакты ищутся в первую очередь, payload
# разбирается отдельно (см. _search_filter) из-за экранирования кириллицы в JSON.
_SEARCH_COLUMNS = (
    Submission.name,
    Submission.company,
    Submission.phone,
    Submission.email,
)


def _deleted_filter(deleted: bool):
    """Условие «видимые» или «скрытые»: списки в админке не должны смешиваться.

    Список скрытых показывает только скрытые записи, а обычный — только видимые: иначе
    под надписью «Показать скрытые» оказывались бы все заявки сразу, а у каждой ещё и
    кнопка «Вернуть», которой нечего вернуть.
    """
    if deleted:
        return Submission.deleted_at.is_not(None)
    return Submission.deleted_at.is_(None)


def normalize_query(value: object) -> str:
    """Приводит поисковый запрос к сравнимой строке: без краёв, с одним пробелом, не длинный.

    Args:
        value: что пришло из query-параметра — строка или None.

    Returns:
        str: готовый запрос; пустая строка означает «фильтр не задан».
    """
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:QUERY_MAX_LENGTH]


def _escape_like(value: str) -> str:
    """Экранирует спецсимволы LIKE: запрос ищется буквально, а не как шаблон."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_filter(query: str):
    """Условие «похоже на запрос» или None, если запрос пустой.

    Ищется по имени, компании, телефону и почте, а также по тексту payload: заявку с
    отметкой «МКД» организатор найдёт по слову из ответа, а не только по контактам.
    Сравнение регистронезависимое — встроенный lower() в SQLite понимает только
    латиницу, а фамилии у нас кириллицей (см. casefold в database.py). Символы `%` и
    `_` экранируются: иначе запрос «100%» превратился бы в шаблон LIKE и нашёл бы всё
    подряд.
    """
    if not query:
        return None
    pattern = f"%{_escape_like(query.casefold())}%"
    return or_(
        *(
            func.casefold(column).like(pattern, escape="\\")
            for column in _SEARCH_COLUMNS
        ),
        # payload разбирается на настоящие слова функцией json_casefold: в базе JSON
        # лежит с экранированием кириллицы, и обычное сравнение по строке не видит
        # в нём ни «МКД», ни «мкд».
        func.json_casefold(cast(Submission.payload, String)).like(pattern, escape="\\"),
    )


def _list_conditions(deleted: bool, query: str) -> list:
    """Собирает условия выборки: видимость и, если задан, поиск по запросу."""
    conditions = [_deleted_filter(deleted)]
    search = _search_filter(normalize_query(query))
    if search is not None:
        conditions.append(search)
    return conditions


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
    session: Session, *, limit: int = LIST_LIMIT, deleted: bool = False, query: str = ""
) -> list[Submission]:
    """Возвращает заявки, свежие сверху.

    Args:
        session: сессия SQLAlchemy.
        limit: сколько записей отдать, свежие приходят первыми.
        deleted: брать только скрытые записи (список для восстановления).
        query: поисковый запрос по контактам и ответам; пустой — без фильтра.

    Returns:
        list[Submission]: либо видимые заявки, либо только скрытые — по флагу deleted.
    """
    stmt = select(Submission).where(*_list_conditions(deleted, query))
    stmt = stmt.order_by(Submission.id.desc()).limit(limit)
    return list(session.scalars(stmt))


def count_submissions(
    session: Session, *, deleted: bool = False, query: str = ""
) -> int:
    """Считает заявки: видимые или скрытые, с учётом поискового запроса."""
    stmt = (
        select(func.count())
        .select_from(Submission)
        .where(*_list_conditions(deleted, query))
    )
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
    query: str = "",
) -> dict:
    """Отдаёт одну страницу заявок вместе со счётчиками для пейджера.

    Страница за пределами диапазона не считается ошибкой: показывается ближайшая
    существующая, чтобы ссылка из истории браузера не приводила к пустому экрану.

    Args:
        session: сессия SQLAlchemy.
        page: номер страницы, начиная с 1.
        per_page: сколько заявок на странице (нормализуется внутри).
        deleted: брать только скрытые записи (список для восстановления).
        query: поисковый запрос по контактам и ответам.

    Returns:
        dict: items — заявки страницы, total — сколько их всего по фильтру, page, per_page,
        pages — сколько страниц, shown_from и shown_to — номера показанных записей.
    """
    per_page = normalize_per_page(per_page)
    conditions = _list_conditions(deleted, query)
    total = count_submissions(session, deleted=deleted, query=query)
    pages = max(1, -(-total // per_page))
    page = min(normalize_page(page), pages)

    stmt = select(Submission).where(*conditions)
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
