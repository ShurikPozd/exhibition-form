"""Тесты резервных копий: дамп базы, ротация, выгрузка в репозиторий и восстановление.

Сеть не используется: httpx подменяется заглушкой, которая отдаёт заготовленные ответы
и записывает вызовы. Проверяется ровно то, что важно для выставки: копия содержит заявки,
в репозиторий уходит новое содержимое, неизменившееся содержимое коммитом не заканчивается,
а восстановление трогает только пустую базу.
"""

import base64
import sqlite3
from pathlib import Path

import httpx
import pytest

import settings
from models import Submission
from services import backup


class _StubResponse:
    """Ответ httpx, который не делает сетевых запросов."""

    def __init__(
        self, status_code: int, json_data: dict | None = None, content: bytes = b""
    ):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=None
            )


class _StubClient:
    """Заглушка httpx.Client: отдаёт заготовленные ответы по порядку и пишет вызовы."""

    def __init__(self, responses: list[_StubResponse], **kwargs):
        self._responses = list(responses)
        self.init_kwargs = kwargs
        self.requests: list[tuple[str, str, dict]] = []

    def __enter__(self) -> "_StubClient":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def get(self, url: str, headers: dict | None = None, **kwargs) -> _StubResponse:
        self.requests.append(("GET", url, dict(headers or {})))
        return self._responses.pop(0)

    def put(self, url: str, headers=None, json=None, **kwargs) -> _StubResponse:
        self.requests.append(
            ("PUT", url, {"headers": headers or {}, "json": json or {}})
        )
        return self._responses.pop(0)


def _install_stub(monkeypatch, responses: list[_StubResponse]) -> _StubClient:
    """Подменяет httpx.Client в модуле бэкапов на заглушку с заданными ответами."""
    stub = _StubClient(responses)
    monkeypatch.setattr(backup.httpx, "Client", lambda **kwargs: stub)
    return stub


def _configure_github(monkeypatch) -> None:
    """Включает выгрузку в репозиторий с тестовыми реквизитами."""
    monkeypatch.setattr(settings, "BACKUP_TOKEN", "тестовый-токен")
    monkeypatch.setattr(settings, "BACKUP_REPO", "ShurikPozd/exhibition-form-backups")


def _dumps() -> list:
    """Все дампы в папке бэкапов тестовой БД."""
    pattern = f"{backup.DUMP_PREFIX}*{backup.DUMP_SUFFIX}"
    return sorted(Path(settings.BACKUP_DIR).glob(pattern))


def test_dump_contains_submitted_rows(created_id, client):
    """Дамп снимается по файлу базы и содержит сохранённую заявку."""
    dump = backup.dump_database()

    assert dump.exists()
    with sqlite3.connect(dump) as connection:
        count = connection.execute("SELECT count(*) FROM submissions").fetchone()[0]
        name = connection.execute("SELECT name FROM submissions").fetchone()[0]
    assert count == 1
    assert name == "Иван Петров"
    assert backup.submissions_count() == 1


def test_dump_is_deterministic_in_bytes(created_id):
    """Одинаковое содержимое даёт одинаковые байты — иначе репозиторий засорялся бы коммитами."""
    data = backup.encode_dump(backup.dump_database())

    assert data == backup.encode_dump(backup.dump_database())
    assert backup.decode_dump(data) == backup.decode_dump(data)


def test_dump_of_empty_database_is_created(client):
    """Дамм снимается и на пустой базе: схема уже создана, заявок просто нет."""
    dump = backup.dump_database()

    assert dump.exists()
    assert backup.submissions_count() == 0


def test_rotate_keeps_only_latest_dumps(monkeypatch, tmp_path):
    """Ротация оставляет последние N копий и удаляет более старые."""
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))
    names = [
        f"{backup.DUMP_PREFIX}2026010{day}-120000{backup.DUMP_SUFFIX}"
        for day in range(1, 6)
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"data")

    removed = backup.rotate(keep=2)

    assert len(removed) == 3
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert remaining == sorted(names[3:])


