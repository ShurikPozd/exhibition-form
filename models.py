"""ORM-модель заявки с анкеты выставки."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utcnow() -> datetime:
    """Возвращает текущее время UTC без tzinfo — так SQLite хранит его единообразно."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Submission(Base):
    """Одна заполненная анкета.

    Контактные поля вынесены в отдельные колонки, чтобы по ним можно было фильтровать
    обычным SQL. Остальные ответы (группы чекбоксов, свободный текст) лежат в payload
    JSON: набор пунктов анкеты меняется от выставки к выставке, и под каждый чекбокс
    заводить колонку не нужно.
    """

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    name: Mapped[str] = mapped_column(String(120), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="", index=True)
    email: Mapped[str] = mapped_column(String(120), default="", index=True)

    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    consent_version: Mapped[str] = mapped_column(String(32), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")

    google_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    google_error: Mapped[str] = mapped_column(String(300), default="")
