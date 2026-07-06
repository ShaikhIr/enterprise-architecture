"""
Customer Master application service.

Orchestrates Customer business rules — create, read, partial update, paginated
list, and delete with an in-use guard — delegating persistence to
``ICustomerRepository``.

Design notes / decoupling
--------------------------
The design's service contract is expressed in terms of API response schemas
(``CustomerResponse``, ``PaginatedResponse``). Those schema/controller files are
owned by a sibling task (6.3), so to avoid coupling this service to schemas that
may still be in flux, the service is **Pydantic-agnostic**:

* CRUD methods accept primitive arguments / lightweight input dataclasses
  defined in this module (:class:`CustomerCreateInput`, :class:`CustomerUpdateInput`).
* CRUD methods return the :class:`CustomerEntity` domain object.
* ``list_customers`` returns an ``(items, total)`` tuple.

The controller task adapts these to the API request/response schemas.

Partial updates use a dedicated ``UNSET`` sentinel so that "field not supplied"
is distinguished from "field explicitly set to null" — the controller populates
:class:`CustomerUpdateInput` from the Pydantic request's ``model_fields_set``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.user import User
from src.domain.enums.masters import CustomerStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository

# ─── Field length limits (per Requirements 8.8, 8.9 and the data model) ───
_MAX_CUSTOMER_CODE_LEN: Final[int] = 50
_MAX_CUSTOMER_NAME_LEN: Final[int] = 255
_MAX_CONTACT_PERSON_LEN: Final[int] = 100
_MAX_CONTACT_NUMBER_LEN: Final[int] = 20
_MAX_CONTACT_EMAIL_LEN: Final[int] = 255

# ─── Format patterns (per Requirements 8.4, 8.9) ───
# GSTN is exactly 15 uppercase alphanumeric characters (Req 8.4).
_GSTN_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{15}$")
# Pragmatic single-pass email check: non-space local part, '@', domain with a dot.
_EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


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
class CustomerCreateInput:
    """Validated-on-the-way-in payload for creating a Customer.

    ``status`` defaults to ``None`` so the service can apply the ``Active``
    default (Req 8.5) when omitted.
    """

    customer_code: str
    customer_name: str
    address: str | None = None
    gstn_number: str | None = None
    contact_person: str | None = None
    contact_number: str | None = None
    contact_email: str | None = None
    status: CustomerStatus | None = None


@dataclass(frozen=True)
class CustomerUpdateInput:
    """Partial-update payload.

    Each field defaults to :data:`UNSET`. Only fields that differ from ``UNSET``
    are applied, leaving all unsupplied fields unchanged. A nullable field set to
    ``None`` explicitly clears that value.
    """

    customer_code: str | _UnsetType = UNSET
    customer_name: str | _UnsetType = UNSET
    address: str | None | _UnsetType = UNSET
    gstn_number: str | None | _UnsetType = UNSET
    contact_person: str | None | _UnsetType = UNSET
    contact_number: str | None | _UnsetType = UNSET
    contact_email: str | None | _UnsetType = UNSET
    status: CustomerStatus | _UnsetType = UNSET


class CustomerService:
    """Application service for Customer Master management."""

    def __init__(
        self, session: AsyncSession, customer_repo: ICustomerRepository
    ) -> None:
        self._session = session
        self._customer_repo = customer_repo

    # ─── Create ───

    async def create_customer(
        self, data: CustomerCreateInput, actor: User
    ) -> CustomerEntity:
        """Validate and persist a new Customer.

        Enforces required fields (Req 8.8), Customer Type enum (Req 8.3), GSTN
        format (Req 8.4), contact-field lengths/email format (Req 8.9), and
        Customer Code uniqueness (Req 8.2); defaults Status to ``Active``
        (Req 8.5). Validation runs before any write, so a rejected request
        persists nothing.
        """
        customer_code = self._validate_customer_code(data.customer_code)
        customer_name = self._validate_customer_name(data.customer_name)
        self._validate_gstn(data.gstn_number)
        self._validate_contact_fields(
            data.contact_person, data.contact_number, data.contact_email
        )

        if await self._customer_repo.exists_by_customer_code(customer_code):
            raise MasterConflictError(
                f"A Customer with code '{customer_code}' already exists"
            )

        customer = CustomerEntity(
            id=uuid4(),
            customer_code=customer_code,
            customer_name=customer_name,
            address=data.address,
            gstn_number=data.gstn_number,
            contact_person=data.contact_person,
            contact_number=data.contact_number,
            contact_email=data.contact_email,
            status=data.status if data.status is not None else CustomerStatus.Active,
            created_by=actor.username,
            modified_by=actor.username,
        )
        return await self._customer_repo.create(customer)

    # ─── Read ───

    async def get_customer(self, customer_id: UUID) -> CustomerEntity:
        """Return a Customer by ID or raise not-found (Req 8.10)."""
        customer = await self._customer_repo.get_by_id(customer_id)
        if customer is None:
            raise MasterNotFoundError("Customer", customer_id)
        return customer

    # ─── Update (partial) ───

    async def update_customer(
        self, customer_id: UUID, patch: CustomerUpdateInput, actor: User
    ) -> CustomerEntity:
        """Apply a partial update to an existing Customer.

        Only supplied fields are changed; unsupplied fields are left untouched.
        Re-validates supplied fields (Req 8.3, 8.4, 8.8, 8.9) and preserves
        Customer Code uniqueness (excluding the record being updated, Req 8.2).
        Unknown ID → not-found (Req 8.10).
        """
        customer = await self._customer_repo.get_by_id(customer_id)
        if customer is None:
            raise MasterNotFoundError("Customer", customer_id)

        if not isinstance(patch.customer_code, _UnsetType):
            new_code = self._validate_customer_code(patch.customer_code)
            if new_code != customer.customer_code and (
                await self._customer_repo.exists_by_customer_code(new_code)
            ):
                raise MasterConflictError(
                    f"A Customer with code '{new_code}' already exists"
                )
            customer.customer_code = new_code

        if not isinstance(patch.customer_name, _UnsetType):
            customer.customer_name = self._validate_customer_name(
                patch.customer_name
            )

        if not isinstance(patch.gstn_number, _UnsetType):
            self._validate_gstn(patch.gstn_number)
            customer.gstn_number = patch.gstn_number

        if not isinstance(patch.contact_person, _UnsetType):
            self._validate_contact_person(patch.contact_person)
            customer.contact_person = patch.contact_person

        if not isinstance(patch.contact_number, _UnsetType):
            self._validate_contact_number(patch.contact_number)
            customer.contact_number = patch.contact_number

        if not isinstance(patch.contact_email, _UnsetType):
            self._validate_contact_email(patch.contact_email)
            customer.contact_email = patch.contact_email

        if not isinstance(patch.address, _UnsetType):
            customer.address = patch.address

        if not isinstance(patch.status, _UnsetType):
            customer.status = patch.status

        customer.mark_modified(actor.username)
        return await self._customer_repo.update(customer)

    # ─── List (pagination) ───

    async def list_customers(
        self,
        skip: int = 0,
        limit: int = 20,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> tuple[list[CustomerEntity], int]:
        """Return a filtered, paginated page of Customers and the total count."""
        items = await self._customer_repo.list_customers(
            skip=skip, limit=limit,
            customer_code=customer_code, customer_name=customer_name,
        )
        total = await self._customer_repo.count(
            customer_code=customer_code, customer_name=customer_name,
        )
        return items, total

    # ─── Delete (with in-use guard) ───

    async def delete_customer(self, customer_id: UUID, actor: User) -> None:
        """Delete a Customer unless it is still in use.

        Rejects with not-found for an unknown ID (Req 8.10). Blocks deletion
        with a conflict error when the Customer is referenced by any active
        Vendor-Customer Mapping or any Invoice Header, leaving the record intact
        (Req 8.6).
        """
        customer = await self._customer_repo.get_by_id(customer_id)
        if customer is None:
            raise MasterNotFoundError("Customer", customer_id)

        if await self._customer_repo.is_referenced_by_active_mapping(customer_id):
            raise MasterConflictError(
                "Customer cannot be deleted while referenced by an active "
                "Vendor-Customer Mapping"
            )

        if await self._customer_repo.is_referenced_by_invoice_header(customer_id):
            raise MasterConflictError(
                "Customer cannot be deleted while referenced by an Invoice Header"
            )

        await self._customer_repo.delete(customer_id)

    # ─── Validation helpers ───

    @staticmethod
    def _validate_customer_code(customer_code: object) -> str:
        """Customer Code: required, non-empty/whitespace, ≤ 50 chars (Req 8.8)."""
        if not isinstance(customer_code, str) or customer_code.strip() == "":
            raise MasterValidationError(
                "customer_code", "Customer Code is required and must not be empty"
            )
        if len(customer_code) > _MAX_CUSTOMER_CODE_LEN:
            raise MasterValidationError(
                "customer_code",
                f"Customer Code must not exceed {_MAX_CUSTOMER_CODE_LEN} characters",
            )
        return customer_code

    @staticmethod
    def _validate_customer_name(customer_name: object) -> str:
        """Customer Name: required, non-empty/whitespace, ≤ 255 chars (Req 8.8)."""
        if not isinstance(customer_name, str) or customer_name.strip() == "":
            raise MasterValidationError(
                "customer_name", "Customer Name is required and must not be empty"
            )
        if len(customer_name) > _MAX_CUSTOMER_NAME_LEN:
            raise MasterValidationError(
                "customer_name",
                f"Customer Name must not exceed {_MAX_CUSTOMER_NAME_LEN} characters",
            )
        return customer_name

    @staticmethod
    def _validate_gstn(gstn_number: str | None) -> None:
        """GSTN: optional; when supplied must match ``[A-Z0-9]{15}`` (Req 8.4)."""
        if gstn_number is not None and not _GSTN_PATTERN.match(gstn_number):
            raise MasterValidationError(
                "gstn_number",
                "GSTN Number must be exactly 15 uppercase alphanumeric characters",
            )

    @classmethod
    def _validate_contact_fields(
        cls,
        contact_person: str | None,
        contact_number: str | None,
        contact_email: str | None,
    ) -> None:
        """Validate all contact fields together (Req 8.9)."""
        cls._validate_contact_person(contact_person)
        cls._validate_contact_number(contact_number)
        cls._validate_contact_email(contact_email)

    @staticmethod
    def _validate_contact_person(contact_person: str | None) -> None:
        """Contact Person: optional, ≤ 100 chars when supplied (Req 8.9)."""
        if (
            contact_person is not None
            and len(contact_person) > _MAX_CONTACT_PERSON_LEN
        ):
            raise MasterValidationError(
                "contact_person",
                f"Contact Person must not exceed {_MAX_CONTACT_PERSON_LEN} characters",
            )

    @staticmethod
    def _validate_contact_number(contact_number: str | None) -> None:
        """Contact Number: optional, ≤ 20 chars when supplied (Req 8.9)."""
        if (
            contact_number is not None
            and len(contact_number) > _MAX_CONTACT_NUMBER_LEN
        ):
            raise MasterValidationError(
                "contact_number",
                f"Contact Number must not exceed {_MAX_CONTACT_NUMBER_LEN} characters",
            )

    @staticmethod
    def _validate_contact_email(contact_email: str | None) -> None:
        """Contact Email: optional; when supplied must be valid email (Req 8.9)."""
        if contact_email is None:
            return
        if len(contact_email) > _MAX_CONTACT_EMAIL_LEN:
            raise MasterValidationError(
                "contact_email",
                f"Contact Email must not exceed {_MAX_CONTACT_EMAIL_LEN} characters",
            )
        if not _EMAIL_PATTERN.match(contact_email):
            raise MasterValidationError(
                "contact_email", "Contact Email is not a valid email address"
            )
