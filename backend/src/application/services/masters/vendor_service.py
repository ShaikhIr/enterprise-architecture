"""
Vendor Master application service.

Orchestrates Vendor business rules — create (with atomic portal-login
provisioning), read, partial update, paginated list, and deactivation
(blocking portal login with best-effort session invalidation) — delegating
persistence to ``IVendorRepository`` and ``IUserRepository``.

Design notes / decoupling
--------------------------
Mirroring :class:`EntityService`, this service is **Pydantic-agnostic** so it is
not coupled to the API request/response schemas owned by the controller task:

* CRUD methods accept primitive arguments / lightweight input dataclasses
  defined in this module (:class:`VendorCreateInput`, :class:`VendorUpdateInput`).
* CRUD methods return the :class:`VendorEntity` domain object.
* ``list_vendors`` returns an ``(items, total)`` tuple.

Partial updates use a dedicated ``UNSET`` sentinel so that "field not supplied"
is distinguished from "field explicitly set to null".

Portal provisioning (Req 6.8) and vendor creation (Req 6.7) share the request's
single DB session, so they commit or roll back atomically with the surrounding
transaction. Deactivation (Req 7.2–7.4, 7.6) sets the vendor ``Inactive``,
blocks the portal user from logging in (``is_active=false``), and makes a
best-effort attempt to invalidate the portal user's live sessions — a failure
of that best-effort step never prevents the deactivation from completing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.enums.masters import VendorStatus
from src.domain.repositories.masters.vendor_repository import IVendorRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.security.password_encoder import hash_password

logger = logging.getLogger(__name__)

# ─── Field length limits (mirroring the VendorModel column definitions) ───
_MAX_VENDOR_CODE_LEN: Final[int] = 50
_MAX_VENDOR_NAME_LEN: Final[int] = 255
_MAX_VENDOR_EMAIL_LEN: Final[int] = 255
_MAX_VENDOR_CONTACT_LEN: Final[int] = 20
_MAX_PAN_LEN: Final[int] = 10
_MAX_BANK_ACCOUNT_LEN: Final[int] = 30
_MAX_BANK_IFSC_LEN: Final[int] = 11
_MAX_BANK_NAME_LEN: Final[int] = 100

# ─── Format patterns (per Requirements 6.5, 6.6) ───
_EMAIL_RE: Final[re.Pattern[str]] = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GSTN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{15}$")


@runtime_checkable
class ISessionInvalidator(Protocol):
    """Port for best-effort invalidation of a portal user's live sessions.

    Implementations target the existing JWT/session mechanism. The Vendor
    deactivation flow calls this within a guarded best-effort block, so any
    failure here must never prevent the deactivation from completing (Req 7.4).
    """

    async def invalidate_user_sessions(self, user_id: UUID) -> None:
        """Invalidate all active sessions for the given user."""
        ...


class _UnsetType:
    """Sentinel marking an update field that was not supplied at all.

    Distinct from ``None``, which represents an explicit request to clear a
    nullable field. Singleton: there is only ever one ``UNSET`` instance.
    """

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "UNSET"

    def __bool__(self) -> bool:  # pragma: no cover - guard against truthiness use
        return False


UNSET: Final[_UnsetType] = _UnsetType()


@dataclass(frozen=True)
class VendorCreateInput:
    """Validated-on-the-way-in payload for creating a Vendor.

    ``status`` defaults to ``None`` so the service can apply the ``Active``
    default (Requirement 6.7) when the caller omits it.
    """

    vendor_code: str
    vendor_name: str
    vendor_email: str
    vendor_contact: str | None = None
    vendor_address: str | None = None
    city: str | None = None
    gstn_number: str | None = None
    pan_number: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None
    bank_name: str | None = None
    status: VendorStatus | None = None


@dataclass(frozen=True)
class VendorUpdateInput:
    """Partial-update payload.

    Each field defaults to :data:`UNSET`. Only fields that differ from ``UNSET``
    are applied, leaving all unsupplied fields unchanged. A nullable field set
    to ``None`` explicitly clears that value.
    """

    vendor_code: str | _UnsetType = UNSET
    vendor_name: str | _UnsetType = UNSET
    vendor_email: str | _UnsetType = UNSET
    vendor_contact: str | None | _UnsetType = UNSET
    vendor_address: str | None | _UnsetType = UNSET
    city: str | None | _UnsetType = UNSET
    gstn_number: str | None | _UnsetType = UNSET
    pan_number: str | None | _UnsetType = UNSET
    bank_account_no: str | None | _UnsetType = UNSET
    bank_ifsc: str | None | _UnsetType = UNSET
    bank_name: str | None | _UnsetType = UNSET
    status: VendorStatus | _UnsetType = UNSET


class VendorService:
    """Application service for Vendor Master management."""

    def __init__(
        self,
        session: AsyncSession,
        vendor_repo: IVendorRepository,
        user_repo: IUserRepository,
        session_invalidator: ISessionInvalidator | None = None,
    ) -> None:
        self._session = session
        self._vendor_repo = vendor_repo
        self._user_repo = user_repo
        self._session_invalidator = session_invalidator

    # ─── Create ───

    async def create_vendor(
        self, data: VendorCreateInput, actor: User
    ) -> VendorEntity:
        """Validate, provision a portal login, and persist a new Vendor.

        Enforces required fields (Req 6.2), trimmed case-insensitive Vendor
        Code and Vendor Email uniqueness (Req 6.3, 6.4), email format (Req 6.5)
        and GSTN format (Req 6.6); defaults ``status`` to ``Active`` (Req 6.7);
        and provisions a portal-login user whose username equals the Vendor Code
        with a system-default password, storing the reference (Req 6.8). All
        validation runs before any write, so a rejected request persists
        nothing; the portal user and vendor are created in the same transaction.
        """
        code = self._require("vendor_code", data.vendor_code, _MAX_VENDOR_CODE_LEN)
        name = self._require("vendor_name", data.vendor_name, _MAX_VENDOR_NAME_LEN)
        email = self._require(
            "vendor_email", data.vendor_email, _MAX_VENDOR_EMAIL_LEN
        )

        self._validate_email(email)
        self._validate_gstn(data.gstn_number)
        self._validate_optional_lengths(data)

        if await self._vendor_repo.exists_by_code(code):
            raise MasterConflictError(
                f"A Vendor with code '{code}' already exists"
            )
        if await self._vendor_repo.exists_by_email(email):
            raise MasterConflictError(
                f"A Vendor with email '{email}' already exists"
            )

        # Portal username equals the Vendor Code (Req 6.8); reject collisions
        # with any pre-existing application user up front so nothing is written.
        if await self._user_repo.exists_by_username(code):
            raise MasterConflictError(
                f"A portal login with username '{code}' already exists"
            )

        portal_user = await self._provision_portal_user(code, name, email, actor)

        vendor = VendorEntity(
            id=uuid4(),
            vendor_code=code,
            vendor_name=name,
            vendor_email=email,
            vendor_contact=data.vendor_contact,
            vendor_address=data.vendor_address,
            city=data.city,
            gstn_number=data.gstn_number,
            pan_number=data.pan_number,
            bank_account_no=data.bank_account_no,
            bank_ifsc=data.bank_ifsc,
            bank_name=data.bank_name,
            portal_user_id=portal_user.id,
            status=VendorStatus.Active if data.status is None else data.status,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._vendor_repo.create(vendor)

    # ─── Read ───

    async def get_vendor(self, vendor_id: UUID) -> VendorEntity:
        """Return a Vendor by ID or raise not-found (Req 6.9, 6.10)."""
        vendor = await self._vendor_repo.get_by_id(vendor_id)
        if vendor is None:
            raise MasterNotFoundError("Vendor", vendor_id)
        return vendor

    # ─── Update (partial) ───

    async def update_vendor(
        self, vendor_id: UUID, patch: VendorUpdateInput, actor: User
    ) -> VendorEntity:
        """Apply a partial update to an existing Vendor.

        Only supplied fields are changed; unsupplied fields are left untouched.
        Re-validates supplied Vendor Email format (Req 6.5) and GSTN format
        (Req 6.6), and preserves Vendor Code / Vendor Email uniqueness
        (excluding the record being updated). Unknown ID → not-found (Req 6.10).
        """
        vendor = await self._vendor_repo.get_by_id(vendor_id)
        if vendor is None:
            raise MasterNotFoundError("Vendor", vendor_id)

        if not isinstance(patch.vendor_code, _UnsetType):
            code = self._require(
                "vendor_code", patch.vendor_code, _MAX_VENDOR_CODE_LEN
            )
            await self._ensure_code_available(code, exclude_id=vendor_id)
            vendor.vendor_code = code

        if not isinstance(patch.vendor_name, _UnsetType):
            vendor.vendor_name = self._require(
                "vendor_name", patch.vendor_name, _MAX_VENDOR_NAME_LEN
            )

        if not isinstance(patch.vendor_email, _UnsetType):
            email = self._require(
                "vendor_email", patch.vendor_email, _MAX_VENDOR_EMAIL_LEN
            )
            self._validate_email(email)
            await self._ensure_email_available(email, exclude_id=vendor_id)
            vendor.vendor_email = email
            # Sync email into the portal user's user_details record
            await self._sync_portal_user_email(vendor.portal_user_id, email)

        if not isinstance(patch.gstn_number, _UnsetType):
            self._validate_gstn(patch.gstn_number)
            vendor.gstn_number = patch.gstn_number

        if not isinstance(patch.vendor_contact, _UnsetType):
            self._validate_max_len(
                "vendor_contact", patch.vendor_contact, _MAX_VENDOR_CONTACT_LEN
            )
            vendor.vendor_contact = patch.vendor_contact

        if not isinstance(patch.vendor_address, _UnsetType):
            vendor.vendor_address = patch.vendor_address

        if not isinstance(patch.city, _UnsetType):
            self._validate_max_len("city", patch.city, 100)
            vendor.city = patch.city

        if not isinstance(patch.pan_number, _UnsetType):
            self._validate_max_len("pan_number", patch.pan_number, _MAX_PAN_LEN)
            vendor.pan_number = patch.pan_number

        if not isinstance(patch.bank_account_no, _UnsetType):
            self._validate_max_len(
                "bank_account_no", patch.bank_account_no, _MAX_BANK_ACCOUNT_LEN
            )
            vendor.bank_account_no = patch.bank_account_no

        if not isinstance(patch.bank_ifsc, _UnsetType):
            self._validate_max_len("bank_ifsc", patch.bank_ifsc, _MAX_BANK_IFSC_LEN)
            vendor.bank_ifsc = patch.bank_ifsc

        if not isinstance(patch.bank_name, _UnsetType):
            self._validate_max_len(
                "bank_name", patch.bank_name, _MAX_BANK_NAME_LEN
            )
            vendor.bank_name = patch.bank_name

        if not isinstance(patch.status, _UnsetType):
            vendor.status = patch.status

        vendor.mark_modified(actor.username)
        return await self._vendor_repo.update(vendor)

    # ─── List (pagination) ───

    async def list_vendors(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_code: str | None = None,
        vendor_name: str | None = None,
        vendor_email: str | None = None,
        city: str | None = None,
        status: str | None = None,
    ) -> tuple[list[VendorEntity], int]:
        """Return a filtered, paginated page of Vendors and the total count."""
        items = await self._vendor_repo.list_all(
            skip=skip, limit=limit,
            vendor_code=vendor_code, vendor_name=vendor_name,
            vendor_email=vendor_email, city=city, status=status,
        )
        total = await self._vendor_repo.count_all(
            vendor_code=vendor_code, vendor_name=vendor_name,
            vendor_email=vendor_email, city=city, status=status,
        )
        return items, total

    # ─── Deactivate ───

    async def deactivate_vendor(
        self, vendor_id: UUID, actor: User
    ) -> VendorEntity:
        """Deactivate a Vendor, blocking portal login while preserving records.

        Unknown ID → not-found (Req 7.1). Sets Status ``Inactive`` (Req 7.2),
        blocks the portal user from authenticating by setting ``is_active=false``
        and makes a best-effort attempt to invalidate that user's live sessions
        (Req 7.3); a failure of session invalidation still completes the
        deactivation (Req 7.4). No existing records are deleted or otherwise
        altered beyond the status/login flags (Req 7.6).
        """
        vendor = await self._vendor_repo.get_by_id(vendor_id)
        if vendor is None:
            raise MasterNotFoundError("Vendor", vendor_id)

        vendor.deactivate(actor.username)
        updated = await self._vendor_repo.update(vendor)

        if vendor.portal_user_id is not None:
            await self._block_and_invalidate_portal_user(
                vendor.portal_user_id, actor
            )

        return updated

    # ─── Private helpers ───

    async def _provision_portal_user(self, vendor_code: str, vendor_name: str, vendor_email: str, actor: User) -> User:
        """Create the vendor's portal-login user (Req 6.8) and a user_details record.

        Stores vendor_email in user_details.email so the portal user is discoverable
        by email and appears correctly in user listings.
        """
        from uuid import uuid4 as _uuid4
        from src.infrastructure.database.models.user_details_model import UserDetailsModel

        portal_user = User(
            id=_uuid4(),
            username=vendor_code,
            password_hash=hash_password(vendor_code),
            is_active=True,
            is_blocked=False,
            is_validate_ad=False,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created_user = await self._user_repo.create(portal_user)

        # Create a user_details record so the portal user appears in user lists
        # and is discoverable by email.
        details = UserDetailsModel(
            id=_uuid4(),
            user_id=created_user.id,
            entity_id=None,
            employee_id=vendor_code,
            employee_name=vendor_name,
            first_name=vendor_name,
            middle_name="",
            last_name="",
            email=vendor_email,  # Store vendor email so it is searchable
            designation_title="",
            department="",
            business_unit="",
            group_company="",
            location="",
            region="",
            zone="",
            grade="",
            office_mobile_no="",
            personal_mobile_no="",
            date_of_joining="",
            reporting_manager="",
            direct_manager_employee_id="",
            direct_manager_name="",
            direct_manager_email="",
            sap_user_id="",
            division_id="",
            territory_id="",
        )
        self._session.add(details)

        return created_user

    async def _sync_portal_user_email(
        self, portal_user_id: UUID | None, new_email: str
    ) -> None:
        """Update user_details.email when the vendor's email address changes."""
        if portal_user_id is None:
            return
        from sqlalchemy import select, update as sa_update
        from src.infrastructure.database.models.user_details_model import UserDetailsModel

        stmt = (
            sa_update(UserDetailsModel)
            .where(UserDetailsModel.user_id == portal_user_id)
            .values(email=new_email)
        )
        await self._session.execute(stmt)

    async def _block_and_invalidate_portal_user(
        self, portal_user_id: UUID, actor: User
    ) -> None:
        """Block portal login (is_active=false) and best-effort invalidate sessions."""
        portal_user = await self._user_repo.get_by_id(portal_user_id)
        if portal_user is not None:
            portal_user.deactivate(actor.username)
            await self._user_repo.update(portal_user)

        # Best-effort session invalidation: never let a failure here prevent
        # the deactivation from completing (Req 7.4).
        if self._session_invalidator is not None:
            try:
                await self._session_invalidator.invalidate_user_sessions(
                    portal_user_id
                )
            except Exception:  # noqa: BLE001 - best-effort, must not propagate
                logger.warning(
                    "Best-effort session invalidation failed for portal user %s; "
                    "vendor deactivation completed regardless",
                    portal_user_id,
                    exc_info=True,
                )

    async def _ensure_code_available(
        self, vendor_code: str, exclude_id: UUID
    ) -> None:
        """Reject a Vendor Code already used by a different vendor."""
        existing = await self._vendor_repo.get_by_code(vendor_code)
        if existing is not None and existing.id != exclude_id:
            raise MasterConflictError(
                f"A Vendor with code '{vendor_code}' already exists"
            )

    async def _ensure_email_available(
        self, vendor_email: str, exclude_id: UUID
    ) -> None:
        """Reject a Vendor Email already used by a different vendor."""
        existing = await self._vendor_repo.get_by_email(vendor_email)
        if existing is not None and existing.id != exclude_id:
            raise MasterConflictError(
                f"A Vendor with email '{vendor_email}' already exists"
            )

    @staticmethod
    def _require(field: str, value: object, max_len: int) -> str:
        """Validate a required string field: present, non-empty, within length.

        Returns the trimmed value so downstream uniqueness/persistence use a
        canonical form.
        """
        if not isinstance(value, str) or value.strip() == "":
            raise MasterValidationError(
                field, f"{field} is required and must not be empty"
            )
        trimmed = value.strip()
        if len(trimmed) > max_len:
            raise MasterValidationError(
                field, f"{field} must not exceed {max_len} characters"
            )
        return trimmed

    @staticmethod
    def _validate_max_len(field: str, value: str | None, max_len: int) -> None:
        """Validate an optional string field's max length when supplied."""
        if value is not None and len(value) > max_len:
            raise MasterValidationError(
                field, f"{field} must not exceed {max_len} characters"
            )

    @staticmethod
    def _validate_email(email: str) -> None:
        """Vendor Email must conform to email format (Req 6.5)."""
        if not _EMAIL_RE.match(email):
            raise MasterValidationError(
                "vendor_email", "Vendor Email is not a valid email address"
            )

    @staticmethod
    def _validate_gstn(gstn_number: str | None) -> None:
        """GSTN, when supplied, must match ``[A-Z0-9]{15}`` (Req 6.6)."""
        if gstn_number and not _GSTN_RE.match(gstn_number):
            raise MasterValidationError(
                "gstn_number",
                "GSTN Number must be 15 uppercase alphanumeric characters",
            )

    @staticmethod
    def _validate_optional_lengths(data: VendorCreateInput) -> None:
        """Validate optional fixed-length fields on create."""
        VendorService._validate_max_len(
            "vendor_contact", data.vendor_contact, _MAX_VENDOR_CONTACT_LEN
        )
        VendorService._validate_max_len("pan_number", data.pan_number, _MAX_PAN_LEN)
        VendorService._validate_max_len(
            "bank_account_no", data.bank_account_no, _MAX_BANK_ACCOUNT_LEN
        )
        VendorService._validate_max_len(
            "bank_ifsc", data.bank_ifsc, _MAX_BANK_IFSC_LEN
        )
        VendorService._validate_max_len(
            "bank_name", data.bank_name, _MAX_BANK_NAME_LEN
        )
