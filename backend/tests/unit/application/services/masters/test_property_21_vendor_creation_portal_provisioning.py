# Feature: lacm-masters, Property 21: Valid vendor creation defaults status and provisions portal login.
"""Property-based test for valid vendor creation and portal-login provisioning.

Property 21: Valid vendor creation defaults status and provisions portal login.

**Validates: Requirements 6.7, 6.8**

*For any* valid create-vendor request, the stored Vendor has Status ``Active``
(Req 6.7), a portal-login user exists whose username equals the Vendor Code with
a system-set default password, and the Vendor's Portal User reference points to
that user (Req 6.8).

The service is exercised end-to-end through ``VendorService.create_vendor`` using
lightweight, real in-memory stand-ins (not mocks) for the Vendor repository and
the User repository. A fresh service/repository set is built per generated
example so single-create uniqueness always holds and no state leaks between
examples. The async service is driven with ``asyncio.run`` because each
Hypothesis example is independent.

Generation builds a single valid create-vendor request (a non-empty, trimmed,
length-bounded Vendor Code / Vendor Name, a format-valid Vendor Email, and an
optional well-formed GSTN) and omits Status so the service must apply the
``Active`` default. The test asserts the stored Vendor's Status, the existence of
a portal user whose username equals the trimmed Vendor Code, that the portal
user's stored password verifies against the system default, and that the
Vendor's ``portal_user_id`` references exactly that user.
"""

from __future__ import annotations

import asyncio
import string
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.services.masters.vendor_service import (
    VendorCreateInput,
    VendorService,
)
from src.config.settings import settings as app_settings
from src.domain.entities.masters.vendor import VendorEntity
from src.domain.entities.user import User
from src.domain.enums.masters import VendorStatus
from src.domain.repositories.masters.vendor_repository import IVendorRepository
from src.infrastructure.security.password_encoder import verify_password

_MAX_VENDOR_CODE_LEN = 50
_MAX_VENDOR_NAME_LEN = 255

_alnum = string.ascii_letters + string.digits


# ─── Real in-memory repositories (duck-typed against the ports) ───


class _InMemoryVendorRepository(IVendorRepository):
    """Dict-backed Vendor repository sufficient for the create round-trip."""

    def __init__(self) -> None:
        self._store: dict[UUID, VendorEntity] = {}

    async def get_by_id(self, vendor_id: UUID) -> VendorEntity | None:
        return self._store.get(vendor_id)

    async def get_by_code(self, vendor_code: str) -> VendorEntity | None:
        target = vendor_code.strip().lower()
        return next(
            (v for v in self._store.values()
             if v.vendor_code.strip().lower() == target),
            None,
        )

    async def get_by_email(self, vendor_email: str) -> VendorEntity | None:
        target = vendor_email.strip().lower()
        return next(
            (v for v in self._store.values()
             if v.vendor_email.strip().lower() == target),
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

    async def list_all(
        self, skip: int = 0, limit: int = 20
    ) -> list[VendorEntity]:
        return list(self._store.values())[skip : skip + limit]

    async def count_all(self) -> int:
        return len(self._store)

    async def exists_by_code(self, vendor_code: str) -> bool:
        return await self.get_by_code(vendor_code) is not None

    async def exists_by_email(self, vendor_email: str) -> bool:
        return await self.get_by_email(vendor_email) is not None


class _InMemoryUserRepository:
    """Dict-backed User repository capturing provisioned portal users."""

    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return next(
            (u for u in self._store.values() if u.username == username), None
        )

    async def create(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def exists_by_username(self, username: str) -> bool:
        return any(u.username == username for u in self._store.values())

    def all_users(self) -> list[User]:
        return list(self._store.values())


def _actor() -> User:
    return User(id=uuid4(), username="admin", is_active=True)


# ─── Generators for a single valid create-vendor request ───

# Vendor Code / Vendor Name: alphanumeric tokens that are non-empty after the
# service trims them and stay within the persisted length caps.
_codes = st.text(alphabet=_alnum, min_size=1, max_size=_MAX_VENDOR_CODE_LEN)
_names = st.text(alphabet=_alnum + " ", min_size=1, max_size=_MAX_VENDOR_NAME_LEN).filter(
    lambda s: s.strip() != ""
)

# Email parts: no '@' and no whitespace, satisfying ``^[^@\s]+@[^@\s]+\.[^@\s]+$``.
_email_part = st.text(alphabet=_alnum, min_size=1, max_size=20)
_emails = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    _email_part,
    _email_part,
    st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=5),
)

# GSTN: absent, or exactly 15 uppercase-alphanumeric characters (Req 6.6 format).
_gstn = st.none() | st.text(
    alphabet=string.ascii_uppercase + string.digits, min_size=15, max_size=15
)


# ``deadline=None``: provisioning the portal user runs a deliberately-slow bcrypt
# password hash per example, which exceeds the default 200ms per-example deadline
# without indicating any property violation.
@settings(max_examples=20, deadline=None)
@given(
    vendor_code=_codes,
    vendor_name=_names,
    vendor_email=_emails,
    gstn_number=_gstn,
)
def test_valid_vendor_creation_defaults_status_and_provisions_portal(
    vendor_code: str,
    vendor_name: str,
    vendor_email: str,
    gstn_number: str | None,
) -> None:
    """Creating a valid Vendor defaults Status Active and provisions the portal login.

    The request omits Status so the service must apply the ``Active`` default
    (Req 6.7). A portal-login user must be provisioned whose username equals the
    (trimmed) Vendor Code, carrying the system-default password, and the stored
    Vendor's ``portal_user_id`` must reference exactly that user (Req 6.8).
    """

    async def scenario() -> tuple[VendorEntity, _InMemoryUserRepository]:
        vendor_repo = _InMemoryVendorRepository()
        user_repo = _InMemoryUserRepository()
        service = VendorService(
            session=None,  # type: ignore[arg-type]
            vendor_repo=vendor_repo,  # type: ignore[arg-type]
            user_repo=user_repo,  # type: ignore[arg-type]
        )

        created = await service.create_vendor(
            VendorCreateInput(
                vendor_code=vendor_code,
                vendor_name=vendor_name,
                vendor_email=vendor_email,
                gstn_number=gstn_number,
                # status omitted → service applies the Active default.
            ),
            _actor(),
        )
        return created, user_repo

    vendor, user_repo = asyncio.run(scenario())
    expected_code = vendor_code.strip()

    # Status defaults to Active on create (Req 6.7).
    assert vendor.status is VendorStatus.Active

    # Exactly one portal user was provisioned, with username == Vendor Code (Req 6.8).
    users = user_repo.all_users()
    assert len(users) == 1
    portal_user = users[0]
    assert portal_user.username == expected_code
    assert vendor.vendor_code == expected_code

    # The portal user carries the system-default password (Req 6.8).
    assert verify_password(
        app_settings.VENDOR_PORTAL_DEFAULT_PASSWORD, portal_user.password_hash
    )
    # The portal user can authenticate (active, not blocked).
    assert portal_user.can_authenticate() is True

    # The Vendor's Portal User reference points to that provisioned user (Req 6.8).
    assert vendor.portal_user_id == portal_user.id
