"""
Cadena de migraciones INDEPENDIENTE para Motored Pedidos (sdd/motored-
pedidos-cimientos, ADR-3).

Este `env.py` importa ÚNICAMENTE `app.motored.database.MotoredBase` (y, a
partir de la Fase 3, `app.motored.models`) como `target_metadata`. NUNCA
debe importar `app.database` ni referenciar el `Base`/metadata de asc360 de
ninguna forma — ambas cadenas de Alembic deben permanecer completamente
desacopladas, incluso si ambas bases de datos terminaran compartiendo la
misma instancia de Postgres.

Comando: `alembic -c alembic_motored.ini upgrade head`
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import settings
from app.motored.database import MotoredBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = MotoredBase.metadata

config.set_main_option("sqlalchemy.url", settings.MOTORED_DATABASE_URL)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_motored",
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version_motored",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
