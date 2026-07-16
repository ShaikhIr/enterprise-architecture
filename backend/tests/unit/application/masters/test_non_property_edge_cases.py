"""
Unit / edge-case tests for non-property acceptance criteria (Task 15.4).

The design classifies a handful of criteria as concrete examples or edge cases
rather than universal properties. They are folded into the property generators
where relevant, but the design also calls for them to be asserted *explicitly*
here so each has a focused, readable regression test.

Service-level criteria covered in this module (the FastAPI ``Query``-boundary
pagination rejection and the 401/403 authz cases live in the integration API
test ``tests/integration/api/test_masters_authz_pagination.py``):

* Empty dropdown returns empty list .......................... Req 2.2
* No-roles user creation allowed (zero assignments) .......... Req 4.10
* Empty mapping list result .................................. Req 14.8
* Unset due date when no agreement exists .................... Req 16.8
* Pre-commit deactivated user still authenticates ............ Req 5.7
* Deactivation completes even when invalidation throws ....... Req 7.4
* Scheduler retry leaves data unchanged ...................... Req 15.3

Every service is exercised through real logic over lightweight in-memory fakes
(no mocking of the behaviour under test), consistent with the existing master
service unit tests.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.application.services.masters.entity_service import EntityService
from src.application.services.masters.invoice_service import (
    InvoiceCreateInput,
    InvoiceLineInput,
    InvoiceService,
)
from src.application.services.masters.mapping_service import MappingService
from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
)
from src.domain.entities.masters.entity import EntityEntity
from src.domain.entities.masters.mapping import MappingEntity
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.enums.masters import InvoiceStatus, MappingStatus, VendorStatus
from src.infrastructure.security.auth_manager import AuthManager
from src.infrastructure.security.jwt_provider import JWTProvider
from src.infrastructure.security.password_encoder import hash_password


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", password_hash="x", is_active=True)


# ───────────────────────────────────────────────────────────────────────────
# Req 2.2 — Empty dropdown returns an empty list when no entity is active.
# ───────────────────────────────────────────────────────────────────────────


class _DropdownEntityRepo:
    """Entity repo stub whose active-set is configurable for the dropdown."""

    def __init__(self, active: list[EntityEntity]) -> None:
        self._active = active

    async def list_active(self) -> list[EntityEntity]:
        return list(self._active)


async def test_dropdown_returns_empty_when_no_active_entities() -> None:
    """Req 2.2: with no active entity, the dropdown is an empty list."""
    service = EntityService(session=None, entity_repo=_DropdownEntityRepo([]))  # type: ignore[arg-type]

    items = await service.get_dropdown()

    assert items == []


async def test_dropdown_includes_only_active_entities() -> None:
    """Contrast for Req 2.1/2.2: an active entity does appear (non-empty case)."""
    active = EntityEntity(
        id=uuid4(), entity_name="Acme", short_code="AC", company_code="ACME",
        is_active=True,
    )
    service = EntityService(session=None, entity_repo=_DropdownEntityRepo([active]))  # type: ignore[arg-type]

    items = await service.get_dropdown()

    assert len(items) == 1
    assert items[0].id == active.id
    assert items[0].label == "AC - Acme"


# ───────────────────────────────────────────────────────────────────────────
# Req 14.8 — A mapping list that matches nothing returns an empty list.
# ───────────────────────────────────────────────────────────────────────────


class _EmptyMappingRepo:
    """Mapping repo that holds no records (every list query is empty)."""

    async def list_mappings(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[MappingEntity]:
        return []

    async def list_mappings_with_names(
        self,
        skip: int = 0,
        limit: int = 20,
        vendor_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list:
        return []

    async def count(
        self, vendor_id: UUID | None = None, customer_id: UUID | None = None
    ) -> int:
        return 0

    async def count_filtered(
        self, vendor_id: UUID | None = None, customer_id: UUID | None = None
    ) -> int:
        return 0


async def test_mapping_list_returns_empty_when_no_match() -> None:
    """Req 14.8: a non-matching mapping list yields ([], 0)."""
    service = MappingService(
        session=None,  # type: ignore[arg-type]
        mapping_repo=_EmptyMappingRepo(),  # type: ignore[arg-type]
        vendor_repo=None,  # type: ignore[arg-type]
        customer_repo=None,  # type: ignore[arg-type]
    )

    items, total = await service.list_mappings(vendor_id=uuid4(), customer_id=uuid4())

    assert items == []
    assert total == 0


# ───────────────────────────────────────────────────────────────────────────
# Req 16.8 — No supplied due date and no applicable agreement -> unset due date.
# ───────────────────────────────────────────────────────────────────────────


class _FakeInvoiceRepo:
    def __init__(self) -> None:
        self.created: list = []

    async def exists_by_invoice_number(
        self, invoice_number: str, exclude_id: UUID | None = None
    ) -> bool:
        return False

    async def create(self, header, lines):  # noqa: ANN001 - domain entities
        header.lines = lines
        self.created.append(header)
        return header


class _ExistsRepo:
    """A reference repo whose lookups always resolve (the record exists)."""

    async def get_by_id(self, _id: UUID) -> object:
        return object()


class _FakeProductRepo:
    async def get_by_id(self, _id: UUID) -> object:
        return object()

    async def get_detail_by_id(self, _id: UUID) -> object:
        return object()


class _NoAgreementRepo:
    """Agreement repo with no overlapping active agreement for any query."""

    async def find_overlapping_active(self, **_kwargs):
        return []


async def test_invoice_due_date_unset_when_no_agreement(actor: User) -> None:
    """Req 16.8: without a supplied due date or applicable agreement, due date is unset."""
    invoice_repo = _FakeInvoiceRepo()
    service = InvoiceService(
        session=None,  # type: ignore[arg-type]
        invoice_repo=invoice_repo,  # type: ignore[arg-type]
        vendor_repo=_ExistsRepo(),  # type: ignore[arg-type]
        customer_repo=_ExistsRepo(),  # type: ignore[arg-type]
        product_repo=_FakeProductRepo(),  # type: ignore[arg-type]
        agreement_repo=_NoAgreementRepo(),  # type: ignore[arg-type]
    )

    header = await service.create_invoice(
        InvoiceCreateInput(
            invoice_number="INV-001",
            invoice_date=date(2025, 1, 10),
            vendor_id=uuid4(),
            customer_id=uuid4(),
            bill_amount_excl_gst=Decimal("100.00"),
            lines=[InvoiceLineInput(product_master_id=uuid4())],
            due_date=None,  # not supplied
        ),
        actor,
    )

    assert header.due_date is None
    # The header is still persisted with its other defaults applied (Req 16.5).
    assert header.invoice_status is InvoiceStatus.Open
    assert len(invoice_repo.created) == 1


# ───────────────────────────────────────────────────────────────────────────
# Req 4.10 — Creating a user with no roles yields zero role assignments.
# ───────────────────────────────────────────────────────────────────────────


class _NoRoleSession:
    """AsyncSession stand-in for ``create_user`` with an empty role set.

    ``create_user`` issues only the Employee-ID uniqueness probe (no role probe
    runs for an empty role set), so a single empty result satisfies it. Every
    staged ``add`` is recorded for inspection.
    """

    class _EmptyScalars:
        def all(self) -> list:
            return []

    class _EmptyResult:
        def first(self):
            return None

        def scalars(self) -> _NoRoleSession._EmptyScalars:
            return _NoRoleSession._EmptyScalars()

    def __init__(self) -> None:
        self.added: list = []

    async def execute(self, _stmt):  # noqa: ANN001 - SQLAlchemy statement
        return self._EmptyResult()

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)


class _UserRepoForCreate:
    def __init__(self) -> None:
        self.store: dict[UUID, User] = {}

    async def exists_by_username(self, username: str) -> bool:
        return any(u.username.lower() == username.lower() for u in self.store.values())

    async def create(self, user: User) -> User:
        self.store[user.id] = user
        return user


class _ActiveEntityRepo:
    def __init__(self, entity: EntityEntity) -> None:
        self._entity = entity

    async def get_by_id(self, entity_id: UUID) -> EntityEntity | None:
        return self._entity if entity_id == self._entity.id else None


async def test_create_user_with_no_roles_assigns_nothing(actor: User) -> None:
    """Req 4.10: a create-user request with no roles creates zero assignments."""
    from src.api.v1.schemas.user_request import CreateUserRequest
    from src.application.services.user_service import UserService
    from src.infrastructure.database.models.role_model import RoleAssignmentModel

    entity = EntityEntity(
        id=uuid4(), entity_name="Acme", short_code="AC", company_code="ACME",
        is_active=True,
    )
    session = _NoRoleSession()
    user_repo = _UserRepoForCreate()
    service = UserService(
        session=session,  # type: ignore[arg-type]
        user_repo=user_repo,  # type: ignore[arg-type]
        entity_repo=_ActiveEntityRepo(entity),  # type: ignore[arg-type]
    )

    request = CreateUserRequest(
        employee_id="E1",
        username="u1",
        entity_id=entity.id,
        role_ids=[],  # no roles supplied
        is_validate_ad=True,
    )

    response = await service.create_user(request, actor)

    # The user is created (Req 4.10 allows a user with no roles) ...
    assert response.id in user_repo.store
    # ... and no role-assignment row is staged.
    assignments = [o for o in session.added if isinstance(o, RoleAssignmentModel)]
    assert assignments == []


# ───────────────────────────────────────────────────────────────────────────
# Req 5.7 — A not-yet-persisted deactivation must NOT block authentication.
# ───────────────────────────────────────────────────────────────────────────


class _SingleUserRepo:
    """Auth-facing repo exposing the single stored user via ``get_by_username``."""

    def __init__(self, user: User) -> None:
        self._user = user

    async def get_by_username(self, username: str) -> User | None:
        return self._user if self._user.username == username else None


async def test_pending_deactivation_still_authenticates() -> None:
    """Req 5.7: while a deactivation edit is not yet persisted, login still works."""
    from src.api.v1.schemas.user_request import EditUserRequest

    password = "StrongPass123!"
    user = User(
        id=uuid4(),
        username="agent1",
        password_hash=hash_password(password),
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
    )
    auth = AuthManager(
        user_repository=_SingleUserRepo(user),  # type: ignore[arg-type]
        jwt_provider=JWTProvider(),
    )

    # An edit that *would* deactivate the user exists but has not been applied
    # or persisted to the stored user yet.
    pending_edit = EditUserRequest(is_active=False)
    assert pending_edit.is_active is False
    assert "is_active" in pending_edit.model_fields_set

    # Because the change is not yet persisted, the stored user is still active
    # and authentication continues to succeed.
    assert user.can_authenticate() is True
    tokens = await auth.login(user.username, password)
    assert tokens.access_token


# ───────────────────────────────────────────────────────────────────────────
# Req 7.4 — Vendor deactivation completes even if session invalidation throws.
# ───────────────────────────────────────────────────────────────────────────


class _DeactivationVendorRepo:
    def __init__(self) -> None:
        self.store: dict[UUID, VendorEntity] = {}

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self.store.get(vendor_id)

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        target = vendor_code.strip().lower()
        return next(
            (v for v in self.store.values() if v.vendor_code.strip().lower() == target),
            None,
        )

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        target = vendor_email.strip().lower()
        return next(
            (v for v in self.store.values() if v.vendor_email.strip().lower() == target),
            None,
        )

    async def create(self, vendor: VendorEntity) -> VendorEntity:
        self.store[vendor.id] = vendor
        return vendor

    async def update(self, vendor: VendorEntity) -> VendorEntity:
        self.store[vendor.id] = vendor
        return vendor

    async def exists_by_code(self, vendor_code: str) -> bool:
        return await self.get_by_code(vendor_code) is not None

    async def exists_by_email(self, vendor_email: str) -> bool:
        return await self.get_by_email(vendor_email) is not None


class _DeactivationUserRepo:
    def __init__(self) -> None:
        self.store: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return next(
            (u for u in self.store.values() if u.username.lower() == username.lower()),
            None,
        )

    async def create(self, user: User) -> User:
        self.store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self.store[user.id] = user
        return user

    async def exists_by_username(self, username: str) -> bool:
        return await self.get_by_username(username) is not None


class _ThrowingInvalidator:
    """Session invalidator that always raises (the unhappy path for Req 7.4)."""

    def __init__(self) -> None:
        self.called = False

    async def invalidate_user_sessions(self, user_id: UUID) -> None:
        self.called = True
        raise RuntimeError("session store unavailable")


async def test_deactivation_completes_when_invalidation_throws(actor: User) -> None:
    """Req 7.4: deactivation finishes (status Inactive, login blocked) despite a throw."""
    vendor_repo = _DeactivationVendorRepo()
    user_repo = _DeactivationUserRepo()
    invalidator = _ThrowingInvalidator()
    service = VendorService(
        session=None,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,  # type: ignore[arg-type]
        user_repo=user_repo,  # type: ignore[arg-type]
        session_invalidator=invalidator,  # type: ignore[arg-type]
    )

    created = await service.create_vendor(
        VendorCreateInput(
            vendor_code="V001",
            vendor_name="Acme Liaisons",
            vendor_email="contact@acme.example",
        ),
        actor,
    )

    # Must not raise, even though invalidation throws.
    result = await service.deactivate_vendor(created.id, actor)

    assert invalidator.called is True
    assert result.status is VendorStatus.Inactive
    portal = await user_repo.get_by_id(created.portal_user_id)
    assert portal is not None
    assert portal.is_active is False  # new logins are blocked


# ───────────────────────────────────────────────────────────────────────────
# Req 15.3 — A failed expiry run leaves data unchanged; the retry then expires.
# ───────────────────────────────────────────────────────────────────────────


class _ExpiryMappingRepo:
    """In-memory mapping repo covering the end-of-day expiry sweep."""

    def __init__(self) -> None:
        self.store: dict[UUID, MappingEntity] = {}

    async def update(self, mapping: MappingEntity) -> MappingEntity:
        self.store[mapping.id] = mapping
        return mapping

    async def list_active_due_for_expiry(self, today: date) -> list[MappingEntity]:
        return [
            m
            for m in self.store.values()
            if m.status is MappingStatus.Active and m.validity_to < today
        ]


class _TxSession:
    """Async-context-manager session recording commit / rollback."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _TxSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _past_due_mapping() -> MappingEntity:
    return MappingEntity(
        id=uuid4(),
        vendor_id=uuid4(),
        customer_id=uuid4(),
        validity_from=date(2024, 1, 1),
        validity_to=date(2025, 1, 1),
        status=MappingStatus.Active,
        created_by="tester",
        modified_by="tester",
    )


