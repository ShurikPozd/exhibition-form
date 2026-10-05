"""Проверки синхронизации с Google Sheets.

Сеть не используется: httpx.post подменяется заглушкой. Проверяем контракт — секрет и
колонки уходят в вебхук, а результат попадает в google_synced_at / google_error.
"""

import httpx
import pytest

import settings
from schemas import SubmissionIn
from services import exporters, google_sheet
from services import submissions as submissions_service


class FakeResponse:
    """Заглушка ответа httpx: приложению нужны только код и текст."""

    def __init__(self, status_code: int = 200, text: str = "ok"):
        self.status_code = status_code
        self.text = text


@pytest.fixture()
def submission(session, valid_payload):
    """Заявка, сохранённая в тестовой базе."""
    return submissions_service.create_submission(session, SubmissionIn(**valid_payload))


@pytest.fixture()
def webhook(monkeypatch):
    """Включает синхронизацию и подменяет httpx.post на заглушку."""

    def factory(status_code: int = 200, text: str = "ok") -> list[dict]:
        calls: list[dict] = []

        def fake_post(url, json=None, timeout=None, **kwargs):
            calls.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse(status_code, text)

        monkeypatch.setattr(
            settings, "GOOGLE_SHEET_WEBHOOK_URL", "https://script.example/exec"
        )
        monkeypatch.setattr(settings, "GOOGLE_SYNC_ENABLED", True)
        monkeypatch.setattr(httpx, "post", fake_post)
        return calls

    return factory


def test_disabled_without_url(monkeypatch):
    """Без URL вебхука синхронизация выключена — приложение работает без Google."""
    monkeypatch.setattr(settings, "GOOGLE_SHEET_WEBHOOK_URL", None)
    assert google_sheet.is_enabled() is False


def test_disabled_by_flag(monkeypatch):
    """GOOGLE_SYNC_ENABLED=false выключает синхронизацию."""
    monkeypatch.setattr(
        settings, "GOOGLE_SHEET_WEBHOOK_URL", "https://script.example/exec"
    )
    monkeypatch.setattr(settings, "GOOGLE_SYNC_ENABLED", False)
    assert google_sheet.is_enabled() is False


def test_disabled_submission_stays_in_sqlite(session, submission):
    """Выключенная синхронизация не мешает: заявка сохранена, ошибок не записано."""
    assert google_sheet.sync_submission(session, submission) is False
    assert submission.google_synced_at is None
    assert submission.google_error == ""


def test_success_marks_submission_as_synced(session, submission, webhook):
    """Успешный ответ вебхука проставляет время синхронизации."""
    calls = webhook(200, "ok")

    assert google_sheet.sync_submission(session, submission) is True
    assert submission.google_synced_at is not None
    assert submission.google_error == ""
    assert len(calls) == 1


def test_request_contains_secret_and_row(session, submission, webhook):
    """В вебхук уходят секрет и строка в колонках выгрузки."""
    calls = webhook(200, "ok")

    google_sheet.sync_submission(session, submission)

    payload = calls[0]["json"]
    assert set(payload) == {"secret", "row"}
    assert payload["row"][2] == "Иван Петров"
    assert len(payload["row"]) == len(exporters.headers())
    assert calls[0]["timeout"] == settings.GOOGLE_SHEET_TIMEOUT


def test_http_error_is_recorded(session, submission, webhook):
    """Ошибка вебхука пишется в google_error, заявка остаётся неотправленной."""
    webhook(500, "Script error")

    assert google_sheet.sync_submission(session, submission) is False
    assert submission.google_synced_at is None
    assert "HTTP 500" in submission.google_error


def test_network_error_is_recorded(session, submission, monkeypatch):
    """Недоступный вебхук не роняет приём заявки: ошибка попадает в google_error."""
    monkeypatch.setattr(
        settings, "GOOGLE_SHEET_WEBHOOK_URL", "https://script.example/exec"
    )
    monkeypatch.setattr(settings, "GOOGLE_SYNC_ENABLED", True)

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", boom)

    assert google_sheet.sync_submission(session, submission) is False
    assert "ConnectError" in submission.google_error


def test_retry_unsynced_counts_failures(session, submission, webhook):
    """Повтор отправляет все неотправленные заявки и считает успехи и ошибки."""
    webhook(500, "Script error")
    expected = len(submissions_service.unsynced_submissions(session))

    result = google_sheet.retry_unsynced(session)

    assert result["failed"] == expected
    assert result["sent"] == 0
    assert result["skipped"] == 0


def test_retry_skips_nothing_when_disabled(session, submission, monkeypatch):
    """Выключенная синхронизация: повтор ничего не шлёт и не считает ошибкой."""
    monkeypatch.setattr(settings, "GOOGLE_SYNC_ENABLED", False)
    expected = len(submissions_service.unsynced_submissions(session))

    result = google_sheet.retry_unsynced(session)

    assert result["skipped"] == expected
    assert result["sent"] == 0
    assert result["failed"] == 0


def test_retry_sends_only_missing_rows(session, submission, webhook):
    """Повтор не дублирует то, что уже в таблице."""
    calls = webhook(200, "ok")
    google_sheet.sync_submission(session, submission)
    calls.clear()

    google_sheet.retry_unsynced(session)

    sent_ids = {call["json"]["row"][0] for call in calls}
    assert str(submission.id) not in sent_ids
