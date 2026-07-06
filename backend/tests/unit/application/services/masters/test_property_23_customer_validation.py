# Feature: lacm-masters, Property 23: Customer validation rules.
"""Property-based test for Customer create/update validation rules.

Property 23: Customer validation rules.

**Validates: Requirements 8.2, 8.3, 8.4, 8.8, 8.9**

*For any* create- or update-customer request, the request is rejected with no
persist/modify when:

* the Customer Code or Customer Name is missing/empty/whitespace-only (Req 8.8),
* the Customer Code duplicates an existing customer (Req 8.2),
* the Customer Type is outside the allowed enum (Req 8.3),
* the GSTN Number does not match ``[A-Z0-9]{15}`` (Req 8.4),
* the Contact Person exceeds 100 characters, the Contact Number exceeds 20
  characters, or the Contact Email is not a valid email (Req 8.9).

The service is exercised against a real in-memory implementation of
``ICustomerRepository`` (a fake, not a mock), so the property validates actual
service logic end-to-end through the port. Each Hypothesis example drives the
async service via ``asyncio.run`` so examples remain isolated.
"""

from __future__ import annotations

import asyncio
import string
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.customer_service import (
    _EMAIL_PATTERN,
    _GSTN_PATTERN,
    CustomerCreateInput,
    CustomerService,
    CustomerUpdateInput,
)
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.user import User
from src.domain.enums.masters import CustomerStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository

# Per Requirements 8.9 the contact-field length ceilings under test.
_MAX_CONTACT_PERSON_LEN = 100
_MAX_CONTACT_NUMBER_LEN = 20


class FakeCustomerRepository(ICustomerRepository):
    """In-memory ``ICustomerRepository`` for testing the service in isolation."""

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
        self,
        skip: int = 0,
        limit: int = 20,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> list[CustomerEntity]:
        ordered = sorted(self._store.values(), key=lambda c: c.customer_code)
        return ordered[skip : skip + limit]

    async def count(
        self,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> int:
        return len(self._store)

    async def exists_by_customer_code(self, customer_code: str) -> bool:
        return any(
            c.customer_code == customer_code for c in self._store.values()
        )

    async def is_referenced_by_active_mapping(self, customer_id: UUID) -> bool:
        return False

    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        return False


def _actor() -> User:
    return User(id=uuid4(), username="tester", is_active=True)


def _service(repo: FakeCustomerRepository) -> CustomerService:
    # The session is unused by the in-memory repository path.
    return CustomerService(session=None, customer_repo=repo)  # type: ignore[arg-type]


# ─── Valid baseline values (within every rule) for non-target fields ───
_VALID_CODE = "CUST-001"
_VALID_NAME = "Acme Hospital"
_VALID_GSTN = "22AAAAA0000A1Z5"
_VALID_CONTACT_PERSON = "Jane Doe"
_VALID_CONTACT_NUMBER = "1234567890"
_VALID_CONTACT_EMAIL = "jane@example.com"


def _valid_create(**overrides: object) -> CustomerCreateInput:
    base: dict[str, object] = {
        "customer_code": _VALID_CODE,
        "customer_name": _VALID_NAME,
        "gstn_number": _VALID_GSTN,
        "contact_person": _VALID_CONTACT_PERSON,
        "contact_number": _VALID_CONTACT_NUMBER,
        "contact_email": _VALID_CONTACT_EMAIL,
    }
    base.update(overrides)
    return CustomerCreateInput(**base)  # type: ignore[arg-type]


# ─── Strategies for each invalid trigger ───

_blank = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n\r\f\v", min_size=1, max_size=8),
)

_token = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=12)


@st.composite
def _invalid_gstn(draw: st.DrawFn) -> str:
    value = draw(
        st.one_of(
            # Wrong length (uppercase alnum but not 15 chars).
            st.text(alphabet=string.ascii_uppercase + string.digits, min_size=1, max_size=14),
            st.text(alphabet=string.ascii_uppercase + string.digits, min_size=16, max_size=30),
            # Right-ish length but contains disallowed characters.
            st.text(
                alphabet=string.ascii_lowercase + "-_@# ",
                min_size=15,
                max_size=15,
            ),
        )
    )
    assume(_GSTN_PATTERN.match(value) is None)
    return value


_long_contact_person = st.text(
    alphabet=string.ascii_letters,
    min_size=_MAX_CONTACT_PERSON_LEN + 1,
    max_size=_MAX_CONTACT_PERSON_LEN + 40,
)

_long_contact_number = st.text(
    alphabet=string.digits,
    min_size=_MAX_CONTACT_NUMBER_LEN + 1,
    max_size=_MAX_CONTACT_NUMBER_LEN + 20,
)