def test_rotate_respects_default_keep(monkeypatch, tmp_path):
    """Без явного числа берётся BACKUP_KEEP — по умолчанию хранится 14 копий."""
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "BACKUP_KEEP", 3)
    for day in range(1, 6):
        (
            tmp_path / f"{backup.DUMP_PREFIX}2026010{day}-000000{backup.DUMP_SUFFIX}"
        ).write_bytes(b"data")

    backup.rotate()

    assert len(list(tmp_path.iterdir())) == 3


def test_rotate_disabled_when_keep_is_zero(monkeypatch, tmp_path):
    """BACKUP_KEEP=0 отключает ротацию: копии не удаляются никогда."""
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "BACKUP_KEEP", 0)
    for day in range(1, 4):
        (
            tmp_path / f"{backup.DUMP_PREFIX}2026010{day}-000000{backup.DUMP_SUFFIX}"
        ).write_bytes(b"data")

    assert backup.rotate() == []
    assert len(list(tmp_path.iterdir())) == 3


def test_upload_writes_copy_when_file_absent(monkeypatch):
    """Нет файла копии — она создаётся: GET даёт 404, PUT кладёт содержимое."""
    _configure_github(monkeypatch)
    data = "сжатый-дамп".encode("utf-8")
    stub = _install_stub(monkeypatch, [_StubResponse(404), _StubResponse(201)])

    result = backup.upload_dump(data)

    assert result == backup._content_sha(data)
    method, url, payload = stub.requests[1]
    assert method == "PUT"
    assert "backups/submissions.db.gz" in url
    assert base64.b64decode(payload["json"]["content"]) == data
    assert (
        "sha" not in payload["json"]
    ), "создание файла не должно передавать старый sha"
    assert payload["headers"]["Authorization"] == "Bearer тестовый-токен"


def test_upload_replaces_existing_copy(monkeypatch):
    """Файл копии есть и отличается — PUT обязан передать его sha, иначе будет конфликт."""
    _configure_github(monkeypatch)
    stub = _install_stub(
        monkeypatch,
        [_StubResponse(200, {"sha": "старый-sha"}), _StubResponse(200)],
    )

    backup.upload_dump("новый-дамп".encode("utf-8"))

    payload = stub.requests[1][2]["json"]
    assert payload["sha"] == "старый-sha"


def test_upload_skips_identical_content(monkeypatch):
    """Содержимое не изменилось — коммита не будет, запись в репозиторий не трогаем."""
    _configure_github(monkeypatch)
    data = "тот-же-дамп".encode("utf-8")
    stub = _install_stub(
        monkeypatch, [_StubResponse(200, {"sha": backup._content_sha(data)})]
    )

    assert backup.upload_dump(data) == ""
    assert [request[0] for request in stub.requests] == ["GET"]


def test_upload_disabled_without_token(monkeypatch):
    """Без токена сеть не трогается вообще: приложение должно работать и без бэкапов в Git."""
    monkeypatch.setattr(settings, "BACKUP_TOKEN", None)
    monkeypatch.setattr(settings, "BACKUP_REPO", "ShurikPozd/exhibition-form-backups")

    def _explode(**kwargs):
        raise AssertionError("сеть не должна вызываться без токена")

    monkeypatch.setattr(backup.httpx, "Client", _explode)

    assert backup.upload_dump(b"dump") == ""


def test_upload_failure_does_not_break_submission(monkeypatch, client, valid_payload):
    """Ошибка выгрузки не должна превращать принятую заявку в ошибку сервера."""
    _configure_github(monkeypatch)

    def _boom(**kwargs):
        raise httpx.ConnectError("сеть недоступна")

    monkeypatch.setattr(backup.httpx, "Client", _boom)

    response = client.post("/api/submissions", json=valid_payload)

    assert response.status_code == 201
    assert backup.submissions_count() == 1


def test_restore_fills_empty_database(created_id, session, monkeypatch):
    """Пустая база восстанавливается из копии: свежий контейнер не должен начинать с нуля."""
    data = backup.encode_dump(backup.dump_database())
    session.query(Submission).delete()
    session.commit()
    session.close()
    assert backup.submissions_count() == 0

    _configure_github(monkeypatch)
    monkeypatch.setattr(backup, "download_dump", lambda: data)

    assert backup.restore_if_empty() is True
    assert backup.submissions_count() == 1


