"""
Shared fixtures for database integration / smoke / migration tests.

These tests need a *real* PostgreSQL server because the master ORM models and the
Alembic migration use PostgreSQL-specific features (``postgresql.UUID`` columns
and functional ``lower(trim(...))`` unique indexes) that cannot be exercised on
SQLite. Each test runs against its own freshly-created, throwaway database so the
schema-management approaches used by the different tests (Alembic vs.
``metadata.create_all``) never collide and nothing leaks into the dev database.

The connection target is derived from ``settings.DATABASE_URL`` (the same
configuration the application uses). If no PostgreSQL server is reachable the
fixtures ``pytest.skip`` with a clear message rather than failing.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from src.config.settings import settings


def _admin_dsn(database: str) -> dict:
    """Build asyncpg connection kwargs for the given maintenance database."""
    url = make_url(settings.DATABASE_URL)
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username,
        "password": url.password,
        "database": database,
    }


async def _server_reachable() -> bool:
    try:
        conn = await asyncpg.connect(**_admin_dsn("postgres"))
        await conn.close()
        return True
    except Exception:
        return False


async def _create_database(name: str) -> None:
    conn = await asyncpg.connect(**_admin_dsn("postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(name: str) -> None:
    conn = await asyncpg.connect(**_admin_dsn("postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


def _test_db_url(name: str) -> str:
    """Return an asyncpg SQLAlchemy URL pointing at the throwaway database."""
    # ``render_as_string(hide_password=False)`` is required: ``str(url)`` masks
    # the password as ``***``, which would otherwise be sent to PostgreSQL
    # verbatim and fail authentication.
    return make_url(settings.DATABASE_URL).set(database=name).render_as_string(
        hide_password=False
    )


@pytest.fixture
def fresh_database() -> Callable[[], str]:
    """Provide a factory creating an isolated, empty PostgreSQL database.

    Yields a callable returning the SQLAlchemy URL of a freshly created
    database. The database is dropped during teardown. Skips the test when no
    PostgreSQL server is reachable.
    """
    if not asyncio.run(_server_reachable()):
        pytest.skip(
            "PostgreSQL server is not reachable at the configured DATABASE_URL; "
            "skipping database-backed smoke/migration tests."
        )

    created: list[str] = []

    def _make() -> str:
        name = f"lacm_masters_test_{uuid.uuid4().hex[:12]}"
        asyncio.run(_create_database(name))
        created.append(name)
        return _test_db_url(name)

    yield _make

    for name in created:
        asyncio.run(_drop_database(name))
