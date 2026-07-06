import asyncio
import asyncpg
from sqlalchemy.engine import make_url
from src.config.settings import settings

print("DATABASE_URL =", settings.DATABASE_URL)
url = make_url(settings.DATABASE_URL)
print("user=", url.username, "pw=", url.password, "db=", url.database, "host=", url.host, "port=", url.port)


def dsn(db):
    return dict(host=url.host or "localhost", port=url.port or 5432,
               user=url.username, password=url.password, database=db)


async def main():
    name = "lacm_diag_test_db"
    admin = await asyncpg.connect(**dsn("postgres"))
    await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    print("created", name)
    try:
        conn = await asyncpg.connect(**dsn(name))
        print("CONNECT_TEST_DB_OK")
        await conn.close()
    except Exception as e:
        print("CONNECT_TEST_DB_FAIL", type(e).__name__, str(e)[:300])
    finally:
        admin = await asyncpg.connect(**dsn("postgres"))
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


asyncio.run(main())
