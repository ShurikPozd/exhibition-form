"""Схемы валидации входящих данных (Pydantic v2).

Лимиты длины берутся из описания анкеты (config/form_fields.py), а тест
tests/test_fields.py проверяет, что ключи схемы и поля анкеты совпадают. Неизвестный
чекбокс — ошибка 422, а не «тихо сохраним мусор в базу».
"""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from config.consent_text import CONSENT_VERSION
from config.form_fields import checkbox_options, field_by_key, max_length
from models import NOTE_MAX_LENGTH as NOTE_MAX
from utils import validators


def _max_length(key: str, default: int) -> int:
    """Берёт лимит длины поля из описания анкеты."""
    field = field_by_key(key)
    length = max_length(field) if field else None
    return length or default


NAME_MAX = _max_length("name", 120)
COMPANY_MAX = _max_length("company", 200)
PHONE_MAX = _max_length("phone", 40)
EMAIL_MAX = _max_length("email", 120)
AFTER_SHOW_MAX = _max_length("after_show", 1000)

ROLE_FIELD = field_by_key("role") or {}
ROLE_OTHER_MAX = ROLE_FIELD.get("other_max_length", 120)


class SubmissionIn(BaseModel):
    """Заявка с формы выставки."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., max_length=NAME_MAX, description="Имя")
    company: str = Field("", max_length=COMPANY_MAX, description="Компания")

    role: list[str] = Field(default_factory=list, description="Кто вы?")
    role_other: str = Field("", max_length=ROLE_OTHER_MAX, description="Кто вы: другое")
    stall: list[str] = Field(
        default_factory=list, description="Что интересует на стенде"
    )
    directions: list[str] = Field(default_factory=list, description="Направления")
    interest: list[str] = Field(default_factory=list, description="Что интересует")

    phone: str = Field("", max_length=PHONE_MAX, description="Телефон")
    email: str = Field("", max_length=EMAIL_MAX, description="Email")
    after_show: str = Field("", max_length=AFTER_SHOW_MAX, description="После выставки")

    consent: bool = Field(
        False, description="Согласие на обработку персональных данных"
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        """Имя обязательно и должно содержать хотя бы один символ."""
        return validators.validate_name(value)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        """Проверяет количество цифр в телефоне."""
        return validators.validate_phone(value)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        """Проверяет адрес почты, если он заполнен."""
        return validators.validate_email(value)

    @field_validator("role", "stall", "directions", "interest")
    @classmethod
    def _check_options(cls, value: list[str], info: ValidationInfo) -> list[str]:
        """Отбрасывает варианты, которых нет в анкете."""
        field = field_by_key(info.field_name)
        if not field:
            return value

        allowed = set(checkbox_options(field))
        unknown = [item for item in value if item not in allowed]
        if unknown:
            raise ValueError(f"варианты не из анкеты: {', '.join(unknown)}")
        return value

    @model_validator(mode="after")
    def _check_submission(self) -> "SubmissionIn":
        """Проверяет правила, которые видны только целиком."""
        if not (self.phone or self.email):
            raise ValueError("оставьте телефон или email, чтобы мы могли вам ответить")
        if "другое" in self.role and not self.role_other:
            raise ValueError("для варианта «другое» уточните, кто вы")
        if not self.consent:
            raise ValueError("нужно согласие на обработку персональных данных")
        return self


class SubmissionEditIn(BaseModel):
    """Правка заявки из админки: контакты и заметка организатора.

    Ответы посетителя (отметки чекбоксов, свободный текст) здесь не меняются: согласие
    подписывалось под тем составом полей, который видел человек на стенде.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., max_length=NAME_MAX, description="Имя")
    company: str = Field("", max_length=COMPANY_MAX, description="Компания")
    phone: str = Field("", max_length=PHONE_MAX, description="Телефон")
    email: str = Field("", max_length=EMAIL_MAX, description="Email")
    note: str = Field("", max_length=NOTE_MAX, description="Заметка")

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        """Имя обязательно и должно содержать хотя бы один символ."""
        return validators.validate_name(value)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        """Проверяет количество цифр в телефоне."""
        return validators.validate_phone(value)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        """Проверяет адрес почты, если он заполнен."""
        return validators.validate_email(value)

    @model_validator(mode="after")
    def _check_contacts(self) -> "SubmissionEditIn":
        """Как и на анкете: без телефона и почты заявку не с кем связать."""
        if not (self.phone or self.email):
            raise ValueError("оставьте телефон или email, чтобы мы могли вам ответить")
        return self


class SubmissionOut(BaseModel):
    """Ответ на успешную отправку.

    Наружу отдаём только идентификатор и время: подтверждать отправку нужно, но
    возвращать обратно персональные данные клиенту незачем.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


__all__ = [
    "SubmissionIn",
    "SubmissionEditIn",
    "SubmissionOut",
    "CONSENT_VERSION",
    "AFTER_SHOW_MAX",
    "COMPANY_MAX",
    "EMAIL_MAX",
    "NAME_MAX",
    "PHONE_MAX",
    "ROLE_OTHER_MAX",
]
