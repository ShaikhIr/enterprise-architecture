# Feature: lacm-masters, Property 22: Deactivation sets Inactive and preserves related data.
"""Property-based test for Vendor deactivation.

Property 22: Deactivation sets Inactive and preserves related data.

**Validates: Requirements 7.2, 7.6**

Requirement 7.2: WHEN a deactivate-vendor request is received for an existing
Vendor, THE Vendor_Service SHALL set the Vendor Status to ``Inactive``.

Requirement 7.6: WHEN a Vendor Status is set to ``Inactive``, THE Vendor_Service
SHALL preserve all of the Vendor's existing records unchanged.

For *any* existing active Vendor, deactivation:

* sets the Vendor Status to ``Inactive`` (Req 7.2),
* blocks the provisioned portal user from logging in by clearing ``is_active``
  on that user (part of the deactivation contract, Req 7.3), and
* leaves all of the Vendor's descriptive records unchanged — vendor code, name,
  email, contact, address, GSTN, PAN, bank details, identity, and the portal
  user reference are all exactly what they were before deactivation (Req 7.6).

The service (:class:`VendorService`) is exercised end-to-end through real
in-memory implementations of ``IVendorRepository`` and ``IUserRepository`` (not
mocks), so the property validates the service's contract through its ports. A
recording session invalidator confirms the portal user's sessions are targeted
for invalidation without coupling the test to a concrete session store.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
)
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.enums.masters import VendorStatus


# ─── In-memory ports (mirroring the production adapters' relevant semantics) ───


class _InMemoryVendorRepository:
    """In-memory ``IVendorRepository`` for the deactivation property."""

    def __init__(self) -> None:
        self._store: dict[UUID, VendorEntity] = {}

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._store.get(vendor_id)

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        target = vendor_code.strip().lower()
        return next(
            (v for v in self._store.values() if v.vendor_code.strip().lower() == target),
            None,
        )

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        target = vendor_email.strip().lower()
        return next(
            (
                v
                for v in self._store.values()
                if v.vendor_email.strip().lower() == target
            ),
            None,
        )

    async def create(self, vendor: VendorEntity) -> VendorEntity:
        self._store[vendor.id] = vendor
        return vendor

    async def update(self, vendor: VendorEntity) -> VendorEntity:
        self._store[vendor.id] = vendor
        return vendor

    async def delete(self, vendor_id: UUID) -> None:
        self._store.pop(vendor_id, None)

    async def list_all(self, skip: int = 0, limit: int = 20) -> list[VendorEntity]:
        return list(self._store.values())[skip : skip + limit]

    async def count_all(self) -> int:
        return len(self._store)

    async def exists_by_code(self, vendor_code: str) -> bool:
        return await self.get_by_code(vendor_code) is not None

    async def exists_by_email(self, vendor_email: str) -> bool:
        return await self.get_by_email(vendor_email) is not None


class _InMemoryUserRepository:
    """In-memory ``IUserRepository`` for the deactivation property."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return next(
            (u for u in self._store.values() if u.username.lower() == username.lower()),
            None,
        )

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


class _RecordingInvalidator:
    """Records portal-user ids whose sessions were asked to be invalidated."""

    def __init__(self) -> None:
        self.invalidated: list[UUID] = []

    async def invalidate_user_sessions(self, user_id: UUID) -> None:
        self.invalidated.append(user_id)


def _actor() -> User:
    return User(id=uuid4(), username="admin", password_hash="x", is_active=True)


# ─── Smart generators constrained to the Vendor input space ───

# Characters safe for a vendor code / name (no leading/trailing whitespace issues
# and no '@'/whitespace that would break the email tokens we reuse them for).
_token_chars = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=122).filter(
        lambda c: c.isalnum()
    ),
    min_size=1,
    max_size=20,
)

# Optional free-text fields bounded well within the service's max-length limits.
_optional_text = st.one_of(st.none(), st.text(min_size=0, max_size=15))

# GSTN: either omitted or a valid 15-char uppercase-alphanumeric string (Req 6.6).
_gstn = st.one_of(
    st.none(),
    st.text(
        alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        min_size=15,
        max_size=15,
    ),
)


