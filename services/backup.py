"""Резервные копии базы заявок: локальные дампы и выгрузка в приватный репозиторий GitHub.

Зачем это нужно. На Render файл SQLite живёт внутри контейнера: контейнер пересоздаётся при
каждом деплое, рестарте и засыпании сервиса, и вместе с ним пропадает база. Поэтому копия
держится в двух местах сразу: в папке бэкапов рядом с базой (быстро, локально) и в закрытом
репозитории GitHub (переживает пересоздание контейнера). При старте, если в базе пусто,
последняя копия забирается обратно.

Что важно не делать: восстановление выполняется только для пустой базы. Непустая база —
это живые заявки, их нельзя перезаписывать копией.
"""

import base64
import gzip
import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
DUMP_PREFIX = "submissions-"
DUMP_SUFFIX = ".db"
REQUEST_TIMEOUT = 30.0

# Один процесс, но фоновых задач несколько: две заявки подряд могут дать два дампа почти
# одновременно, а коммит в репозитории у них общий (один и тот же путь файла). Замок не даёт
# двум задачам одновременно переписать одну копию.
_UPLOAD_LOCK = threading.Lock()


def _is_sqlite() -> bool:
    """Сообщает, что база — файл SQLite (тогда её можно снять дампом)."""
    return settings.DATABASE_URL.startswith("sqlite")


def db_path() -> Path:
    """Путь к файлу базы.

    Берётся из DATABASE_URL, а не из settings.DB_PATH: тот собирается из DATA_DIR и
    игнорирует явный DATABASE_URL, а на тестах и на Render база задаётся именно так.
    """
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///") :])
    return Path(settings.DB_PATH)


def _dump_path(db_path_override: str | Path | None = None) -> tuple[Path, Path]:
    """Возвращает путь к базе и к папке с дампами с учётом переопределений."""
    path = Path(db_path_override) if db_path_override else db_path()
    return path, Path(settings.BACKUP_DIR)


def submissions_count(db_path_override: str | Path | None = None) -> int:
    """Считает заявки в базе; 0, если файла ещё нет или таблица не создана.

    Своё соединение вместо ORM: этой функцией проверяют базу до её инициализации, когда
    таблицы `submissions` может ещё не существовать.
    """
    path, _ = _dump_path(db_path_override)
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute("SELECT count(*) FROM submissions").fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0


def dump_database(db_path_override: str | Path | None = None) -> Path:
    """Снимает согласованный снимок базы и возвращает путь к файлу дампа.

    Снимок делает штатный `sqlite3.Connection.backup`: он учитывает WAL и не блокирует
    запись заявок, поэтому дамп можно брать прямо под нагрузкой, на работающем приложении.
    """
    source, directory = _dump_path(db_path_override)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = directory / f"{DUMP_PREFIX}{stamp}{DUMP_SUFFIX}"

    reader = sqlite3.connect(source)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()

    logger.info("Дамп базы создан: %s (%s байт)", target.name, target.stat().st_size)
    return target


def rotate(keep: int | None = None, backup_dir: str | Path | None = None) -> list[Path]:
    """Удаляет старые дампы, оставляя последние keep штук. Возвращает удалённые пути.

    Имена дампов начинаются с метки времени UTC в формате `YYYYmmdd-HHMMSS`, поэтому
    сортировка по имени — это сортировка по времени, и переименовывать ничего не нужно.
    """
    limit = settings.BACKUP_KEEP if keep is None else keep
    directory = Path(backup_dir) if backup_dir else Path(settings.BACKUP_DIR)
    if limit <= 0:
        return []
    dumps = sorted(directory.glob(f"{DUMP_PREFIX}*{DUMP_SUFFIX}"))
    stale = dumps[:-limit] if len(dumps) > limit else []
    for path in stale:
        path.unlink(missing_ok=True)
    if stale:
        logger.info("Ротация бэкапов: удалено %s старых копий", len(stale))
    return stale


def encode_dump(dump: str | Path) -> bytes:
    """Сжимает дамп для хранения в Git.

    `mtime=0` у gzip нужен для одной важной вещи: без него в архив попадает время
    упаковки, и одинаковое содержимое давало бы разные файлы — тогда репозиторий
    засорялся бы коммитами без изменений.
    """
    return gzip.compress(Path(dump).read_bytes(), compresslevel=6, mtime=0)


def decode_dump(data: bytes) -> bytes:
    """Распаковывает дамп, полученный из GitHub."""
    return gzip.decompress(data)


def _headers() -> dict[str, str]:
    """Заголовки GitHub Contents API. Токен в заголовок, в лог не попадает."""
    return {
        "Authorization": f"Bearer {settings.BACKUP_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "exhibition-form-backup",
    }


