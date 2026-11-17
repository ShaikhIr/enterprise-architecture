"""
Database seed script.
Creates initial admin user for development/testing.

Usage:
    python -m scripts.seed_data
"""

import asyncio

from sqlalchemy import select

from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.unit_of_work import UnitOfWork
from src.infrastructure.security.password_encoder import hash_password


async def seed_admin_user() -> None:
    """Create default admin user if not exists."""
    async with UnitOfWork() as uow:
        stmt = select(UserModel).where(UserModel.username == "admin")
        result = await uow.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            print("Admin user already exists. Skipping seed.")
            return

        admin = UserModel(
            username="admin",
            password_hash=hash_password("Admin@123!"),
            is_active=True,
            is_blocked=False,
            is_validate_ad=False,
            created_by="seed_script",
            modified_by="seed_script",
        )
        uow.session.add(admin)
        await uow.commit()
        print(f"Admin user created: username=admin, id={admin.id}")


if __name__ == "__main__":
    asyncio.run(seed_admin_user())
