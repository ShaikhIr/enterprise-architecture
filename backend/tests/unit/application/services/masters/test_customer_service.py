"""
Unit tests for :class:`CustomerService`.

These exercise the service's business rules against a lightweight in-memory
fake repository (a real implementation of ``ICustomerRepository``, not a mock),
so the tests validate actual service logic end-to-end through the port.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.customer_service import (
    CustomerCreateInput,
    CustomerService,
    CustomerUpdateInput,
)
from src.domain.entities.masters.customer import CustomerEntity
from src.domain.entities.user import User
from src.domain.enums.masters import CustomerStatus
from src.domain.repositories.masters.customer_repository import ICustomerRepository


class FakeCustomerRepository(ICustomerRepository):
    """In-memory ICustomerRepository for unit testing the service."""

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
        return any(c.customer_code == customer_code for c in self._store.values())

    async def is_referenced_by_active_mapping(self, customer_id: UUID) -> bool:
        return customer_id in self.active_mapping_refs

    async def is_referenced_by_invoice_header(self, customer_id: UUID) -> bool:
        return customer_id in self.invoice_header_refs


@pytest.fixture
def repo() -> FakeCustomerRepository:
    return FakeCustomerRepository()


@pytest.fixture
def service(repo: FakeCustomerRepository) -> CustomerService:
    # The session is unused by the in-memory repository path.
    return CustomerService(session=None, customer_repo=repo)  # type: ignore[arg-type]


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


def _valid_input(**overrides: object) -> CustomerCreateInput:
    base = {
        "customer_code": "CUST-001",
        "customer_name": "Acme Hospital",
        "gstn_number": "22AAAAA0000A1Z5",
        "contact_person": "Jane Doe",
        "contact_number": "1234567890",
        "contact_email": "jane@example.com",
    }
    base.update(overrides)
    return CustomerCreateInput(**base)  # type: ignore[arg-type]


# ─── Create: defaults & persistence (Req 8.5) ───


async def test_create_defaults_status_active(
    service: CustomerService, actor: User
) -> None:
    created = await service.create_customer(_valid_input(), actor)
    assert created.status == CustomerStatus.Active
    assert created.customer_code == "CUST-001"
    assert created.customer_name == "Acme Hospital"
    assert created.created_by == "admin"


# ─── Create: validation (Req 8.2, 8.4, 8.8, 8.9) ───


@pytest.mark.parametrize("field", ["customer_code", "customer_name"])
async def test_create_rejects_missing_required(
    service: CustomerService, actor: User, field: str
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_customer(_valid_input(**{field: "   "}), actor)
    assert exc.value.field == field


@pytest.mark.parametrize("gstn", ["short", "22aaaaa0000a1z5", "22AAAAA0000A1Z5X"])
async def test_create_rejects_invalid_gstn(
    service: CustomerService, actor: User, gstn: str
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_customer(_valid_input(gstn_number=gstn), actor)
    assert exc.value.field == "gstn_number"


async def test_create_rejects_long_contact_person(
    service: CustomerService, actor: User
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_customer(
            _valid_input(contact_person="x" * 101), actor
        )
    assert exc.value.field == "contact_person"


async def test_create_rejects_long_contact_number(
    service: CustomerService, actor: User
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_customer(
            _valid_input(contact_number="9" * 21), actor
        )
    assert exc.value.field == "contact_number"


async def test_create_rejects_invalid_email(
    service: CustomerService, actor: User
) -> None:
    with pytest.raises(MasterValidationError) as exc:
        await service.create_customer(
            _valid_input(contact_email="not-an-email"), actor
        )
    assert exc.value.field == "contact_email"


async def test_create_rejects_duplicate_code(
    service: CustomerService, actor: User
) -> None:
    await service.create_customer(_valid_input(), actor)
    with pytest.raises(MasterConflictError):
        await service.create_customer(
            _valid_input(customer_name="Other"), actor
        )


# ─── Read / not-found (Req 8.10) ───


async def test_get_unknown_raises_not_found(service: CustomerService) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.get_customer(uuid4())


# ─── Update (partial) ───


async def test_update_partial_preserves_unsupplied_fields(
    service: CustomerService, actor: User
) -> None:
    created = await service.create_customer(_valid_input(), actor)
    updated = await service.update_customer(
        created.id,
        CustomerUpdateInput(customer_name="Renamed Hospital"),
        actor,
    )
    assert updated.customer_name == "Renamed Hospital"
    # Unsupplied fields preserved.
    assert updated.customer_code == "CUST-001"
    assert updated.gstn_number == "22AAAAA0000A1Z5"


async def test_update_unknown_raises_not_found(
    service: CustomerService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.update_customer(
            uuid4(), CustomerUpdateInput(customer_name="X"), actor
        )


async def test_update_duplicate_code_conflict(
    service: CustomerService, actor: User
) -> None:
    await service.create_customer(_valid_input(customer_code="CUST-001"), actor)
    second = await service.create_customer(
        _valid_input(customer_code="CUST-002", customer_name="Two"), actor
    )
    with pytest.raises(MasterConflictError):
        await service.update_customer(
            second.id, CustomerUpdateInput(customer_code="CUST-001"), actor
        )


async def test_update_same_code_allowed(
    service: CustomerService, actor: User
) -> None:
    created = await service.create_customer(_valid_input(), actor)
    updated = await service.update_customer(
        created.id, CustomerUpdateInput(customer_code="CUST-001"), actor
    )
    assert updated.customer_code == "CUST-001"


# ─── List / pagination (Req 8.7) ───


async def test_list_returns_slice_and_total(
    service: CustomerService, actor: User
) -> None:
    for i in range(5):
        await service.create_customer(
            _valid_input(customer_code=f"CUST-{i:03d}", customer_name=f"C{i}"),
            actor,
        )
    items, total = await service.list_customers(skip=1, limit=2)
    assert total == 5
    assert len(items) == 2
    assert [c.customer_code for c in items] == ["CUST-001", "CUST-002"]


# ─── Delete guard (Req 8.6, 8.10) ───


async def test_delete_unknown_raises_not_found(
    service: CustomerService, actor: User
) -> None:
    with pytest.raises(MasterNotFoundError):
        await service.delete_customer(uuid4(), actor)


async def test_delete_blocked_by_active_mapping(
    service: CustomerService, repo: FakeCustomerRepository, actor: User
) -> None:
    created = await service.create_customer(_valid_input(), actor)
    repo.active_mapping_refs.add(created.id)
    with pytest.raises(MasterConflictError):
        await service.delete_customer(created.id, actor)
    assert await repo.get_by_id(created.id) is not None


async def test_delete_blocked_by_invoice_header(
    service: CustomerService, repo: FakeCustomerRepository, actor: User
) -> None:
    created = await service.create_customer(_valid_input(), actor)
    repo.invoice_header_refs.add(created.id)
    with pytest.raises(MasterConflictError):
        await service.delete_customer(created.id, actor)
    assert await repo.get_by_id(created.id) is not None


async def test_delete_succeeds_when_unreferenced(
    service: CustomerService, repo: FakeCustomerRepository, actor: User
) -> None:
    created = await service.create_customer(_valid_input(), actor)
    await service.delete_customer(created.id, actor)
    assert await repo.get_by_id(created.id) is None
