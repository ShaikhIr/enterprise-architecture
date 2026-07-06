# Feature: lacm-masters, Property 25: Customer deletion is blocked while referenced.
"""Property-based test for the Customer deletion guard.

Property 25: Customer deletion is blocked while referenced.

**Validates: Requirements 8.6**

*For any* Customer, a delete request is rejected with a conflict error and the
Customer is retained when at least one active Vendor-Customer Mapping or Invoice
Header references it; when no such reference exists the deletion succeeds and
the record is removed.

The service is exercised end-to-end through a real in-memory implementation of
``ICustomerRepository`` (a fake, not a mock), whose reference-existence probes
(``is_referenced_by_active_mapping`` / ``is_referenced_by_invoice_header``) are
parameterised per example. A fresh service/repository pair is built per example
so no state leaks between examples, and the async service is driven with
``asyncio.run`` because each Hypothesis example is independent.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
)
from src.application.services.masters.customer_service import (
    CustomerCreateInput,
    CustomerService,
)
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.user import User
from src.domain.enums.masters import CustomerStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository


class _InMemoryCustomerRepository(ICustomerRepository):
    """Real in-memory ``ICustomerRepository`` with configurable references.

    The two reference probes consult sets that the test seeds, so the property
    can drive every combination of "referenced by active mapping" and
    "referenced by invoice header".
    """

    def __init__(self) -> None:
        self._store: dict[UUID, CustomerEntity] = {}
        self.active_mapping_refs: set[UUID] = set()
        self.invoice_header_refs: set[UUID] = set()

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
        return customer_id in self.active_mapping_refs

    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        return customer_id in self.invoice_header_refs


def _valid_create(**overrides: object) -> CustomerCreateInput:
    base: dict[str, object] = {
        "customer_code": "CUST-001",
        "customer_name": "Acme Hospital",
        "gstn_number": "22AAAAA0000A1Z5",
        "contact_person": "Jane Doe",
        "contact_number": "1234567890",
        "contact_email": "jane@example.com",
    }
    base.update(overrides)
    return CustomerCreateInput(**base)  # type: ignore[arg-type]


@settings(max_examples=20)
@given(
    referenced_by_mapping=st.booleans(),
    referenced_by_invoice=st.booleans(),
)
def test_customer_deletion_blocked_while_referenced(
    referenced_by_mapping: bool,
    referenced_by_invoice: bool,
) -> None:
    """Deletion is blocked iff referenced; otherwise it removes the record.

    For every combination of active-mapping/invoice-header references the
    service must, per Req 8.6:

    * raise ``MasterConflictError`` and retain the Customer when at least one
      reference exists, and
    * delete the Customer when no reference exists.
    """

    async def scenario() -> None:
        repo = _InMemoryCustomerRepository()
        service = CustomerService(session=None, customer_repo=repo)  # type: ignore[arg-type]
        actor = User(id=uuid4(), username="admin", is_active=True)

        created = await service.create_customer(_valid_create(), actor)

        if referenced_by_mapping:
            repo.active_mapping_refs.add(created.id)
        if referenced_by_invoice:
            repo.invoice_header_refs.add(created.id)

        is_referenced = referenced_by_mapping or referenced_by_invoice

        if is_referenced:
            # Blocked with a conflict error; the record is retained.
            with pytest.raises(MasterConflictError):
                await service.delete_customer(created.id, actor)
            assert await repo.get_by_id(created.id) is not None
        else:
            # No reference: deletion succeeds and the record is gone.
            await service.delete_customer(created.id, actor)
            assert await repo.get_by_id(created.id) is None

    asyncio.run(scenario())
