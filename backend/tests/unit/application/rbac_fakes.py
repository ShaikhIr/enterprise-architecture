"""
In-memory fakes for the RBAC-related ports.

Same style as `master_fakes.py` and `user_fakes.py`: hand-written, dict-backed, reads
return deep copies so a caller mutating a returned entity changes nothing until it calls
`update`, and `create` stamps the sentinel id 0 with a distinct fake id the way the
database autoincrement would.

`FakeRoleRepository` reads the role-permission links it owns and resolves them to
`Permission` entities through the `FakePermissionRepository` it is given, because
"which permissions does this role hold" spans both ports. Like the real adapter, a role
read without `with_permissions` carries an empty permission list.
"""

import copy
import itertools
from datetime import datetime

from src.domain.entities.audit_log import AuditLog
from src.domain.entities.role import Permission, PermissionScope, Role, RoleAssignment
from src.domain.repositories.audit_log_repository import IAuditLogRepository
from src.domain.repositories.permission_repository import IPermissionRepository
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.domain.repositories.role_repository import IRoleRepository
from src.domain.services.password_hasher import IPasswordHasher
from src.domain.services.permission_resolver import IPermissionResolver

# Module-level so ids stay unique across every fake and every test.
_fake_id_seq = itertools.count(1)


def _next_fake_id() -> int:
    return next(_fake_id_seq)


class FakePermissionRepository(IPermissionRepository):
    """Dict-backed `IPermissionRepository`."""

    def __init__(self) -> None:
        self.rows: dict[int, Permission] = {}

    def add(self, permission: Permission) -> Permission:
        """Seed a row synchronously (test setup helper, not part of the port)."""
        if permission.id == 0:
            permission.id = _next_fake_id()
        self.rows[permission.id] = copy.deepcopy(permission)
        return copy.deepcopy(permission)

    async def get_by_id(self, permission_id: int) -> Permission | None:
        return copy.deepcopy(self.rows.get(permission_id))

    async def get_by_code(self, code: str) -> Permission | None:
        for row in self.rows.values():
            if row.code == code:
                return copy.deepcopy(row)
        return None

    async def list_active(self, scope: str | None = None) -> list[Permission]:
        rows = [r for r in self.rows.values() if r.is_active]
        if scope is not None:
            rows = [r for r in rows if r.scope == scope]
        rows.sort(key=lambda r: (r.scope, r.resource))
        return [copy.deepcopy(r) for r in rows]

    async def create(self, permission: Permission) -> Permission:
        return self.add(permission)


class FakeRoleRepository(IRoleRepository):
    """Dict-backed `IRoleRepository`, with the role-permission links it owns."""

    def __init__(self, permissions: FakePermissionRepository | None = None) -> None:
        self.rows: dict[int, Role] = {}
        self.links: set[tuple[int, int]] = set()  # (role_id, permission_id)
        self._permissions = permissions or FakePermissionRepository()

    def add(self, role: Role) -> Role:
        """Seed a row synchronously (test setup helper, not part of the port)."""
        if role.id == 0:
            role.id = _next_fake_id()
        stored = copy.deepcopy(role)
        stored.permissions = []  # links, not the entity, own this relationship
        self.rows[role.id] = stored
        return copy.deepcopy(role)

    def link(self, role_id: int, permission_id: int) -> None:
        """Seed a role-permission link synchronously."""
        self.links.add((role_id, permission_id))

    def _hydrated(self, role: Role, *, with_permissions: bool) -> Role:
        result = copy.deepcopy(role)
        if with_permissions:
            result.permissions = [
                copy.deepcopy(self._permissions.rows[pid])
                for rid, pid in sorted(self.links)
                if rid == role.id and pid in self._permissions.rows
            ]
        return result

    async def get_by_id(self, role_id: int, *, with_permissions: bool = False) -> Role | None:
        role = self.rows.get(role_id)
        return self._hydrated(role, with_permissions=with_permissions) if role else None

    async def get_by_code(self, code: str) -> Role | None:
        for role in self.rows.values():
            if role.code == code:
                return self._hydrated(role, with_permissions=False)
        return None

    async def list_active(self, tenant_id: int | None = None) -> list[Role]:
        rows = [r for r in self.rows.values() if r.is_active]
        if tenant_id:
            rows = [r for r in rows if r.tenant_id in (tenant_id, None)]
        rows.sort(key=lambda r: r.code)
        return [self._hydrated(r, with_permissions=True) for r in rows]

    async def list_by_ids(self, role_ids: list[int]) -> list[Role]:
        wanted = set(role_ids)
        rows = sorted((r for r in self.rows.values() if r.id in wanted), key=lambda r: r.id)
        return [self._hydrated(r, with_permissions=True) for r in rows]

    async def create(self, role: Role) -> Role:
        return self.add(role)

    async def update(self, role: Role) -> Role:
        if role.id not in self.rows:
            raise ValueError(f"Role {role.id} not found")
        stored = copy.deepcopy(role)
        stored.permissions = []
        self.rows[role.id] = stored
        return self._hydrated(stored, with_permissions=True)

    async def is_permission_granted(self, role_id: int, permission_id: int) -> bool:
        return (role_id, permission_id) in self.links

    async def grant_permission(
        self, role_id: int, permission_id: int, granted_by: str
    ) -> None:
        self.links.add((role_id, permission_id))

    async def revoke_permission(self, role_id: int, permission_id: int) -> bool:
        if (role_id, permission_id) not in self.links:
            return False
        self.links.discard((role_id, permission_id))
        return True


