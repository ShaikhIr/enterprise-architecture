"""
In-memory fakes for the user repository ports.

Hand-written and dict-backed, like `master_fakes.py`: reads return deep copies so a caller
mutating a returned entity changes nothing until it calls `update`, and `create` stamps the
sentinel id 0 with a distinct fake id the way the database autoincrement would.
"""

import copy
import itertools
from datetime import datetime

from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.user import User
from src.domain.entities.user_details import UserDetails
from src.domain.repositories.refresh_token_repository import IRefreshTokenRepository
from src.domain.repositories.user_details_repository import IUserDetailsRepository
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.external.employee_ad.employee_ad_client import EmployeeValidationResult

# Module-level so ids stay unique across every fake and every test.
_user_id_seq = itertools.count(1)


def _next_id() -> int:
    return next(_user_id_seq)


class FakeUserRepository(IUserRepository):
    """Dict-backed `IUserRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, User] = {}

    def add(self, user: User) -> User:
        """Seed a row synchronously (test setup helper, not part of the port)."""
        if user.id == 0:
            user.id = _next_id()
        self.rows[user.id] = copy.deepcopy(user)
        return copy.deepcopy(user)

    async def get_by_id(self, user_id: int) -> User | None:
        return copy.deepcopy(self.rows.get(user_id))

    async def get_by_username(self, username: str) -> User | None:
        for row in self.rows.values():
            if row.username == username:
                return copy.deepcopy(row)
        return None

    async def create(self, user: User) -> User:
        return self.add(user)

    async def update(self, user: User) -> User:
        if user.id not in self.rows:
            raise ValueError(f"User {user.id} not found")
        self.rows[user.id] = copy.deepcopy(user)
        return copy.deepcopy(user)

    async def delete(self, user_id: int) -> None:
        self.rows.pop(user_id, None)

    async def list_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        ordered = sorted(self.rows.values(), key=lambda u: u.id)
        return [copy.deepcopy(u) for u in ordered[skip : skip + limit]]

    async def exists_by_username(self, username: str) -> bool:
        return any(row.username == username for row in self.rows.values())


class FakeUserDetailsRepository(IUserDetailsRepository):
    """Dict-backed `IUserDetailsRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, UserDetails] = {}

    def add(self, details: UserDetails) -> UserDetails:
        """Seed a row synchronously (test setup helper, not part of the port)."""
        if details.id == 0:
            details.id = _next_id()
        self.rows[details.id] = copy.deepcopy(details)
        return copy.deepcopy(details)

    async def get_by_user_id(self, user_id: int) -> UserDetails | None:
        for row in self.rows.values():
            if row.user_id == user_id:
                return copy.deepcopy(row)
        return None

    async def get_by_email(self, email: str) -> UserDetails | None:
        wanted = email.strip().lower()
        for row in self.rows.values():
            if row.email.strip().lower() == wanted:
                return copy.deepcopy(row)
        return None

    async def get_many_by_user_ids(self, user_ids: list[int]) -> dict[int, UserDetails]:
        wanted = set(user_ids)
        return {
            row.user_id: copy.deepcopy(row)
            for row in self.rows.values()
            if row.user_id is not None and row.user_id in wanted
        }

    async def create(self, details: UserDetails) -> UserDetails:
        return self.add(details)

    async def update(self, details: UserDetails) -> UserDetails:
        if details.id not in self.rows:
            raise ValueError(f"UserDetails {details.id} not found")
        self.rows[details.id] = copy.deepcopy(details)
        return copy.deepcopy(details)


class FakeRefreshTokenRepository(IRefreshTokenRepository):
    """Dict-backed `IRefreshTokenRepository`, keyed by jti."""

    def __init__(self) -> None:
        self.rows: dict[str, RefreshToken] = {}

    async def create(self, token: RefreshToken) -> RefreshToken:
        if token.id == 0:
            token.id = _next_id()
        self.rows[token.jti] = copy.deepcopy(token)
        return copy.deepcopy(token)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        return copy.deepcopy(self.rows.get(jti))

    async def mark_used(self, jti: str, used_at: datetime) -> bool:
        row = self.rows.get(jti)
        if row is None or row.used_at is not None or row.revoked_at is not None:
            return False
        row.used_at = used_at
        return True

    async def revoke_family(self, family_id: str, revoked_at: datetime) -> None:
        for row in self.rows.values():
            if row.family_id == family_id and row.revoked_at is None:
                row.revoked_at = revoked_at

    async def delete_expired(self, before: datetime) -> int:
        expired = [jti for jti, row in self.rows.items() if row.expires_at < before]
        for jti in expired:
            del self.rows[jti]
        return len(expired)

    def family(self, family_id: str) -> list[RefreshToken]:
        """Every token of one session, oldest first (test inspection helper)."""
        return sorted(
            (copy.deepcopy(r) for r in self.rows.values() if r.family_id == family_id),
            key=lambda r: r.id,
        )


class FakeDirectory:
    """
    Stands in for the corporate directory (Darwin AD).

    Not a repository: it models an external service, so a test sets what it answers or
    raises, and reads back which calls it received.
    """

    def __init__(self) -> None:
        self.valid = True
        self.error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    async def validate_credentials(
        self, employee_id: str, password: str
    ) -> EmployeeValidationResult:
        self.calls.append((employee_id, password))
        if self.error is not None:
            raise self.error
        return EmployeeValidationResult(is_success=True, is_valid_user=self.valid)
