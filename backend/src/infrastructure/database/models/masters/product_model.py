"""
SQLAlchemy ORM model for the Product Master entity.

The former two-level hierarchy (product_masters + product_details) has been
collapsed into a single ``product_master`` table. The table now carries both
the base-product identity fields (``basic_material_code``, ``product_name``)
that were previously on ``product_masters``, and the SKU/child-variant fields
(``child_code``, etc.) that were previously on ``product_details``.

The separate ``product_masters`` table and ``ProductMasterModel`` class have
been removed.
"""

from decimal import Decimal

from sqlalchemy import String, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums.masters import ProductStatus
from src.infrastructure.database.models.base_model import BaseModel


class ProductMasterModel(BaseModel):
    """Product Master database table mapping (merged product_details table)."""

    __tablename__ = "product_master"

    # ── Fields previously on product_masters ─────────────────────────────
    basic_material_code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Fields previously on product_details ─────────────────────────────
    child_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    variant_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsn_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pack_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gst_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProductStatus.Active.value
    )