class FakeRoleAssignmentStore(IRoleAssignmentRepository):
    """
    Dict-backed `IRoleAssignmentRepository` that keeps real assignment rows.

    `workflow_fakes.FakeRoleAssignmentRepository` models only role membership (role ->
    user ids) for the approval chain; it cannot represent a deactivated assignment or
    hand back an assignment with an id, which the RBAC and user services need.
    """

    def __init__(self) -> None:
        self.rows: dict[int, RoleAssignment] = {}

    def add(self, assignment: RoleAssignment) -> RoleAssignment:
        """Seed a row synchronously (test setup helper, not part of the port)."""
        if assignment.id == 0:
            assignment.id = _next_fake_id()
        self.rows[assignment.id] = copy.deepcopy(assignment)
        return copy.deepcopy(assignment)

    async def get_active(self, user_id: int, role_id: int) -> RoleAssignment | None:
        for row in self.rows.values():
            if row.user_id == user_id and row.role_id == role_id and row.is_active:
                return copy.deepcopy(row)
        return None

    async def list_for_user(self, user_id: int) -> list[RoleAssignment]:
        return [copy.deepcopy(r) for r in self.rows.values() if r.user_id == user_id]

    async def list_active_for_user(self, user_id: int) -> list[RoleAssignment]:
        return [
            copy.deepcopy(r)
            for r in self.rows.values()
            if r.user_id == user_id and r.is_active
        ]

    async def list_active_user_ids_for_role(self, role_id: int) -> list[int]:
        return [r.user_id for r in self.rows.values() if r.role_id == role_id and r.is_active]

    async def deactivate_all_for_user(self, user_id: int, modified_by: str) -> int:
        changed = 0
        for row in self.rows.values():
            if row.user_id == user_id and row.is_active:
                row.is_active = False
                row.modified_by = modified_by
                changed += 1
        return changed

    async def create(self, assignment: RoleAssignment) -> RoleAssignment:
        return self.add(assignment)

    async def deactivate(self, assignment_id: int, modified_by: str) -> None:
        row = self.rows.get(assignment_id)
        if row is not None:
            row.is_active = False
            row.modified_by = modified_by


class FakeAuditLogRepository(IAuditLogRepository):
    """List-backed, append-only `IAuditLogRepository`."""

    def __init__(self) -> None:
        self.entries: list[AuditLog] = []

    def seed(self, entry: AuditLog) -> AuditLog:
        """Add an entry synchronously (test setup helper, not part of the port)."""
        if entry.id == 0:
            entry.id = _next_fake_id()
        self.entries.append(copy.deepcopy(entry))
        return copy.deepcopy(entry)

    async def add(self, entry: AuditLog) -> None:
        self.seed(entry)

    def _filtered(
        self,
        action: str | None,
        actor_id: int | None,
        actor_username: str | None,
        resource_type: str | None,
    ) -> list[AuditLog]:
        rows = list(self.entries)
        if action is not None:
            rows = [r for r in rows if r.action == action]
        if actor_id is not None:
            rows = [r for r in rows if r.actor_id == actor_id]
        if actor_username is not None:
            rows = [r for r in rows if r.actor_username == actor_username]
        if resource_type is not None:
            rows = [r for r in rows if r.resource_type == resource_type]
        return rows

    async def query(
        self,
        *,
        action: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditLog]:
        rows = self._filtered(action, actor_id, actor_username, resource_type)
        # Newest first; reversing first keeps later insertions ahead on a timestamp tie.
        rows = sorted(reversed(rows), key=lambda r: r.created_at, reverse=True)
        return [copy.deepcopy(r) for r in rows[skip : skip + limit]]

    async def count(
        self,
        *,
        action: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        return len(self._filtered(action, actor_id, actor_username, resource_type))

    async def latest_timestamp_by_actor(
        self, action: str, actor_ids: list[int]
    ) -> dict[int, datetime]:
        latest: dict[int, datetime] = {}
        for entry in self.entries:
            if entry.action != action or entry.actor_id not in actor_ids:
                continue
            assert entry.actor_id is not None
            current = latest.get(entry.actor_id)
            if current is None or entry.created_at > current:
                latest[entry.actor_id] = entry.created_at
        return latest


class FakePermissionResolver(IPermissionResolver):
    """Resolver whose answers are set directly by the test."""

    def __init__(self) -> None:
        self.permissions: dict[int, list[Permission]] = {}
        self.fields: dict[tuple[int, str], dict[str, list[str]]] = {}
        #: Every `get_user_permissions` call as (user_id, tenant_id, scope).
        self.permission_calls: list[tuple[int, int | None, PermissionScope | None]] = []

    async def get_user_permissions(
        self,
        user_id: int,
        tenant_id: int | None = None,
        scope: PermissionScope | None = None,
    ) -> list[Permission]:
        self.permission_calls.append((user_id, tenant_id, scope))
        rows = self.permissions.get(user_id, [])
        if scope is not None:
            rows = [p for p in rows if p.scope == scope]
        return [copy.deepcopy(p) for p in rows]

    async def has_permission(
        self, user_id: int, permission_code: str, tenant_id: int | None = None
    ) -> bool:
        return any(p.code == permission_code for p in self.permissions.get(user_id, []))

    async def get_field_permissions(
        self, user_id: int, resource: str, tenant_id: int | None = None
    ) -> dict[str, list[str]]:
        return copy.deepcopy(self.fields.get((user_id, resource), {}))


class FakePasswordHasher(IPasswordHasher):
    """Deterministic, reversible stand-in so tests can see what was hashed."""

    def hash(self, plain_password: str) -> str:
        return f"hashed::{plain_password}"

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return password_hash == self.hash(plain_password)
