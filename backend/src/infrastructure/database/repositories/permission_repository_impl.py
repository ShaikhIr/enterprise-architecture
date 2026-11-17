"""
Permission repository implementation (Adapter).
Implements IPermissionRepository using SQLAlchemy async.
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import Permission
from src.domain.repositories.permission_repository import IPermissionRepository
from src.infrastructure.database.models.role_model import PermissionModel


class PermissionRepositoryImpl(IPermissionRepository):
    """Concrete implementation of permission persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, permission_id: int) -> Permission | None:
        model = await self._session.get(PermissionModel, permission_id)
        return self._to_entity(model) if model else None

    async def get_by_code(self, code: str) -> Permission | None:
        stmt = select(PermissionModel).where(PermissionModel.code == code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_active(self, scope: str | None = None) -> list[Permission]:
        stmt = select(PermissionModel).where(PermissionModel.is_active.is_(True))
        if scope:
            stmt = stmt.where(PermissionModel.scope == scope)
        stmt = stmt.order_by(PermissionModel.scope, PermissionModel.resource)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def create(self, permission: Permission) -> Permission:
        model = PermissionModel(
            code=permission.code,
            name=permission.name,
            description=permission.description,
            scope=permission.scope,
            resource=permission.resource,
            action=permission.action,
            is_active=permission.is_active,
            created_by=permission.created_by,
            modified_by=permission.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: PermissionModel) -> Permission:
        """Map ORM model to domain entity."""
        return Permission(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            scope=model.scope,
            resource=model.resource,
            action=model.action,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
