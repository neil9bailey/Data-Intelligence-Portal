from collections.abc import Generator
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from app.settings import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False, "timeout": 10} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
_backup_lock = threading.Lock()


def _normalise_sqlite_journal_mode(value: str) -> str:
    mode = (value or "").strip().upper()
    allowed_modes = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}
    return mode if mode in allowed_modes else "DELETE"


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout = 10000")
            cursor.execute(f"PRAGMA journal_mode = {_normalise_sqlite_journal_mode(settings.sqlite_journal_mode)}")
        finally:
            cursor.close()


def ensure_sqlite_parent() -> None:
    if not settings.database_url.startswith("sqlite:///"):
        return
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    if db_path not in {"", ":memory:"}:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def sqlite_db_path() -> Path | None:
    if not settings.database_url.startswith("sqlite:///"):
        return None
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    if db_path in {"", ":memory:"}:
        return None
    return Path(db_path)


def sqlite_persistent_copy_path() -> Path | None:
    if not settings.sqlite_persistent_copy_path:
        return None
    if not settings.database_url.startswith("sqlite:///"):
        return None
    return Path(settings.sqlite_persistent_copy_path)


def restore_sqlite_persistent_copy() -> None:
    source_path = sqlite_persistent_copy_path()
    db_path = sqlite_db_path()
    if source_path is None or db_path is None:
        return
    if not source_path.exists() or source_path.stat().st_size == 0:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, db_path)


def backup_sqlite_persistent_copy() -> None:
    target_path = sqlite_persistent_copy_path()
    source_path = sqlite_db_path()
    if target_path is None or source_path is None:
        return
    if not source_path.exists() or source_path.stat().st_size == 0:
        return

    with _backup_lock:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="dip-sqlite-backup-", suffix=".sqlite", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            source_connection = sqlite3.connect(source_path)
            backup_connection = sqlite3.connect(temp_path)
            try:
                source_connection.backup(backup_connection)
            finally:
                backup_connection.close()
                source_connection.close()
            shutil.copy2(temp_path, target_path)
        finally:
            temp_path.unlink(missing_ok=True)


@contextmanager
def sqlite_startup_lock(timeout_seconds: int = 120, stale_seconds: int = 300):
    db_path = sqlite_db_path()
    if db_path is None:
        yield
        return

    lock_path = db_path.parent / ".dip-db-startup.lock"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    while not acquired:
        try:
            os.mkdir(lock_path)
            acquired = True
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > stale_seconds:
                    shutil.rmtree(lock_path, ignore_errors=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"Timed out waiting for SQLite startup lock at {lock_path}")
            time.sleep(2)

    try:
        yield
    finally:
        if acquired:
            shutil.rmtree(lock_path, ignore_errors=True)


def init_db() -> None:
    ensure_sqlite_parent()
    retry_sqlite_locked(lambda: SQLModel.metadata.create_all(engine))
    retry_sqlite_locked(apply_sqlite_schema_updates)


def retry_sqlite_locked(action):
    for attempt in range(6):
        try:
            return action()
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == 5:
                raise
            time.sleep(2 * (attempt + 1))
    return None


def apply_sqlite_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    updates: dict[str, dict[str, str]] = {
        "extractedrequirement": {
            "requirement_category": "requirement_category VARCHAR DEFAULT 'general'",
        },
        "extractedqualityquestion": {
            "requirement_category": "requirement_category VARCHAR DEFAULT 'general'",
        },
    }
    with engine.begin() as connection:
        for table_name, columns in updates.items():
            existing = {row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}
            if not existing:
                continue
            for column_name, ddl in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