def test_restore_never_overwrites_existing_rows(created_id, monkeypatch):
    """В базе есть заявки — восстановление не выполняется и сеть не трогается."""
    _configure_github(monkeypatch)

    def _explode():
        raise AssertionError("копия не должна запрашиваться, пока база не пуста")

    monkeypatch.setattr(backup, "download_dump", _explode)

    assert backup.restore_if_empty() is False


def test_restore_without_token_changes_nothing(session, monkeypatch):
    """Без настроенного репозитория восстановление — no-op."""
    monkeypatch.setattr(settings, "BACKUP_TOKEN", None)
    monkeypatch.setattr(settings, "BACKUP_REPO", None)

    assert backup.restore_if_empty() is False
    assert backup.submissions_count() == 0


def test_restore_missing_copy_keeps_database(client, monkeypatch):
    """Копии в репозитории нет — база просто остаётся пустой, без ошибки."""
    _configure_github(monkeypatch)
    monkeypatch.setattr(backup, "download_dump", lambda: None)

    assert backup.restore_if_empty() is False
    assert backup.submissions_count() == 0


def test_submissions_count_without_file(tmp_path):
    """Нет файла базы — это ноль заявок, а не исключение."""
    assert backup.submissions_count(tmp_path / "нет-такой-базы.db") == 0


def test_backup_runs_after_submission(client, valid_payload):
    """После приёма заявки дамп снимается сам: ждать расписания не нужно."""
    client.post("/api/submissions", json=valid_payload)

    dumps = _dumps()
    assert dumps, "после заявки должен появиться дамп без ожидания расписания"
    newest = dumps[-1]
    with sqlite3.connect(newest) as connection:
        count = connection.execute("SELECT count(*) FROM submissions").fetchone()[0]
    assert count == 1, "дамп снят до сохранения заявки или вовсе без неё"


def test_backup_survives_broken_database(monkeypatch, caplog):
    """Сбой бэкапа не поднимается наружу: приложение продолжает принимать заявки."""
    monkeypatch.setattr(
        backup,
        "dump_database",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("диск полон")),
    )

    with caplog.at_level("ERROR"):
        backup.run_backup("проверка устойчивости")

    assert "Бэкап не удался" in caplog.text


def test_run_backup_dumps_and_uploads(client, valid_payload, monkeypatch):
    """Полный цикл: дамп на диске и содержимое, отданное в выгрузку."""
    _configure_github(monkeypatch)
    uploaded: list[bytes] = []
    monkeypatch.setattr(backup, "upload_dump", uploaded.append)

    client.post("/api/submissions", json=valid_payload)

    assert len(uploaded) == 1
    assert backup.decode_dump(uploaded[0])


def test_run_backup_skipped_for_non_sqlite(monkeypatch, caplog):
    """Если база не файл SQLite — бэкап пропускается с предупреждением, а не падает."""
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://localhost/exhibition")

    with caplog.at_level("WARNING"):
        backup.run_backup("проверка другой СУБД")

    assert "бэкап пропущен" in caplog.text


def test_periodic_backup_disabled_in_tests():
    """В тестах фонового цикла нет: это проверяет настройку conftest, а не случайность."""
    assert settings.BACKUP_INTERVAL_HOURS == 0


def test_backup_dir_is_outside_working_data():
    """Дампы тестов не должны попадать в рабочую data/ с настоящими заявками."""
    assert settings.BACKUP_DIR.endswith("backup")
    assert "exhibition-form-tests" in settings.BACKUP_DIR


@pytest.mark.parametrize("keep", [1, 2, 14])
def test_rotate_never_raises_on_empty_dir(monkeypatch, tmp_path, keep):
    """Пустая папка бэкапов — не повод для ошибки: ротация должна быть безразличной."""
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))

    assert backup.rotate(keep=keep) == []
