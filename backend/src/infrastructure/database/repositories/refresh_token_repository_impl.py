"""
Refresh token repository implementation (Adapter).
Implements IRefreshTokenRepository using SQLAlchemy async.
"""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.refresh_token import RefreshToken
from src.domain.repositories.refresh_token_repository import IRefreshTokenRepository
from src.infrastructure.database.models.refresh_token_model import RefreshTokenModel


class RefreshTokenRepositoryImpl(IRefreshTokenRepository):
    """Concrete implementation of refresh-token persistence using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            jti=token.jti,
            family_id=token.family_id,
            user_id=token.user_id,
            expires_at=token.expires_at,
            used_at=token.used_at,
            revoked_at=token.revoked_at,
            created_by=token.created_by,
            modified_by=token.modified_by,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.jti == jti)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def mark_used(self, jti: str, used_at: datetime) -> bool:
        # One conditional UPDATE, so of two concurrent refreshes of the same token exactly
        # one matches the WHERE clause and gets rowcount 1.
        stmt = (
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.jti == jti,
                RefreshTokenModel.used_at.is_(None),
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(used_at=used_at)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return result.rowcount == 1

    async def revoke_family(self, family_id: str, revoked_at: datetime) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)

    async def delete_expired(self, before: datetime) -> int:
        stmt = (
            delete(RefreshTokenModel)
            .where(RefreshTokenModel.expires_at < before)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount)

    @staticmethod
    def _to_entity(model: RefreshTokenModel) -> RefreshToken:
        """Map ORM model to domain entity."""
        return RefreshToken(
            id=model.id,
            jti=model.jti,
            family_id=model.family_id,
            user_id=model.user_id,
            expires_at=model.expires_at,
            used_at=model.used_at,
            revoked_at=model.revoked_at,
            created_by=model.created_by,
            created_date=model.created_date,
            modified_by=model.modified_by,
            modified_date=model.modified_date,
        )
