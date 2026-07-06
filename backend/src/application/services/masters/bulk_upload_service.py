"""
Bulk Upload application service.

Processes a bulk-upload file for one of the masters that supports import
(Vendor, Customer, Product Master, Product Detail, Agreement, and
Vendor-Customer Mapping) and returns a per-row accounting report.

Behaviour (Requirement 19)
--------------------------
* **Unparseable file → whole-file rejection (Req 19.2).** If the uploaded file
  cannot be decoded or does not carry the columns required for the target
  entity type, the entire file is rejected by raising
  :class:`~src.application.exceptions.application_exceptions.MasterValidationError`
  and **nothing** is stored.
* **Row independence (Req 19.1, 19.3).** Each data row is processed inside its
  own savepoint (``session.begin_nested``). A row that fails validation (or
  references an unresolvable Business Code) is rolled back to the savepoint and
  recorded as a positional :class:`BulkRowError`, leaving previously stored rows
  intact and letting the batch continue.
* **Business-code resolution (Req 19.4, 19.5).** A row that references another
  master by its Business Code (e.g. an Agreement row naming a Vendor Code and a
  Product Detail Child Code) has each code resolved to the referenced record's
  UUID before the row is stored. An unresolvable code skips the row with a
  positional error naming the offending code.
* **Report (Req 19.6).** On completion the service returns a
  :class:`BulkUploadReport` carrying the count of rows received, stored, and
  skipped, plus the row-level errors for skipped rows. The accounting invariant
  ``received == stored + skipped`` always holds.

Design notes / decoupling
--------------------------
Mirroring the sibling master services, this service is **Pydantic-agnostic** and
delegates per-row creation to the relevant master service
(:class:`VendorService`, :class:`CustomerService`, :class:`ProductService`,
:class:`AgreementService`, :class:`MappingService`) so all field validation,
uniqueness, and default rules are reused rather than duplicated. The controller
task (14.2) adapts :class:`BulkUploadReport` to the API response schema and
routes the multipart upload by ``entity_type``.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable, Final, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.agreement_service import (
    AgreementCreateInput,
    AgreementService,
)
from src.application.services.masters.customer_service import (
    CustomerCreateInput,
    CustomerService,
)
from src.application.services.masters.mapping_service import (
    MappingCreateInput,
    MappingService,
)
from src.application.services.masters.product_service import (
    ProductMasterCreateInput,
    ProductService,
)
from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
)
from src.domain.entities.user import User
from src.domain.enums.masters import (
    CustomerStatus,
    MappingStatus,
    ProductStatus,
    VendorStatus,
)
from src.domain.repositories.masters.customer_repository import ICustomerRepository
from src.domain.repositories.masters.product_repository import IProductRepository
from src.domain.repositories.masters.vendor_repository import IVendorRepository


# ─── Supported entity types ───
ENTITY_VENDOR: Final[str] = "vendor"
ENTITY_CUSTOMER: Final[str] = "customer"
ENTITY_PRODUCT_MASTER: Final[str] = "product_master"
ENTITY_AGREEMENT: Final[str] = "agreement"
ENTITY_MAPPING: Final[str] = "mapping"

SUPPORTED_ENTITY_TYPES: Final[frozenset[str]] = frozenset(
    {
        ENTITY_VENDOR,
        ENTITY_CUSTOMER,
        ENTITY_PRODUCT_MASTER,
        ENTITY_AGREEMENT,
        ENTITY_MAPPING,
    }
)


@dataclass
class BulkRowError:
    """A single skipped-row error, naming the 1-based row position and reason."""

    row_number: int
    reason: str


@dataclass
class BulkUploadReport:
    """Per-row accounting for a bulk-upload request (Req 19.6).

    The invariant ``received == stored + skipped`` always holds, and there is
    exactly one :class:`BulkRowError` per skipped row.
    """

    received: int = 0
    stored: int = 0
    skipped: int = 0
    errors: list[BulkRowError] = field(default_factory=list)


class _ReadableFile(Protocol):
    """Minimal protocol for the uploaded file (e.g. Starlette ``UploadFile``)."""

    async def read(self, size: int = -1) -> bytes | str: ...


# A row handler validates/resolves one parsed row and delegates to a master
# service. It raises ``MasterValidationError``/``MasterConflictError`` for a row
# that must be skipped.
_RowHandler = Callable[[dict[str, str], User], Awaitable[None]]


class BulkUploadService:
    """Application service implementing bulk master upload (Requirement 19)."""

    def __init__(
        self,
        session: AsyncSession,
        vendor_service: VendorService,
        customer_service: CustomerService,
        product_service: ProductService,
        agreement_service: AgreementService,
        mapping_service: MappingService,
        vendor_repo: IVendorRepository,
        customer_repo: ICustomerRepository,
        product_repo: IProductRepository,
    ) -> None:
        self._session = session
        self._vendor_service = vendor_service
        self._customer_service = customer_service
        self._product_service = product_service
        self._agreement_service = agreement_service
        self._mapping_service = mapping_service
        self._vendor_repo = vendor_repo
        self._customer_repo = customer_repo
        self._product_repo = product_repo

    async def process(
        self, entity_type: str, file: _ReadableFile, actor: User
    ) -> BulkUploadReport:
        """Process a bulk-upload file for ``entity_type`` and report the result.

        Raises :class:`MasterValidationError` for an unknown ``entity_type`` or
        an unparseable file (whole-file rejection, nothing stored — Req 19.2).
        Otherwise every parsed data row is processed independently inside its
        own savepoint and the populated :class:`BulkUploadReport` is returned.
        """
        normalized_type = (entity_type or "").strip().lower()
        if normalized_type not in SUPPORTED_ENTITY_TYPES:
            raise MasterValidationError(
                "entity_type",
                f"Unsupported bulk-upload entity type '{entity_type}'",
            )

        required_columns, handler = self._resolve_handler(normalized_type)
        rows = await self._parse_rows(file, required_columns)

        report = BulkUploadReport(received=len(rows))
        for index, row in enumerate(rows, start=1):
            try:
                async with self._session.begin_nested():
                    await handler(row, actor)
                report.stored += 1
            except (MasterValidationError, MasterConflictError) as exc:
                report.skipped += 1
                report.errors.append(
                    BulkRowError(row_number=index, reason=str(exc))
                )
        return report

    # ─────────────────────────────── Parsing ──────────────────────────────

    async def _parse_rows(
        self, file: _ReadableFile, required_columns: frozenset[str]
    ) -> list[dict[str, str]]:
        """Parse the uploaded CSV file into normalized row dictionaries.

        Rejects the whole file (Req 19.2) when it cannot be decoded as UTF-8
        text, when it has no header row, or when it is missing one of the
        ``required_columns`` for the target entity type.
        """
        raw = await file.read()
        if isinstance(raw, str):
            data = raw
        else:
            try:
                data = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise MasterValidationError(
                    "file", "The uploaded file is not valid UTF-8 text"
                ) from exc

        try:
            reader = csv.reader(io.StringIO(data))
            records = list(reader)
        except csv.Error as exc:
            raise MasterValidationError(
                "file", "The uploaded file could not be parsed as CSV"
            ) from exc

        if not records:
            raise MasterValidationError(
                "file", "The uploaded file is empty"
            )

        header = [cell.strip().lower() for cell in records[0]]
        if not any(header):
            raise MasterValidationError(
                "file", "The uploaded file has no header row"
            )

        missing = required_columns - set(header)
        if missing:
            raise MasterValidationError(
                "file",
                "The uploaded file is missing required columns: "
                + ", ".join(sorted(missing)),
            )

        rows: list[dict[str, str]] = []
        for raw_row in records[1:]:
            # Skip fully blank lines so they do not inflate the received count.
            if not any(cell.strip() for cell in raw_row):
                continue
            row: dict[str, str] = {}
            for col_index, column in enumerate(header):
                if not column:
                    continue
                value = raw_row[col_index] if col_index < len(raw_row) else ""
                row[column] = value.strip()
            rows.append(row)
        return rows

    # ─────────────────────────── Handler dispatch ─────────────────────────

    def _resolve_handler(
        self, entity_type: str
    ) -> tuple[frozenset[str], _RowHandler]:
        """Return the required columns and row handler for ``entity_type``."""
        dispatch: dict[str, tuple[frozenset[str], _RowHandler]] = {
            ENTITY_VENDOR: (
                frozenset({"vendor_code", "vendor_name", "vendor_email"}),
                self._handle_vendor_row,
            ),
            ENTITY_CUSTOMER: (
                frozenset({"customer_code", "customer_name"}),
                self._handle_customer_row,
            ),
            ENTITY_PRODUCT_MASTER: (
                frozenset({"basic_material_code", "product_name", "child_code"}),
                self._handle_product_master_row,
            ),
            ENTITY_AGREEMENT: (
                frozenset(
                    {
                        "vendor_code",
                        "product_detail_code",
                        "from_date",
                        "to_date",
                    }
                ),
                self._handle_agreement_row,
            ),
            ENTITY_MAPPING: (
                frozenset(
                    {
                        "vendor_code",
                        "customer_code",
                        "validity_from",
                        "validity_to",
                    }
                ),
                self._handle_mapping_row,
            ),
        }
        return dispatch[entity_type]

    # ───────────────────────────── Row handlers ───────────────────────────

    async def _handle_vendor_row(self, row: dict[str, str], actor: User) -> None:
        await self._vendor_service.create_vendor(
            VendorCreateInput(
                vendor_code=row.get("vendor_code", ""),
                vendor_name=row.get("vendor_name", ""),
                vendor_email=row.get("vendor_email", ""),
                vendor_contact=_optional(row.get("vendor_contact")),
                vendor_address=_optional(row.get("vendor_address")),
                gstn_number=_optional(row.get("gstn_number")),
                pan_number=_optional(row.get("pan_number")),
                bank_account_no=_optional(row.get("bank_account_no")),
                bank_ifsc=_optional(row.get("bank_ifsc")),
                bank_name=_optional(row.get("bank_name")),
                status=_parse_enum(
                    "status", row.get("status"), VendorStatus
                ),
            ),
            actor,
        )

    async def _handle_customer_row(self, row: dict[str, str], actor: User) -> None:
        await self._customer_service.create_customer(
            CustomerCreateInput(
                customer_code=row.get("customer_code", ""),
                customer_name=row.get("customer_name", ""),
                address=_optional(row.get("address")),
                gstn_number=_optional(row.get("gstn_number")),
                contact_person=_optional(row.get("contact_person")),
                contact_number=_optional(row.get("contact_number")),
                contact_email=_optional(row.get("contact_email")),
                status=_parse_enum(
                    "status", row.get("status"), CustomerStatus
                ),
            ),
            actor,
        )

    async def _handle_product_master_row(
        self, row: dict[str, str], actor: User
    ) -> None:
        await self._product_service.create(
            ProductMasterCreateInput(
                basic_material_code=row.get("basic_material_code", ""),
                product_name=row.get("product_name", ""),
                child_code=row.get("child_code", ""),
                variant_description=_optional(row.get("variant_description")),
                hsn_code=_optional(row.get("hsn_code")),
                pack_size=_optional(row.get("pack_size")),
                unit_of_measure=_optional(row.get("unit_of_measure")),
                mrp=_parse_decimal("mrp", row.get("mrp")),
                rate=_parse_decimal("rate", row.get("rate")),
                gst_percent=_parse_decimal("gst_percent", row.get("gst_percent")),
                status=_parse_enum(
                    "status", row.get("status"), ProductStatus
                ),
            ),
            actor,
        )

    async def _handle_agreement_row(
        self, row: dict[str, str], actor: User
    ) -> None:
        vendor_id = await self._resolve_vendor(row.get("vendor_code", ""))
        detail_id = await self._resolve_product_detail(
            row.get("product_detail_code", "")
        )
        await self._agreement_service.create_agreement(
            AgreementCreateInput(
                vendor_id=vendor_id,
                product_detail_id=detail_id,
                from_date=_parse_date("from_date", row.get("from_date")),
                to_date=_parse_date("to_date", row.get("to_date")),
                slab_in_days=_parse_int("slab_in_days", row.get("slab_in_days")),
                reduction_percent=_parse_decimal(
                    "reduction_percent", row.get("reduction_percent")
                ),
                max_commission_percent=_parse_decimal(
                    "max_commission_percent", row.get("max_commission_percent")
                ),
                min_commission_percent=_parse_decimal(
                    "min_commission_percent", row.get("min_commission_percent")
                ),
                credit_days=_parse_int("credit_days", row.get("credit_days")),
            ),
            actor,
        )

    async def _handle_mapping_row(self, row: dict[str, str], actor: User) -> None:
        vendor_id = await self._resolve_vendor(row.get("vendor_code", ""))
        customer_id = await self._resolve_customer(row.get("customer_code", ""))
        validity_from = _parse_date("validity_from", row.get("validity_from"))
        validity_to = _parse_date("validity_to", row.get("validity_to"))
        await self._mapping_service.create_mapping(
            MappingCreateInput(
                vendor_id=vendor_id,
                customer_id=customer_id,
                validity_from=validity_from,
                validity_to=validity_to,
                status=_parse_enum("status", row.get("status"), MappingStatus),
            ),
            actor,
        )

    # ──────────────────── Business-code resolution (Req 19.4/19.5) ─────────

    async def _resolve_vendor(self, vendor_code: str) -> UUID:
        code = vendor_code.strip()
        if not code:
            raise MasterValidationError(
                "vendor_code", "Vendor Code is required"
            )
        vendor = await self._vendor_repo.get_by_code(code)
        if vendor is None:
            raise MasterValidationError(
                "vendor_code",
                f"Could not resolve Vendor Code '{code}' to an existing Vendor",
            )
        return vendor.id

    async def _resolve_customer(self, customer_code: str) -> UUID:
        code = customer_code.strip()
        if not code:
            raise MasterValidationError(
                "customer_code", "Customer Code is required"
            )
        customer = await self._customer_repo.get_by_customer_code(code)
        if customer is None:
            raise MasterValidationError(
                "customer_code",
                f"Could not resolve Customer Code '{code}' to an existing "
                "Customer",
            )
        return customer.id

    async def _resolve_product_master(self, basic_material_code: str) -> UUID:
        code = basic_material_code.strip()
        if not code:
            raise MasterValidationError(
                "product_master_code", "Basic Material Code is required"
            )
        master = await self._product_repo.get_by_basic_material_code(code)
        if master is None:
            raise MasterValidationError(
                "product_master_code",
                f"Could not resolve Basic Material Code '{code}' to an existing "
                "Product Master",
            )
        return master.id

    async def _resolve_product_detail(self, child_code: str) -> UUID:
        code = child_code.strip()
        if not code:
            raise MasterValidationError(
                "product_detail_code", "Product Detail Child Code is required"
            )
        detail = await self._product_repo.get_by_child_code(code)
        if detail is None:
            raise MasterValidationError(
                "product_detail_code",
                f"Could not resolve Child Code '{code}' to an existing Product "
                "Detail",
            )
        return detail.id


# ─────────────────────────── Field coercion helpers ───────────────────────


def _optional(value: str | None) -> str | None:
    """Return a trimmed non-empty string, or ``None`` for blanks."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _parse_enum(field_name: str, value: str | None, enum_cls):
    """Coerce a cell to ``enum_cls``; blank → ``None``; invalid → skip the row."""
    trimmed = _optional(value)
    if trimmed is None:
        return None
    try:
        return enum_cls(trimmed)
    except ValueError as exc:
        valid = ", ".join(member.value for member in enum_cls)
        raise MasterValidationError(
            field_name,
            f"Invalid value '{trimmed}'. Must be one of: {valid}",
        ) from exc


