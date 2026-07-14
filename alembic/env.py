from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import get_settings
from app.db import Base
from app.models import snapshots  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
SNAPSHOT_ALEMBIC_VERSION_TABLE = "snapshot_service_alembic_version"


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        version_table=SNAPSHOT_ALEMBIC_VERSION_TABLE,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_snapshot_tables,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_settings().database_url
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=SNAPSHOT_ALEMBIC_VERSION_TABLE,
            include_name=include_snapshot_tables,
        )
        with context.begin_transaction():
            context.run_migrations()


def include_snapshot_tables(name, type_, parent_names):
    if type_ == "table":
        return name in {
            "snapshot_runs",
            "wallet_snapshots",
            "chain_snapshots",
            "snapshot_balance_snapshots",
            SNAPSHOT_ALEMBIC_VERSION_TABLE,
        }
    return True


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