@st.composite
def _vendor_inputs(draw: st.DrawFn) -> VendorCreateInput:
    """Generate a valid create-vendor payload spanning the optional fields."""
    code = draw(_token_chars)
    name = draw(st.text(min_size=1, max_size=50).map(str.strip).filter(bool))
    local = draw(_token_chars)
    domain = draw(_token_chars)
    tld = draw(st.sampled_from(["com", "example", "org", "io"]))
    email = f"{local}@{domain}.{tld}"

    return VendorCreateInput(
        vendor_code=code,
        vendor_name=name,
        vendor_email=email,
        vendor_contact=draw(st.one_of(st.none(), st.text(min_size=0, max_size=15))),
        vendor_address=draw(_optional_text),
        gstn_number=draw(_gstn),
        pan_number=draw(st.one_of(st.none(), st.text(min_size=0, max_size=10))),
        bank_account_no=draw(st.one_of(st.none(), st.text(min_size=0, max_size=20))),
        bank_ifsc=draw(st.one_of(st.none(), st.text(min_size=0, max_size=11))),
        bank_name=draw(_optional_text),
        status=VendorStatus.Active,
    )


# A snapshot of every descriptive (non-status, non-audit) field on a vendor.
def _descriptive_snapshot(vendor: VendorEntity) -> dict[str, object]:
    return {
        "id": vendor.id,
        "vendor_code": vendor.vendor_code,
        "vendor_name": vendor.vendor_name,
        "vendor_email": vendor.vendor_email,
        "vendor_contact": vendor.vendor_contact,
        "vendor_address": vendor.vendor_address,
        "gstn_number": vendor.gstn_number,
        "pan_number": vendor.pan_number,
        "bank_account_no": vendor.bank_account_no,
        "bank_ifsc": vendor.bank_ifsc,
        "bank_name": vendor.bank_name,
        "portal_user_id": vendor.portal_user_id,
        "created_by": vendor.created_by,
        "created_date": vendor.created_date,
    }


# ``deadline=None``: creating a Vendor provisions a portal user whose password is
# hashed with bcrypt (intentionally slow). That cost is incidental to this
# property, so the per-example deadline is disabled to avoid flaky timing.
@settings(max_examples=20, deadline=None)
@given(data=_vendor_inputs())
def test_deactivation_sets_inactive_and_preserves_related_data(
    data: VendorCreateInput,
) -> None:
    """Deactivating an active Vendor flips status, blocks login, preserves records.

    An active Vendor (with a provisioned portal user) is created via the service.
    A descriptive snapshot is taken, then the Vendor is deactivated. The result
    MUST have Status ``Inactive`` (Req 7.2), the portal user MUST be blocked from
    logging in (``is_active`` cleared), and every descriptive field MUST be
    byte-for-byte identical to the pre-deactivation snapshot (Req 7.6).
    """

    async def scenario() -> None:
        vendor_repo = _InMemoryVendorRepository()
        user_repo = _InMemoryUserRepository()
        invalidator = _RecordingInvalidator()
        service = VendorService(
            session=None,  # type: ignore[arg-type]  # unused by the in-memory ports
            vendor_repo=vendor_repo,
            user_repo=user_repo,
            session_invalidator=invalidator,
        )
        actor = _actor()

        created = await service.create_vendor(data, actor)

        # Precondition: the vendor starts Active with a provisioned portal user.
        assert created.status is VendorStatus.Active
        assert created.portal_user_id is not None
        portal_before = await user_repo.get_by_id(created.portal_user_id)
        assert portal_before is not None and portal_before.is_active is True

        before = _descriptive_snapshot(created)

        result = await service.deactivate_vendor(created.id, actor)

        # Req 7.2: status becomes Inactive.
        assert result.status is VendorStatus.Inactive
        # The persisted record reflects the same.
        persisted = await vendor_repo.get_by_id(created.id)
        assert persisted is not None and persisted.status is VendorStatus.Inactive

        # Portal login is blocked and its sessions targeted for invalidation.
        portal_after = await user_repo.get_by_id(created.portal_user_id)
        assert portal_after is not None and portal_after.is_active is False
        assert invalidator.invalidated == [created.portal_user_id]

        # Req 7.6: every descriptive field is preserved unchanged.
        assert _descriptive_snapshot(result) == before

    asyncio.run(scenario())
