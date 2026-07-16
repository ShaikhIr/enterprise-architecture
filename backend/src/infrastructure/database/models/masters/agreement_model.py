"""
SQLAlchemy ORM model for the Agreement entity.

Maps the Agreement domain entity to the ``agreements`` table. An Agreement
references a Vendor and a Product Detail and may reference a prior Agreement it
renews. The prior-agreement self-reference uses ``ON DELETE SET NULL`` so that
deleting a superseded agreement nulls the renewal's reference rather than
cascading.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums.masters import AgreementStatus, AgreementType
from src.infrastructure.database.models.base_model import BaseModel


class AgreementModel(BaseModel):
    """Agreement database table mapping."""

    __tablename__ = "agreements"

    vendor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id"),
        nullable=False,
        index=True,
    )
    product_master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_master.id"),
        nullable=False,
        index=True,
    )
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    slab_in_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reduction_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_commission_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )
    min_commission_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )
    credit_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agreement_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgreementType.Original.value
    )
    prior_agreement_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agreements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agreement_document_ref: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgreementStatus.Active.value
    )

    __table_args__ = (
        Index(
            "ix_agreements_vendor_detail_status",
            "vendor_id",
            "product_master_id",
            "status",
        ),
    )
