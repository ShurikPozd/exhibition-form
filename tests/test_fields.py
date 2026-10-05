"""Проверки описания анкеты: состав полей, раскладка чекбоксов, совпадение со схемой.

Это защита от расхождения между бумажным макетом, формой и валидацией: если добавить поле
в config/form_fields.py и забыть про schemas.py, тест упадёт.
"""

from config.form_fields import (
    CHECKBOX_GROUP,
    CONSENT,
    FORM_FIELDS,
    LAYOUT_COLUMNS,
    LAYOUT_ROW,
    checkbox_fields,
    checkbox_options,
    field_by_key,
)
from schemas import SubmissionIn

EXPECTED_KEYS = [
    "name",
    "company",
    "role",
    "stall",
    "directions",
    "interest",
    "phone",
    "email",
    "after_show",
    "consent",
]

# Раскладка подтверждена по макету анкеты: 5+5, 3+3, один ряд из 5, один ряд из 3
EXPECTED_LAYOUT = {
    "role": (LAYOUT_COLUMNS, [5, 5]),
    "stall": (LAYOUT_COLUMNS, [3, 3]),
    "directions": (LAYOUT_ROW, [5]),
    "interest": (LAYOUT_ROW, [3]),
}


def test_field_keys_and_numbers():
    """Поля идут в порядке анкеты, номера с 1 по 10 без пропусков."""
    assert [field["key"] for field in FORM_FIELDS] == EXPECTED_KEYS
    assert [field["number"] for field in FORM_FIELDS] == list(range(1, 11))


def test_schema_knows_every_field():
    """Каждое поле анкеты есть в схеме валидации, «другое» — тоже."""
    for key in EXPECTED_KEYS:
        assert key in SubmissionIn.model_fields, key
    assert "role_other" in SubmissionIn.model_fields


def test_checkbox_layout():
    """Чекбоксы разложены как в макете: две колонки или один ряд."""
    assert {field["key"] for field in checkbox_fields()} == set(EXPECTED_LAYOUT)

    for key, (layout, sizes) in EXPECTED_LAYOUT.items():
        field = field_by_key(key)
        assert field is not None
        assert field["layout"] == layout
        if layout == LAYOUT_COLUMNS:
            actual = [len(column) for column in field["columns"]]
        else:
            actual = [len(field["options"])]
        assert actual == sizes, key


def test_options_are_unique_inside_group():
    """Внутри группы нет повторяющихся вариантов — иначе получится две одинаковые строки."""
    for field in checkbox_fields():
        options = checkbox_options(field)
        assert len(options) == len(set(options)), field["key"]


def test_role_has_other_option():
    """В блоке «Кто вы?» есть пункт «другое» и поле для его уточнения."""
    field = field_by_key("role")
    assert "другое" in checkbox_options(field)
    assert field["other_key"] == "role_other"


def test_consent_is_last_and_required():
    """Согласие на ПДн — последний блок и без него заявка не принимается."""
    consent = field_by_key("consent")
    assert consent["type"] == CONSENT
    assert consent["required"] is True
    assert FORM_FIELDS[-1]["key"] == "consent"


def test_every_checkbox_group_is_a_group():
    """Проверка самого типа поля: все четыре группы — чекбоксы."""
    for key in EXPECTED_LAYOUT:
        assert field_by_key(key)["type"] == CHECKBOX_GROUP
