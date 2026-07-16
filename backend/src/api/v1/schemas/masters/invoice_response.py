"""
Invoice Master response schemas (Pydantic v2).

Maps the :class:`InvoiceHeaderEntity` aggregate (and its
:class:`InvoiceLineEntity` children) to the API representation, exposing the
persisted header fields, denormalized vendor/customer names, the nested lines,
and the standard audit fields.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from src.domain.entities.masters.invoice import (
    InvoiceHeaderEntity,
    InvoiceLineEntity,
)


class InvoiceLineResponse(BaseModel):
    """API representation of a single Invoice Line."""

    id: UUID
    invoice_header_id: UUID | None = None
    product_master_id: UUID | None = None
    product_child_code: str | None = None
    product_name: str | None = None
    quantity: Decimal | None = None
    line_amount: Decimal | None = None
    vat_gst_amount: Decimal | None = None
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(
        cls,
        entity: InvoiceLineEntity,
        product_child_code: str | None = None,
        product_name: str | None = None,
    ) -> "InvoiceLineResponse":
        """Build a response DTO from a domain :class:`InvoiceLineEntity`."""
        return cls(
            id=entity.id,
            invoice_header_id=entity.invoice_header_id,
            product_master_id=entity.product_master_id,
            product_child_code=product_child_code,
            product_name=product_name,
            quantity=entity.quantity,
            line_amount=entity.line_amount,
            vat_gst_amount=entity.vat_gst_amount,
            created_by=entity.created_by,
            created_date=entity.created_date,
            modified_by=entity.modified_by,
            modified_date=entity.modified_date,
        )


class InvoiceResponse(BaseModel):
    """API representation of an Invoice Header with its lines."""

    id: UUID
    invoice_number: str
    invoice_date: date | None = None
    vendor_id: UUID | None = None
    vendor_name: str | None = None
    customer_id: UUID | None = None
    customer_name: str | None = None
    entity_id: UUID | None = None
    bill_amount_excl_gst: Decimal
    bill_amount_incl_tax: Decimal | None = None
    amount_deducted: Decimal
    tds_value: Decimal
    due_date: date | None = None
    payment_clearing_date: date | None = None
    sap_clearing_document_no: str | None = None
    invoice_status: str
    # Expose status under a frontend-friendly key as well
    status: str | None = None
    lines: list[InvoiceLineResponse]
    created_by: str
    created_date: datetime
    modified_by: str
    modified_date: datetime

    @classmethod
    def from_entity(
        cls,
        entity: InvoiceHeaderEntity,
        vendor_name: str | None = None,
        customer_name: str | None = None,
        product_lookup: dict | None = None,
    ) -> "InvoiceResponse":
        """Build a response DTO from a domain :class:`InvoiceHeaderEntity`.

        ``product_lookup`` maps product_master_id (UUID) →
        ``(child_code, product_name)`` tuple for denormalising line items.
        """
        status_value = entity.invoice_status.value
        lookup = product_lookup or {}
        return cls(
            id=entity.id,
            invoice_number=entity.invoice_number,
            invoice_date=entity.invoice_date,
            vendor_id=entity.vendor_id,
            vendor_name=vendor_name,
            customer_id=entity.customer_id,
            customer_name=customer_name,
            entity_id=entity.entity_id,
            bill_amount_excl_gst=entity.bill_amount_excl_gst,
            bill_amount_incl_tax=entity.bill_amount_incl_tax,
            amount_deducted=entity.amount_deducted,
            tds_value=entity.tds_value,
            due_date=entity.due_date,
            payment_clearing_date=entity.payment_clearing_date,
            sap_clearing_document_no=entity.sap_clearing_document_no,
            invoice_status=status_value,
            status=status_value,
            lines=[
                InvoiceLineResponse.from_entity(
                    line,
                    product_child_code=lookup.get(line.product_master_id, (None, None))[0],
                    product_name=lookup.get(line.product_master_id, (None, None))[1],
                )
                for line in entity.lines
            ],
            created_by=entity.created_by,
            created_date=entity.created_date,
            modified_by=entity.modified_by,
            modified_date=entity.modified_date,
        )
