"""
Unit tests for VendorService (CRUD, portal provisioning, deactivation).

Uses lightweight in-memory fakes for the Vendor and User repositories so the
service's business rules are exercised against real logic (no mocking of the
behaviour under test). Covers Requirements 6.2–6.11 and 7.1–7.6.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterNotFoundError,
    MasterValidationError,
)
from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
    VendorUpdateInput,
)
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.enums.masters import VendorStatus
from src.infrastructure.security.password_encoder import verify_password

# ─── In-memory fakes ───


class FakeVendorRepository:
    """Minimal in-memory IVendorRepository for service unit tests."""

    def __init__(self) -> None:
        self._store: dict[UUID, VendorEntity] = {}

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._store.get(vendor_id)

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        target = vendor_code.strip().lower()
        for v in self._store.values():
            if v.vendor_code.strip().lower() == target:
                return v
        return None

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        target = vendor_email.strip().lower()
        for v in self._store.values():
            if v.vendor_email.strip().lower() == target:
                return v
        return None

    async def create(self, vendor: VendorEntity) -> VendorEntity:
        self._store[vendor.id] = vendor
        return vendor

    async def update(self, vendor: VendorEntity) -> VendorEntity:
        if vendor.id not in self._store:
            raise ValueError("Vendor not found")
        self._store[vendor.id] = vendor
        return vendor

    async def delete(self, vendor_id: UUID) -> None:
        self._store.pop(vendor_id, None)

    async def list_all(self, skip: int = 0, limit: int = 20) -> list[VendorEntity]:
        ordered = sorted(self._store.values(), key=lambda v: v.created_date)
        return ordered[skip : skip + limit]

    async def count_all(self) -> int:
        return len(self._store)

    async def exists_by_code(self, vendor_code: str) -> bool:
        return await self.get_by_code(vendor_code) is not None

    async def exists_by_email(self, vendor_email: str) -> bool:
        return await self.get_by_email(vendor_email) is not None


class FakeUserRepository:
    """Minimal in-memory IUserRepository for service unit tests."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        for u in self._store.values():
            if u.username.lower() == username.lower():
                return u
        return None

    async def get_by_email(self, email: str) -> User | None:
        return None

    async def create(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def delete(self, user_id: UUID) -> None:
        self._store.pop(user_id, None)

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return list(self._store.values())[skip : skip + limit]

    async def exists_by_username(self, username: str) -> bool:
        return await self.get_by_username(username) is not None


class RecordingInvalidator:
    """Session invalidator that records the user ids it was asked to invalidate."""

    def __init__(self) -> None:
        self.invalidated: list[UUID] = []

    async def invalidate_user_sessions(self, user_id: UUID) -> None:
        self.invalidated.append(user_id)


class FailingInvalidator:
    """Session invalidator that always raises, to test best-effort tolerance."""

    async def invalidate_user_sessions(self, user_id: UUID) -> None:
        raise RuntimeError("session store unavailable")


# ─── Fixtures ───


@pytest.fixture
def actor() -> User:
    return User(id=uuid4(), username="admin", password_hash="x", is_active=True)


@pytest.fixture
def vendor_repo() -> FakeVendorRepository:
    return FakeVendorRepository()


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


def _service(vendor_repo, user_repo, invalidator=None) -> VendorService:
    return VendorService(
        session=None,  # type: ignore[arg-type]  # unused by the fakes
        vendor_repo=vendor_repo,
        user_repo=user_repo,
        session_invalidator=invalidator,
    )


def _valid_input(**overrides) -> VendorCreateInput:
    base = dict(
        vendor_code="V001",
        vendor_name="Acme Liaisons",
        vendor_email="contact@acme.example",
    )
    base.update(overrides)
    return VendorCreateInput(**base)


# ─── Create: defaults + portal provisioning (Req 6.7, 6.8) ───


async def test_create_defaults_status_active_and_provisions_portal(
    vendor_repo, user_repo, actor
):
    service = _service(vendor_repo, user_repo)

    vendor = await service.create_vendor(_valid_input(), actor)

    assert vendor.status is VendorStatus.Active
    assert vendor.portal_user_id is not None

    portal = await user_repo.get_by_id(vendor.portal_user_id)
    assert portal is not None
    assert portal.username == "V001"
    assert portal.is_validate_ad is False
    assert portal.is_active is True
    # Default password is set (and hashed, not stored in plain text).
    assert portal.password_hash != ""
    assert verify_password("ChangeMe@123", portal.password_hash)


# ─── Create: required-field validation (Req 6.2) ───


@pytest.mark.parametrize("field", ["vendor_code", "vendor_name", "vendor_email"])
async def test_create_rejects_missing_required_field(
    vendor_repo, user_repo, actor, field
):
    service = _service(vendor_repo, user_repo)

    with pytest.raises(MasterValidationError) as exc:
        await service.create_vendor(_valid_input(**{field: "   "}), actor)

    assert exc.value.field == field
    assert await vendor_repo.count_all() == 0
    # No partial portal user written either.
    assert await user_repo.list_all() == []


# ─── Create: email-format validation (Req 6.5) ───


async def test_create_rejects_invalid_email(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)

    with pytest.raises(MasterValidationError) as exc:
        await service.create_vendor(_valid_input(vendor_email="not-an-email"), actor)

    assert exc.value.field == "vendor_email"
    assert await vendor_repo.count_all() == 0


# ─── Create: GSTN-format validation (Req 6.6) ───


@pytest.mark.parametrize("bad_gstn", ["short", "lowercase000001", "1234567890123456"])
async def test_create_rejects_invalid_gstn(vendor_repo, user_repo, actor, bad_gstn):
    service = _service(vendor_repo, user_repo)

    with pytest.raises(MasterValidationError) as exc:
        await service.create_vendor(_valid_input(gstn_number=bad_gstn), actor)

    assert exc.value.field == "gstn_number"
    assert await vendor_repo.count_all() == 0


async def test_create_accepts_valid_gstn(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    vendor = await service.create_vendor(
        _valid_input(gstn_number="27ABCDE1234F1Z5"), actor
    )
    assert vendor.gstn_number == "27ABCDE1234F1Z5"


# ─── Create: uniqueness (Req 6.3, 6.4) ───


async def test_create_rejects_duplicate_code_case_insensitive(
    vendor_repo, user_repo, actor
):
    service = _service(vendor_repo, user_repo)
    await service.create_vendor(_valid_input(), actor)

    with pytest.raises(MasterConflictError):
        await service.create_vendor(
            _valid_input(vendor_code="v001", vendor_email="other@acme.example"),
            actor,
        )
    assert await vendor_repo.count_all() == 1


async def test_create_rejects_duplicate_email_case_insensitive(
    vendor_repo, user_repo, actor
):
    service = _service(vendor_repo, user_repo)
    await service.create_vendor(_valid_input(), actor)

    with pytest.raises(MasterConflictError):
        await service.create_vendor(
            _valid_input(vendor_code="V002", vendor_email="CONTACT@acme.example"),
            actor,
        )
    assert await vendor_repo.count_all() == 1


async def test_create_rejects_when_portal_username_taken(
    vendor_repo, user_repo, actor
):
    # Pre-existing application user occupying the would-be portal username.
    await user_repo.create(
        User(id=uuid4(), username="V001", password_hash="x", is_active=True)
    )
    service = _service(vendor_repo, user_repo)

    with pytest.raises(MasterConflictError):
        await service.create_vendor(_valid_input(), actor)
    assert await vendor_repo.count_all() == 0


# ─── Read (Req 6.9, 6.10) ───


async def test_get_returns_existing_vendor(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    created = await service.create_vendor(_valid_input(), actor)

    fetched = await service.get_vendor(created.id)
    assert fetched.id == created.id


async def test_get_unknown_id_raises_not_found(vendor_repo, user_repo):
    service = _service(vendor_repo, user_repo)
    with pytest.raises(MasterNotFoundError):
        await service.get_vendor(uuid4())


# ─── Update (partial + validation) ───


async def test_update_applies_only_supplied_fields(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    created = await service.create_vendor(
        _valid_input(vendor_name="Old Name", bank_name="Old Bank"), actor
    )

    updated = await service.update_vendor(
        created.id, VendorUpdateInput(vendor_name="New Name"), actor
    )

    assert updated.vendor_name == "New Name"
    assert updated.bank_name == "Old Bank"  # untouched
    assert updated.vendor_code == created.vendor_code


async def test_update_rejects_invalid_email(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    created = await service.create_vendor(_valid_input(), actor)

    with pytest.raises(MasterValidationError):
        await service.update_vendor(
            created.id, VendorUpdateInput(vendor_email="bad"), actor
        )


async def test_update_unknown_id_raises_not_found(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    with pytest.raises(MasterNotFoundError):
        await service.update_vendor(uuid4(), VendorUpdateInput(vendor_name="X"), actor)


async def test_update_rejects_duplicate_email_of_other_vendor(
    vendor_repo, user_repo, actor
):
    service = _service(vendor_repo, user_repo)
    await service.create_vendor(
        _valid_input(vendor_code="V001", vendor_email="a@x.example"), actor
    )
    second = await service.create_vendor(
        _valid_input(vendor_code="V002", vendor_email="b@x.example"), actor
    )

    with pytest.raises(MasterConflictError):
        await service.update_vendor(
            second.id, VendorUpdateInput(vendor_email="a@x.example"), actor
        )


async def test_update_same_email_on_same_vendor_is_allowed(
    vendor_repo, user_repo, actor
):
    service = _service(vendor_repo, user_repo)
    created = await service.create_vendor(_valid_input(), actor)

    updated = await service.update_vendor(
        created.id,
        VendorUpdateInput(vendor_email=created.vendor_email, vendor_name="Renamed"),
        actor,
    )
    assert updated.vendor_name == "Renamed"


# ─── List / pagination (Req 6.11) ───


async def test_list_returns_slice_and_full_total(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    for i in range(5):
        await service.create_vendor(
            _valid_input(vendor_code=f"V{i}", vendor_email=f"v{i}@x.example"), actor
        )

    items, total = await service.list_vendors(skip=1, limit=2)
    assert total == 5
    assert len(items) == 2


# ─── Deactivation (Req 7.1, 7.2, 7.3, 7.4, 7.6) ───


async def test_deactivate_unknown_id_raises_not_found(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    with pytest.raises(MasterNotFoundError):
        await service.deactivate_vendor(uuid4(), actor)


async def test_deactivate_sets_inactive_and_blocks_portal_login(
    vendor_repo, user_repo, actor
):
    invalidator = RecordingInvalidator()
    service = _service(vendor_repo, user_repo, invalidator)
    created = await service.create_vendor(_valid_input(), actor)

    result = await service.deactivate_vendor(created.id, actor)

    assert result.status is VendorStatus.Inactive
    portal = await user_repo.get_by_id(created.portal_user_id)
    assert portal is not None
    assert portal.is_active is False  # blocks login
    assert invalidator.invalidated == [created.portal_user_id]


async def test_deactivate_completes_when_session_invalidation_fails(
    vendor_repo, user_repo, actor
):
    service = _service(vendor_repo, user_repo, FailingInvalidator())
    created = await service.create_vendor(_valid_input(), actor)

    # Must not raise even though invalidation throws (Req 7.4).
    result = await service.deactivate_vendor(created.id, actor)

    assert result.status is VendorStatus.Inactive
    portal = await user_repo.get_by_id(created.portal_user_id)
    assert portal.is_active is False


async def test_deactivate_preserves_vendor_record_fields(vendor_repo, user_repo, actor):
    service = _service(vendor_repo, user_repo)
    created = await service.create_vendor(
        _valid_input(vendor_name="Acme", bank_name="HDFC"), actor
    )

    result = await service.deactivate_vendor(created.id, actor)

    # Only status (and audit) change; descriptive data is preserved (Req 7.6).
    assert result.vendor_name == "Acme"
    assert result.bank_name == "HDFC"
    assert result.vendor_code == created.vendor_code
    assert result.portal_user_id == created.portal_user_id
