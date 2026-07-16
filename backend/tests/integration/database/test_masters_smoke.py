"""
Smoke tests for the LACM master ORM models (task 15.5).

Each new master model must create its table with a UUID primary key and the
shared audit columns and round-trip a persisted row. The ``users.entity_id``
link column must exist and be nullable.

These tests build the schema directly from the SQLAlchemy metadata
(``Base.metadata.create_all``) on an isolated throwaway PostgreSQL database,
persist a connected graph of rows in dependency order, then read every row back
in a fresh session to confirm the round-trip and the auto-populated audit
fields.

Requirements: 1.1, 3.1, 6.1, 8.1, 9.1, 10.1, 11.1, 16.1
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.database.models.base_model import Base
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.models.masters.agreement_model import AgreementModel
from src.infrastructure.database.models.masters.customer_model import CustomerModel
from src.infrastructure.database.models.masters.entity_model import EntityModel
from src.infrastructure.database.models.masters.invoice_model import (
    InvoiceHeaderModel,
    InvoiceLineModel,
)
from src.infrastructure.database.models.masters.mapping_model import MappingModel
from src.infrastructure.database.models.masters.product_model import (
    ProductDetailModel,
    ProductMasterModel,
)
from src.infrastructure.database.models.masters.vendor_model import VendorModel

AUDIT_FIELDS = ("created_by", "created_date", "modified_by", "modified_date")


def _suffix() -> str:
    """Short unique suffix so repeated runs never collide on unique columns."""
    return uuid.uuid4().hex[:8]


async def _persist_graph(session: AsyncSession) -> dict[str, tuple[type, uuid.UUID]]:
    """Insert one row per master model in dependency order; return {label: (cls, id)}."""
    s = _suffix()

    entity = EntityModel(
        entity_name=f"Acme Holdings {s}",
        short_code=f"AC{s[:4]}",
        company_code=f"CC{s}",
    )
    session.add(entity)
    await session.flush()

    # A user linked to the entity exercises the users.entity_id FK (Req 3.1).
    user = UserModel(
        username=f"smoke_user_{s}",
        password_hash="hashed-secret",
        entity_id=entity.id,
    )
    session.add(user)
    await session.flush()

    vendor = VendorModel(
        vendor_code=f"VEN{s}",
        vendor_name=f"Vendor {s}",
        vendor_email=f"vendor_{s}@example.com",
        portal_user_id=user.id,
    )
    session.add(vendor)
    await session.flush()

    customer = CustomerModel(
        customer_code=f"CUS{s}",
        customer_name=f"Customer {s}",
    )
    session.add(customer)
    await session.flush()

    product_master = ProductMasterModel(
        basic_material_code=f"BM{s}",
        product_name=f"Product {s}",
    )
    session.add(product_master)
    await session.flush()

    product_detail = ProductDetailModel(
        child_code=f"CH{s}",
        product_master_id=product_master.id,
        mrp=Decimal("100.00"),
        rate=Decimal("80.00"),
        gst_percent=Decimal("18.00"),
    )
    session.add(product_detail)
    await session.flush()

    agreement = AgreementModel(
        vendor_id=vendor.id,
        product_master_id=product_detail.id,
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
        slab_in_days=30,
        reduction_percent=Decimal("5.00"),
        max_commission_percent=Decimal("10.00"),
        min_commission_percent=Decimal("2.00"),
        credit_days=45,
    )
    session.add(agreement)
    await session.flush()

    mapping = MappingModel(
        vendor_id=vendor.id,
        customer_id=customer.id,
        validity_from=date(2024, 1, 1),
        validity_to=date(2024, 12, 31),
    )
    session.add(mapping)
    await session.flush()

    header = InvoiceHeaderModel(
        invoice_number=f"INV{s}",
        invoice_date=date(2024, 3, 1),
        vendor_id=vendor.id,
        customer_id=customer.id,
        bill_amount_excl_gst=Decimal("1000.00"),
    )
    session.add(header)
    await session.flush()

    line = InvoiceLineModel(
        invoice_header_id=header.id,
        product_master_id=product_detail.id,
        quantity=Decimal("10.000"),
        line_amount=Decimal("800.00"),
    )
    session.add(line)
    await session.flush()

    await session.commit()

    return {
        "EntityModel": (EntityModel, entity.id),
        "VendorModel": (VendorModel, vendor.id),
        "CustomerModel": (CustomerModel, customer.id),
        "ProductMasterModel": (ProductMasterModel, product_master.id),
        "ProductDetailModel": (ProductDetailModel, product_detail.id),
        "AgreementModel": (AgreementModel, agreement.id),
        "MappingModel": (MappingModel, mapping.id),
        "InvoiceHeaderModel": (InvoiceHeaderModel, header.id),
        "InvoiceLineModel": (InvoiceLineModel, line.id),
    }


async def _run_roundtrip(url: str) -> None:
    engine = create_async_engine(url, poolclass=None)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            persisted = await _persist_graph(session)

        # Read every row back in a fresh session and verify the round-trip.
        async with factory() as session:
            for label, (model_cls, row_id) in persisted.items():
                row = await session.get(model_cls, row_id)
                assert row is not None, f"{label} row {row_id} did not round-trip"
                # UUID primary key.
                assert isinstance(row.id, uuid.UUID), (
                    f"{label}.id is not a UUID: {row.id!r}"
                )
                assert row.id == row_id
                # Audit columns auto-populated by AuditMixin defaults.
                for field in AUDIT_FIELDS:
                    assert getattr(row, field) is not None, (
                        f"{label}.{field} was not populated"
                    )
                assert row.created_by == "system"
                assert row.modified_by == "system"
    finally:
        await engine.dispose()


async def _run_entity_id_nullable(url: str) -> None:
    """A user with no entity_id persists, proving the column is nullable (Req 3.1)."""
    engine = create_async_engine(url, poolclass=None)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        s = _suffix()
        async with factory() as session:
            user = UserModel(
                username=f"no_entity_user_{s}",
                password_hash="hashed-secret",
                entity_id=None,
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        async with factory() as session:
            stored = await session.get(UserModel, user_id)
            assert stored is not None
            assert stored.entity_id is None
    finally:
        await engine.dispose()


def test_master_models_create_tables_and_round_trip(fresh_database):
    """Each master model creates its table (UUID PK + audit columns) and round-trips."""
    url = fresh_database()
    asyncio.run(_run_roundtrip(url))


def test_users_entity_id_exists_and_is_nullable(fresh_database):
    """users.entity_id is declared nullable and accepts NULL (Req 3.1)."""
    # Static guarantee from the ORM mapping.
    assert UserModel.__table__.c.entity_id.nullable is True
    # Behavioural guarantee against a real database.
    url = fresh_database()
    asyncio.run(_run_entity_id_nullable(url))
