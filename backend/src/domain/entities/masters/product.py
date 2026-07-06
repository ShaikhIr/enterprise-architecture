"""
Product Master domain entity.

The former two-level hierarchy (ProductMasterEntity + ProductDetailEntity) has
been collapsed into a single ``ProductMasterEntity`` that holds both the
base-product identity fields (``basic_material_code``, ``product_name``) and
the SKU/variant fields (``child_code``, etc.).

Downstream entities (agreements, invoices) reference ``ProductMasterEntity``
directly via its ``id``.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from src.domain.entities.base_entity import BaseEntity
from src.domain.enums.masters import ProductStatus


@dataclass
class ProductMasterEntity(BaseEntity):
    """
    Product Master aggregate root (merged product_details).

    Business Rules:
    - Child Code must be unique (enforced at repository level).
    - Basic Material Code identifies the base molecule/formulation.
    - MRP and Rate must be >= 0; GST percent must be within 0-100.
    """

    # ── Base-product identity (previously on the old ProductMasterEntity) ─
    basic_material_code: str = field(default="")
    product_name: str = field(default="")

    # ── SKU/variant fields (previously on ProductDetailEntity) ────────────
    child_code: str = field(default="")
    variant_description: str | None = field(default=None)
    hsn_code: str | None = field(default=None)
    pack_size: str | None = field(default=None)
    unit_of_measure: str | None = field(default=None)
    mrp: Decimal | None = field(default=None)
    rate: Decimal | None = field(default=None)
    gst_percent: Decimal | None = field(default=None)
    status: ProductStatus = field(default=ProductStatus.Active)