def _backup_url() -> str:
    """Адрес файла с копией в репозитории."""
    return f"{GITHUB_API}/repos/{settings.BACKUP_REPO}/contents/{settings.BACKUP_PATH}"


def _content_sha(data: bytes) -> str:
    """Считает идентификатор содержимого файла по правилам Git (sha1 от заголовка и данных).

    GitHub отдаёт этот же идентификатор в поле `sha`. Сравнив его до загрузки, можно
    не качать файл обратно и понять, что содержимое не изменилось.
    """
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324  (не для безопасности)


def _configured() -> bool:
    """Сообщает, заданы ли репозиторий и токен для выгрузки копий."""
    return bool(settings.BACKUP_REPO and settings.BACKUP_TOKEN)


def upload_dump(data: bytes) -> str:
    """Кладёт сжатый дамп в приватный репозиторий GitHub.

    Возвращает идентификатор загруженного файла. Пустая строка означает «коммит не нужен»:
    либо выгрузка не настроена, либо содержимое в репозитории уже такое же.
    """
    if not _configured():
        logger.info("Выгрузка копии в репозиторий не настроена — только локальный дамп")
        return ""
    if not data:
        logger.warning("Дамп пустой — выгрузка в репозиторий пропущена")
        return ""

    new_sha = _content_sha(data)
    with _UPLOAD_LOCK, httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        current_sha = ""
        response = client.get(_backup_url(), headers=_headers())
        if response.status_code == 200:
            current_sha = response.json().get("sha", "")
        elif response.status_code != 404:
            response.raise_for_status()

        if current_sha == new_sha:
            logger.info("Копия в репозитории не изменилась — коммит не делаем")
            return ""

        payload: dict[str, str] = {
            "message": "backup: копия базы заявок",
            "content": base64.b64encode(data).decode("ascii"),
            "branch": settings.BACKUP_BRANCH,
        }
        if current_sha:
            payload["sha"] = current_sha
        result = client.put(_backup_url(), headers=_headers(), json=payload)
        result.raise_for_status()

    logger.info("Копия базы загружена: %s (%s байт)", settings.BACKUP_PATH, len(data))
    return new_sha


def download_dump() -> bytes | None:
    """Забирает копию из репозитория; None, если её там ещё нет."""
    if not _configured():
        return None
    headers = _headers()
    headers["Accept"] = "application/vnd.github.raw"
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.get(_backup_url(), headers=headers)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def restore_if_empty(db_path_override: str | Path | None = None) -> bool:
    """Восстанавливает базу из копии в репозитории, только если заявок нет ни одной.

    На Render пустая база означает свежий контейнер, а не пропавшие данные: заявки лежат
    в копии. Поэтому пустая база — единственный случай, когда её можно заменить целиком.
    Непустая база не трогается никогда.

    Returns:
        True, если база была восстановлена.
    """
    path, _ = _dump_path(db_path_override)
    if not _configured():
        return False
    if submissions_count(path) > 0:
        logger.info("В базе есть заявки — восстановление из репозитория не выполняется")
        return False

    data = download_dump()
    if not data:
        logger.info("Копии в репозитории нет — база остаётся пустой")
        return False

    raw = decode_dump(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.restore")
    temp_path.write_bytes(raw)
    # Копия переносится в базу штатным sqlite3.Connection.backup, а не переименованием
    # файла: файл базы может быть открыт соединением приложения, а на Windows открытый
    # файл переименовать нельзя. Backup переписывает страницы на месте и обрезает хвост.
    reader = sqlite3.connect(temp_path)
    writer = sqlite3.connect(path)
    try:
        reader.backup(writer)
        # Сбрасываем журнал в саму базу: копия должна лежать в главном файле, а не в
        # -wal, который мог остаться от прежнего соединения и закрыть собой новые страницы.
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        writer.close()
        reader.close()
    temp_path.unlink(missing_ok=True)
    logger.info("База восстановлена из репозитория: заявок %s", submissions_count(path))
    return True


def run_backup(reason: str) -> None:
    """Делает полный цикл: дамп, ротация, выгрузка в репозиторий.

    Ошибки не поднимаются дальше: сбой бэкапа не должен валить приём заявок, поэтому всё
    непредвиденное пишется в лог, а приложение продолжает работать.

    Args:
        reason: что вызвало бэкап (после заявки, по расписанию, вручную) — попадает в лог.
    """
    if not _is_sqlite():
        logger.warning("База не SQLite — бэкап пропущен: %s", settings.DATABASE_URL)
        return
    try:
        dump = dump_database()
        rotate()
        upload_dump(encode_dump(dump))
    except Exception:
        logger.exception("Бэкап не удался (%s) — приложение работает дальше", reason)
