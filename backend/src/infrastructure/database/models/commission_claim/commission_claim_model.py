"""
SQLAlchemy ORM models for Commission Claim Management.

Defines four tables:
- claim_headers       — top-level claim aggregate (Requirements 1.1, 4.1)
- claim_lines         — per-invoice commission rows (Requirements 4.1, 3.10)
- claim_audit_logs    — append-only audit trail (Requirements 14.1, 14.2, 14.3)
- claim_number_sequences — financial-year sequence counter (Requirements 13.1–13.4)
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class ClaimHeaderModel(BaseModel):
    """
    Claim Header — top-level aggregate for a commission claim.

    One header owns many ClaimLines (cascade delete-orphan) and many
    ClaimAuditLogModel entries.  Status, vendor link, and header totals
    are maintained here.

    Table: claim_headers
    Requirements: 1.1, 4.1, 13.3
    """

    __tablename__ = "claim_headers"

    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id"),
        nullable=True,
        index=True,
    )
    claim_number: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Draft", index=True
    )
    workflow_instance_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Header totals — persisted, recalculated on every line change (Req 4.1)
    total_claim_amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0")
    )
    total_commission_amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0")
    )
    total_gst_amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0")
    )
    total_tds_amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0")
    )
    total_ld_amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0")
    )
    total_retention_amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0")
    )

    # Post-closure fields (Req 9.2, 9.3, 9.5)
    gstn_verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Pending"
    )
    gst_invoice_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    gst_invoice_upload_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    sap_p2p_booking_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # Relationships
    lines: Mapped[list["ClaimLineModel"]] = relationship(
        "ClaimLineModel",
        back_populates="header",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    audit_logs: Mapped[list["ClaimAuditLogModel"]] = relationship(
        "ClaimAuditLogModel",
        back_populates="header",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_claim_headers_vendor_status", "vendor_id", "status"),
    )


class ClaimLineModel(BaseModel):
    """
    Claim Line — single invoice-level row within a Claim Header.

    Stores all invoice-sourced inputs and all 7 commission formula outputs.
    Cascades delete from parent header via ON DELETE CASCADE at the DB level.

    Table: claim_lines
    Unique constraint: uq_claim_line_invoice (claim_header_id, invoice_header_id)
    Requirements: 3.10, 4.1
    """

    __tablename__ = "claim_lines"

    claim_header_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_headers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_header_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice_headers.id"),
        nullable=False,
        index=True,
    )
    product_master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_master.id"),
        nullable=False,
    )
    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=False,
    )

    # Invoice-sourced input fields
    bill_amount_excl_gst: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    amount_deducted: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    tds_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    ld_charges: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    retention_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )

    # 7-step formula outputs — all persisted for audit (Req 3.10)
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    commission_payable_base: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_clearing_date: Mapped[date] = mapped_column(Date, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applicable_commission_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=Decimal("0")
    )
    commission_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    gst_on_commission: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    final_line_claim_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )

    # POD & remarks
    pod_document_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    remarks: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Relationship back to header
    header: Mapped["ClaimHeaderModel"] = relationship(
        "ClaimHeaderModel",
        back_populates="lines",
    )

    __table_args__ = (
        UniqueConstraint(
            "claim_header_id",
            "invoice_header_id",
            "product_master_id",
            name="uq_claim_line_invoice_product",
        ),
        Index("ix_claim_lines_header", "claim_header_id"),
    )


class ClaimAuditLogModel(BaseModel):
    """
    Claim Audit Log — append-only record of every action on a claim.

    No update or delete endpoints are exposed for this model (Req 14.3).
    ``field_changes`` stores per-field old/new diffs for field-edit events.

    Table: claim_audit_logs
    Requirements: 14.1, 14.2, 14.3
    """

    __tablename__ = "claim_audit_logs"

    claim_header_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_headers.id"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_username: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    workflow_step_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB dict of {"field_name": {"old": ..., "new": ...}} for field-edit events
    field_changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationship back to header (lazy select — audit trail is paged, not eager)
    header: Mapped["ClaimHeaderModel"] = relationship(
        "ClaimHeaderModel",
        back_populates="audit_logs",
    )

    __table_args__ = (
        Index(
            "ix_claim_audit_logs_header_ts",
            "claim_header_id",
            "timestamp_utc",
        ),
    )


class ClaimNumberSequenceModel(BaseModel):
    """
    Claim Number Sequence — one row per Indian financial year.

    ``last_sequence`` is incremented under a SELECT … FOR UPDATE advisory lock
    so concurrent submissions in the same financial year receive unique numbers.

    Table: claim_number_sequences
    Requirements: 13.1, 13.2, 13.3, 13.4
    """

    __tablename__ = "claim_number_sequences"

    # e.g. "2025-26" — one row per financial year
    financial_year: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False
    )
    last_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    __table_args__ = (
        Index("ix_claim_number_seq_fy", "financial_year", unique=True),
    )
