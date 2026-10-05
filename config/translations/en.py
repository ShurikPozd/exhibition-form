"""Английские переводы анкеты.

Переводится только текст, который видит посетитель. Значения чекбоксов остаются
русскими: браузер отправляет значение из config/form_fields.py, поэтому в базу и в
выгрузку попадает привычный менеджеру вариант, а иностранец на экране видит перевод.

Словарь хранится отдельно от описания анкеты, чтобы правка перевода не задевала
структуру полей, а проверка «все ли значения переведены» оставалась в тестах.
"""

from typing import Any

CONSENT_TEMPLATE_PARTS = (
    "By submitting this form I confirm that I have read the personal data processing "
    "terms of {operator_name} and consent to the processing of the data I have entered "
    "(name, company, phone number, email address) for the purpose of handling "
    "exhibition enquiries and contacting me about them. The data is used only for "
    "these purposes and is not shared with third parties, except where required by law."
)


def consent_text(
    operator_name: str, operator_email: str = "", operator_address: str = ""
) -> str:
    """Собирает английский текст согласия с теми же реквизитами оператора.

    Условия обработки те же, что и в русской версии, поэтому версия согласия
    (CONSENT_VERSION) общая: меняется текст целиком, а не язык.
    """
    parts = [CONSENT_TEMPLATE_PARTS.format(operator_name=operator_name)]
    if operator_address:
        parts.append(f"Data is stored at: {operator_address}.")
    if operator_email:
        parts.append(f"You may withdraw consent in writing to {operator_email}.")
    return " ".join(parts)


TRANSLATION: dict[str, Any] = {
    # Заголовки блоков: ключ поля из config/form_fields.py
    "labels": {
        "name": "Name",
        "company": "Company",
        "role": "Who are you?",
        "stall": "What interests you at the iRidi stand",
        "directions": "Areas of interest",
        "interest": "What would you like to discuss",
        "phone": "Phone",
        "email": "Email",
        "after_show": "What to send / prepare after the show",
        "consent": "Consent to personal data processing",
        "role_other": "Other: tell us who you are",
    },
    # Подписи вариантов: ключ — значение, которое уходит в базу и в выгрузку
    "options": {
        "интегратор": "integrator",
        "дизайнер, архитектор": "designer / architect",
        "электрик, слаботочник": "electrician / low-voltage specialist",
        "застройщик, девелопер": "property developer",
        "проектировщик": "design engineer",
        "частное лицо, смотрю для себя": "private visitor, just looking",
        "заказчик от юр. лица": "purchaser (company)",
        "инженер по эксплуатации": "facilities / maintenance engineer",
        "продавец УД, ЭУИ, инженерки": "sales: smart home, electrical, engineering systems",
        "другое": "Other",
        "материалы о продуктах": "product materials",
        "ищу себе инсталлятора": "looking for an installer",
        "обучающие курсы": "training courses",
        "ищу вендора как инсталлятора": "looking for a vendor to install with",
        "хочу стать дистрибьютором": "want to become a distributor",
        "договориться о презентации pre-sale менеджера": (
            "arrange a presentation by a pre-sales manager"
        ),
        "SmartHome": "Smart Home",
        "Коммерция, AV": "Commercial & AV",
        "МКД": "MDU / multifamily buildings",
        "Отели": "Hotels",
        "BMS": "BMS",
        "Нужно КП, презентация, встреча или партнерство": (
            "Pricing, a presentation, a meeting or a partnership"
        ),
        "Будущие планы": "Future plans",
        "Смотрю, что есть на рынке": "Just browsing what is available",
    },
    "placeholders": {
        "name": "How should we address you",
        "company": "Optional",
        "phone": "+___ ___ ___-__-__",
        "email": "name@example.com",
        "after_show": "What to send or prepare after the exhibition",
    },
    "hints": {
        "role": "Select all that apply",
        "stall": "Select all that apply",
        "directions": "Select all that apply",
        "interest": "Select all that apply",
    },
    "notes": {
        "phone": "or give an email below",
        "email": "or give a phone number above",
    },
    "other": {
        "role_other": {
            "label": "Other: tell us who you are",
            "placeholder": "e.g. journalist",
        }
    },
    "ui": {
        "title": "Exhibition visitor form",
        "lead": "Fill this in on the tablet — it takes a minute.",
        "lead_note": (
            "Required: name, phone or email, and consent to data processing. "
            "Everything else is optional."
        ),
        "lang_switch": "Form language",
        "submit": "Submit the form",
        "consent_show": "Show the consent text",
        "consent_version": "Consent version:",
        "done_title": "Thank you!",
        "done_text": "Your form has been received. We will contact you after the show.",
        "done_id": "Request number:",
        "done_again": "Start a new form now",
    },
    "js": {
        "contact_required": "phone or email — at least one of the two",
        "contact_required_email": "email or phone — at least one of the two",
        "contact_required_submit": (
            "please give a phone number or an email — at least one of the two"
        ),
        "name_required": "please enter your name",
        "phone_short": "the phone number has too few digits: {count}",
        "phone_long": "the phone number has too many digits: {count}",
        "phone_digits_few": "digits: {count} — at least {min} needed",
        "phone_digits_many": "digits: {count} — more than {max} is not accepted",
        "phone_foreign": (
            "digits: {count} — add the country code if this is not a Russian number"
        ),
        "phone_ok": "digits: {count} — that is enough",
        "done_next": "New form in {seconds} s",
        "email_invalid": "the email address looks incomplete",
        "email_ok": "the email address looks valid",
        "foreign_chars": "the number contains unexpected characters",
        "consent_required": "consent to personal data processing is required",
        "status_check": "Please check the hints under the fields.",
        "status_sending": "Sending…",
        "status_offline": (
            "No connection to the server. Check the internet connection and send again."
        ),
        "status_generic": "Something went wrong. Please check the form and send again.",
        "status_fields": "please check the fields",
        "draft_restored": "Draft restored — please check it and send.",
    },
    # Подсказки для ошибок сервера: ответ API остаётся на русском, экран переводит
    "server": {
        "name": "please enter your name",
        "phone": "please check the phone number",
        "email": "the email address looks incomplete",
        "role_other": "please tell us who you are if you picked Other",
        "consent": "consent to personal data processing is required",
        "role": "please pick the options listed in the form",
        "stall": "please pick the options listed in the form",
        "directions": "please pick the options listed in the form",
        "interest": "please pick the options listed in the form",
    },
    "consent": consent_text,
}