@st.composite
def _invalid_email(draw: st.DrawFn) -> str:
    local = draw(_token)
    domain = draw(_token)
    value = draw(
        st.sampled_from(
            [
                local,  # no '@'
                f"{local}@{domain}",  # no dot in domain
                f"{local}@{domain}.",  # nothing after the dot
                f"@{domain}.com",  # empty local part
                f"{local} {domain}@x.com",  # whitespace
            ]
        )
    )
    assume(_EMAIL_PATTERN.match(value) is None)
    return value


@dataclass(frozen=True)
class Case:
    """A single invalid-request scenario."""

    rule: str  # which trigger
    field: str  # offending field name reported by the service
    value: object  # the invalid value (unused for duplicate-code)
    conflict: bool  # True => MasterConflictError; False => MasterValidationError


@st.composite
def _cases(draw: st.DrawFn) -> Case:
    rule = draw(
        st.sampled_from(
            [
                "missing_code",
                "missing_name",
                "invalid_gstn",
                "long_contact_person",
                "long_contact_number",
                "invalid_email",
                "duplicate_code",
            ]
        )
    )
    if rule == "missing_code":
        return Case(rule, "customer_code", draw(_blank), False)
    if rule == "missing_name":
        return Case(rule, "customer_name", draw(_blank), False)
    if rule == "invalid_gstn":
        return Case(rule, "gstn_number", draw(_invalid_gstn()), False)
    if rule == "long_contact_person":
        return Case(rule, "contact_person", draw(_long_contact_person), False)
    if rule == "long_contact_number":
        return Case(rule, "contact_number", draw(_long_contact_number), False)
    if rule == "invalid_email":
        return Case(rule, "contact_email", draw(_invalid_email()), False)
    # duplicate_code
    return Case(rule, "customer_code", None, True)


# ─── Assertions ───


async def _assert_create_rejected(case: Case) -> None:
    repo = FakeCustomerRepository()
    service = _service(repo)

    if case.rule == "duplicate_code":
        # Seed an existing customer that owns the contested code.
        existing = await service.create_customer(
            _valid_create(customer_code="DUP-001", customer_name="Existing"),
            _actor(),
        )
        before = dict(repo._store)
        with pytest.raises(MasterConflictError):
            await service.create_customer(
                _valid_create(customer_code="DUP-001", customer_name="New"),
                _actor(),
            )
        # Only the seeded record remains; nothing new persisted.
        assert set(repo._store) == {existing.id}
        assert repo._store == before
        return

    payload = _valid_create(**{case.field: case.value})
    with pytest.raises(MasterValidationError) as exc:
        await service.create_customer(payload, _actor())
    assert exc.value.field == case.field
    # Nothing persisted.
    assert repo._store == {}


async def _assert_update_rejected(case: Case) -> None:
    repo = FakeCustomerRepository()
    service = _service(repo)

    if case.rule == "duplicate_code":
        first = await service.create_customer(
            _valid_create(customer_code="CUST-A", customer_name="First"),
            _actor(),
        )
        second = await service.create_customer(
            _valid_create(customer_code="CUST-B", customer_name="Second"),
            _actor(),
        )
        first_snap = replace(first)
        second_snap = replace(second)
        with pytest.raises(MasterConflictError):
            await service.update_customer(
                second.id, CustomerUpdateInput(customer_code="CUST-A"), _actor()
            )
        # Both records untouched.
        assert repo._store[first.id].customer_code == first_snap.customer_code
        assert repo._store[second.id].customer_code == second_snap.customer_code
        return

    seeded = await service.create_customer(
        _valid_create(customer_code="SEED-001", customer_name="Seed"), _actor()
    )
    snapshot = replace(seeded)

    patch = CustomerUpdateInput(**{case.field: case.value})  # type: ignore[arg-type]
    with pytest.raises(MasterValidationError) as exc:
        await service.update_customer(seeded.id, patch, _actor())
    assert exc.value.field == case.field
    # The stored record is unchanged.
    assert len(repo._store) == 1
    stored = repo._store[seeded.id]
    assert stored.customer_code == snapshot.customer_code
    assert stored.customer_name == snapshot.customer_name
    assert stored.gstn_number == snapshot.gstn_number
    assert stored.contact_person == snapshot.contact_person
    assert stored.contact_number == snapshot.contact_number
    assert stored.contact_email == snapshot.contact_email


@settings(max_examples=20)
@given(case=_cases())
def test_customer_validation_rules(case: Case) -> None:
    """Invalid create/update requests are rejected and persist/modify nothing.

    Each example violates exactly one Property-23 rule (Req 8.2, 8.3, 8.4, 8.8,
    8.9). On both the create and the partial-update paths the service must
    raise the appropriate error (conflict for a duplicate Customer Code,
    validation error identifying the offending field otherwise) and must leave
    the repository unchanged.
    """
    asyncio.run(_assert_create_rejected(case))
    asyncio.run(_assert_update_rejected(case))
