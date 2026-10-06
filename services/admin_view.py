"""Карточка заявки для админки: один заход вместо таблицы из 13 колонок.

Почему карточка, а не таблица: в анкете десять полей плюс заметка, и в виде таблицы
список не помещался по ширине — приходилось листать колонки вправо. Карточка показывает
те же данные вертикально, поэтому одинаково читается на ноутбуке и на телефоне.

Значения берутся тем же services.exporters.cell_value, что и для выгрузки, поэтому текст
в карточке и в Excel не расходится (в том числе раскрывается пункт «другое»). Поля,
которые посетитель не отметил, в карточке не показываются: пустая строка «Направления: »
только занимает место.

Согласие на обработку персональных данных не выводится: без него заявка не сохраняется,
поэтому в админке оно всегда есть и повторять его в каждой карточке незачем.
"""

from typing import Any

from config.form_fields import CONSENT, FORM_FIELDS
from models import Submission
from services.exporters import VALUE_MAX_LENGTH, cell_value

# Дата в карточке короче, чем в выгрузке: «05.10.2026 21:37» вместо
# «2026-10-05 21:37:00» — год и секунды в списке заявок лишние.
CARD_DATE_FORMAT = "%d.%m.%Y %H:%M"

# Поля, которые в карточке идут шапкой (имя, компания, контакты), а не строками ответов.
CONTACT_FIELDS = ("name", "company", "phone", "email")


def _answers(submission: Submission) -> list[dict[str, str]]:
    """Собирает строки ответов посетителя, пропуская пустые.

    Args:
        submission: заявка из базы.

    Returns:
        list[dict[str, str]]: пары «подпись — значение» в порядке анкеты.
    """
    rows: list[dict[str, str]] = []
    for field in FORM_FIELDS:
        if field["key"] in CONTACT_FIELDS or field["type"] == CONSENT:
            continue
        value = cell_value(submission, field)
        if not value:
            continue
        rows.append(
            {"label": field.get("export_title", field["label"]), "value": value}
        )
    return rows


def build_card(submission: Submission) -> dict[str, Any]:
    """Готовит одну заявку для шаблона админки.

    Args:
        submission: заявка из базы.

    Returns:
        dict[str, Any]: номер, дата, контакты, строки ответов, заметка и признак того,
        что заявка скрыта. Контакты склеены в одну строку, чтобы шапка карточки не
        расползалась: на телефоне телефон и почта и так в две строки.
    """
    contacts = [
        str(value).strip()
        for value in (submission.phone, submission.email)
        if str(value or "").strip()
    ]
    return {
        "id": submission.id,
        "date": submission.created_at.strftime(CARD_DATE_FORMAT),
        "name": str(submission.name or "").strip(),
        "company": str(submission.company or "").strip(),
        "contacts": " · ".join(contacts),
        "answers": _answers(submission),
        "note": str(submission.note or "").strip()[:VALUE_MAX_LENGTH],
        "deleted": submission.deleted_at is not None,
    }


def build_cards(items: list[Submission]) -> list[dict[str, Any]]:
    """Готовит список карточек для одной страницы админки."""
    return [build_card(item) for item in items]
