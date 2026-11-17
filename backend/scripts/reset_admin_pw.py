"""Quick script to reset admin password for testing."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.infrastructure.database.unit_of_work import UnitOfWork
from src.infrastructure.security.password_encoder import hash_password


async def reset() -> None:
    async with UnitOfWork() as uow:
        new_hash = hash_password("Admin@123")
        await uow.session.execute(
            text("UPDATE users SET password_hash = :h WHERE username = 'admin'"),
            {"h": new_hash},
        )
        await uow.commit()
        print("Admin password reset to: Admin@123")


if __name__ == "__main__":
    asyncio.run(reset())
