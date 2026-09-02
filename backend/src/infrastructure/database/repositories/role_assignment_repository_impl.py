"""
Role assignment repository implementation (Adapter).
Implements IRoleAssignmentRepository using SQLAlchemy async.
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import RoleAssignment
from src.domain.repositories.role_assignment_repository import IRoleAssignmentRepository
from src.infrastructure.database.models.role_model import RoleAssignmentModel
from src.infrastructure.database.models.user_model import UserModel


class RoleAssignmentRepositoryImpl(IRoleAssignmentRepository):
    """Concrete implementation of role assignment persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, user_id: int, role_id: int) -> RoleAssignment | None:
        stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == user_id,
            RoleAssignmentModel.role_id == role_id,
            RoleAssignmentModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_for_user(self, user_id: int) -> list[RoleAssignment]:
        stmt = select(RoleAssignmentModel).where(RoleAssignmentModel.user_id == user_id)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_active_for_user(self, user_id: int) -> list[RoleAssignment]:
        stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == user_id,
            RoleAssignmentModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_active_user_ids_for_role(self, role_id: int) -> list[int]:
        # Joined to users rather than read from role_assignments alone: an
        # assignment can still be active while the account behind it has been
        # deactivated or blocked, and such a user must not be handed approvals.
        stmt = (
            select(RoleAssignmentModel.user_id)
            .join(UserModel, UserModel.id == RoleAssignmentModel.user_id)
            .where(
                RoleAssignmentModel.role_id == role_id,
                RoleAssignmentModel.is_active.is_(True),
                UserModel.is_active.is_(True),
                UserModel.is_blocked.is_(False),
            )
            .order_by(UserModel.username)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_all_for_user(self, user_id: int, modified_by: str) -> int:
        stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == user_id,
            RoleAssignmentModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())
        for model in models:
            model.is_active = False
            model.modified_by = modified_by
        if models:
            await self._session.flush()
        return len(models)

    async def create(self, assignment: RoleAssignment) -> RoleAssignment:
        model = RoleAssignmentModel(
            user_id=assignment.user_id,
            role_id=assignment.role_id,
            tenant_id=assignment.tenant_id,
            is_active=assignment.is_active,
            created_by=assignment.created_by,
            modified_by=assignment.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def deactivate(self, assignment_id: int, modified_by: str) -> None:
        model = await self._session.get(RoleAssignmentModel, assignment_id)
        if model is None:
            return
        model.is_active = False
        model.modified_by = modified_by
        await self._session.flush()

    @staticmethod
    def _to_entity(model: RoleAssignmentModel) -> RoleAssignment:
        """Map ORM model to domain entity."""
        return RoleAssignment(
            id=model.id,
            user_id=model.user_id,
            role_id=model.role_id,
            tenant_id=model.tenant_id,
            is_active=model.is_active,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
