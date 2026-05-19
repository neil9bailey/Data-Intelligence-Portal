from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database import database_mode_for_url


def test_database_mode_detects_sqlite_and_postgresql_urls():
    assert database_mode_for_url("sqlite:///data/app.sqlite") == "sqlite"
    assert database_mode_for_url("postgresql+psycopg://user:pass@db:5432/dip") == "postgresql"
    assert database_mode_for_url("postgres://user:pass@db:5432/dip") == "postgresql"


def test_alembic_initial_revision_is_registered():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert "20260519_0001" in script.get_heads()