def _parse_int(field_name: str, value: str | None) -> int | None:
    """Coerce a cell to ``int``; blank → ``None``; invalid → skip the row."""
    trimmed = _optional(value)
    if trimmed is None:
        return None
    try:
        return int(trimmed)
    except ValueError as exc:
        raise MasterValidationError(
            field_name, f"'{trimmed}' is not a valid integer"
        ) from exc


def _parse_decimal(field_name: str, value: str | None) -> Decimal | None:
    """Coerce a cell to ``Decimal``; blank → ``None``; invalid → skip the row."""
    trimmed = _optional(value)
    if trimmed is None:
        return None
    try:
        return Decimal(trimmed)
    except (InvalidOperation, ValueError) as exc:
        raise MasterValidationError(
            field_name, f"'{trimmed}' is not a valid number"
        ) from exc


def _parse_date(field_name: str, value: str | None) -> date | None:
    """Coerce a cell to an ISO ``date``; blank → ``None``; invalid → skip row."""
    trimmed = _optional(value)
    if trimmed is None:
        return None
    try:
        return date.fromisoformat(trimmed)
    except ValueError as exc:
        raise MasterValidationError(
            field_name,
            f"'{trimmed}' is not a valid ISO date (expected YYYY-MM-DD)",
        ) from exc
