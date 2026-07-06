"""
Product Master application service.

The former two-level hierarchy (ProductMaster + ProductDetail) has been
collapsed into a single ``ProductMasterEntity``. This service provides CRUD
operations for that merged entity.

Partial updates use a dedicated ``UNSET`` sentinel so that "field not supplied"
is distinguished from "field explicitly set to null".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.product import ProductMasterEntity
from src.domain.entities.user import User
from src.domain.enums.masters import ProductStatus
from src.domain.repositories.masters.product_repository import IProductRepository

# ─── Field length limits (aligned with ORM column sizes) ─────────────────────
_MAX_BASIC_MATERIAL_CODE_LEN: Final[int] = 50
_MAX_PRODUCT_NAME_LEN: Final[int] = 255
_MAX_CHILD_CODE_LEN: Final[int] = 50
_MAX_HSN_CODE_LEN: Final[int] = 20
_MAX_PACK_SIZE_LEN: Final[int] = 50
_MAX_UNIT_OF_MEASURE_LEN: Final[int] = 20

# ─── GST percentage bounds ────────────────────────────────────────────────────
_MIN_GST_PERCENT: Final[Decimal] = Decimal("0")
_MAX_GST_PERCENT: Final[Decimal] = Decimal("100")


class _UnsetType:
    """Sentinel marking an update field that was not supplied at all."""

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover
        return "UNSET"

    def __bool__(self) -> bool:  # pragma: no cover
        return False


UNSET: Final[_UnsetType] = _UnsetType()


# ─── Input dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProductMasterCreateInput:
    """Payload for creating a Product Master."""

    basic_material_code: str
    product_name: str
    child_code: str
    variant_description: str | None = None
    hsn_code: str | None = None
    pack_size: str | None = None
    unit_of_measure: str | None = None
    mrp: Decimal | None = None
    rate: Decimal | None = None
    gst_percent: Decimal | None = None
    status: ProductStatus | None = None


@dataclass(frozen=True)
class ProductMasterUpdateInput:
    """Partial-update payload for a Product Master.

    Each field defaults to :data:`UNSET`; only supplied fields are applied.
    """

    basic_material_code: str | _UnsetType = UNSET
    product_name: str | _UnsetType = UNSET
    child_code: str | _UnsetType = UNSET
    variant_description: str | None | _UnsetType = UNSET
    hsn_code: str | None | _UnsetType = UNSET
    pack_size: str | None | _UnsetType = UNSET
    unit_of_measure: str | None | _UnsetType = UNSET
    mrp: Decimal | None | _UnsetType = UNSET
    rate: Decimal | None | _UnsetType = UNSET
    gst_percent: Decimal | None | _UnsetType = UNSET
    status: ProductStatus | _UnsetType = UNSET


# ─── Service ──────────────────────────────────────────────────────────────────


class ProductService:
    """Application service for Product Master management."""

    def __init__(
        self, session: AsyncSession, product_repo: IProductRepository
    ) -> None:
        self._session = session
        self._product_repo = product_repo

    async def create(
        self, data: ProductMasterCreateInput, actor: User
    ) -> ProductMasterEntity:
        """Validate and persist a new Product Master."""
        self._validate_basic_material_code(data.basic_material_code)
        self._validate_product_name(data.product_name)
        self._validate_child_code(data.child_code)
        self._validate_optional_lengths(
            hsn_code=data.hsn_code,
            pack_size=data.pack_size,
            unit_of_measure=data.unit_of_measure,
        )
        self._validate_mrp(data.mrp)
        self._validate_rate(data.rate)
        self._validate_gst_percent(data.gst_percent)

        if await self._product_repo.exists_by_child_code(data.child_code):
            raise MasterConflictError(
                f"A Product Master with Child Code '{data.child_code}' already exists"
            )

        product = ProductMasterEntity(
            id=uuid4(),
            basic_material_code=data.basic_material_code,
            product_name=data.product_name,
            child_code=data.child_code,
            variant_description=data.variant_description,
            hsn_code=data.hsn_code,
            pack_size=data.pack_size,
            unit_of_measure=data.unit_of_measure,
            mrp=data.mrp,
            rate=data.rate,
            gst_percent=data.gst_percent,
            status=ProductStatus.Active if data.status is None else data.status,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._product_repo.create(product)

    async def get(self, product_id: UUID) -> ProductMasterEntity:
        """Return a Product Master by ID or raise not-found."""
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise MasterNotFoundError("Product Master", product_id)
        return product

    async def update(
        self, product_id: UUID, patch: ProductMasterUpdateInput, actor: User
    ) -> ProductMasterEntity:
        """Apply a partial update to a Product Master."""
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise MasterNotFoundError("Product Master", product_id)

        if not isinstance(patch.basic_material_code, _UnsetType):
            self._validate_basic_material_code(patch.basic_material_code)
            product.basic_material_code = patch.basic_material_code

        if not isinstance(patch.product_name, _UnsetType):
            self._validate_product_name(patch.product_name)
            product.product_name = patch.product_name

        if not isinstance(patch.child_code, _UnsetType):
            self._validate_child_code(patch.child_code)
            if await self._product_repo.exists_by_child_code(
                patch.child_code, exclude_id=product_id
            ):
                raise MasterConflictError(
                    f"A Product Master with Child Code '{patch.child_code}' already exists"
                )
            product.child_code = patch.child_code

        if not isinstance(patch.variant_description, _UnsetType):
            product.variant_description = patch.variant_description

        if not isinstance(patch.hsn_code, _UnsetType):
            self._validate_length("hsn_code", patch.hsn_code, _MAX_HSN_CODE_LEN)
            product.hsn_code = patch.hsn_code

        if not isinstance(patch.pack_size, _UnsetType):
            self._validate_length("pack_size", patch.pack_size, _MAX_PACK_SIZE_LEN)
            product.pack_size = patch.pack_size

        if not isinstance(patch.unit_of_measure, _UnsetType):
            self._validate_length(
                "unit_of_measure", patch.unit_of_measure, _MAX_UNIT_OF_MEASURE_LEN
            )
            product.unit_of_measure = patch.unit_of_measure

        if not isinstance(patch.mrp, _UnsetType):
            self._validate_mrp(patch.mrp)
            product.mrp = patch.mrp

        if not isinstance(patch.rate, _UnsetType):
            self._validate_rate(patch.rate)
            product.rate = patch.rate

        if not isinstance(patch.gst_percent, _UnsetType):
            self._validate_gst_percent(patch.gst_percent)
            product.gst_percent = patch.gst_percent

        if not isinstance(patch.status, _UnsetType):
            product.status = patch.status

        product.mark_modified(actor.username)
        return await self._product_repo.update(product)

    async def list(
        self, skip: int = 0, limit: int = 20
    ) -> tuple[list[ProductMasterEntity], int]:
        """Return a page of Product Masters and the total count."""
        items = await self._product_repo.list(skip=skip, limit=limit)
        total = await self._product_repo.count()
        return items, total

    async def delete(self, product_id: UUID, actor: User) -> None:
        """Delete a Product Master by ID."""
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise MasterNotFoundError("Product Master", product_id)
        await self._product_repo.delete(product_id)

    # ─── Validation helpers ───────────────────────────────────────────────

    @staticmethod
    def _validate_basic_material_code(value: object) -> None:
        if not isinstance(value, str) or value.strip() == "":
            raise MasterValidationError(
                "basic_material_code",
                "Basic Material Code is required and must not be empty",
            )
        if len(value) > _MAX_BASIC_MATERIAL_CODE_LEN:
            raise MasterValidationError(
                "basic_material_code",
                f"Basic Material Code must not exceed {_MAX_BASIC_MATERIAL_CODE_LEN} characters",
            )

    @staticmethod
    def _validate_product_name(value: object) -> None:
        if not isinstance(value, str) or value.strip() == "":
            raise MasterValidationError(
                "product_name", "Product Name is required and must not be empty"
            )
        if len(value) > _MAX_PRODUCT_NAME_LEN:
            raise MasterValidationError(
                "product_name",
                f"Product Name must not exceed {_MAX_PRODUCT_NAME_LEN} characters",
            )

    @staticmethod
    def _validate_child_code(value: object) -> None:
        if not isinstance(value, str) or value.strip() == "":
            raise MasterValidationError(
                "child_code", "Child Code is required and must not be empty"
            )
        if len(value) > _MAX_CHILD_CODE_LEN:
            raise MasterValidationError(
                "child_code",
                f"Child Code must not exceed {_MAX_CHILD_CODE_LEN} characters",
            )

    @staticmethod
    def _validate_mrp(value: Decimal | None) -> None:
        if value is not None and value < 0:
            raise MasterValidationError("mrp", "MRP must be greater than or equal to 0")

    @staticmethod
    def _validate_rate(value: Decimal | None) -> None:
        if value is not None and value < 0:
            raise MasterValidationError("rate", "Rate must be greater than or equal to 0")

    @staticmethod
    def _validate_gst_percent(value: Decimal | None) -> None:
        if value is not None and (
            value < _MIN_GST_PERCENT or value > _MAX_GST_PERCENT
        ):
            raise MasterValidationError(
                "gst_percent", "GST % must be between 0 and 100 inclusive"
            )

    @staticmethod
    def _validate_length(field_name: str, value: str | None, max_len: int) -> None:
        if value is not None and len(value) > max_len:
            raise MasterValidationError(
                field_name, f"{field_name} must not exceed {max_len} characters"
            )

    @classmethod
    def _validate_optional_lengths(
        cls,
        *,
        hsn_code: str | None,
        pack_size: str | None,
        unit_of_measure: str | None,
    ) -> None:
        cls._validate_length("hsn_code", hsn_code, _MAX_HSN_CODE_LEN)
        cls._validate_length("pack_size", pack_size, _MAX_PACK_SIZE_LEN)
        cls._validate_length("unit_of_measure", unit_of_measure, _MAX_UNIT_OF_MEASURE_LEN)
