# Feature: lacm-masters, Property 20: Vendor required-field, format, and uniqueness validation.
"""Property-based test for Vendor required-field, format, and uniqueness validation.

Property 20: Vendor required-field, format, and uniqueness validation.

**Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6**

For any create/update-vendor request, the :class:`VendorService` rejects the
request and persists/modifies nothing when:

* Vendor Code, Vendor Name, or Vendor Email is missing or empty (Req 6.2),
* Vendor Code duplicates an existing vendor (Req 6.3),
* Vendor Email duplicates an existing vendor (Req 6.4),
* Vendor Email is not valid email format (Req 6.5),
* GSTN Number is present and does not match ``[A-Z0-9]{15}`` (Req 6.6).

The service is exercised against real in-memory implementations of
``IVendorRepository`` and ``IUserRepository`` (fakes, not mocks), so the
property validates the actual service logic end-to-end through the ports. Each
Hypothesis example drives the async service via ``asyncio.run`` so examples
remain isolated.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.exceptions.application_exceptions import (
    MasterConflictError,
    MasterValidationError,
)
from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
    VendorUpdateInput,
)
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.repositories.masters.vendor_repository import IVendorRepository
from src.domain.repositories.user_repository import IUserRepository

# ─── Valid baseline values (each comfortably valid for its field) ───
_VALID_CODE = "VND001"
_VALID_NAME = "Valid Vendor Pvt Ltd"
_VALID_EMAIL = "vendor@example.com"
_VALID_GSTN = "27ABCDE1234F1Z5"  # 15 uppercase alphanumeric chars


class FakeVendorRepository(IVendorRepository):
    """In-memory ``IVendorRepository`` performing trimmed uniqueness matching."""

    def __init__(self) -> None:
        self._store: dict[UUID, VendorEntity] = {}

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._store.get(vendor_id)

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        target = vendor_code.strip()
        for v in self._store.values():
            if v.vendor_code.strip() == target:
                return v
        return None

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        target = vendor_email.strip()
        for v in self._store.values():
            if v.vendor_email.strip() == target:
                return v
        return None

    async def create(self, vendor: VendorEntity) -> VendorEntity:
        self._store[vendor.id] = vendor
        return vendor

    async def update(self, vendor: VendorEntity) -> VendorEntity:
        self._store[vendor.id] = vendor
        return vendor

    async def delete(self, vendor_id: UUID) -> None:
        self._store.pop(vendor_id, None)

    async def list_all(
        self, skip: int = 0, limit: int = 20
    ) -> list[VendorEntity]:
        return list(self._store.values())[skip : skip + limit]

    async def count_all(self) -> int:
        return len(self._store)

    async def exists_by_code(self, vendor_code: str) -> bool:
        target = vendor_code.strip()
        return any(v.vendor_code.strip() == target for v in self._store.values())

    async def exists_by_email(self, vendor_email: str) -> bool:
        target = vendor_email.strip()
        return any(
            v.vendor_email.strip() == target for v in self._store.values()
        )

    @property
    def count(self) -> int:
        return len(self._store)

    def snapshot(self) -> dict[UUID, tuple]:
        """Field-level snapshot used to assert no record was modified."""
        return {
            vid: (
                v.vendor_code,
                v.vendor_name,
                v.vendor_email,
                v.gstn_number,
                v.status,
            )
            for vid, v in self._store.items()
        }


class FakeUserRepository(IUserRepository):
    """In-memory ``IUserRepository`` sufficient for portal provisioning."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        for u in self._store.values():
            if u.username == username:
                return u
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

    async def get_by_email(self, email: str) -> User | None:
        return None

    async def exists_by_username(self, username: str) -> bool:
        return any(u.username == username for u in self._store.values())


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


# ─── Strategies ───

# Missing / empty / whitespace-only values for a required field (Req 6.2).
_blank_values = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n\r\f\v", min_size=1, max_size=6),
)

# Strings that cannot be valid emails: a single token with no '@' at all.
_bad_emails = st.one_of(
    st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20),
    st.sampled_from(["plainaddress", "missing-at.example.com", "a@b", "@no-local.com"]),
)

# GSTN values that are present but violate ``[A-Z0-9]{15}``: lowercase letters
# (wrong case) and/or the wrong length, but never empty (empty is not validated).
_bad_gstn = st.one_of(
    st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=14),
    st.text(alphabet=string.ascii_uppercase + string.digits, min_size=1, max_size=14),
    st.text(alphabet=string.ascii_uppercase + string.digits, min_size=16, max_size=25),
    st.sampled_from(["abcde1234f1z5gh", "27ABCDE1234F1Z5!", "lowercase123456"]),
)


@st.composite
def rejection_cases(draw: st.DrawFn) -> dict:
    """Produce one rejection scenario describing the trigger and its value.

    Returns a dict with keys:
      * ``trigger`` — one of ``required_missing``/``duplicate``/``bad_email``/
        ``bad_gstn``,
      * ``field`` — the offending field name,
      * ``value`` — the invalid value (for create) where applicable,
      * ``error`` — the expected exception type.
    """
    trigger = draw(
        st.sampled_from(
            ["required_missing", "duplicate", "bad_email", "bad_gstn"]
        )
    )
    if trigger == "required_missing":
        field = draw(
            st.sampled_from(["vendor_code", "vendor_name", "vendor_email"])
        )
        return {
            "trigger": trigger,
            "field": field,
            "value": draw(_blank_values),
            "error": MasterValidationError,
        }
    if trigger == "duplicate":
        field = draw(st.sampled_from(["vendor_code", "vendor_email"]))
        return {"trigger": trigger, "field": field, "error": MasterConflictError}
    if trigger == "bad_email":
        return {
            "trigger": trigger,
            "field": "vendor_email",
            "value": draw(_bad_emails),
            "error": MasterValidationError,
        }
    return {
        "trigger": trigger,
        "field": "gstn_number",
        "value": draw(_bad_gstn),
        "error": MasterValidationError,
    }


