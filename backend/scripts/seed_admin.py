"""Create admin user without deprecated role column."""
import asyncio
import sys
sys.path.insert(0, r"d:\enterprise-architecture\backend")

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:root@localhost:5432/enterprise_db")

from uuid import uuid4
from sqlalchemy import select
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.security.password_encoder import hash_password


async def seed():
    async with async_session_factory() as session:
        stmt = select(UserModel).where(UserModel.username == "admin")
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            print("Admin user already exists.")
            return
        admin = UserModel(
            id=uuid4(),
            username="admin",
            password_hash=hash_password("Admin@123!"),
            is_active=True,
            is_blocked=False,
            is_validate_ad=False,
            created_by="seed_script",
            modified_by="seed_script",
        )
        session.add(admin)
        await session.commit()
        print(f"Admin user created: username=admin, id={admin.id}")


if __name__ == "__main__":
    asyncio.run(seed())
