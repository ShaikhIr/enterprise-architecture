"""
Role repository implementation (Adapter).
Implements IRoleRepository using SQLAlchemy async.
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.entities.role import Permission, Role
from src.domain.repositories.role_repository import IRoleRepository
from src.infrastructure.database.models.role_model import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
)
from src.infrastructure.database.repositories.permission_repository_impl import (
    PermissionRepositoryImpl,
)


class RoleRepositoryImpl(IRoleRepository):
    """Concrete implementation of role persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Reads ───

    async def get_by_id(self, role_id: int, *, with_permissions: bool = False) -> Role | None:
        stmt = select(RoleModel).where(RoleModel.id == role_id)
        if with_permissions:
            stmt = stmt.options(selectinload(RoleModel.permissions))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model, with_permissions=with_permissions) if model else None

    async def get_by_code(self, code: str) -> Role | None:
        stmt = select(RoleModel).where(RoleModel.code == code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_active(self, tenant_id: int | None = None) -> list[Role]:
        stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(RoleModel.is_active.is_(True))
        )
        if tenant_id:
            # Tenant-scoped roles plus global ones.
            stmt = stmt.where(
                (RoleModel.tenant_id == tenant_id) | (RoleModel.tenant_id.is_(None))
            )
        stmt = stmt.order_by(RoleModel.code)
        result = await self._session.execute(stmt)
        return [self._to_entity(m, with_permissions=True) for m in result.scalars().all()]

    async def list_by_ids(self, role_ids: list[int]) -> list[Role]:
        if not role_ids:
            return []
        stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(RoleModel.id.in_(role_ids))
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m, with_permissions=True) for m in result.scalars().all()]

    # ─── Writes ───

    async def create(self, role: Role) -> Role:
        model = RoleModel(
            code=role.code,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            is_active=role.is_active,
            tenant_id=role.tenant_id,
            parent_role_id=role.parent_role_id,
            created_by=role.created_by,
            modified_by=role.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        # Reload with permissions so callers can build a response without
        # triggering a lazy load outside the greenlet context.
        refreshed = await self.get_by_id(role.id, with_permissions=True)
        return refreshed if refreshed else self._to_entity(model)

    async def update(self, role: Role) -> Role:
        model = await self._session.get(RoleModel, role.id)
        if model is None:
            raise ValueError(f"Role with id {role.id} not found")

        model.name = role.name
        model.description = role.description
        model.is_active = role.is_active
        model.parent_role_id = role.parent_role_id
        model.modified_by = role.modified_by

        await self._session.flush()
        refreshed = await self.get_by_id(role.id, with_permissions=True)
        return refreshed if refreshed else self._to_entity(model)

    # ─── Role ↔ Permission links ───

    async def is_permission_granted(self, role_id: int, permission_id: int) -> bool:
        stmt = select(RolePermissionModel.id).where(
            RolePermissionModel.role_id == role_id,
            RolePermissionModel.permission_id == permission_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def grant_permission(
        self, role_id: int, permission_id: int, granted_by: str
    ) -> None:
        self._session.add(
            RolePermissionModel(
                role_id=role_id,
                permission_id=permission_id,
                created_by=granted_by,
                modified_by=granted_by,
            )
        )
        await self._session.flush()

    async def revoke_permission(self, role_id: int, permission_id: int) -> bool:
        stmt = select(RolePermissionModel).where(
            RolePermissionModel.role_id == role_id,
            RolePermissionModel.permission_id == permission_id,
        )
        result = await self._session.execute(stmt)
        link = result.scalar_one_or_none()
        if link is None:
            return False
        await self._session.delete(link)
        await self._session.flush()
        return True

    # ─── Internals ───

    @staticmethod
    def _to_entity(model: RoleModel, *, with_permissions: bool = False) -> Role:
        """Map ORM model to domain entity."""
        permissions: list[Permission] = []
        if with_permissions:
            permissions = [
                PermissionRepositoryImpl._to_entity(p)
                for p in model.permissions
                if isinstance(p, PermissionModel)
            ]
        return Role(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            is_system=model.is_system,
            is_active=model.is_active,
            tenant_id=model.tenant_id,
            parent_role_id=model.parent_role_id,
            permissions=permissions,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