def _build_service() -> tuple[VendorService, FakeVendorRepository, FakeUserRepository]:
    vendor_repo = FakeVendorRepository()
    user_repo = FakeUserRepository()
    service = VendorService(
        session=None,  # type: ignore[arg-type]
        vendor_repo=vendor_repo,
        user_repo=user_repo,
    )
    return service, vendor_repo, user_repo


def _create_input(field: str, value: object) -> VendorCreateInput:
    """A create payload with all fields valid except ``field`` set to ``value``."""
    kwargs: dict[str, object] = {
        "vendor_code": _VALID_CODE,
        "vendor_name": _VALID_NAME,
        "vendor_email": _VALID_EMAIL,
        "gstn_number": _VALID_GSTN,
    }
    kwargs[field] = value
    return VendorCreateInput(**kwargs)  # type: ignore[arg-type]


async def _assert_create_rejected(case: dict) -> None:
    service, vendor_repo, user_repo = _build_service()
    actor = _actor()

    if case["trigger"] == "duplicate":
        # Seed a valid vendor whose code/email the second create will duplicate.
        await service.create_vendor(
            VendorCreateInput(
                vendor_code=_VALID_CODE,
                vendor_name=_VALID_NAME,
                vendor_email=_VALID_EMAIL,
            ),
            actor,
        )
        assert vendor_repo.count == 1
        before = vendor_repo.snapshot()

        # The second create duplicates exactly one unique field; the other is
        # kept distinct so the conflict is attributable to the field under test.
        if case["field"] == "vendor_code":
            payload = VendorCreateInput(
                vendor_code=_VALID_CODE,
                vendor_name="Another Vendor",
                vendor_email="other@example.com",
            )
        else:
            payload = VendorCreateInput(
                vendor_code="VND999",
                vendor_name="Another Vendor",
                vendor_email=_VALID_EMAIL,
            )

        with pytest.raises(case["error"]):
            await service.create_vendor(payload, actor)

        # No second vendor stored and the seeded record is untouched.
        assert vendor_repo.count == 1
        assert vendor_repo.snapshot() == before
        return

    # required_missing / bad_email / bad_gstn — nothing seeded.
    with pytest.raises(case["error"]) as exc:
        await service.create_vendor(_create_input(case["field"], case["value"]), actor)

    if case["error"] is MasterValidationError:
        assert exc.value.field == case["field"]
    # Nothing persisted: neither a vendor nor a portal-login user.
    assert vendor_repo.count == 0
    assert user_repo._store == {}


async def _assert_update_rejected(case: dict) -> None:
    # Update path applies to email format (6.5), GSTN format (6.6), required
    # non-empty (6.2 — empty supplied value), and uniqueness (6.3, 6.4).
    service, vendor_repo, _ = _build_service()
    actor = _actor()

    seeded = await service.create_vendor(
        VendorCreateInput(
            vendor_code=_VALID_CODE,
            vendor_name=_VALID_NAME,
            vendor_email=_VALID_EMAIL,
            gstn_number=_VALID_GSTN,
        ),
        actor,
    )

    if case["trigger"] == "duplicate":
        # A second valid vendor whose unique field the update will collide with.
        other = await service.create_vendor(
            VendorCreateInput(
                vendor_code="VND999",
                vendor_name="Other Vendor",
                vendor_email="other@example.com",
            ),
            actor,
        )
        before = vendor_repo.snapshot()
        if case["field"] == "vendor_code":
            patch = VendorUpdateInput(vendor_code=other.vendor_code)
        else:
            patch = VendorUpdateInput(vendor_email=other.vendor_email)

        with pytest.raises(case["error"]):
            await service.update_vendor(seeded.id, patch, actor)

        assert vendor_repo.snapshot() == before
        return

    before = vendor_repo.snapshot()
    if case["field"] == "vendor_code":
        patch = VendorUpdateInput(vendor_code=case["value"])  # type: ignore[arg-type]
    elif case["field"] == "vendor_name":
        patch = VendorUpdateInput(vendor_name=case["value"])  # type: ignore[arg-type]
    elif case["field"] == "vendor_email":
        patch = VendorUpdateInput(vendor_email=case["value"])  # type: ignore[arg-type]
    else:
        patch = VendorUpdateInput(gstn_number=case["value"])  # type: ignore[arg-type]

    with pytest.raises(case["error"]) as exc:
        await service.update_vendor(seeded.id, patch, actor)

    if case["error"] is MasterValidationError:
        assert exc.value.field == case["field"]
    # No record was modified.
    assert vendor_repo.snapshot() == before


# ``deadline=None``: valid create/seed paths provision a portal-login user via
# the real (intentionally slow) bcrypt password hasher, so per-example timing is
# not a meaningful signal for this validation property.
@settings(max_examples=20, deadline=None)
@given(case=rejection_cases())
def test_vendor_required_field_format_and_uniqueness_validation(case: dict) -> None:
    """Invalid vendor create/update requests are rejected and persist nothing.

    Covers every Requirement 6.2–6.6 rejection trigger across both the create
    and the partial-update paths: a violating request must raise the
    appropriate master error and leave the vendor store unchanged.
    """
    asyncio.run(_assert_create_rejected(case))
    asyncio.run(_assert_update_rejected(case))
