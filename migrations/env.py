"""Alembic migration environment.

Ensures Alembic reads DATABASE_URL from the project's .env file so that
migrations run against the intended database (e.g., Postgres) instead of
defaulting to SQLite.
"""

import os
import pathlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from Adventorator.db import Base
from dotenv import load_dotenv


# Load environment variables from the project root .env before reading DATABASE_URL
_ROOT = pathlib.Path(__file__).resolve().parents[1]
_ENV_PATH = _ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH)
else:
    # Fall back to default lookup on PATH/CWD if no file at expected location
    load_dotenv()


config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _sync_db_url() -> str:
    """Return a sync DB URL for Alembic using appropriate sync drivers.

    - For Postgres: force the psycopg (v3) driver: postgresql+psycopg://
    - For SQLite: drop the aiosqlite suffix to use the builtin pysqlite driver.
    """
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./adventorator.sqlite3")
    # Normalize Postgres URLs to psycopg (v3) sync driver
    if url.startswith("postgresql+") or url.startswith("postgresql://"):
        # Remove any async driver suffix then enforce +psycopg
        base = url.replace("+asyncpg", "").replace("+psycopg", "")
        if base.startswith("postgresql://"):
            return base.replace("postgresql://", "postgresql+psycopg://", 1)
        # Handles e.g., postgresql+driver:// -> postgresql+psycopg://
        return "postgresql+psycopg://" + base.split("://", 1)[1]
    # SQLite: strip async driver
    return url.replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    context.configure(url=_sync_db_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_sync_db_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()