def test_failed_expiry_run_leaves_data_unchanged_then_retry_expires() -> None:
    """Req 15.3: a failed run mutates nothing; the next run (retry) expires the records."""
    from src.infrastructure.background.tasks import mapping_tasks

    repo = _ExpiryMappingRepo()
    past = _past_due_mapping()
    repo.store[past.id] = past
    today = date(2025, 6, 1)

    class _BoomService:
        async def expire_due_mappings(self, _today: date) -> int:
            raise RuntimeError("boom")

    # First run fails before completion: the transaction rolls back and the
    # error propagates so Celery can retry. The mapping is left untouched.
    failing_session = _TxSession()
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            mapping_tasks.expire_due_mappings(
                today,
                session_factory=lambda: failing_session,
                service_builder=lambda _s: _BoomService(),  # type: ignore[arg-type]
            )
        )

    assert failing_session.rolled_back is True
    assert failing_session.committed is False
    assert repo.store[past.id].status is MappingStatus.Active  # unchanged

    # The retry on the next scheduled run completes and expires the past-due record.
    retry_session = _TxSession()
    real_service = MappingService(
        session=retry_session,  # type: ignore[arg-type]
        mapping_repo=repo,  # type: ignore[arg-type]
        vendor_repo=object(),  # type: ignore[arg-type]  # unused on expiry path
        customer_repo=object(),  # type: ignore[arg-type]
    )
    expired = asyncio.run(
        mapping_tasks.expire_due_mappings(
            today,
            session_factory=lambda: retry_session,
            service_builder=lambda _s: real_service,
        )
    )

    assert expired == 1
    assert retry_session.committed is True
    assert repo.store[past.id].status is MappingStatus.Expired
