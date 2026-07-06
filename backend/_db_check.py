import asyncio
import asyncpg


async def main():
    try:
        conn = await asyncpg.connect(
            user="postgres",
            password="root",
            database="liasioningagent",
            host="localhost",
            port=5432,
        )
    except Exception as e:
        print("CONNECT_FAIL", repr(e))
        return
    rows = await conn.fetch(
        "select table_name from information_schema.tables "
        "where table_schema='public' order by table_name"
    )
    print("TABLES:", [r["table_name"] for r in rows])
    await conn.close()


asyncio.run(main())
