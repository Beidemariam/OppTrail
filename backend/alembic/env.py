"""Alembic environment for OppTrail (ADR 0002).

No ORM is adopted here: `target_metadata` stays `None` and every revision is
written as explicit SQL. Alembic provides the version table, the ordering and
the batch-rebuild support SQLite needs for column changes, which is all ADR 0002
asked of it.
"""

from sqlalchemy import create_engine, pool

from alembic import context
from app.database import sqlalchemy_url

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=sqlalchemy_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(sqlalchemy_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
