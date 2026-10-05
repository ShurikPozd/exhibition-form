"""Проверки маскирования секретов и персональных данных в логах.

Отдельный акцент на токене доступа к админке: он попадает в URL, а uvicorn пишет URL
в access-лог целиком. Проверяем именно готовую строку записи логгера, потому что
реальная утечка обнаруживается в тексте лога, а не в аргументах.
"""

import logging

import pytest

from utils.masking import (
    TOKEN_MASK,
    AccessLogTokenFilter,
    install_access_log_mask,
    mask_email,
    mask_phone,
    mask_query_token,
)

SECRET = "rKOaFV782Znk_T0IhLyt8mhbjxC70EDYHnj-z5aG6RI"


def make_record(msg, args):
    """Собирает запись логгера как её создаёт logging."""
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, msg, args, None
    )


def rendered(record: logging.LogRecord) -> str:
    """Возвращает готовую строку записи — именно она попадает в лог."""
    return record.getMessage()


# --- Уже было: персональные данные ---


def test_mask_phone_keeps_last_digits():
    """Телефон узнаётся по последним цифрам, но не читается целиком."""
    assert mask_phone("+7 (903) 211-70-83") == "***7083"
    assert mask_phone("123") == "***"


def test_mask_email_keeps_domain():
    """Почта узнаётся по домену и последним буквам имени."""
    assert mask_email("ivan@example.com") == "**an@example.com"
    assert mask_email("мусор") == "***"


# --- Новое: токен в access-логе ---


def test_query_token_value_is_masked():
    """Значение токена в адресе заменяется, путь и код остаются."""
    line = f'127.0.0.1 - "GET /admin?token={SECRET} HTTP/1.1" 200'
    masked = mask_query_token(line)
    assert SECRET not in masked
    assert masked == f'127.0.0.1 - "GET /admin?token={TOKEN_MASK} HTTP/1.1" 200'


def test_query_token_masked_among_other_params():
    """Токен не единственный параметр — остальные не должны пострадать."""
    line = f"/?lang=en&token={SECRET}&x=1"
    masked = mask_query_token(line)
    assert masked == f"/?lang=en&token={TOKEN_MASK}&x=1"


def test_url_without_token_is_untouched():
    """Обычные адреса не меняются: иначе лог станет нечитаемым."""
    line = '127.0.0.1 - "GET /?lang=en HTTP/1.1" 200'
    assert mask_query_token(line) == line


def test_word_token_in_path_is_not_masked():
    """Слово «token» вне query-строки не считается секретом."""
    line = "/static/js/token=abc.js"
    assert mask_query_token(line) == line


def test_uvicorn_style_record_is_masked():
    """Запись в формате uvicorn (путь в args) очищается от токена."""
    record = make_record(
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", f"/admin?token={SECRET}", "1.1", 200),
    )
    assert AccessLogTokenFilter().filter(record) is True
    line = rendered(record)
    assert SECRET not in line
    assert f"token={TOKEN_MASK}" in line
    assert "200" in line


def test_access_token_parameter_is_masked_too():
    """Параметр access_token маскируется так же, как token."""
    assert SECRET not in mask_query_token(f"/admin?access_token={SECRET}")


def test_dict_style_record_is_masked():
    """Запись с именованными аргументами (%(path)s) тоже очищается."""
    record = make_record(
        "%(client)s %(path)s", {"client": "1.2.3.4", "path": f"/admin?token={SECRET}"}
    )
    assert AccessLogTokenFilter().filter(record) is True
    assert SECRET not in rendered(record)
    assert "1.2.3.4" in rendered(record)


def test_preformatted_message_is_masked():
    """Если uvicorn пришлёт уже готовую строку, токен всё равно не уедет в лог."""
    record = make_record(f'GET /admin?token={SECRET} HTTP/1.1" 200', None)
    AccessLogTokenFilter().filter(record)
    assert SECRET not in rendered(record)


def test_filter_keeps_non_string_arguments():
    """Числовые и прочие аргументы не должны ломать форматирование."""
    record = make_record("%s %s", (f"/admin?token={SECRET}", 200))
    AccessLogTokenFilter().filter(record)
    assert SECRET not in rendered(record)
    assert rendered(record).endswith("200")


def test_install_is_idempotent():
    """Повторная установка не добавляет второй фильтр."""
    logger = install_access_log_mask()
    install_access_log_mask()
    filters = [
        item for item in logger.filters if isinstance(item, AccessLogTokenFilter)
    ]
    assert len(filters) == 1


def test_filter_installed_on_startup():
    """Импорт logger_config (он выполняется при старте приложения) уже вешает фильтр."""
    assert any(
        isinstance(item, AccessLogTokenFilter)
        for item in logging.getLogger("uvicorn.access").filters
    )


@pytest.mark.parametrize(
    "args",
    [
        ("127.0.0.1", "GET", f"/admin?token={SECRET}", "1.1", 200),
        ("127.0.0.1", "GET", f"/api/submissions.xlsx?token={SECRET}", "1.1", 403),
    ],
)
def test_no_secret_survives_anywhere_in_record(args):
    """Секрет не должен остаться ни в одном аргументе записи."""
    record = make_record('%s - "%s %s HTTP/%s" %d', args)
    AccessLogTokenFilter().filter(record)
    assert SECRET not in repr(record.args)
    assert SECRET not in rendered(record)
