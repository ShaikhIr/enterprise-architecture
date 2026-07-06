"""
Migration smoke test for the LACM master tables (task 15.5).

Verifies that the Alembic migration chain (including
``f3a4b5c6d7e8_create_master_tables``) applies cleanly on a fresh database and
that a subsequent downgrade removes every master object again, then re-applies
without error. This exercises the full upgrade/downgrade round-trip rather than
just the final schema.

The migration ``env.py`` always reads ``settings.DATABASE_URL`` for its
connection target, so the test points it at an isolated throwaway database by
patching that single setting. Alembic's command API drives its own event loop
(``asyncio.run`` inside ``run_migrations_online``), therefore these tests are
intentionally synchronous.

Requirements: 1.1, 3.1, 6.1, 8.1, 9.1, 10.1, 11.1, 16.1
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

import src.config.settings as settings_module

# Tables created by the master migration (Req 1.1, 6.1, 8.1, 9.1, 10.1, 11.1, 16.1).
MASTER_TABLES = {
    "entities",
    "vendors",
    "customers",
    "product_masters",
    "product_details",
    "agreements",
    "vendor_customer_mappings",
    "invoice_headers",
    "invoice_lines",
}

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_MIGRATIONS_DIR = _BACKEND_ROOT / "src" / "infrastructure" / "database" / "migrations"


def _make_alembic_config() -> Config:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    # Use absolute script location so the test is independent of the cwd.
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return cfg


def _dsn_from_url(url_str: str) -> dict:
    url = make_url(url_str)
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username,
        "password": url.password,
        "database": url.database,
    }


async def _public_tables(url_str: str) -> set[str]:
    conn = await asyncpg.connect(**_dsn_from_url(url_str))
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        return {r["table_name"] for r in rows}
    finally:
        await conn.close()


async def _column(url_str: str, table: str, column: str) -> asyncpg.Record | None:
    conn = await asyncpg.connect(**_dsn_from_url(url_str))
    try:
        return await conn.fetchrow(
            "SELECT column_name, is_nullable, data_type "
            "FROM information_schema.columns "
            "WHERE table_name = $1 AND column_name = $2",
            table,
            column,
        )
    finally:
        await conn.close()


def test_migration_upgrade_downgrade_round_trip(fresh_database, monkeypatch):
    """`alembic upgrade head` then `downgrade -1` then `upgrade head` all apply cleanly."""
    test_url = fresh_database()
    # env.py reads settings.DATABASE_URL; point the whole chain at the test DB.
    monkeypatch.setattr(settings_module.settings, "DATABASE_URL", test_url)

    cfg = _make_alembic_config()

    # ---- upgrade to head -------------------------------------------------- #
    command.upgrade(cfg, "head")
    tables = asyncio.run(_public_tables(test_url))
    missing = MASTER_TABLES - tables
    assert not missing, f"master tables missing after upgrade: {sorted(missing)}"
    assert "alembic_version" in tables

    # users.entity_id link column exists and is nullable (Req 3.1).
    entity_id_col = asyncio.run(_column(test_url, "users", "entity_id"))
    assert entity_id_col is not None, "users.entity_id column was not created"
    assert entity_id_col["is_nullable"] == "YES"

    # ---- downgrade one revision (removes the master migration) ------------ #
    command.downgrade(cfg, "-1")
    tables_after_down = asyncio.run(_public_tables(test_url))
    still_present = MASTER_TABLES & tables_after_down
    assert not still_present, (
        f"master tables not dropped on downgrade: {sorted(still_present)}"
    )
    assert asyncio.run(_column(test_url, "users", "entity_id")) is None, (
        "users.entity_id should be removed on downgrade"
    )

    # ---- re-apply to head (idempotent / clean re-upgrade) ----------------- #
    command.upgrade(cfg, "head")
    tables_reapplied = asyncio.run(_public_tables(test_url))
    assert MASTER_TABLES <= tables_reapplied
