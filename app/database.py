from collections.abc import Generator
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.settings import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def ensure_sqlite_parent() -> None:
    if not settings.database_url.startswith("sqlite:///"):
        return
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    if db_path not in {"", ":memory:"}:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    ensure_sqlite_parent()
    SQLModel.metadata.create_all(engine)
    apply_sqlite_schema_updates()


def apply_sqlite_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    updates: dict[str, dict[str, str]] = {}
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
