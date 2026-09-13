"""Окружение Alembic.

Ключевой момент: URL базы берётся из настроек приложения, а не из alembic.ini.
Так миграции в CI, в Docker и в кластере автоматически едут в ту же базу,
что и приложение, и негде разъехаться.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base  # импорт создаёт все таблицы в Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Сгенерировать SQL без подключения к базе: alembic upgrade head --sql.

    Пригодится, когда DBA требует посмотреть SQL глазами до применения на проде.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Без этого Alembic не замечает смену типа колонки
            # (например, Numeric(10,2) -> Numeric(14,2)).
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
