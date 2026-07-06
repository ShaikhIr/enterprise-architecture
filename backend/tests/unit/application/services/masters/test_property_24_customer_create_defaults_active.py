# Feature: lacm-masters, Property 24: Valid customer creation defaults status Active.
"""Property-based test for valid Customer creation defaulting to Active status.

Property 24: Valid customer creation defaults status Active.

**Validates: Requirements 8.5**

*For any* valid create-customer request (one whose Customer Code/Name are
present and within bounds, whose Customer Type is omitted or a valid
``CustomerType``, whose GSTN — when supplied — matches ``[A-Z0-9]{15}``, and
whose contact fields satisfy their length/format limits), creating the Customer
with no Status supplied yields a stored record whose Status is ``Active`` and
whose supplied fields are preserved exactly.

The service is exercised end-to-end through a real in-memory implementation of
``ICustomerRepository`` (not a mock). A fresh service/repository pair is built
per generated example so no state leaks between examples. The async service is
driven with ``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.customer_service import (
    CustomerCreateInput,
    CustomerService,
)
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.user import User
from src.domain.enums.masters import CustomerStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository

_MAX_CUSTOMER_CODE_LEN = 50
_MAX_CUSTOMER_NAME_LEN = 255
_MAX_CONTACT_PERSON_LEN = 100
_MAX_CONTACT_NUMBER_LEN = 20


class _InMemoryCustomerRepository(ICustomerRepository):
    """Minimal real ``ICustomerRepository`` backed by a dict."""

    def __init__(self) -> None:
        self._store: dict[UUID, CustomerEntity] = {}

    async def get_by_id(self, customer_id: UUID) -> CustomerEntity | None:
        return self._store.get(customer_id)

    async def get_by_customer_code(
        self, customer_code: str
    ) -> CustomerEntity | None:
        for c in self._store.values():
            if c.customer_code == customer_code:
                return c
        return None

    async def create(self, customer: CustomerEntity) -> CustomerEntity:
        self._store[customer.id] = customer
        return customer

    async def update(self, customer: CustomerEntity) -> CustomerEntity:
        self._store[customer.id] = customer
        return customer

    async def delete(self, customer_id: UUID) -> None:
        self._store.pop(customer_id, None)

    async def list_customers(
        self, skip: int = 0, limit: int = 20
    ) -> list[CustomerEntity]:
        ordered = sorted(self._store.values(), key=lambda c: c.customer_code)
        return ordered[skip : skip + limit]

    async def count(self) -> int:
        return len(self._store)

    async def exists_by_customer_code(self, customer_code: str) -> bool:
        return any(
            c.customer_code == customer_code for c in self._store.values()
        )

    async def is_referenced_by_active_mapping(self, customer_id: UUID) -> bool:
        return False

    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        return False


# A required string field: non-empty/whitespace after trimming, within cap.
def _required_text(max_size: int) -> st.SearchStrategy[str]:
    return st.text(min_size=1, max_size=max_size).filter(lambda s: s.strip() != "")


# Optional address: absent or any string (no validation constraint).
_optional_address = st.none() | st.text(max_size=255)
# Optional GSTN: absent or exactly 15 uppercase alphanumeric chars.
_gstn_alphabet = st.sampled_from(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)
_optional_gstn = st.none() | st.text(
    alphabet=_gstn_alphabet, min_size=15, max_size=15
)
# Optional contact person/number within their length caps.
_optional_contact_person = st.none() | st.text(max_size=_MAX_CONTACT_PERSON_LEN)
_optional_contact_number = st.none() | st.text(max_size=_MAX_CONTACT_NUMBER_LEN)


@st.composite
def _valid_emails(draw: st.DrawFn) -> str:
    """Generate emails matching the service's ``[^@\\s]+@[^@\\s]+\\.[^@\\s]+`` rule."""
    part = st.text(
        alphabet=st.characters(
            min_codepoint=97, max_codepoint=122  # lowercase ascii letters
        ),
        min_size=1,
        max_size=10,
    )
    local = draw(part)
    domain = draw(part)
    tld = draw(part)
    return f"{local}@{domain}.{tld}"


_optional_contact_email = st.none() | _valid_emails()


@settings(max_examples=20)
@given(
    customer_code=_required_text(_MAX_CUSTOMER_CODE_LEN),
    customer_name=_required_text(_MAX_CUSTOMER_NAME_LEN),
    address=_optional_address,
    gstn_number=_optional_gstn,
    contact_person=_optional_contact_person,
    contact_number=_optional_contact_number,
    contact_email=_optional_contact_email,
)
def test_valid_customer_creation_defaults_status_active(
    customer_code: str,
    customer_name: str,
    address: str | None,
    gstn_number: str | None,
    contact_person: str | None,
    contact_number: str | None,
    contact_email: str | None,
) -> None:
    """Creating a valid Customer with no Status supplied defaults to Active.

    The input omits ``status`` so the service must apply the ``Active`` default
    (Req 8.5). All supplied fields must be preserved exactly on the stored
    record (verified by reading it back by id).
    """

    async def scenario() -> CustomerEntity:
        repo = _InMemoryCustomerRepository()
        service = CustomerService(session=None, customer_repo=repo)  # type: ignore[arg-type]
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await service.create_customer(
            CustomerCreateInput(
                customer_code=customer_code,
                customer_name=customer_name,
                address=address,
                gstn_number=gstn_number,
                contact_person=contact_person,
                contact_number=contact_number,
                contact_email=contact_email,
                # status intentionally omitted to exercise the Active default.
            ),
            actor,
        )
        # Read it back by its generated id to confirm what was persisted.
        return await service.get_customer(created.id)

    stored = asyncio.run(scenario())

    # Status defaults to Active when omitted (Req 8.5).
    assert stored.status == CustomerStatus.Active
    # Supplied fields are preserved exactly.
    assert stored.customer_code == customer_code
    assert stored.customer_name == customer_name
    assert stored.address == address
    assert stored.gstn_number == gstn_number
    assert stored.contact_person == contact_person
    assert stored.contact_number == contact_number
    assert stored.contact_email == contact_email
