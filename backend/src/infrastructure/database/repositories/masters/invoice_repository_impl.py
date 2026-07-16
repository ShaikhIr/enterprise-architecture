"""
Invoice repository implementation (Adapter).

Implements :class:`IInvoiceRepository` using SQLAlchemy async, covering the
Invoice Header / Invoice Line aggregate. Header creation persists the header and
all of its lines atomically; header deletion cascades to lines via the
``ON DELETE CASCADE`` foreign key plus the ORM ``delete-orphan`` relationship.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)
from src.domain.enums.masters import InvoiceStatus
from src.domain.repositories.masters.invoice_repository import IInvoiceRepository
from src.infrastructure.database.models.masters.customer_model import CustomerModel
from src.infrastructure.database.models.masters.invoice_model import (
    InvoiceHeaderModel,
    InvoiceLineModel,
)
from src.infrastructure.database.models.masters.vendor_model import VendorModel


class InvoiceRepositoryImpl(IInvoiceRepository):
    """Concrete implementation of invoice persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, header: InvoiceHeaderEntity, lines: list[InvoiceLineEntity]
    ) -> InvoiceHeaderEntity:
        model = InvoiceHeaderModel(
            id=header.id,
            invoice_number=header.invoice_number,
            invoice_date=header.invoice_date,
            vendor_id=header.vendor_id,
            customer_id=header.customer_id,
            entity_id=header.entity_id,
            bill_amount_excl_gst=header.bill_amount_excl_gst,
            bill_amount_incl_tax=header.bill_amount_incl_tax,
            amount_deducted=header.amount_deducted,
            tds_value=header.tds_value,
            due_date=header.due_date,
            payment_clearing_date=header.payment_clearing_date,
            sap_clearing_document_no=header.sap_clearing_document_no,
            invoice_status=str(header.invoice_status),
            created_by=header.created_by,
            modified_by=header.modified_by,
        )
        model.lines = [
            InvoiceLineModel(
                id=line.id,
                invoice_header_id=header.id,
                product_master_id=line.product_master_id,
                quantity=line.quantity,
                line_amount=line.line_amount,
                vat_gst_amount=line.vat_gst_amount,
                created_by=line.created_by,
                modified_by=line.modified_by,
            )
            for line in lines
        ]
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model, attribute_names=["lines"])
        return self._header_to_entity(model)

    async def get_by_id(self, header_id: UUID) -> InvoiceHeaderEntity | None:
        stmt = (
            select(InvoiceHeaderModel)
            .options(selectinload(InvoiceHeaderModel.lines))
            .where(InvoiceHeaderModel.id == header_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._header_to_entity(model) if model else None

    async def get_by_invoice_number(
        self, invoice_number: str
    ) -> InvoiceHeaderEntity | None:
        stmt = (
            select(InvoiceHeaderModel)
            .options(selectinload(InvoiceHeaderModel.lines))
            .where(InvoiceHeaderModel.invoice_number == invoice_number)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._header_to_entity(model) if model else None

    async def update(self, header: InvoiceHeaderEntity) -> InvoiceHeaderEntity:
        stmt = (
            select(InvoiceHeaderModel)
            .options(selectinload(InvoiceHeaderModel.lines))
            .where(InvoiceHeaderModel.id == header.id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Invoice Header with id {header.id} not found")

        model.invoice_number = header.invoice_number
        model.invoice_date = header.invoice_date
        model.vendor_id = header.vendor_id
        model.customer_id = header.customer_id
        model.entity_id = header.entity_id
        model.bill_amount_excl_gst = header.bill_amount_excl_gst
        model.bill_amount_incl_tax = header.bill_amount_incl_tax
        model.amount_deducted = header.amount_deducted
        model.tds_value = header.tds_value
        model.due_date = header.due_date
        model.payment_clearing_date = header.payment_clearing_date
        model.sap_clearing_document_no = header.sap_clearing_document_no
        model.invoice_status = str(header.invoice_status)
        model.modified_by = header.modified_by
        model.modified_date = header.modified_date

        await self._session.flush()
        await self._session.refresh(model, attribute_names=["lines"])
        return self._header_to_entity(model)

    async def delete(self, header_id: UUID) -> None:
        stmt = select(InvoiceHeaderModel).where(InvoiceHeaderModel.id == header_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    async def list(
        self, skip: int = 0, limit: int = 20
    ) -> list[InvoiceHeaderEntity]:
        stmt = (
            select(InvoiceHeaderModel)
            .options(selectinload(InvoiceHeaderModel.lines))
            .order_by(InvoiceHeaderModel.created_date, InvoiceHeaderModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._header_to_entity(m) for m in models]

    async def list_with_names(
        self,
        skip: int = 0,
        limit: int = 20,
        invoice_number: str | None = None,
        vendor_name: str | None = None,
        customer_name: str | None = None,
        invoice_status: str | None = None,
        vendor_id: str | None = None,
        entity_id: str | None = None,
    ) -> list[tuple[InvoiceHeaderEntity, str | None, str | None]]:
        """Return invoice headers with denormalized vendor_name / customer_name."""
        stmt = (
            select(
                InvoiceHeaderModel,
                VendorModel.vendor_name.label("vendor_name"),
                CustomerModel.customer_name.label("customer_name"),
            )
            .options(selectinload(InvoiceHeaderModel.lines))
            .outerjoin(VendorModel, InvoiceHeaderModel.vendor_id == VendorModel.id)
            .outerjoin(CustomerModel, InvoiceHeaderModel.customer_id == CustomerModel.id)
        )
        if invoice_number:
            stmt = stmt.where(
                InvoiceHeaderModel.invoice_number.ilike(f"%{invoice_number}%")
            )
        if vendor_name:
            stmt = stmt.where(
                VendorModel.vendor_name.ilike(f"%{vendor_name}%")
            )
        if customer_name:
            stmt = stmt.where(
                CustomerModel.customer_name.ilike(f"%{customer_name}%")
            )
        if invoice_status:
            stmt = stmt.where(
                InvoiceHeaderModel.invoice_status == invoice_status
            )
        if vendor_id:
            stmt = stmt.where(
                InvoiceHeaderModel.vendor_id == vendor_id
            )
        if entity_id:
            stmt = stmt.where(
                InvoiceHeaderModel.entity_id == entity_id
            )
        stmt = stmt.order_by(
            InvoiceHeaderModel.created_date.desc(), InvoiceHeaderModel.id
        ).offset(skip).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            (self._header_to_entity(row[0]), row[1], row[2])
            for row in rows
        ]

    async def count(self) -> int:
        stmt = select(func.count()).select_from(InvoiceHeaderModel)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_filtered(
        self,
        invoice_number: str | None = None,
        vendor_name: str | None = None,
        customer_name: str | None = None,
        invoice_status: str | None = None,
        vendor_id: str | None = None,
        entity_id: str | None = None,
    ) -> int:
        """Count invoice headers matching the given filters."""
        stmt = (
            select(func.count())
            .select_from(InvoiceHeaderModel)
            .outerjoin(VendorModel, InvoiceHeaderModel.vendor_id == VendorModel.id)
            .outerjoin(CustomerModel, InvoiceHeaderModel.customer_id == CustomerModel.id)
        )
        if invoice_number:
            stmt = stmt.where(
                InvoiceHeaderModel.invoice_number.ilike(f"%{invoice_number}%")
            )
        if vendor_name:
            stmt = stmt.where(
                VendorModel.vendor_name.ilike(f"%{vendor_name}%")
            )
        if customer_name:
            stmt = stmt.where(
                CustomerModel.customer_name.ilike(f"%{customer_name}%")
            )
        if invoice_status:
            stmt = stmt.where(
                InvoiceHeaderModel.invoice_status == invoice_status
            )
        if vendor_id:
            stmt = stmt.where(
                InvoiceHeaderModel.vendor_id == vendor_id
            )
        if entity_id:
            stmt = stmt.where(
                InvoiceHeaderModel.entity_id == entity_id
            )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_lines_by_ids(
        self, line_ids: list[UUID]
    ) -> list[InvoiceLineEntity]:
        if not line_ids:
            return []
        stmt = select(InvoiceLineModel).where(InvoiceLineModel.id.in_(line_ids))
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._line_to_entity(m) for m in models]

    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        stmt = select(InvoiceHeaderModel.id).where(
            InvoiceHeaderModel.invoice_number == invoice_number
        )
        if exclude_id is not None:
            stmt = stmt.where(InvoiceHeaderModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def exists_by_id(self, header_id: UUID) -> bool:
        stmt = select(InvoiceHeaderModel.id).where(
            InvoiceHeaderModel.id == header_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def exists_for_customer(self, customer_id: UUID) -> bool:
        stmt = select(InvoiceHeaderModel.id).where(
            InvoiceHeaderModel.customer_id == customer_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def exists_for_vendor(self, vendor_id: UUID) -> bool:
        stmt = select(InvoiceHeaderModel.id).where(
            InvoiceHeaderModel.vendor_id == vendor_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # --- Mappers ---

    @staticmethod
    def _header_to_entity(model: InvoiceHeaderModel) -> InvoiceHeaderEntity:
        return InvoiceHeaderEntity(
            id=model.id,
            invoice_number=model.invoice_number,
            invoice_date=model.invoice_date,
            vendor_id=model.vendor_id,
            customer_id=model.customer_id,
            entity_id=model.entity_id,
            bill_amount_excl_gst=model.bill_amount_excl_gst,
            bill_amount_incl_tax=model.bill_amount_incl_tax,
            amount_deducted=model.amount_deducted,
            tds_value=model.tds_value,
            due_date=model.due_date,
            payment_clearing_date=model.payment_clearing_date,
            sap_clearing_document_no=model.sap_clearing_document_no,
            invoice_status=InvoiceStatus(model.invoice_status),
            lines=[
                InvoiceRepositoryImpl._line_to_entity(line)
                for line in model.lines
            ],
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )

    @staticmethod
    def _line_to_entity(model: InvoiceLineModel) -> InvoiceLineEntity:
        return InvoiceLineEntity(
            id=model.id,
            invoice_header_id=model.invoice_header_id,
            product_master_id=model.product_master_id,
            quantity=model.quantity,
            line_amount=model.line_amount,
            vat_gst_amount=model.vat_gst_amount,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
