from logging.config import fileConfig
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.db.models import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = (os.getenv("DATABASE_URL") or os.getenv("PG_DSN") or "").strip()
# Same normalisation as app.core.db_switch.resolve_dsn (kept local: importing
# db_switch would build the runtime adapter as a side effect).
for _prefix in ("postgres://", "postgresql+psycopg://"):
    if database_url.startswith(_prefix):
        database_url = "postgresql://" + database_url[len(_prefix):]
if database_url:
    # configparser treats '%' as interpolation; escape it for passwords like 'p%40ss'.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
