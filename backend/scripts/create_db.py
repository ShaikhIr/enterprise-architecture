"""Create the enterprise_db database if it doesn't exist."""
import asyncio
import asyncpg


async def create_database():
    conn = await asyncpg.connect("postgresql://postgres:root@localhost:5432/postgres")
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'enterprise_db'"
        )
        if not exists:
            await conn.execute("CREATE DATABASE enterprise_db")
            print("Database 'enterprise_db' created successfully.")
        else:
            print("Database 'enterprise_db' already exists.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_database())
